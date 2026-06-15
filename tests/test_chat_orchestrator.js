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
    children: [],
    lastChild: null,
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text; },
    appendChild(child) { this.children.push(child); this.lastChild = child; return child; },
    replaceChildren() { this.children = []; this._text = ""; this.lastChild = null; },
  };
}
const documentStub = {
  createElement: (tag) => makeNode(tag),
  getElementById: () => null,
};
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
new Function("window", "document", "TextDecoder", code)(win, documentStub, function () {});

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

// Sub-Agent-Start ist idempotent (kein Doppel-Card bei gleicher agent_id)
const agentsBefore = panel._orch.agentsBox.children.length;
win.orchestratorHandleEvent(panel, { type: "subagent_start", agent_id: "a1", role: "research" });
check("agent card idempotent", panel._orch.agentsBox.children.length === agentsBefore);

// Partial-Run -> issue-Status
const panel2 = win.buildOrchestratorPanel("x", "fast");
win.orchestratorHandleEvent(panel2, { type: "done", run: { partial: true } });
check("partial run shows issue", panel2._orch.status._text.includes("teilweise"));

// error-Event
const panel3 = win.buildOrchestratorPanel("x", "fast");
win.orchestratorHandleEvent(panel3, { type: "error", message: "kaputt" });
check("error status", panel3._orch.status._text === "kaputt" && panel3._orch.status.className.includes("error"));

console.log("\n" + (passed + failed) + " tests: " + passed + " passed, " + failed + " failed");
if (failed > 0) process.exit(1);
