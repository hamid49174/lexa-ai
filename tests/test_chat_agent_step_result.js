/**
 * Regression coverage for collapsible agent-step tool-result panels.
 * Run with: node tests/test_chat_agent_step_result.js
 */
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "chat_agent_runs.js"), "utf8");

function extractFn(source, name) {
  const needle = `function ${name}(`;
  const start = source.indexOf(needle);
  if (start === -1) throw new Error(`'${name}' not found`);
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") { depth -= 1; if (depth === 0) return source.slice(start, i + 1); }
  }
  throw new Error(`No closing brace for '${name}'`);
}

class El {
  constructor(tag) {
    this.tagName = String(tag || "div").toLowerCase();
    this.children = [];
    this.attributes = {};
    this.handlers = {};
    this.hidden = false;
    this._text = "";
  }
  set className(v) { this.attributes.class = String(v || ""); }
  get className() { return this.attributes.class || ""; }
  set textContent(v) { this._text = String(v == null ? "" : v); this.children = []; }
  get textContent() { return this._text; }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k]; }
  appendChild(n) { this.children.push(n); return n; }
  append(...n) { n.forEach((x) => this.appendChild(x)); }
  addEventListener(type, fn) { (this.handlers[type] = this.handlers[type] || []).push(fn); }
  click() { (this.handlers.click || []).forEach((fn) => fn({})); }
  remove() {}
  _has(cls) { return (this.className || "").split(/\s+/).includes(cls); }
  querySelector(sel) {
    const cls = sel.replace(/^\./, "").split(".")[0];
    for (const c of this.children) {
      if (c._has && c._has(cls)) return c;
      const deep = c.querySelector && c.querySelector(sel);
      if (deep) return deep;
    }
    return null;
  }
}

const sandbox = new Function("document", "t",
  `${extractFn(src, "renderAgentStepResult")}\nreturn { renderAgentStepResult };`);
const { renderAgentStepResult } = sandbox({ createElement: (tag) => new El(tag) }, (key) => key);

let passed = 0, failed = 0;
function assert(desc, ok, detail = "") {
  if (ok) { console.log(`  ok: ${desc}`); passed += 1; }
  else { console.error(`  FAIL: ${desc}${detail ? " - " + detail : ""}`); failed += 1; }
}

console.log("\nagent step tool-result panel:");

// 1. Success result -> collapsed panel with toggle + body
const step = new El("div"); step.className = "agent-step";
renderAgentStepResult(step, { status: "success", result: "system ok: cpu 12%" });
const wrap = step.querySelector(".agent-step-result");
assert("result panel rendered for non-empty result", Boolean(wrap));
const toggle = wrap && wrap.querySelector(".agent-step-result-toggle");
const body = wrap && wrap.querySelector(".agent-step-result-body");
assert("body holds the tool result text", body && body.textContent === "system ok: cpu 12%", body && body.textContent);
assert("body collapsed by default", body && body.hidden === true);
assert("toggle starts collapsed (aria-expanded false)", toggle && toggle.getAttribute("aria-expanded") === "false");

// 2. Toggle expands then collapses
toggle.click();
assert("toggle expands body", body.hidden === false && toggle.getAttribute("aria-expanded") === "true");
toggle.click();
assert("toggle re-collapses body", body.hidden === true && toggle.getAttribute("aria-expanded") === "false");

// 3. Error step -> is-error variant, error text wins
const estep = new El("div"); estep.className = "agent-step";
renderAgentStepResult(estep, { status: "failed", error: "permission denied", result: "ignored" });
const ewrap = estep.querySelector(".agent-step-result");
assert("error variant flagged", ewrap && ewrap._has("is-error"));
assert("error text preferred over result", ewrap && ewrap.querySelector(".agent-step-result-body").textContent === "permission denied");

// 4. Empty result -> no panel
const empty = new El("div"); empty.className = "agent-step";
renderAgentStepResult(empty, { status: "success", result: "   " });
assert("no panel for empty result", empty.querySelector(".agent-step-result") === null);

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
