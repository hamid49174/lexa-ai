/**
 * Static/unit tests for chat message rendering safety.
 * Run with: node tests/test_chat_rendering.js
 */

const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat.js"),
  "utf8"
);
const formattingSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_formatting.js"),
  "utf8"
);

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

function escapeHtmlForStub(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function makeDomStub() {
  const voidTags = new Set(["br", "hr", "img", "input"]);

  class TextNode {
    constructor(value) { this.value = String(value || ""); }
    get textContent() { return this.value; }
    set textContent(value) { this.value = String(value || ""); }
    get outerHTML() { return escapeHtmlForStub(this.value); }
  }

  class ElementNode {
    constructor(tag) {
      this.tagName = String(tag || "div").toLowerCase();
      this.children = [];
      this.attributes = {};
      this.dataset = new Proxy({}, {
        set: (_target, key, value) => {
          const attr = String(key).replace(/[A-Z]/g, (ch) => "-" + ch.toLowerCase());
          this.setAttribute("data-" + attr, value);
          return true;
        },
      });
    }
    appendChild(node) {
      const child = typeof node === "string" ? new TextNode(node) : node;
      this.children.push(child);
      return child;
    }
    append(...nodes) { nodes.forEach((node) => this.appendChild(node)); }
    replaceChildren(...nodes) {
      this.children = [];
      this.append(...nodes);
    }
    setAttribute(name, value) { this.attributes[String(name)] = String(value); }
    getAttribute(name) { return this.attributes[String(name)]; }
    set textContent(value) { this.children = [new TextNode(value)]; }
    get textContent() { return this.children.map((child) => child.textContent || "").join(""); }
    set className(value) { this.setAttribute("class", value); }
    get className() { return this.attributes.class || ""; }
    set type(value) { this.setAttribute("type", value); }
    get type() { return this.attributes.type || ""; }
    set href(value) { this.setAttribute("href", value); }
    get href() { return this.attributes.href || ""; }
    set src(value) { this.setAttribute("src", value); }
    get src() { return this.attributes.src || ""; }
    set alt(value) { this.setAttribute("alt", value); }
    get alt() { return this.attributes.alt || ""; }
    set target(value) { this.setAttribute("target", value); }
    get target() { return this.attributes.target || ""; }
    set rel(value) { this.setAttribute("rel", value); }
    get rel() { return this.attributes.rel || ""; }
    set title(value) { this.setAttribute("title", value); }
    get title() { return this.attributes.title || ""; }
    get innerHTML() { return this.children.map((child) => child.outerHTML || "").join(""); }
    get outerHTML() {
      const attrs = Object.entries(this.attributes)
        .map(([key, value]) => ` ${key}="${escapeHtmlForStub(value)}"`)
        .join("");
      if (voidTags.has(this.tagName)) return `<${this.tagName}${attrs}>`;
      return `<${this.tagName}${attrs}>${this.innerHTML}</${this.tagName}>`;
    }
  }

  return {
    createElement: (tag) => new ElementNode(tag),
    createTextNode: (value) => new TextNode(value),
    getElementById: () => null,
  };
}

const escHtml = extractFn(src, "escapeHtml");
const renderFormatted = extractFn(src, "renderFormattedMessage");
const rendererStart = src.indexOf("function appendInlineMarkdown(");
const rendererEnd = src.indexOf("function generateSuggestions(");
if (rendererStart === -1 || rendererEnd === -1 || rendererEnd <= rendererStart) {
  throw new Error("renderer helper block not found");
}
const rendererBlock = src.slice(rendererStart, rendererEnd);

const sandbox = new Function("document", "URL", `
  "use strict";
  ${escHtml}
  ${formattingSrc}
  ${renderFormatted}
  ${rendererBlock}
  return { escapeHtml, stripModelFunctionTags, normalizeChatUrl, formatMessage, renderFormattedMessage };
`);

let escapeHtml;
let stripModelFunctionTags;
let normalizeChatUrl;
let formatMessage;
let renderFormattedMessage;
try {
  ({ escapeHtml, stripModelFunctionTags, normalizeChatUrl, formatMessage, renderFormattedMessage } = sandbox(makeDomStub(), URL));
} catch (e) {
  console.error("Sandbox setup failed:", e.message);
  process.exit(1);
}

let passed = 0;
let failed = 0;
function assert(desc, ok, detail = "") {
  if (ok) {
    console.log(`  ok: ${desc}`);
    passed += 1;
  } else {
    console.error(`  FAIL: ${desc}${detail ? " - " + detail : ""}`);
    failed += 1;
  }
}

console.log("\nescapeHtml():");
assert("escapes <", escapeHtml("<").includes("&lt;"));
assert("escapes >", escapeHtml(">").includes("&gt;"));
assert("escapes &", escapeHtml("a & b").includes("&amp;"));
assert("escapes quote", escapeHtml('"').includes("&quot;"));
assert("plain text unchanged", escapeHtml("hello") === "hello");
assert("full XSS tag escaped", !escapeHtml("<script>alert(1)</script>").includes("<script>"));

console.log("\nformatting helper boundaries:");
assert("stripModelFunctionTags handles empty input", stripModelFunctionTags(null) === "");
assert("stripModelFunctionTags removes wrapped function payloads", stripModelFunctionTags("before <function=tool>{\"x\":1}</function> after") === "before  after");
assert("stripModelFunctionTags removes open function tags", stripModelFunctionTags("<function=tool name=\"x\"/>hello") === "hello");
assert("normalizeChatUrl handles empty input", normalizeChatUrl("") === "");
assert("normalizeChatUrl keeps safe web links", normalizeChatUrl("https://example.com/a?q=1") === "https://example.com/a?q=1");
assert("normalizeChatUrl allows mailto links for text", normalizeChatUrl("mailto:test@example.com") === "mailto:test@example.com");
assert("normalizeChatUrl blocks mailto links for images", normalizeChatUrl("mailto:test@example.com", { image: true }) === "");
assert("normalizeChatUrl blocks javascript links", normalizeChatUrl("javascript:alert(1)") === "");
assert("normalizeChatUrl blocks local file links", normalizeChatUrl("file:///C:/Users/admin/.ssh/id_rsa") === "");

console.log("\nformatMessage():");

const r1 = formatMessage('<script>alert("xss")</script>');
assert("script tag not in output", !r1.includes("<script>"), r1.slice(0, 120));
assert("script content rendered as text", r1.includes("&lt;script&gt;"), r1.slice(0, 120));

const r2 = formatMessage("<img src=x onerror=alert(1)>");
assert("img onerror not rendered raw", !r2.includes("<img src=x"), r2.slice(0, 120));
assert("onerror payload is text", r2.includes("&lt;img") && r2.includes("onerror="), r2.slice(0, 120));

const r3 = formatMessage("```python\nprint('<b>hi</b>')\n```");
assert("code block uses pre/code", r3.includes("<pre") && r3.includes("<code"), r3.slice(0, 160));
assert("code content HTML-escaped", !r3.includes("<b>hi</b>"), r3.slice(0, 160));

const r4 = formatMessage("This is **bold** text");
assert("bold markdown renders strong", r4.includes("<strong>bold</strong>"), r4);

const r5 = formatMessage("This is *italic* word");
assert("italic markdown renders em", r5.includes("<em>italic</em>"), r5);

const r6 = formatMessage("**<script>evil()</script>**");
assert("XSS inside bold markers escaped", !r6.includes("<script>"), r6.slice(0, 120));

const r7 = formatMessage("![logo](javascript:alert(1))");
assert("unsafe image protocol not rendered", !r7.includes("<img"), r7.slice(0, 120));

const r8 = formatMessage("[click](javascript:alert(1))");
assert("unsafe link protocol not rendered", !r8.includes("<a "), r8.slice(0, 120));

const r9 = formatMessage("![logo](https://example.com/logo.png)");
assert("safe chat image uses CSS class", r9.includes('class="chat-img"'), r9);
assert("chat image has no inline style", !r9.includes("style="), r9);

const r10 = formatMessage("[safe](https://example.com/a?q=1)");
assert("safe link rendered", r10.includes("<a ") && r10.includes("https://example.com/"), r10);
assert("safe link gets noopener", r10.includes('rel="noopener noreferrer"'), r10);
assert("safe web link opens controlled target", r10.includes('target="_blank"'), r10);

const r11 = formatMessage("[mail](mailto:test@example.com)");
assert("mailto link allowed", r11.includes('href="mailto:test@example.com"'), r11);
assert("mailto link does not force blank target", !r11.includes('target="_blank"'), r11);

const xssPayloads = [
  '<a href="javascript:alert(1)">x</a>',
  '<div onclick="alert(1)">x</div>',
  '<svg onload=alert(1)>',
  '![x](data:text/html,<script>alert(1)</script>)',
  '[x](data:text/html,<script>alert(1)</script>)',
  '[x](file:///C:/Users/admin/.ssh/id_rsa)',
  '[x](vbscript:msgbox(1))',
  '[broken](javascript:alert(1)',
  'tool error: <img src=x onmouseover=alert(1)>',
  'model output: <body onload=alert(1)>',
];
xssPayloads.forEach((payload, index) => {
  const rendered = formatMessage(payload);
  assert(
    `payload ${index + 1} has no executable tag`,
    !/(<script|<svg|<iframe|<object|<embed|<a href="javascript|<img src=x)/i.test(rendered),
    rendered
  );
  assert(`payload ${index + 1} has no inline handler attribute`, !/<[^>]+\son[a-z]+\s*=/i.test(rendered), rendered);
  assert(
    `payload ${index + 1} has no unsafe protocol attr`,
    !/(href|src)="(?:javascript:|data:text\/html|file:\/\/|vbscript:)/i.test(rendered),
    rendered
  );
});

const target = makeDomStub().createElement("div");
renderFormattedMessage(target, "<script>alert(1)</script>");
assert(
  "renderFormattedMessage appends escaped DOM text",
  target.innerHTML.includes("&lt;script&gt;") && !target.innerHTML.includes("<script>"),
  target.innerHTML
);
assert(
  "renderFormattedMessage source avoids assigning formatMessage via innerHTML",
  !src.includes("target.innerHTML = formatMessage")
);

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
