/* Unit-Test fuer die MCP-Server-Verwaltung (mcp_settings.js).
 * Laedt das echte Modul mit Stubs und prueft Parser + DOM-Render (CSP-sicher).
 * Run: node tests/test_mcp_settings.js
 */
const fs = require("fs");
const path = require("path");

let passed = 0, failed = 0;
function check(name, cond) {
  if (cond) { passed++; console.log("  ok: " + name); }
  else { failed++; console.log("  FAIL: " + name); }
}

const code = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "mcp_settings.js"), "utf8");

// Minimaler DOM-Stub
function makeEl() {
  return {
    className: "", textContent: "", type: "", dataset: {}, children: [],
    append(...kids) { this.children.push(...kids); },
    appendChild(k) { this.children.push(k); return k; },
    replaceChildren(...kids) { this.children = kids; },
  };
}
const documentStub = {
  createElement: () => makeEl(),
  createDocumentFragment: () => makeEl(),
  getElementById: () => null,
};

const exportLine = "\n;return { mcpParseArgs, mcpParseEnv, mcpStatusLabel, renderMcpServerList };";
// eslint-disable-next-line no-new-func
const factory = new Function(
  "window", "document", "t", "showToast", "showInputModal",
  code + exportLine
);
const mod = factory({}, documentStub, (k) => k, () => {}, async () => null);

// ── Parser ──
check("mcpParseArgs splits lines + trims + drops empty",
  JSON.stringify(mod.mcpParseArgs("-y\n  pkg \n\n/path")) === JSON.stringify(["-y", "pkg", "/path"]));
check("mcpParseArgs empty -> []", JSON.stringify(mod.mcpParseArgs("")) === "[]");

const env = mod.mcpParseEnv("KEY=val\nFOO = bar=baz\n# nicht\nNOEQ\n=leer");
check("mcpParseEnv parses KEY=val", env.KEY === "val");
check("mcpParseEnv keeps everything after first '=' ", env.FOO === "bar=baz");
check("mcpParseEnv ignores lines without key", !("NOEQ" in env) && !("" in env));

// ── Render ──
function collectActions(node, acc) {
  if (!node) return acc;
  if (node.dataset && node.dataset.action) acc.push(node.dataset.action + ":" + (node.dataset.arg || ""));
  for (const c of node.children || []) collectActions(c, acc);
  return acc;
}

const emptyList = makeEl();
mod.renderMcpServerList(emptyList, { enabled: true, servers: [] });
check("empty servers -> single empty row", emptyList.children.length === 1 && emptyList.children[0].className === "mcp-empty");

const disabledList = makeEl();
mod.renderMcpServerList(disabledList, { enabled: false });
check("disabled -> empty row", disabledList.children.length === 1);

const list = makeEl();
mod.renderMcpServerList(list, { enabled: true, servers: [
  { name: "filesystem", command: "npx", args: ["-y", "srv"], status: "connected" },
  { name: "git", command: "uvx", args: [], status: "disconnected" },
] });
check("renders one row per server", list.children.length === 1 && list.children[0].children.length === 2);
const actions = collectActions(list, []);
check("connected server offers disconnect+remove",
  actions.includes("mcpDisconnectServer:filesystem") && actions.includes("mcpRemoveServer:filesystem"));
check("disconnected server offers connect+remove",
  actions.includes("mcpConnectServer:git") && actions.includes("mcpRemoveServer:git"));

check("mcpStatusLabel maps status keys",
  mod.mcpStatusLabel("connected") === "mcp.statusConnected" &&
  mod.mcpStatusLabel("error") === "mcp.statusError" &&
  mod.mcpStatusLabel("x") === "mcp.statusDisconnected");

// ── CSP-Sicherheit + Verdrahtung ──
check("no innerHTML usage", !/\.innerHTML/.test(code));
const appActions = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "app_actions.js"), "utf8");
for (const a of ["mcpAddServer", "mcpConnectServer", "mcpDisconnectServer", "mcpRemoveServer"]) {
  check(`app_actions dispatches ${a}`, appActions.includes(`case "${a}"`));
}
const preload = fs.readFileSync(path.join(__dirname, "..", "frontend", "preload.js"), "utf8");
for (const b of ["mcpAddServer", "mcpUpdateServer", "mcpRemoveServer"]) {
  check(`preload defines bridge ${b}`, preload.includes(`${b}:`) && preload.includes(`bridgePolicy("${b}"`));
}

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
