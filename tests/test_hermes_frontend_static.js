/**
 * Static smoke tests for Hermes health and provider fallback frontend surfaces.
 * Run with: node tests/test_hermes_frontend_static.js
 */

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const dashboard = fs.readFileSync(path.join(root, "frontend", "src", "dashboard.js"), "utf8");
const settings = fs.readFileSync(path.join(root, "frontend", "src", "settings.js"), "utf8");
const system = fs.readFileSync(path.join(root, "frontend", "src", "system.js"), "utf8");
const preload = fs.readFileSync(path.join(root, "frontend", "preload.js"), "utf8");
const html = fs.readFileSync(path.join(root, "frontend", "src", "index.html"), "utf8");
const deI18n = fs.readFileSync(path.join(root, "frontend", "src", "i18n", "de.json"), "utf8");
const enI18n = fs.readFileSync(path.join(root, "frontend", "src", "i18n", "en.json"), "utf8");

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

console.log("\nHermes frontend:");

assert("dashboard fetches backend health for Hermes state", dashboard.includes("window.lexa.health()") && dashboard.includes("healthRes"));
assert("dashboard renders Anthropic provider status", dashboard.includes('["anthropic", "Claude"]'));
assert("dashboard renders provider fallback status", dashboard.includes("fallback_available") && dashboard.includes('t("dashboard.aiFallback")'));
assert("dashboard renders Hermes health row", dashboard.includes("const hermes = healthRes.status") && dashboard.includes('createDashboardAiRow("Hermes", hermesLabel, hermesReady)'));

assert("settings tracks Anthropic provider status", settings.includes("anthropic-status") && settings.includes("ai.anthropic?.available"));
assert("settings builds Hermes readiness signal", settings.includes("function hermesReadinessSignal") && settings.includes("diagnostics?.hermes") && settings.includes("health?.hermes"));
assert("settings includes Hermes in readiness checks and cards", settings.includes('label: "Hermes"') && settings.includes("hermes.checkState") && settings.includes("diagnosticsLabel(hermes.state)"));
assert("settings counts four AI providers", settings.includes('const providers = ["groq", "openai", "gemini", "anthropic"]') && settings.includes("`${aiReadyCount}/4`"));
assert("settings renders Hermes gateway autostart control", settings.includes("function renderHermesGatewayAutostart") && settings.includes("hermesGatewayAutostartSet") && settings.includes("setupHermesGatewayAutostartControls"));
assert("settings Hermes gateway autostart cannot stay busy after toggle", settings.includes("let _hermesGatewayAutostartRunning = false") && settings.includes("let _hermesGatewayAutostartLastPayload = null") && settings.includes("_hermesGatewayAutostartLastPayload = payload") && settings.includes("_hermesGatewayAutostartRunning || !canToggle") && settings.includes('toggle.setAttribute("aria-busy", "true")') && settings.includes('toggle.removeAttribute("aria-busy")') && settings.includes("if (_hermesGatewayAutostartRunning)") && settings.includes("finally") && settings.includes("renderHermesGatewayAutostart(_hermesGatewayAutostartLastPayload)"));

assert("settings page exposes Anthropic status row", html.includes('id="anthropic-status"') && html.includes('data-i18n="settings.anthropicApiKey"'));
assert("settings page exposes Hermes gateway autostart toggle", html.includes('id="hermes-gateway-autostart-status"') && html.includes('id="hermes-gateway-autostart-toggle"'));
assert("system page exposes Startup Health panel", html.includes('id="startup-health-panel"') && html.includes('id="startup-health-content"') && html.includes('data-action="refreshStartupHealth"'));
assert("system page exposes Hermes overview cockpit", html.includes('id="hermes-overview-panel"') && html.includes('id="hermes-overview-content"') && html.includes('data-action="refreshHermesOverview"'));
assert("system view renders Startup Health from backend", system.includes("function refreshStartupHealth") && system.includes("window.lexa.startupHealth({ probeVoice: false })") && system.includes("function renderStartupHealth"));
assert("system view renders Hermes overview from backend", system.includes("function refreshHermesOverview") && system.includes("window.lexa.hermesOverview({ includeContext: true })") && system.includes("function renderHermesOverview"));
assert("system view renders Hermes capability gaps", system.includes("function createSystemOverviewCapabilityGapRow") && system.includes('t("system.hermesMetricCapabilities")') && system.includes('t("system.hermesCapabilityGaps")') && system.includes("capabilityPayload.gaps"));
assert("system view renders Hermes provider fallback status", system.includes("function createHermesProviderRows") && system.includes('t("system.hermesMetricFallbacks")') && system.includes('t("system.hermesProviders")') && system.includes("payload.providerStatus"));
assert("system view renders Hermes media readiness", system.includes("function createHermesMediaRows") && system.includes('t("system.hermesMetricMedia")') && system.includes('t("system.hermesMedia")') && system.includes("payload.mediaStatus"));
assert("system view renders Hermes extension readiness", system.includes("function createHermesExtensionRows") && system.includes('t("system.hermesMetricExtensions")') && system.includes('t("system.hermesExtensions")') && system.includes("payload.extensionStatus"));
assert("system view preserves canonical backend request ids in errors", system.includes("function systemErrorMessage") && system.includes("payload?.requestId") && system.includes("Request ID:") && system.includes('systemErrorMessage(payload, t("system.hermesOverviewUnavailable")'));
assert("preload smoke mock includes Hermes health", preload.includes("hermes: {") && preload.includes('state: "ready"') && preload.includes("telegram_configured"));
assert("preload exposes Hermes gateway autostart API", preload.includes("hermesGatewayAutostartStatus") && preload.includes("hermesGatewayAutostartSet") && preload.includes("/hermes/gateway/autostart"));
assert("preload exposes Hermes capabilities API", preload.includes("hermesCapabilities: async") && preload.includes("/hermes/capabilities"));
assert("preload exposes Hermes providers API", preload.includes("hermesProviders: async") && preload.includes("/hermes/providers"));
assert("preload exposes Hermes media API", preload.includes("hermesMedia: async") && preload.includes("/hermes/media"));
assert("preload exposes Hermes extensions API", preload.includes("hermesExtensions: async") && preload.includes("/hermes/extensions"));
assert("preload exposes Hermes overview API", preload.includes("hermesOverview: async") && preload.includes("/hermes/overview?"));
assert("preload exposes startup health through canonical apiJson", preload.includes("startupHealth: async") && preload.includes("/health/startup") && preload.includes('apiJson(res, "Startup health not reachable")'));
assert("i18n includes new Hermes/fallback/media/extension labels", deI18n.includes('"dashboard.aiFallback"') && enI18n.includes('"settings.anthropicDesc"') && deI18n.includes('"settings.hermesGatewayAutostart"') && deI18n.includes('"system.hermesCockpitTitle"') && deI18n.includes('"system.hermesCapabilityGaps"') && deI18n.includes('"system.hermesProviders"') && deI18n.includes('"system.hermesMedia"') && deI18n.includes('"system.hermesExtensions"') && deI18n.includes('"system.startupHealthTitle"') && enI18n.includes('"system.startupHealthTitle"') && enI18n.includes('"system.hermesMedia"') && enI18n.includes('"system.hermesExtensions"'));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
