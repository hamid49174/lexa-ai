/* DOM-Stub-Test fuer chat_orchestrator.js (Phase 48 E).
 * Testet den reinen Event-Dispatch/Renderer ohne echtes Electron/DOM.
 */
const fs = require("fs");
const path = require("path");
const assert = require("assert");

let passed = 0;
let failed = 0;
function check(name, cond) {
  if (cond) { passed++; console.log("  ok: " + name); }
  else { failed++; console.log("  FAIL: " + name); }
}

// ── Minimaler DOM-Stub ──
function makeNode(tag) {
  return {
    tag,
    className: "",
    _text: "",
    attrs: {},
    children: [],
    lastChild: null,
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text; },
    appendChild(child) { this.children.push(child); this.lastChild = child; return child; },
    replaceChildren() { this.children = []; this._text = ""; this.lastChild = null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    getAttribute(k) { return this.attrs[k]; },
    addEventListener(ev, fn) { (this._handlers = this._handlers || {})[ev] = fn; },
  };
}
const _effortNodes = { "agent-effort-label": makeNode("span"), "agent-effort-btn": makeNode("button") };
const documentStub = {
  createElement: (tag) => makeNode(tag),
  createTextNode: (txt) => { const n = makeNode("#text"); n._text = String(txt); return n; },
  getElementById: (id) => _effortNodes[id] || null,
};
const localStorageStub = (() => {
  const m = {};
  return { getItem: (k) => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: (k) => { delete m[k]; } };
})();
function allText(node) {
  if (!node) return "";
  let t = node._text || "";
  for (const c of node.children || []) t += " " + allText(c);
  return t;
}

// ── Datei laden (IIFE -> window-Globals) ──
const code = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "chat_orchestrator.js"), "utf8");
const win = {};
// eslint-disable-next-line no-new-func
new Function("window", "document", "TextDecoder", "localStorage", code)(win, documentStub, function () {}, localStorageStub);

check("exposes sendOrchestratorMessage", typeof win.sendOrchestratorMessage === "function");
check("exposes orchestratorHandleEvent", typeof win.orchestratorHandleEvent === "function");

const panel = win.buildOrchestratorPanel("Vergleiche A und B", "thorough");
check("panel has state", panel && panel._orch && typeof panel._orch === "object");

win.orchestratorHandleEvent(panel, { type: "plan", plan: { subtasks: [{ role: "research", objective: "Finde A" }, { role: "knowledge", objective: "Suche B" }] } });
win.orchestratorHandleEvent(panel, { type: "subagent_start", agent_id: "a1", role: "research", label: "Recherche", objective: "Finde A" });
win.orchestratorHandleEvent(panel, { type: "subagent_step", agent_id: "a1", step: { tool: "web_search", status: "done", summary: "Treffer" } });
win.orchestratorHandleEvent(panel, { type: "subagent_done", agent_id: "a1", status: "done", summary: "Recherche fertig" });
win.orchestratorHandleEvent(panel, { type: "verification", verdict: { agent_id: "a1", passed: true, score: 0.9 } });
win.orchestratorHandleEvent(panel, { type: "synthesis", content: "FINALE ANTWORT" });
win.orchestratorHandleEvent(panel, { type: "done", run: { partial: false } });

const text = allText(panel);
check("renders plan", text.includes("Plan") && text.includes("Recherche") && text.includes("Finde A"));
check("renders agent step tool", text.includes("web_search") && text.includes("Treffer"));
check("renders verification", text.includes("Verifikation"));
check("stores synthesis", panel._orch.synthesis === "FINALE ANTWORT");
check("status done", panel._orch.status._text === "fertig");
check("phase plan done", panel._orch.phases.plan.className.indexOf("done") !== -1);
check("phase synth done", panel._orch.phases.synth.className.indexOf("done") !== -1);
check("counts show agents", panel._orch.counts._text.indexOf("Agenten") !== -1);

// Sub-Agent-Start ist idempotent (kein Doppel-Card bei gleicher agent_id)
const agentsBefore = panel._orch.agentsBox.children.length;
win.orchestratorHandleEvent(panel, { type: "subagent_start", agent_id: "a1", role: "research" });
check("agent card idempotent", panel._orch.agentsBox.children.length === agentsBefore);

// ── MCP-Coding-Bruecke (Phase 49 #4/J) ──
const panelM = win.buildOrchestratorPanel("Analysiere den Code", "fast");
win.orchestratorHandleEvent(panelM, { type: "mcp", servers: { filesystem: "connected", serena: "disabled" } });
const mText = allText(panelM);
check("renders mcp servers", mText.includes("MCP-Coding") && mText.includes("filesystem") && mText.includes("serena"));
// unbekanntes Event darf nicht crashen
win.orchestratorHandleEvent(panelM, { type: "voellig_unbekannt", foo: 1 });
check("unknown event is safe", panelM._orch.status._text === "laeuft …");

