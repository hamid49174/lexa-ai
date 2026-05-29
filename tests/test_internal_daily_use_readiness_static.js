/**
 * Static smoke for internal daily-use readiness labels and docs.
 * Run with: node tests/test_internal_daily_use_readiness_static.js
 */

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend", "src", "index.html"), "utf8");
const layoutCss = fs.readFileSync(path.join(root, "frontend", "src", "css", "layout.css"), "utf8");
const viewsCss = [
  fs.readFileSync(path.join(root, "frontend", "src", "css", "views.css"), "utf8"),
  fs.readFileSync(path.join(root, "frontend", "src", "css", "views_settings.css"), "utf8"),
].join("\n");
const matrix = fs.readFileSync(path.join(root, "docs", "product", "feature_readiness_matrix.md"), "utf8");
const websiteSnapshot = fs.readFileSync(path.join(root, "docs", "product", "website_external_hardening_snapshot.md"), "utf8");

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

function hasAll(source, terms) {
  return terms.every((term) => source.includes(term));
}

console.log("\nInternal daily-use readiness:");

assert(
  "feature matrix records all readiness classifications",
  hasAll(matrix, ["CORE", "BETA", "INTERNAL_ONLY", "HIDE", "FIX_REQUIRED"])
);
assert(
  "feature matrix covers risky visible surfaces",
  hasAll(matrix, ["Voice", "Personal OS", "Hermes", "License", "Auto-update", "Trace Replay", "Agent Simulation", "Plugin"])
);
assert(
  "feature matrix keeps public release postponed",
  matrix.includes("Public release remains postponed") && matrix.includes("PublicRC remains blocked")
);
assert(
  "website snapshot preserves external hardening without release claims",
  hasAll(websiteSnapshot, ["../lexa-website/index.html", "../lexa-website/i18n.js", "not itself a Git repository", "not a website release target"])
);
assert(
  "website snapshot keeps domain and CDN decisions open",
  hasAll(websiteSnapshot, ["og:url", "CDN/CSP/SRI", "decision", "PublicRC remains blocked"])
);
assert(
  "UI exposes readiness chips for beta and internal surfaces",
  html.includes('data-readiness="beta"') && html.includes('data-readiness="internal"')
);
assert(
  "Personal OS navigation is marked internal",
  html.includes('data-view="personal-os"') && html.includes('data-readiness="internal"') && html.includes(">Internal<")
);
assert(
  "voice entry and settings are marked beta",
  html.includes('data-voice-entry-label') && html.includes('Voice surface is beta') && html.includes('Wake word is beta')
);
assert(
  "Hermes and license settings are visibly internal",
  html.includes('Hermes Gateway is internal') && html.includes('License integrity is internal')
);
assert(
  "readiness chip CSS exists for nav and settings",
  layoutCss.includes(".readiness-chip") && viewsCss.includes(".settings-group-title .readiness-chip")
);

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
