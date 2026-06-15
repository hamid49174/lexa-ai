/* DOM-Stub-Test fuer agents.js (Phase 48 F): Status + Run-Historie + Replay. */
const fs = require("fs");
const path = require("path");

let passed = 0, failed = 0;
function check(name, cond) {
  if (cond) { passed++; console.log("  ok: " + name); }
  else { failed++; console.log("  FAIL: " + name); }
}

function makeNode(tag) {
  const node = {
    tag, className: "", _text: "", children: [], _handlers: {},
    type: "", title: "",
    set textContent(v) { this._text = String(v); this.children = []; },
    get textContent() { return this._text; },
    appendChild(c) { c.parent = node; node.children.push(c); return c; },
    replaceChildren(...kids) { node.children = []; node._text = ""; kids.forEach((k) => node.appendChild(k)); },
    addEventListener(ev, fn) { node._handlers[ev] = fn; },
    classList: {
      add(...cs) { const set = new Set(node.className.split(" ").filter(Boolean)); cs.forEach((c) => set.add(c)); node.className = Array.from(set).join(" "); },
      remove(...cs) { const set = new Set(node.className.split(" ").filter(Boolean)); cs.forEach((c) => set.delete(c)); node.className = Array.from(set).join(" "); },
      contains(c) { return node.className.split(" ").includes(c); },
    },
    setAttribute() {},
    _matches(sel) {
      return sel.split(".").filter(Boolean).every((tok) => node.className.split(" ").includes(tok));
    },
    querySelectorAll(sel) { const out = []; (function walk(n) { (n.children || []).forEach((c) => { if (c._matches && c._matches(sel)) out.push(c); walk(c); }); })(node); return out; },
    querySelector(sel) { return node.querySelectorAll(sel)[0] || null; },
  };
  return node;
}

function allText(node) {
  if (!node) return "";
  let s = node._text || "";
  for (const c of node.children || []) s += " " + allText(c);
  return s;
}

const els = {
  "agents-status-banner": makeNode("div"),
  "agents-runs-list": makeNode("div"),
  "agents-detail": makeNode("div"),
};
const documentStub = {
  createElement: (tag) => makeNode(tag),
  getElementById: (id) => els[id] || null,
};
const win = {};

function load(file, extraArg) {
  const code = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", file), "utf8");
  // eslint-disable-next-line no-new-func
  new Function("window", "document", "TextDecoder", code)(win, documentStub, function () {});
  void extraArg;
}
load("chat_orchestrator.js");
load("agents.js");

check("exposes refreshAgentsView", typeof win.refreshAgentsView === "function");

// Gemockte Bridge
const detailCalls = [];
win.lexa = {
  orchestratorStatus: async () => ({ enabled: true, modes: ["thorough", "fast"], max_subagents: 4, browser: { available: false, reason: "aus" } }),
  orchestratorRuns: async () => ({ runs: [
    { run_id: "r1", goal: "Vergleiche A und B", status: "completed", mode: "thorough", subagent_count: 2, created_at: "2026-06-16T08:00:00Z" },
    { run_id: "r2", goal: "Plane meinen Tag", status: "partial", mode: "fast", subagent_count: 1, created_at: "2026-06-16T07:00:00Z" },
  ] }),
  orchestratorRunDetail: async (id) => {
    detailCalls.push(id);
    return {
      run_id: id, goal: "Vergleiche A und B", mode: "thorough", answer: "FINALE ANTWORT " + id,
      events: [
        { type: "plan", plan: { subtasks: [{ role: "research", objective: "Finde A" }] } },
        { type: "subagent_start", agent_id: "a1", role: "research", label: "Recherche", objective: "Finde A" },
        { type: "subagent_done", agent_id: "a1", status: "done", summary: "fertig" },
        { type: "done", run: { partial: false } },
      ],
    };
  },
};

(async () => {
  await win.refreshAgentsView();

  check("status banner shows ready", allText(els["agents-status-banner"]).includes("bereit"));
  check("status banner shows browser off", allText(els["agents-status-banner"]).toLowerCase().includes("browser"));

  const items = els["agents-runs-list"].querySelectorAll("agents-run-item");
  check("renders 2 run items", items.length === 2);
  check("run item shows goal", allText(items[0]).includes("Vergleiche A und B"));

  // Erster Lauf automatisch geoeffnet
  check("first run auto-opened detail", detailCalls.length >= 1 && detailCalls[0] === "r1");
  check("detail shows answer", allText(els["agents-detail"]).includes("FINALE ANTWORT r1"));
  check("detail replays plan", allText(els["agents-detail"]).includes("Finde A"));
  check("first item active", items[0].classList.contains("active"));

  // Klick auf zweiten Lauf laedt dessen Detail
  items[1]._handlers.click && items[1]._handlers.click();
  await new Promise((r) => setTimeout(r, 0));
  check("click loads second run", detailCalls.includes("r2"));

  console.log("\n" + (passed + failed) + " tests: " + passed + " passed, " + failed + " failed");
  if (failed > 0) process.exit(1);
})();
