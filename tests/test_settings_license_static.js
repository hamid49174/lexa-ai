/**
 * Static tests for Settings license action robustness.
 * Run with: node tests/test_settings_license_static.js
 */

const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "settings.js"),
  "utf8"
);

function extractFn(source, name) {
  const needles = [`async function ${name}(`, `function ${name}(`];
  const start = needles
    .map((needle) => source.indexOf(needle))
    .filter((index) => index >= 0)
    .sort((a, b) => a - b)[0];
  if (start === undefined) throw new Error(`'${name}' not found`);
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`No closing brace for '${name}'`);
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

console.log("\nSettings license actions:");
const activateLicenseSource = extractFn(src, "activateLicense");
const removeLicenseSource = extractFn(src, "removeLicense");
const licenseActionSource = extractFn(src, "runSettingsLicenseAction");
const licenseBusySource = extractFn(src, "setSettingsLicenseActionsBusy");

assert("settings license actions share a singleflight guard", src.includes("let _licenseActionRunning = false") && licenseActionSource.includes("if (_licenseActionRunning) return") && licenseActionSource.includes("_licenseActionRunning = true") && licenseActionSource.includes("_licenseActionRunning = false"));
assert("settings license actions expose busy state on both license buttons", src.includes("const SETTINGS_LICENSE_ACTIONS = [") && src.includes('"activateLicense"') && src.includes('"removeLicense"') && licenseBusySource.includes("SETTINGS_LICENSE_ACTIONS.forEach") && licenseBusySource.includes("setSettingsActionButtonsBusy(actionName, busy)") && licenseActionSource.includes("setSettingsLicenseActionsBusy(true)") && licenseActionSource.includes("setSettingsLicenseActionsBusy(false)"));
assert("license activation runs through the shared guard", activateLicenseSource.includes("await runSettingsLicenseAction(async () =>") && activateLicenseSource.includes("await window.lexa.licenseActivate(key)") && activateLicenseSource.includes("await loadLicenseStatus()"));
assert("license removal runs through the shared guard", removeLicenseSource.includes("await runSettingsLicenseAction(async () =>") && removeLicenseSource.includes("await window.lexa.licenseSet(") && removeLicenseSource.includes("await loadLicenseStatus()"));
assert("license removal reports backend failures to the user", removeLicenseSource.includes("try {") && removeLicenseSource.includes("catch (e)") && removeLicenseSource.includes("showToast") && removeLicenseSource.includes("settingsClip(e.message || e"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