// ── Quellen (zitierte Synthese, Phase 49 #3) ──
const panelS = win.buildOrchestratorPanel("Recherche", "thorough");
win.orchestratorHandleEvent(panelS, { type: "sources", sources: [
  { id: 1, title: "Beispiel A", url: "https://a.test" },
  { id: 2, title: "Beispiel B", url: "https://b.test" },
] });
const sText = allText(panelS);
check("renders sources section", sText.includes("Quellen") && sText.includes("Beispiel A"));
check("stores sources on panel", panelS._orch.sources.length === 2);
const linkNode = (function find(n) {
  if (n && n.tag === "a") return n;
  for (const c of (n && n.children) || []) { const r = find(c); if (r) return r; }
  return null;
})(panelS._orch.sourcesBox);
check("source link has href + safe rel/target", linkNode && linkNode.href === "https://a.test"
  && linkNode.target === "_blank" && linkNode.rel === "noopener noreferrer");

// done-Fallback rendert Quellen, falls das sources-Event fehlte
const panelSf = win.buildOrchestratorPanel("Recherche", "fast");
win.orchestratorHandleEvent(panelSf, { type: "done", run: { partial: false, sources: [{ id: 1, title: "Nur im done", url: "https://c.test" }] } });
check("done renders fallback sources", allText(panelSf).includes("Nur im done"));

// kein sources-Event -> keine Quellen-Sektion
const panelNo = win.buildOrchestratorPanel("x", "fast");
win.orchestratorHandleEvent(panelNo, { type: "synthesis", content: "Antwort" });
win.orchestratorHandleEvent(panelNo, { type: "done", run: { partial: false, sources: [] } });
check("no sources -> empty box", panelNo._orch.sourcesBox.children.length === 0);

// Partial-Run -> issue-Status
const panel2 = win.buildOrchestratorPanel("x", "fast");
win.orchestratorHandleEvent(panel2, { type: "done", run: { partial: true } });
check("partial run shows issue", panel2._orch.status._text.includes("teilweise"));

// error-Event
const panel3 = win.buildOrchestratorPanel("x", "fast");
win.orchestratorHandleEvent(panel3, { type: "error", message: "kaputt" });
check("error status", panel3._orch.status._text === "kaputt" && panel3._orch.status.className.includes("error"));

// ── Agenten-Aufwand-Regler ──
check("effort default is off", win.getAgentEffort() === "off");
win.setAgentEffort("thorough");
check("setAgentEffort persists", win.getAgentEffort() === "thorough");
check("effort button label updated", _effortNodes["agent-effort-label"]._text === "Gruendlich");
check("effort button data-effort updated", _effortNodes["agent-effort-btn"].attrs["data-effort"] === "thorough");
win.cycleAgentEffort();
check("cycle thorough->off", win.getAgentEffort() === "off");
win.cycleAgentEffort();
check("cycle off->fast", win.getAgentEffort() === "fast");
win.setAgentEffort("bloedsinn");
check("invalid effort falls back to fast", win.getAgentEffort() === "fast");

// ── needsOrchestratorMode (Auto-Trigger-Heuristik) ──
check("triggers on compare task", win.needsOrchestratorMode("Vergleiche Tauri und Electron fuer eine Desktop-App ausfuehrlich") === true);
check("triggers on research task", win.needsOrchestratorMode("Recherchiere den aktuellen Stand zu Gemini 3.5 Flash bitte genau") === true);
check("triggers on multipart und-task", win.needsOrchestratorMode("Finde Infos zu Thema A und zu Thema B und fasse beides sauber zusammen") === true);
check("no trigger on simple question", win.needsOrchestratorMode("wie geht es dir heute?") === false);
check("no trigger on short text", win.needsOrchestratorMode("hallo") === false);

// ── maybeAutoOrchestrate (LLM-Triage primaer, Regex-Fallback) ──
(async () => {
  win.setAgentEffort("fast");
  win.lexa = {
    orchestratorTriage: async (t) => ({ needs_agents: /AGENT/.test(t), mode: "fast", source: "llm" }),
    orchestratorRun: async () => ({ ok: false, status: 503, statusText: "", streamId: "" }),
    agentStreamRead: async () => ({ done: true, value: [] }),
  };
  check("auto: short text -> false (kein Triage)", (await win.maybeAutoOrchestrate("kurz")) === false);
  check("auto: triage needs=false -> false", (await win.maybeAutoOrchestrate("Eine ganz normale laengere Frage ohne Treffer hier")) === false);
  check("auto: triage needs=true -> true", (await win.maybeAutoOrchestrate("Bitte AGENT diese lange komplexe Aufgabe gruendlich bearbeiten")) === true);
  win.setAgentEffort("off");
  check("auto: effort off -> false", (await win.maybeAutoOrchestrate("Bitte AGENT diese lange komplexe Aufgabe bearbeiten")) === false);
  win.setAgentEffort("fast");

  console.log("\n" + (passed + failed) + " tests: " + passed + " passed, " + failed + " failed");
  if (failed > 0) process.exit(1);
})();
