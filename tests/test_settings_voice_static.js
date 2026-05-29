/**
 * Static tests for Settings voice test robustness.
 * Run with: node tests/test_settings_voice_static.js
 */

const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "settings.js"),
  "utf8"
);
const html = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "index.html"),
  "utf8"
);
const viewsCss = [
  fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "css", "views.css"), "utf8"),
  fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "css", "views_settings.css"), "utf8"),
].join("\n");

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

console.log("\nSettings voice:");
const mimeSource = extractFn(src, "settingsPreferredVoiceMimeType");
const testVoiceSource = extractFn(src, "testVoice");
const testMicrophoneSource = extractFn(src, "testMicrophone");
const displayStateSource = extractFn(src, "voiceDiagnosticDisplayState");
const wakeWordOnlySource = extractFn(src, "voiceDiagnosticsWakeWordOnly");
const architectureRowsSource = extractFn(src, "voiceDiagnosticsArchitectureRows");
const changeAiModelSource = extractFn(src, "changeAiModel");
const appendRowSource = extractFn(src, "appendVoiceDiagnosticRow");
const renderDiagnosticsSource = extractFn(src, "renderVoiceDiagnostics");
const runDiagnosticsSource = extractFn(src, "runVoiceDiagnostics");
const runSystemDiagnosticsSource = extractFn(src, "runSystemDiagnostics");
const setupBackupControlsSource = extractFn(src, "setupBackupControls");
const settingsBusySource = extractFn(src, "setSettingsActionBusy");
const settingsActionButtonsBusySource = extractFn(src, "setSettingsActionButtonsBusy");
const settingsLocaleSource = extractFn(src, "settingsLocale");
const settingsFormatDateSource = extractFn(src, "settingsFormatDate");
const settingsFormatDateTimeSource = extractFn(src, "settingsFormatDateTime");
const architectureRows = new Function(`${architectureRowsSource}; return voiceDiagnosticsArchitectureRows;`)();

