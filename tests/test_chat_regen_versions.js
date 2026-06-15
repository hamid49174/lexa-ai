/**
 * Regression coverage for regenerate version navigation (ChatGPT-style ‹n/m›).
 * Run with: node tests/test_chat_regen_versions.js
 *
 * applyRegenVersions/renderRegenNav are DOM-interactive, so this file ships its own
 * minimal DOM stub (querySelector by class, insertAdjacentElement, click simulation)
 * rather than reusing the rendering-test stub.
 */
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "chat.js"), "utf8");

function extractFn(source, name) {
  const needle = `function ${name}(`;
  const start = source.indexOf(needle);
  if (start === -1) throw new Error(`'${name}' not found`);
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    else if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`No closing brace for '${name}'`);
}

class El {
  constructor(tag) {
    this.tagName = String(tag || "div").toLowerCase();
    this.children = [];
    this.parentElement = null;
    this.attributes = {};
    this.handlers = {};
    this.disabled = false;
    this._text = "";
    this.dataset = {};
  }
  set className(v) { this.attributes.class = String(v || ""); }
  get className() { return this.attributes.class || ""; }
  set textContent(v) { this._text = String(v == null ? "" : v); this.children = []; }
  get textContent() { return this._text; }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k]; }
  appendChild(node) { node.parentElement = this; this.children.push(node); return node; }
  append(...nodes) { nodes.forEach((n) => this.appendChild(n)); }
  addEventListener(type, fn) { (this.handlers[type] = this.handlers[type] || []).push(fn); }
  click() { (this.handlers.click || []).forEach((fn) => fn({})); }
  insertAdjacentElement(pos, node) {
    const parent = this.parentElement;
    if (!parent) return node;
    const idx = parent.children.indexOf(this);
    node.parentElement = parent;
    parent.children.splice(pos === "afterend" ? idx + 1 : idx, 0, node);
    return node;
  }
  remove() {
    if (this.parentElement) {
      const i = this.parentElement.children.indexOf(this);
      if (i >= 0) this.parentElement.children.splice(i, 1);
    }
  }
  _matches(sel) { return ("." + (this.className || "").split(/\s+/).join(".")).includes(sel); }
  querySelector(sel) {
    for (const c of this.children) {
      if (c._matches && c._matches(sel)) return c;
      const deep = c.querySelector && c.querySelector(sel);
      if (deep) return deep;
    }
    return null;
  }
}

const renderCalls = [];
const persistCalls = [];
let saveCount = 0;
const sandbox = new Function(
  "document", "t", "renderFormattedMessage", "setMessagePersistText", "saveCurrentConversation",
  `${extractFn(src, "applyRegenVersions")}\n${extractFn(src, "renderRegenNav")}\nreturn { applyRegenVersions, renderRegenNav };`
);
const { applyRegenVersions } = sandbox(
  { createElement: (tag) => new El(tag) },
  (key) => key,
  (target, text) => renderCalls.push(text),
  (msg, text) => persistCalls.push(text),
  () => { saveCount += 1; }
);

let passed = 0, failed = 0;
function assert(desc, ok, detail = "") {
  if (ok) { console.log(`  ok: ${desc}`); passed += 1; }
  else { console.error(`  FAIL: ${desc}${detail ? " - " + detail : ""}`); failed += 1; }
}

function makeMsg() {
  const msg = new El("div"); msg.className = "message system-message";
  const body = new El("div"); body.className = "msg-body";
  const textEl = new El("div"); textEl.className = "msg-text";
  body.appendChild(textEl);
  msg.appendChild(body);
  return { msg, body, textEl };
}

console.log("\nregenerate version navigation:");

// 1. Two versions -> nav with label 2/2, prev enabled, next disabled
const { msg } = makeMsg();
applyRegenVersions(msg, "Version zwei", ["Version eins"]);
assert("versions array appends new after previous", JSON.stringify(msg._regenVersions) === JSON.stringify(["Version eins", "Version zwei"]));
assert("active index points at newest", msg._regenIndex === 1);
const nav = msg.querySelector(".regen-nav");
assert("nav rendered for >1 versions", Boolean(nav), JSON.stringify(msg._regenVersions));
const label = nav && nav.querySelector(".regen-nav-label");
assert("label shows 2/2", label && label.textContent === "2/2", label && label.textContent);
const btns = nav ? nav.children.filter((c) => c.className.includes("regen-nav-btn")) : [];
assert("prev disabled? no (at last)", btns[0] && btns[0].disabled === false);
assert("next disabled at last version", btns[1] && btns[1].disabled === true);

// 2. Click prev -> shows version 1, persists it, re-renders, saves
renderCalls.length = 0; persistCalls.length = 0; saveCount = 0;
btns[0].click();
assert("prev switches to version 1 (index 0)", msg._regenIndex === 0);
assert("prev re-renders older version text", renderCalls[renderCalls.length - 1] === "Version eins", JSON.stringify(renderCalls));
assert("prev updates persisted text to active version", persistCalls[persistCalls.length - 1] === "Version eins");
assert("prev persists conversation", saveCount >= 1);
const label2 = msg.querySelector(".regen-nav").querySelector(".regen-nav-label");
assert("label now 1/2", label2.textContent === "1/2", label2.textContent);

// 3. Single version -> no nav
const single = makeMsg();
applyRegenVersions(single.msg, "nur eine", []);
assert("no nav for a single version", single.msg.querySelector(".regen-nav") === null);
assert("single version stored", JSON.stringify(single.msg._regenVersions) === JSON.stringify(["nur eine"]));

// 4. Third regenerate appends -> 3/3
applyRegenVersions(msg, "Version drei", msg._regenVersions);
assert("third version appended", msg._regenVersions.length === 3 && msg._regenVersions[2] === "Version drei");
const label3 = msg.querySelector(".regen-nav").querySelector(".regen-nav-label");
assert("label 3/3 after third regenerate", label3.textContent === "3/3", label3.textContent);

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
