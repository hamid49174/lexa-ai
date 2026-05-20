/**
 * Direct checks for extracted settings preference helpers.
 * Run with: node tests/test_settings_helpers.js
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..");
const helperSrc = fs.readFileSync(path.join(root, "frontend", "src", "settings_helpers.js"), "utf8");

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

const context = { String };
vm.createContext(context);
vm.runInContext(helperSrc, context, { filename: "settings_helpers.js" });

console.log("\nsettings helper boundaries:");

assert("valid themes are preserved", context.settingsSafeTheme("light") === "light" && context.settingsSafeTheme("dark") === "dark");
assert("invalid themes fall back to dark", context.settingsSafeTheme("solarized<script>") === "dark" && context.settingsSafeTheme(null) === "dark");
assert("valid accents are preserved", context.settingsSafeAccent("green") === "green" && context.settingsSafeAccent("amber") === "amber");
assert("invalid accents fall back to purple", context.settingsSafeAccent("<img src=x onerror=alert(1)>") === "purple" && context.settingsSafeAccent(undefined) === "purple");
assert("valid font sizes are preserved", context.settingsSafeFontSize("13") === "13" && context.settingsSafeFontSize(16) === "16");
assert("invalid font sizes fall back to 14", context.settingsSafeFontSize("99") === "14" && context.settingsSafeFontSize("") === "14");
assert("valid languages are preserved", context.settingsSafeLanguage("de") === "de" && context.settingsSafeLanguage("en") === "en");
assert("invalid languages fall back to de", context.settingsSafeLanguage("fr") === "de" && context.settingsSafeLanguage(null) === "de");
assert("helper script remains classic", !/(^|\n)\s*(import|export)\b/.test(helperSrc));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
