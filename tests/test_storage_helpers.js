/**
 * Direct checks for safe renderer preference storage helpers.
 * Run with: node tests/test_storage_helpers.js
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..");
const storageSrc = fs.readFileSync(path.join(root, "frontend", "src", "storage.js"), "utf8");

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

function runStorageContext(localStorage) {
  const context = { console, JSON, Map, String, window: { localStorage } };
  vm.createContext(context);
  vm.runInContext(storageSrc, context, { filename: "storage.js" });
  return context;
}

console.log("\nstorage helpers:");

const backing = new Map();
const workingStorage = {
  getItem: (key) => backing.has(key) ? backing.get(key) : null,
  setItem: (key, value) => { backing.set(key, String(value)); },
  removeItem: (key) => { backing.delete(key); },
};
const working = runStorageContext(workingStorage);
working.lexaStorageSet("lexa-theme", "light");
assert("writes through to available localStorage", backing.get("lexa-theme") === "light");
assert("reads from available localStorage", working.lexaStorageGet("lexa-theme", "dark") === "light");
assert("json helper parses arrays", Array.isArray(working.lexaStorageJson("missing", [])));

const brokenStorage = {
  getItem: () => { throw new Error("blocked"); },
  setItem: () => { throw new Error("blocked"); },
  removeItem: () => { throw new Error("blocked"); },
};
const broken = runStorageContext(brokenStorage);
assert("missing keys return fallback when storage is blocked", broken.lexaStorageGet("lexa-lang", "de") === "de");
assert("set falls back to memory when storage is blocked", broken.lexaStorageSet("lexa-lang", "en") === false && broken.lexaStorageGet("lexa-lang", "de") === "en");
assert("remove clears memory when storage is blocked", broken.lexaStorageRemove("lexa-lang") === false && broken.lexaStorageGet("lexa-lang", "de") === "de");
assert("helper script remains classic", !/(^|\n)\s*(import|export)\b/.test(storageSrc));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
