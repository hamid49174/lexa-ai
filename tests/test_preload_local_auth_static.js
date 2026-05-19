const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "frontend", "preload.js"), "utf8");

let passed = 0;
let failed = 0;
function assert(desc, ok) {
  if (ok) {
    console.log(`  ok: ${desc}`);
    passed += 1;
  } else {
    console.error(`  FAIL: ${desc}`);
    failed += 1;
  }
}

console.log("\nPreload local auth:");
assert("does not expose local auth token on window.lexa", !src.includes("localAuthToken:"));
assert("gets local auth token only through IPC", src.includes('ipcRenderer.invoke("local-auth-token")'));
assert("adds X-Lexa-Local-Token header centrally", src.includes("headers.set(LOCAL_AUTH_HEADER, token)"));
assert("guards token forwarding to local backend URLs", src.includes("function isLocalLexaBackendUrl") && src.includes('"127.0.0.1"') && src.includes('"localhost"'));
assert("does not send legacy confirmed flag as authorization", src.includes("void confirmed; // Legacy UI hint only") && !src.includes("JSON.stringify({ command, params, confirmed })"));
assert("exposes explicit prepare and confirmed execution bridge methods", src.includes("prepareCompanionExecute") && src.includes("/companion/execute/prepare") && src.includes("executeWithConfirmation"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
