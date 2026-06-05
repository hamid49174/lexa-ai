/**
 * Static smoke tests for the read-only tool audit surface.
 * Run with: node tests/test_tool_audit_surface.js
 */

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const preload = fs.readFileSync(path.join(root, "frontend", "preload.js"), "utf8");
const system = fs.readFileSync(path.join(root, "frontend", "src", "system.js"), "utf8");
const index = fs.readFileSync(path.join(root, "frontend", "src", "index.html"), "utf8");
const styles = fs.readFileSync(path.join(root, "frontend", "src", "css", "views.css"), "utf8");
const en = fs.readFileSync(path.join(root, "frontend", "src", "i18n", "en.json"), "utf8");
const de = fs.readFileSync(path.join(root, "frontend", "src", "i18n", "de.json"), "utf8");

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

console.log("\nTool audit surface:");
assert("preload exposes companionAuditRecent bridge", preload.includes("companionAuditRecent: async"));
assert("bridge calls read-only audit endpoint", preload.includes("/companion/audit/recent?") && preload.includes('params.set("hideNoise"'));
assert("bridge normalizes audit HTTP errors", preload.includes('personalOsJson(res, "Audit request failed")'));
assert("system view includes audit panel markup", index.includes("system-audit-panel") && index.includes("system-audit-list") && index.includes('role="list"') && index.includes('aria-busy="false"'));
assert("refresh button uses delegated action", index.includes('data-action="refreshSystemAuditActivity"'));
assert("fallback system view localizes audit chrome", system.includes('t("system.trust")') && system.includes('t("system.recentToolActivity")') && system.includes('t("system.refresh")'));
assert("renderer requests bounded high-signal entries", system.includes("window.lexa.companionAuditRecent(12, true)"));
assert("renderer explains hidden polling noise", system.includes("system.auditNoiseOnly") && system.includes("skipped_noise"));
assert("renderer marks redacted audit details", system.includes("entry.redacted") && system.includes("system-audit-redacted"));
assert("refresh ignores stale audit responses", system.includes("systemAuditRefreshSeq") && system.includes("requestId !== systemAuditRefreshSeq"));
assert("audit refresh exposes busy state", system.includes("aria-busy") && system.includes('setSystemAuditMessage(t("common.loading"), "muted", true)') && system.includes('list.setAttribute("aria-busy", "false")'));
assert("audit rows expose accessible labels and titles", system.includes('row.setAttribute("role", "listitem")') && system.includes('row.setAttribute(') && system.includes('"aria-label"') && system.includes(".title ="));
assert("renderer uses DOM nodes for audit rows", system.includes("document.createElement(\"div\")") && system.includes("list.replaceChildren(fragment)"));
assert("system view shell renders through DOM helpers", system.includes("function createSystemTextElement") && system.includes("function createSystemPanelHeader") && system.includes("function createSystemActionButton") && system.includes("div.append(title, grid, startupPanel, hermesPanel, auditPanel)") && system.includes('auditList.setAttribute("role", "list")') && !system.includes("div.innerHTML = `"));
assert("system metric cards render through DOM helpers", system.includes("function createSystemInfoCard") && system.includes("function createSystemInfoBar") && system.includes("const cpuPercent = systemDisplayPercent(d.cpu_percent)") && system.includes("grid.replaceChildren(") && system.includes("createSystemInfoCard(t(\"system.cpuUsage\")") && !system.includes("grid.innerHTML") && !system.includes("${d.cpu_percent}%") && !system.includes("${d.ram_used_gb} GB"));
assert("system quick bar renders through DOM helpers", system.includes("function createSystemQuickStat") && system.includes("function systemBootTimeLabel") && system.includes("bar.replaceChildren(") && system.includes("createSystemQuickStat(systemBootTimeLabel(d.boot_time)") && !system.includes("bar.innerHTML"));
assert("startup health overview renders through DOM helpers", system.includes("function createSystemOverviewSummary") && system.includes("function createSystemOverviewCheckRow") && system.includes("function createSystemOverviewFileRow") && system.includes("createSystemOverviewSummary(payload.state") && system.includes("createSystemOverviewSection(t(\"system.startupChecks\")") && !system.includes("checks.length ? checks.map((check) => {") && !system.includes("providerRows = providers.length ? providers.map((provider) => `"));
assert("Hermes overview renders through DOM helpers", system.includes("function createSystemOverviewTaskList") && system.includes("createSystemOverviewSummary(payload.healthState") && system.includes("createSystemOverviewSection(t(\"system.hermesChecks\")") && system.includes("createSystemOverviewSection(t(\"system.hermesNextAction\")") && !system.includes("target.innerHTML") && !system.includes("taskRows = tasks.length ? tasks.map"));
assert("system overview counters are normalized before template rendering", system.includes("function systemDisplayCount") && system.includes("return `${systemDisplayCount(counts?.ok)}") && system.includes("const toolsPct = systemDisplayNumber(systemDisplayPercent(tools.healthPct))") && system.includes("const contextCount = systemDisplayCount(counts.contextFiles ?? files.length ?? 0)") && !system.includes("const toolsPct = Number(tools.healthPct || 0)") && !system.includes("const contextCount = Number("));
assert("renderer classifies audit status", system.includes("function systemAuditStatusClass"));
assert("styles keep audit rows bounded", styles.includes(".system-audit-command") && styles.includes("text-overflow: ellipsis"));
assert("styles keep overview metrics bounded", styles.includes("grid-template-columns: repeat(auto-fit, minmax(150px, 1fr))") && styles.includes(".system-overview-metric strong") && styles.includes("overflow-wrap: anywhere"));
assert("redaction label is localized", en.includes("system.auditDetailsRedacted") && de.includes("system.auditDetailsRedacted"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
