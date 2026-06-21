/* Unit-Test fuer die In-Konversation-Suche (Ctrl+F) in chat_search.js.
 * Laedt das echte Modul mit einem minimalen DOM-Stub und prueft Match-Logik,
 * Highlight-Wrapping, Navigation und das Clear-Roundtrip (Text wird wiederhergestellt).
 */
const fs = require("fs");
const path = require("path");

let passed = 0, failed = 0;
function check(name, cond) {
  if (cond) { passed++; console.log("  ok: " + name); }
  else { failed++; console.log("  FAIL: " + name); }
}

// ── Minimaler DOM-Stub (Text/Element/Fragment) ──
class N {
  constructor(type, opts = {}) {
    this.nodeType = type; // 1=element, 3=text, 11=fragment
    this.childNodes = [];
    this.parentNode = null;
    this._class = "";
    this.dataset = {};
    if (type === 3) this.nodeValue = opts.nodeValue || "";
    if (type === 1) this.tagName = (opts.tagName || "DIV").toUpperCase();
  }
  get textContent() {
    if (this.nodeType === 3) return this.nodeValue;
    return this.childNodes.map((c) => c.textContent).join("");
  }
  set textContent(v) {
    if (this.nodeType === 3) { this.nodeValue = String(v); return; }
    const t = new N(3, { nodeValue: String(v) }); t.parentNode = this; this.childNodes = [t];
  }
  get className() { return this._class; }
  set className(v) { this._class = String(v); }
  appendChild(c) {
    if (c.nodeType === 11) { c.childNodes.slice().forEach((k) => { k.parentNode = this; this.childNodes.push(k); }); }
    else { c.parentNode = this; this.childNodes.push(c); }
    return c;
  }
  append(...cs) { cs.forEach((c) => this.appendChild(c)); }
  replaceChild(nw, old) {
    const i = this.childNodes.indexOf(old);
    if (i === -1) return;
    if (nw.nodeType === 11) {
      const kids = nw.childNodes.slice(); kids.forEach((k) => { k.parentNode = this; });
      this.childNodes.splice(i, 1, ...kids);
    } else { nw.parentNode = this; this.childNodes.splice(i, 1, nw); }
    old.parentNode = null;
  }
  normalize() {
    const merged = [];
    for (const c of this.childNodes) {
      const last = merged[merged.length - 1];
      if (last && last.nodeType === 3 && c.nodeType === 3) last.nodeValue += c.nodeValue;
      else merged.push(c);
    }
    this.childNodes = merged;
  }
  setAttribute() {}
  scrollIntoView() {}
}

const _byId = {};
const documentStub = {
  getElementById: (id) => _byId[id] || null,
  createElement: (tag) => new N(1, { tagName: tag }),
  createTextNode: (v) => new N(3, { nodeValue: String(v) }),
  createDocumentFragment: () => new N(11),
};

// Chat-Baum: msg-text mit Text + einem <strong> mit weiterem Text.
const root = new N(1, { tagName: "DIV" });
const msgText = new N(1, { tagName: "DIV" }); msgText.className = "msg-text";
const t1 = new N(3, { nodeValue: "Hallo Welt, " });
const strong = new N(1, { tagName: "STRONG" });
const t2 = new N(3, { nodeValue: "hallo nochmal" });
strong.appendChild(t2);
msgText.appendChild(t1); msgText.appendChild(strong);
root.appendChild(msgText);
_byId["chat-messages"] = root;
const countEl = new N(1, { tagName: "SPAN" });
_byId["chat-find-count"] = countEl;

const ORIGINAL_TEXT = root.textContent;

// ── Modul laden ──
const code = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "chat_search.js"), "utf8");
const win = {};
// eslint-disable-next-line no-new-func
new Function("window", "document", "t", "showToast", "LexaState", code)(
  win, documentStub, (k) => k, () => {}, { get: () => null, set: () => {} }
);

check("exposes chatFindRanges", typeof win.chatFindRanges === "function");
check("exposes runChatFind", typeof win.runChatFind === "function");

// ── Pure Match-Logik ──
check("ranges: case-insensitive, no overlap", win.chatFindRanges("Hallo hallo HALLO", "hallo").length === 3);
check("ranges: empty query -> none", win.chatFindRanges("abc", "").length === 0);
check("ranges: no match -> none", win.chatFindRanges("abc", "xyz").length === 0);
const r = win.chatFindRanges("xax", "x");
check("ranges: correct indices", r[0][0] === 0 && r[0][1] === 1 && r[1][0] === 2 && r[1][1] === 3);

// ── Highlight im Baum ──
const hits = win.runChatFind("hallo");
check("runChatFind finds both occurrences (2)", hits === 2);
check("count shows 1/2 after find", countEl.textContent === "1/2");
// Treffer sind als <mark class=chat-find-mark> gewrappt
function countMarks(node) {
  let n = 0;
  for (const c of node.childNodes) {
    if (c.nodeType === 1 && c.tagName === "MARK") n += 1;
    if (c.nodeType === 1) n += countMarks(c);
  }
  return n;
}
check("two marks inserted in DOM", countMarks(root) === 2);
check("first mark is current", (function find(node) {
  for (const c of node.childNodes) {
    if (c.nodeType === 1 && c.tagName === "MARK") return c.className.indexOf("chat-find-current") !== -1;
    if (c.nodeType === 1) { const v = find(c); if (v !== null) return v; }
  }
  return null;
})(root) === true);

// ── Navigation ──
win.chatFindNext();
check("count advances to 2/2", countEl.textContent === "2/2");
win.chatFindNext();
check("wraps back to 1/2", countEl.textContent === "1/2");

// ── Clear-Roundtrip ──
win.clearChatFindHighlights();
check("no marks after clear", countMarks(root) === 0);
check("original text restored", root.textContent === ORIGINAL_TEXT);

console.log("\n" + (passed + failed) + " tests: " + passed + " passed, " + failed + " failed");
if (failed > 0) process.exit(1);