assert("settings voice test revokes TTS object URLs", testVoiceSource.includes("URL.revokeObjectURL(audioUrl)") && testVoiceSource.includes("audio.onended = revoke"));
assert("settings microphone checks recording support", testMicrophoneSource.includes("typeof MediaRecorder") && testMicrophoneSource.includes("navigator.mediaDevices?.getUserMedia"));
assert("settings microphone chooses supported mime type", mimeSource.includes("MediaRecorder.isTypeSupported") && testMicrophoneSource.includes("settingsPreferredVoiceMimeType()"));
assert("settings microphone records non-empty chunks only", testMicrophoneSource.includes("e.data.size > 0"));
assert("settings microphone posts the actual recorder mime type", testMicrophoneSource.includes("recorder.mimeType || mimeType ||"));
assert("settings microphone stops tracks on startup failure", testMicrophoneSource.includes("if (stream) stream.getTracks().forEach"));
assert("settings refresh renders aggregate voice diagnostics", src.includes("renderVoiceDiagnostics(voice)"));
assert("settings refresh renders voice offline state before backend return", src.includes('if (!LexaState.get("backendOnline")) {') && src.includes('renderVoiceDiagnostics({ ok: false, state: "blocked", summary: "Backend offline.", checks: [] });'));
assert("settings AI model changes block duplicate backend writes and restore select state", src.includes("let _aiModelChangeRunning = false") && changeAiModelSource.includes("if (!modelId || _aiModelChangeRunning) return") && changeAiModelSource.includes('const select = document.getElementById("model-select")') && changeAiModelSource.includes("_aiModelChangeRunning = true") && changeAiModelSource.includes("setSettingsActionBusy(select, true)") && changeAiModelSource.includes("await window.lexa.setAiModel(modelId)") && changeAiModelSource.includes("finally") && changeAiModelSource.includes("_aiModelChangeRunning = false") && changeAiModelSource.includes("setSettingsActionBusy(select, false)"));
assert("settings voice diagnostics uses explicit audio probe", runDiagnosticsSource.includes("window.lexa.voiceDiagnostics(true)"));
assert("settings voice diagnostics blocks duplicate runs and exposes busy state", src.includes("let _voiceDiagnosticsRunning = false") && runDiagnosticsSource.includes("if (_voiceDiagnosticsRunning) return") && runDiagnosticsSource.includes("_voiceDiagnosticsRunning = true") && runDiagnosticsSource.includes("setSettingsActionBusy(btn, true)") && runDiagnosticsSource.includes("_voiceDiagnosticsRunning = false") && runDiagnosticsSource.includes("setSettingsActionBusy(btn, false)") && settingsBusySource.includes('button.setAttribute("aria-busy", busy ? "true" : "false")'));
assert("settings system diagnostics blocks duplicate refreshes and restores action buttons", src.includes("let _systemDiagnosticsRunning = false") && settingsActionButtonsBusySource.includes('document.querySelectorAll(`[data-action="${actionName}"]`)') && settingsActionButtonsBusySource.includes("setSettingsActionBusy(button, busy)") && runSystemDiagnosticsSource.includes("if (_systemDiagnosticsRunning) return") && runSystemDiagnosticsSource.includes("_systemDiagnosticsRunning = true") && runSystemDiagnosticsSource.includes('setSettingsActionButtonsBusy("runSystemDiagnostics", true)') && runSystemDiagnosticsSource.includes("await refreshSettingsView()") && runSystemDiagnosticsSource.includes("finally") && runSystemDiagnosticsSource.includes("_systemDiagnosticsRunning = false") && runSystemDiagnosticsSource.includes('setSettingsActionButtonsBusy("runSystemDiagnostics", false)'));
assert("settings voice diagnostics treats wake-word-only warning as ready", displayStateSource.includes("voiceDiagnosticsWakeWordOnly(diagnostics)") && displayStateSource.includes('return "ready"'));
assert("settings voice diagnostics isolates wake-word-only warning", wakeWordOnlySource.includes('problemChecks.length === 1') && wakeWordOnlySource.includes('problemChecks[0]?.id === "wakeword"'));
assert("settings voice diagnostics explains wake word inactive separately", renderDiagnosticsSource.includes("Voice core ready. Wake Word ist ausgeschaltet."));
assert("settings voice diagnostics renders checks with DOM nodes", appendRowSource.includes("document.createElement") && renderDiagnosticsSource.includes("replaceChildren()"));
assert("settings voice diagnostics renders checks through shared row helper", appendRowSource.includes("document.createElement") && renderDiagnosticsSource.includes("appendVoiceDiagnosticRow(panelEl, check)"));
assert("settings voice diagnostics shows voice architecture hints", architectureRowsSource.includes("wake_engine") && architectureRowsSource.includes("Realtime provider") && renderDiagnosticsSource.includes("voiceDiagnosticsArchitectureRows(diagnostics)"));
const sampleArchitectureRows = architectureRows({
  wakeword: {
    wake_engine: { name: "legacy_transcript_phrase_match", local: false, legacy: true, uses_stt: true, ready: true },
    fallback_stt_min_interval_s: 2,
    fallback_stt_max_interval_s: 6,
    fallback_stt_interval_s: 3.5,
  },
  realtime: {
    preferred: "openai_realtime",
    configured: true,
    runtime_requested: false,
    runtime_implemented: false,
    runtime_active: false,
    ready: false,
    active_path: "cascaded_stt_llm_tts",
    next_action: "Keep using cascaded voice or enable realtime after transport implementation.",
  },
  realtime_preflight: {
    can_start: false,
    blockers: ["Realtime audio transport is not implemented yet."],
    warnings: [],
  },
});
assert("settings voice diagnostics builds wake-engine architecture row", sampleArchitectureRows.some((row) => row.id === "wake-engine" && row.detail.includes("legacy") && row.detail.includes("3.5s") && row.detail.includes("max 6s")));
assert("settings voice diagnostics builds realtime architecture row", sampleArchitectureRows.some((row) => row.id === "realtime-provider" && row.detail.includes("openai_realtime configured") && row.detail.includes("runtime off") && row.detail.includes("cascaded_stt_llm_tts active") && row.detail.includes("blocker: Realtime audio transport is not implemented yet.") && row.detail.includes("Keep using cascaded voice")));
assert("settings active TTS status follows the actual engine", src.includes("ttsProviderLabels") && src.includes("voice.tts?.engine") && src.includes("gpt-4o-mini-tts"));
assert("settings TTS copy no longer claims Cartesia is primary", html.includes("TTS PROVIDER") && html.includes("OpenAI prim") && html.includes("OpenAI/ElevenLabs/Cartesia/SAPI") && !html.includes("CARTESIA SONIC (Primary TTS)"));
assert("settings voice diagnostics clips visible error text", renderDiagnosticsSource.includes("settingsClip(") && runDiagnosticsSource.includes("settingsClip("));
assert("settings page exposes voice diagnostics action", html.includes('id="voice-diagnostics-panel"') && html.includes('data-action="runVoiceDiagnostics"'));
assert("settings backup and index actions block duplicate runs", setupBackupControlsSource.includes('btnCreate.getAttribute("aria-busy") === "true"') && setupBackupControlsSource.includes("setSettingsActionBusy(btnCreate, true)") && setupBackupControlsSource.includes("setSettingsActionBusy(btnCreate, false)") && setupBackupControlsSource.includes('btnList.getAttribute("aria-busy") === "true"') && setupBackupControlsSource.includes("setSettingsActionBusy(btnList, true)") && setupBackupControlsSource.includes("setSettingsActionBusy(btnList, false)") && setupBackupControlsSource.includes('restoreBtn.getAttribute("aria-busy") === "true"') && setupBackupControlsSource.includes("setSettingsActionBusy(restoreBtn, true)") && setupBackupControlsSource.includes("setSettingsActionBusy(restoreBtn, false)") && setupBackupControlsSource.includes('btnFts.getAttribute("aria-busy") === "true"') && setupBackupControlsSource.includes("setSettingsActionBusy(btnFts, true)") && setupBackupControlsSource.includes("setSettingsActionBusy(btnFts, false)"));
assert("settings CSS includes voice diagnostics states", viewsCss.includes(".voice-diagnostics-panel") && viewsCss.includes(".voice-diagnostic-check.blocked"));
assert("settings dates follow the active app locale", settingsLocaleSource.includes("t?._locale") && settingsLocaleSource.includes('return "en-US"') && settingsFormatDateSource.includes("toLocaleDateString(settingsLocale())") && settingsFormatDateTimeSource.includes("toLocaleString(settingsLocale())") && src.includes("settingsFormatDate(lic.expires)") && src.includes("settingsFormatDateTime(b.created)") && !src.includes("toLocaleDateString(\"de-DE\")") && !src.includes("toLocaleString('de-DE')"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
