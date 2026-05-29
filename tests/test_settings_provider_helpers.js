/**
 * Direct checks for provider/model settings display helpers.
 * Run with: node tests/test_settings_provider_helpers.js
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..");
const helperSrc = fs.readFileSync(path.join(root, "frontend", "src", "settings_provider_helpers.js"), "utf8");

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

function createElement(tag) {
  const node = {
    tagName: String(tag || "").toUpperCase(),
    children: [],
    attributes: {},
    textContent: "",
    value: "",
    _innerHTML: "",
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    replaceChildren(...children) {
      this.children = children;
    },
    set innerHTML(value) {
      this._innerHTML = String(value || "");
      if (this._innerHTML === "") this.children = [];
    },
    get innerHTML() {
      return this._innerHTML;
    },
  };
  Object.defineProperty(node, "label", {
    get() { return this.attributes.label || ""; },
    set(value) { this.attributes.label = String(value || ""); },
  });
  Object.defineProperty(node, "selected", {
    get() { return this.attributes.selected === true; },
    set(value) { this.attributes.selected = Boolean(value); },
  });
  return node;
}

const context = {
  String,
  Boolean,
  Object,
  Array,
  document: { createElement },
};
vm.createContext(context);
vm.runInContext(helperSrc, context, { filename: "settings_provider_helpers.js" });

console.log("\nprovider settings helper boundaries:");

const groupedData = {
  current: "openai:gpt-4o-mini",
  current_name: "GPT-4o mini",
  available: { "openai:gpt-4o-mini": "GPT-4o mini" },
  grouped: {
    openai: {
      label: "OpenAI",
      models: {
        "openai:gpt-4o-mini": "GPT-4o mini",
        "openai:gpt-4.1": "GPT-4.1",
      },
    },
  },
};

const flatData = {
  current: "groq:llama",
  current_name: "Groq Llama",
  available: {
    "groq:llama": "Groq Llama",
    "anthropic:claude": "Claude",
  },
};

assert("available provider data is recognized", context.settingsAiModelHasAvailableData(groupedData) === true && context.settingsAiModelHasAvailableData({ available: [] }) === false);
assert("flat model options preserve current backend order", JSON.stringify(context.settingsAiModelFlatOptions(flatData)) === JSON.stringify(Object.entries(flatData.available)));
const groups = context.settingsAiModelGroupedOptions(groupedData);
assert("grouped model options preserve labels and entries", groups.length === 1 && groups[0].label === "OpenAI" && groups[0].options.length === 2 && groups[0].options[0][0] === "openai:gpt-4o-mini", JSON.stringify(groups));
assert("malformed provider/model payloads normalize to empty options", context.settingsAiModelFlatOptions({ available: "bad" }).length === 0 && context.settingsAiModelGroupedOptions({ grouped: "bad" }).length === 0);
assert("description text uses current name and falls back to current id", context.settingsAiModelDescriptionText(groupedData) === "Aktiv: GPT-4o mini" && context.settingsAiModelDescriptionText({ current: "safe:model", available: {} }) === "Aktiv: safe:model");

const select = createElement("select");
const desc = createElement("div");
const rendered = context.settingsRenderAiModelSelection(groupedData, select, desc);
assert("render helper populates grouped model options", rendered === true && select.children.length === 1 && select.children[0].children.length === 2 && desc.textContent === "Aktiv: GPT-4o mini", JSON.stringify(select));
assert("render helper clears select with replaceChildren", helperSrc.includes("select.replaceChildren()") && !helperSrc.includes("select.innerHTML"));
assert("render helper marks the active model option", select.children[0].children[0].selected === true && select.children[0].children[1].selected === false, JSON.stringify(select.children[0].children));

const unsafeSelect = createElement("select");
const unsafeDesc = createElement("div");
const unsafeData = {
  current: "unsafe:model",
  current_name: "<script>alert(1)</script>",
  available: { "unsafe:model": "<img src=x onerror=alert(1)>" },
};
context.settingsRenderAiModelSelection(unsafeData, unsafeSelect, unsafeDesc);
assert("unsafe model labels stay text values for DOM rendering", unsafeSelect.children[0].textContent === "<img src=x onerror=alert(1)>" && unsafeDesc.textContent === "Aktiv: <script>alert(1)</script>");
assert("missing select or missing available data does not render", context.settingsRenderAiModelSelection(unsafeData, null, unsafeDesc) === false && context.settingsRenderAiModelSelection({ available: null }, createElement("select"), unsafeDesc) === false);
assert("helper script remains classic", !/(^|\n)\s*(import|export)\b/.test(helperSrc));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
