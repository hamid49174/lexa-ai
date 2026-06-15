/* ════════════════════════════════════════════════
   LEXA AI — Settings Module
   Settings view, Theme/Accent/Font preferences,
   Voice settings (TTS + STT), Backup management,
   Profile saving
   Extracted from tools.js
   ════════════════════════════════════════════════ */

function translateDiagnosticsText(text) {
  if (!text) return "";
  try {
    if (typeof t !== "undefined" && t._locale && t._locale.startsWith("en")) {
      return text;
    }
  } catch (_) {}
  const mappings = {
    // Labels
    "Missing tool": "Fehlendes Tool",
    "Voice check": "Voice-Check",
    "Wake engine": "Wake-Engine",
    "Realtime provider": "Echtzeit-Provider",
    "Backend": "Backend",
    "AI providers": "KI-Provider",
    "Hermes": "Hermes",
    "Voice path": "Sprachpfad",
    "Memory store": "Speicher",
    "Local tools": "Lokale Tools",
    "MCP": "MCP-Server",
    "Signal": "Signal",
    "Tooling": "Werkzeuge",

    // Details & Status summaries
    "Voice stack is ready.": "Sprach-Stack ist bereit.",
    "Voice stack is usable but needs attention.": "Sprach-Stack ist nutzbar, benötigt aber Aufmerksamkeit.",
    "Voice stack has a blocking issue.": "Sprach-Stack hat ein blockierendes Problem.",
    "Backend offline.": "Backend offline.",
    "Backend healthy.": "Backend gesund."
  };

  if (mappings[text]) return mappings[text];

  let translated = text;
  Object.entries(mappings).forEach(([key, val]) => {
    translated = translated.replaceAll(key, val);
  });
  return translated;
}

let _voiceDiagnosticsRunning = false;
let _systemDiagnosticsRunning = false;
let _aiModelChangeRunning = false;
let _sttModelChangeRunning = false;
let _sttEngineChangeRunning = false;
let _settingsSecretActionRunning = false;
let _licenseActionRunning = false;
let _hermesGatewayAutostartRunning = false;
let _hermesGatewayAutostartLastPayload = null;
let _settingsRefreshSeq = 0;
const SETTINGS_SECRET_ACTIONS = [
  "setDeepgramKey",
  "deleteDeepgramKey",
  "setCartesiaKey",
  "deleteCartesiaKey",
  "elevenlabsKeyAction",
];
const SETTINGS_LICENSE_ACTIONS = [
  "activateLicense",
  "removeLicense",
];

function setSettingsActionBusy(button, busy) {
  if (!button) return;
  button.disabled = Boolean(busy);
  button.setAttribute("aria-busy", busy ? "true" : "false");
}

function setSettingsActionButtonsBusy(actionName, busy) {
  document.querySelectorAll(`[data-action="${actionName}"]`).forEach((button) => {
    setSettingsActionBusy(button, busy);
  });
}

function setSettingsSecretActionsBusy(busy) {
  SETTINGS_SECRET_ACTIONS.forEach((actionName) => setSettingsActionButtonsBusy(actionName, busy));
}

function setSettingsLicenseActionsBusy(busy) {
  SETTINGS_LICENSE_ACTIONS.forEach((actionName) => setSettingsActionButtonsBusy(actionName, busy));
}

async function runSettingsLicenseAction(actionFn) {
  if (_licenseActionRunning) return;
  _licenseActionRunning = true;
  setSettingsLicenseActionsBusy(true);
  try {
    await actionFn();
  } finally {
    _licenseActionRunning = false;
    setSettingsLicenseActionsBusy(false);
  }
}

async function runSettingsSecretAction(actionFn) {
  if (_settingsSecretActionRunning) return;
  _settingsSecretActionRunning = true;
  setSettingsSecretActionsBusy(true);
  try {
    await actionFn();
  } finally {
    _settingsSecretActionRunning = false;
    setSettingsSecretActionsBusy(false);
  }
}

// ── SETTINGS VIEW ────────────────────────────────
async function refreshSettingsView() {
  const requestId = ++_settingsRefreshSeq;
  // Desktop settings (work even when backend is offline)
  try {
    const autostartToggle = document.getElementById("autostart-toggle");
    if (autostartToggle) autostartToggle.checked = window.lexa.getAutostart();
  } catch (e) { console.warn("[Settings] Failed to get autostart status:", e.message || e); }
  const notifToggle = document.getElementById("notifications-toggle");
  if (notifToggle) notifToggle.checked = LexaState.get("notificationsEnabled");

  // License status works offline (reads local file via IPC)
  loadLicenseStatus();

  if (!LexaState.get("backendOnline")) {
    renderVoiceDiagnostics({ ok: false, state: "blocked", summary: "Backend offline.", checks: [] });
    renderHermesGatewayAutostart({ supported: false, enabled: false, can_enable: false, error: "Backend offline." });
    renderSystemReadiness({
      ok: false,
      state: "blocked",
      score: 0,
      summary: "Backend offline. Diagnostics sind erst nach erfolgreicher Verbindung verlässlich.",
      cards: [],
      checks: [{ label: "Backend", state: "blocked", detail: "Lokaler API-Dienst antwortet nicht." }],
    });
    setupHermesGatewayAutostartControls();
    return "blocked";
  }

  const [aiRes, voiceRes, healthRes, memRes, cmdsRes, toolHealthRes, mcpRes, diagnosticsRes, hermesAutostartRes] = await Promise.allSettled([
    window.lexa.aiStatus(),
    window.lexa.voiceStatus(),
    window.lexa.health(),
    window.lexa.memoryStats(),
    window.lexa.commands(),
    window.lexa.healthTools(),
    window.lexa.mcpServers(),
    window.lexa.diagnostics(),
    window.lexa.hermesGatewayAutostartStatus?.(),
  ]);
  if (requestId !== _settingsRefreshSeq || !LexaState.get("backendOnline")) return null;

  const ai = aiRes.status === "fulfilled" ? aiRes.value : { gemini: {} };
  const voice = voiceRes.status === "fulfilled" ? voiceRes.value : { tts: {}, stt: {} };
  const health = healthRes.status === "fulfilled" ? healthRes.value : {};
  const mem = memRes.status === "fulfilled" ? memRes.value : {};
  const toolHealth = toolHealthRes.status === "fulfilled" ? toolHealthRes.value : { tools: {}, available_count: 0, total_count: 0, health_pct: 0 };
  const mcp = mcpRes.status === "fulfilled" ? mcpRes.value : { enabled: false, servers: [] };
  const diagnostics = diagnosticsRes.status === "fulfilled" ? diagnosticsRes.value : {};
  const hermesAutostart = hermesAutostartRes.status === "fulfilled"
    ? hermesAutostartRes.value
    : { supported: false, enabled: false, can_enable: false, error: "Autostart-Status nicht verfügbar." };
  renderVoiceDiagnostics(voice);
  renderHermesGatewayAutostart(hermesAutostart);
  const readinessModel = buildSystemReadinessModel({
    ai,
    voice,
    health,
    mem,
    toolHealth,
    mcp,
    diagnostics,
    commandsTotal: cmdsRes.status === "fulfilled" ? cmdsRes.value.total : 0,
  });
  renderSystemReadiness(readinessModel);

  // Gemini-only: nur der Gemini-Status wird angezeigt.
  const geminiEl = document.getElementById("gemini-status");
  if (geminiEl) { geminiEl.textContent = ai.gemini?.available ? t("settings.connected") : t("settings.offline"); geminiEl.className = "setting-status" + (ai.gemini?.available ? "" : " offline"); }

  // TTS Status — Cartesia (Primary) + ElevenLabs (Fallback)
  const cartesiaStatusEl = document.getElementById("cartesia-status");
  if (cartesiaStatusEl) {
    const ttsEngine = voice.tts?.engine || "unknown";
    const ttsProviderLabels = {
      openai: "OpenAI " + (voice.tts?.openai_model || "gpt-4o-mini-tts"),
      elevenlabs: "ElevenLabs " + (voice.tts?.elevenlabs_model || ""),
      cartesia: "Cartesia " + (voice.tts?.cartesia_model || "sonic-2"),
      sapi: "Windows SAPI",
    };
    const ready = Boolean(voice.tts?.ready || voice.tts?.available);
    cartesiaStatusEl.textContent = ready
      ? ((ttsProviderLabels[ttsEngine] || ttsEngine) + " aktiv")
      : "Nicht konfiguriert";
    cartesiaStatusEl.className = "setting-status" + (ready ? "" : " offline");
  }
  // ElevenLabs-Status (#el-status) wird ausschließlich von loadElevenLabsSettings()
  // gesetzt (drei Zustände, lokalisiert). Kein doppelter Schreibzugriff hier.

  // STT Status — Deepgram (Primary) + Groq (Fallback) + Local
  const sttEl = document.getElementById("stt-status");
  const sttEngine = voice.stt?.engine || "deepgram";
  const sttLabels = { openai: "OpenAI GPT-4o Transcribe", deepgram: "Deepgram Nova-3", groq: "Groq Whisper", local: "Lokal" };
  const sttLabel = sttLabels[sttEngine] || sttEngine;
  if (sttEl) { sttEl.textContent = voice.stt?.ready ? (sttLabel + " aktiv") : "Nicht konfiguriert"; sttEl.className = "setting-status" + (voice.stt?.ready ? "" : " offline"); }
  // Set engine dropdown
  const engineSelect = document.getElementById("stt-engine-select");
  if (engineSelect) engineSelect.value = sttEngine;
  // Show/hide Deepgram key group based on engine
  const dgKeyGroup = document.getElementById("deepgram-key-group");
  if (dgKeyGroup) dgKeyGroup.classList.toggle("hidden", sttEngine !== "deepgram");
  // Update description
  const sttDesc = document.getElementById("stt-model-desc");
  if (sttDesc) {
    const oaiOk = voice.stt?.openai_available ? "OpenAI OK" : "Kein OpenAI Key";
    const dgOk = voice.stt?.deepgram_available ? "Deepgram OK" : "Kein Deepgram Key";
    const groqOk = voice.stt?.groq_available ? "Groq OK" : "Kein Groq Key";
    sttDesc.textContent = oaiOk + " | " + dgOk + " | " + groqOk + " | Engine: " + sttLabel;
  }

  const versionEl = document.getElementById("settings-version");
  if (versionEl && health.version) versionEl.textContent = `v${health.version}`;

  if (cmdsRes.status === "fulfilled") {
    const countEl = document.getElementById("settings-cmd-count");
    if (countEl) countEl.textContent = t("system.registered", {count: cmdsRes.value.total});
  }

  const dbEl = document.getElementById("settings-db-path");
  if (dbEl && mem.db_path) dbEl.textContent = mem.db_path;

  // Load model selection + theme preferences + voice settings
  loadModelSelection();
  loadThemePreferences();
  loadVoiceSettings();
  loadElevenLabsSettings(voice);

  // Wire backup controls
  setupHermesGatewayAutostartControls();
  setupBackupControls();

  return readinessModel.state;
}

// AI model selection uses the guarded renderer bridge; API-key/keyring actions live elsewhere.
async function loadModelSelection() {
  try {
    const data = await window.lexa.aiModels();
    const select = document.getElementById("model-select");
    const desc = document.getElementById("model-desc");
    settingsRenderAiModelSelection(data, select, desc);
  } catch (e) {
    console.warn("[Settings] Failed to load model selection:", e.message || e);
  }
}

async function changeAiModel(modelId) {
  if (!modelId || _aiModelChangeRunning) return;
  const select = document.getElementById("model-select");
  _aiModelChangeRunning = true;
  setSettingsActionBusy(select, true);
  try {
    const result = await window.lexa.setAiModel(modelId);
    showToast(result.status || t("chat.modelChanged"), "success");
    const desc = document.getElementById("model-desc");
    if (desc && result.current) desc.textContent = settingsAiModelDescriptionText(result.current);
  } catch (e) {
    console.warn("[Settings] Failed to change AI model:", e.message || e);
    showToast(t("toast.modelChangeFailed"), "error");
  } finally {
    _aiModelChangeRunning = false;
    setSettingsActionBusy(select, false);
  }
}

function diagnosticsClipLines(value, max = 4) {
  const lines = String(value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  return lines.slice(0, max).join(" ");
}

function diagnosticsBadgeClass(state) {
  const normalized = voiceDiagnosticState({ state });
  return normalized === "blocked" ? "offline" : normalized === "attention" ? "warning" : "";
}

function diagnosticsLabel(state) {
  const normalized = voiceDiagnosticState({ state });
  return normalized === "blocked" ? "BLOCKED" : normalized === "attention" ? "ATTENTION" : "READY";
}

function diagnosticsPct(value, fallback = 0) {
  const numeric = Number.isFinite(Number(value)) ? Number(value) : fallback;
  return Math.max(0, Math.min(100, Math.round(numeric)));
}

function diagnosticsCountWhere(items, predicate) {
  return Array.isArray(items) ? items.filter(predicate).length : 0;
}

function hermesReadinessSignal(diagnostics, health) {
  const full = diagnostics?.hermes && typeof diagnostics.hermes === "object" ? diagnostics.hermes : {};
  const compact = health?.hermes && typeof health.hermes === "object" ? health.hermes : {};
  const rawState = full.health_state || compact.state || "unknown";
  const state = rawState === "ready" ? "ready" : rawState === "blocked" ? "blocked" : "attention";
  const summary = diagnosticsClipLines(full.summary || compact.summary || "Hermes-Status nicht verfügbar.", 2);
  const canRun = Boolean(full.can_run_tasks ?? compact.can_run_tasks);
  const gateway = full.gateway && typeof full.gateway === "object" ? full.gateway : {};
  const telegramConfigured = Boolean(gateway.configured ?? compact.telegram_configured);
  return {
    state,
    summary,
    canRun,
    telegramConfigured,
    checkState: state === "blocked" ? "attention" : state,
  };
}

function readinessSummaryFromState(state, blockers, warnings) {
  if (state === "blocked") {
    return blockers[0] || "Kritische Konfiguration fehlt. Kernpfade sind noch nicht produktionsreif.";
  }
  if (state === "attention") {
    return warnings[0] || "Lexa ist nutzbar, aber mehrere Pfade brauchen noch Härtung oder Konfiguration.";
  }
  return "Kernpfade sind bereit. Backend, Modelle, Voice und lokale Tooling-Signale wirken konsistent.";
}

function buildSystemReadinessModel({ ai, voice, health, mem, toolHealth, mcp, diagnostics, commandsTotal }) {
  const providers = ["gemini"];
  const aiReadyCount = diagnosticsCountWhere(providers, (name) => ai?.[name]?.available);
  const aiReady = aiReadyCount > 0;
  const fallbackAvailable = Array.isArray(ai?.fallback_available) ? ai.fallback_available.length : 0;
  const hermes = hermesReadinessSignal(diagnostics, health);
  const voiceReady = voiceDiagnosticDisplayState(voice) === "ready";
  const voiceAttention = voiceDiagnosticDisplayState(voice) === "attention";
  const toolPct = diagnosticsPct(toolHealth?.health_pct);
  const toolsReady = toolPct >= 60 || (toolHealth?.available_count || 0) >= 5;
  const toolsAttention = toolPct >= 35 && !toolsReady;
  const mcpServers = Array.isArray(mcp?.servers) ? mcp.servers : [];
  const mcpConnected = diagnosticsCountWhere(mcpServers, (server) => server?.connected);
  const mcpConfigured = mcpServers.length;
  const memoryReady = Boolean(mem?.db_path || diagnostics?.db_size_kb >= 0);
  const checks = [];

  checks.push({
    label: "Backend",
    state: health?.status === "ok" ? "ready" : "blocked",
    detail: health?.status === "ok"
      ? `Online, uptime ${health?.uptime || "unknown"}, version ${health?.version || "unknown"}`
      : "Health endpoint meldet keinen OK-Zustand.",
  });
  checks.push({
    label: "AI providers",
    state: aiReady ? "ready" : "blocked",
    detail: `${aiReadyCount}/${providers.length} Provider verfügbar. Aktiv: ${ai?.active_provider || ai?.selected_provider || "unknown"}. Fallbacks: ${fallbackAvailable}.`,
  });
  checks.push({
    label: "Hermes",
    state: hermes.checkState,
    detail: `${hermes.summary} Tasks: ${hermes.canRun ? "bereit" : "nicht bereit"}. Telegram: ${hermes.telegramConfigured ? "konfiguriert" : "offen"}.`,
  });
  checks.push({
    label: "Voice path",
    state: voiceReady ? "ready" : voiceAttention ? "attention" : "blocked",
    detail: diagnosticsClipLines(voice?.summary || voice?.error || "Voice-Status nicht verfügbar."),
  });
  checks.push({
    label: "Memory store",
    state: memoryReady ? "ready" : "blocked",
    detail: `DB ${diagnostics?.db_size_kb ?? "?"} KB, ${mem?.conversations || 0} Chats, ${mem?.memories || 0} Memories.`,
  });
  checks.push({
    label: "Local tools",
    state: toolsReady ? "ready" : toolsAttention ? "attention" : "blocked",
    detail: `${toolHealth?.available_count || 0}/${toolHealth?.total_count || 0} Tools verfügbar (${toolPct}%).`,
  });
  checks.push({
    label: "MCP",
    state: mcpConfigured === 0 ? "attention" : mcpConnected > 0 ? "ready" : "attention",
    detail: mcpConfigured === 0
      ? "Keine MCP-Server konfiguriert."
      : `${mcpConnected}/${mcpConfigured} MCP-Server verbunden.`,
  });

  const blockers = checks.filter((check) => voiceDiagnosticState({ state: check.state }) === "blocked").map((check) => `${check.label}: ${check.detail}`);
  const warnings = checks.filter((check) => voiceDiagnosticState({ state: check.state }) === "attention").map((check) => `${check.label}: ${check.detail}`);
  const scoreParts = [
    health?.status === "ok" ? 22 : 0,
    aiReadyCount * 10,
    hermes.state === "ready" ? 8 : hermes.state === "attention" ? 4 : 2,
    voiceReady ? 20 : voiceAttention ? 10 : 0,
    toolsReady ? 18 : toolsAttention ? 8 : 0,
    memoryReady ? 12 : 0,
    mcpConnected > 0 ? 10 : mcpConfigured > 0 ? 6 : 3,
    commandsTotal > 0 ? 8 : 0,
  ];
  const score = Math.max(0, Math.min(100, scoreParts.reduce((sum, part) => sum + part, 0)));
  const state = blockers.length > 0 ? "blocked" : warnings.length > 0 ? "attention" : "ready";

  const cards = [
    {
      label: "Backend",
      value: health?.status === "ok" ? "Online" : "Offline",
      meta: health?.uptime ? `Uptime ${health.uptime}` : "No uptime",
      state: health?.status === "ok" ? "ready" : "blocked",
    },
    {
      label: "AI",
      value: `${aiReadyCount}/${providers.length}`,
      meta: ai?.active_provider ? `Aktiv ${ai.active_provider}, Fallbacks ${fallbackAvailable}` : "Kein aktiver Provider",
      state: aiReady ? "ready" : "blocked",
    },
    {
      label: "Hermes",
      value: diagnosticsLabel(hermes.state),
      meta: hermes.summary,
      state: hermes.state,
    },
    {
      label: "Voice",
      value: diagnosticsLabel(voiceDiagnosticDisplayState(voice)),
      meta: diagnosticsClipLines(voice?.summary || "Voice status fehlt.", 2),
      state: voiceDiagnosticDisplayState(voice),
    },
    {
      label: "Tooling",
      value: `${toolPct}%`,
      meta: `${toolHealth?.available_count || 0}/${toolHealth?.total_count || 0} lokal verfügbar`,
      state: toolsReady ? "ready" : toolsAttention ? "attention" : "blocked",
    },
    {
      label: "MCP",
      value: mcpConfigured ? `${mcpConnected}/${mcpConfigured}` : "0",
      meta: mcpConfigured ? "verbunden/konfiguriert" : "nicht eingerichtet",
      state: mcpConfigured === 0 ? "attention" : mcpConnected > 0 ? "ready" : "attention",
    },
    {
      label: "Commands",
      value: String(commandsTotal || 0),
      meta: "registrierte Systemaktionen",
      state: commandsTotal > 0 ? "ready" : "blocked",
    },
  ];

  const missingToolNames = Object.entries(toolHealth?.tools || {})
    .filter(([, status]) => !status?.available)
    .slice(0, 4)
    .map(([name, status]) => `${name}: ${status?.note || "not available"}`);
  missingToolNames.forEach((detail) => {
    checks.push({ label: "Missing tool", state: "attention", detail });
  });

  return {
    ok: state === "ready",
    state,
    score,
    summary: readinessSummaryFromState(state, blockers, warnings),
    cards,
    checks,
  };
}

function renderSystemReadiness(model) {
  const scoreEl = document.getElementById("readiness-score");
  const statusEl = document.getElementById("readiness-status");
  const summaryEl = document.getElementById("readiness-summary");
  const gridEl = document.getElementById("readiness-grid");
  const checksEl = document.getElementById("readiness-checks");

  if (scoreEl) scoreEl.textContent = `${diagnosticsPct(model?.score)}%`;
  if (statusEl) {
    statusEl.textContent = diagnosticsLabel(model?.state);
    statusEl.className = "setting-status " + diagnosticsBadgeClass(model?.state);
  }
  if (summaryEl) summaryEl.textContent = settingsClip(model?.summary || "Diagnostics nicht verfügbar.", 220);

  if (gridEl) {
    gridEl.replaceChildren();
    (model?.cards || []).forEach((card) => {
      const item = document.createElement("div");
      item.className = "readiness-card";

      const head = document.createElement("div");
      head.className = "readiness-card-head";
      const label = document.createElement("span");
      label.className = "readiness-card-label";
      label.textContent = translateDiagnosticsText(card.label || "Signal");
      const pill = document.createElement("span");
      pill.className = "readiness-pill " + (voiceDiagnosticState({ state: card.state }) === "blocked" ? "blocked" : voiceDiagnosticState({ state: card.state }) === "attention" ? "warn" : "ok");
      pill.textContent = diagnosticsLabel(card.state);
      head.appendChild(label);
      head.appendChild(pill);

      const value = document.createElement("div");
      value.className = "readiness-card-value";
      value.textContent = translateDiagnosticsText(settingsClip(card.value || "--", 36));

      const meta = document.createElement("div");
      meta.className = "readiness-card-meta";
      meta.textContent = translateDiagnosticsText(settingsClip(card.meta || "", 120));

      item.appendChild(head);
      item.appendChild(value);
      item.appendChild(meta);
      gridEl.appendChild(item);
    });
  }

  if (checksEl) {
    checksEl.replaceChildren();
    (model?.checks || []).forEach((check) => {
      appendVoiceDiagnosticRow(checksEl, check);
    });
  }
}

function normalizeHermesGatewayAutostart(payload) {
  const status = payload?.autostart && typeof payload.autostart === "object" ? payload.autostart : (payload || {});
  return {
    supported: Boolean(status.supported),
    enabled: Boolean(status.enabled),
    canEnable: Boolean(status.can_enable),
    missing: Array.isArray(status.missing) ? status.missing : [],
    nextAction: status.nextAction || payload?.error || status.error || "",
    path: status.startup_path || "",
  };
}

function renderHermesGatewayAutostart(payload) {
  _hermesGatewayAutostartLastPayload = payload;
  const state = normalizeHermesGatewayAutostart(payload);
  const statusEl = document.getElementById("hermes-gateway-autostart-status");
  const toggle = document.getElementById("hermes-gateway-autostart-toggle");
  const canToggle = state.supported && (state.enabled || state.canEnable);
  const title = state.nextAction || state.path || (state.missing.length ? state.missing.join(", ") : "");

  if (toggle) {
    toggle.checked = state.enabled;
    toggle.disabled = _hermesGatewayAutostartRunning || !canToggle;
    toggle.title = title;
    toggle.setAttribute("aria-disabled", toggle.disabled ? "true" : "false");
    if (_hermesGatewayAutostartRunning) toggle.setAttribute("aria-busy", "true");
    else toggle.removeAttribute("aria-busy");
  }

  if (statusEl) {
    if (!state.supported) {
      statusEl.textContent = t("settings.unsupported");
      statusEl.className = "setting-status offline";
    } else if (state.enabled) {
      statusEl.textContent = t("settings.enabled");
      statusEl.className = "setting-status";
    } else if (state.canEnable) {
      statusEl.textContent = t("settings.ready");
      statusEl.className = "setting-status warning";
    } else {
      statusEl.textContent = t("settings.blocked");
      statusEl.className = "setting-status offline";
    }
    statusEl.title = title;
  }
}

function setupHermesGatewayAutostartControls() {
  const toggle = document.getElementById("hermes-gateway-autostart-toggle");
  if (!toggle || toggle._lexaHermesGatewayBound) return;
  toggle._lexaHermesGatewayBound = true;
  toggle.addEventListener("change", () => {
    toggleHermesGatewayAutostart(toggle.checked);
  });
}

async function toggleHermesGatewayAutostart(enabled) {
  const toggle = document.getElementById("hermes-gateway-autostart-toggle");
  const previous = !Boolean(enabled);
  if (_hermesGatewayAutostartRunning) {
    if (toggle) toggle.checked = previous;
    return;
  }
  if (!LexaState.get("backendOnline") || !window.lexa?.hermesGatewayAutostartSet) {
    if (toggle) toggle.checked = previous;
    renderHermesGatewayAutostart({ supported: false, enabled: false, can_enable: false, error: "Backend offline." });
    showToast(t("settings.hermesGatewayAutostartBlocked"), "error");
    return;
  }

  _hermesGatewayAutostartRunning = true;
  if (toggle) {
    toggle.disabled = true;
    toggle.setAttribute("aria-disabled", "true");
    toggle.setAttribute("aria-busy", "true");
  }
  try {
    const result = await window.lexa.hermesGatewayAutostartSet(Boolean(enabled));
    renderHermesGatewayAutostart(result?.autostart || result);
    if (result?.success) {
      showToast(enabled ? t("settings.hermesGatewayAutostartOn") : t("settings.hermesGatewayAutostartOff"), enabled ? "success" : "info");
    } else {
      showToast(settingsClip(result?.error || result?.autostart?.nextAction || t("settings.errorGeneric"), 160), "error");
    }
  } catch (e) {
    if (toggle) toggle.checked = previous;
    showToast(t("settings.errorPrefix", {message: e.message || e}), "error");
    try {
      renderHermesGatewayAutostart(await window.lexa.hermesGatewayAutostartStatus?.());
    } catch (_) {}
  } finally {
    _hermesGatewayAutostartRunning = false;
    if (_hermesGatewayAutostartLastPayload) renderHermesGatewayAutostart(_hermesGatewayAutostartLastPayload);
    else if (toggle) {
      toggle.disabled = false;
      toggle.setAttribute("aria-disabled", "false");
      toggle.removeAttribute("aria-busy");
    }
  }
}

async function runSystemDiagnostics() {
  if (_systemDiagnosticsRunning) return;
  if (!LexaState.get("backendOnline")) {
    renderSystemReadiness({
      ok: false,
      state: "blocked",
      score: 0,
      summary: "Backend offline. Diagnostics konnten nicht aktualisiert werden.",
      cards: [],
      checks: [{ label: "Backend", state: "blocked", detail: "Lokaler API-Dienst antwortet nicht." }],
    });
    showToast("Diagnostics: Backend offline", "error");
    return;
  }

  _systemDiagnosticsRunning = true;
  setSettingsActionButtonsBusy("runSystemDiagnostics", true);
  showToast("System Diagnostics laufen...", "info");
  try {
    // Status direkt aus dem berechneten Readiness-Modell verwenden, nicht aus
    // dem (englisch-/locale-abhaengigen) gerenderten Text auslesen.
    const state = await refreshSettingsView();
    if (state === "ready") showToast("System Readiness ist grün.", "success");
    else if (state === "attention") showToast("System Readiness braucht Aufmerksamkeit.", "warning", 5000);
    else showToast("System Readiness ist blockiert.", "error", 6000);
  } catch (e) {
    showToast(t("settings.errorPrefix", {message: e.message || e}), "error");
  } finally {
    _systemDiagnosticsRunning = false;
    setSettingsActionButtonsBusy("runSystemDiagnostics", false);
  }
}

function settingsClip(value, max = 180) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return text.slice(0, Math.max(0, max - 12)).trimEnd() + " [truncated]";
}

function settingsLocale() {
  try {
    if (t?._locale) return t._locale;
    if (typeof LexaI18n !== "undefined" && LexaI18n.getCurrentLanguage?.() === "en") return "en-US";
  } catch (_) {}
  return "de-DE";
}

function settingsFormatDate(value) {
  return value ? new Date(value).toLocaleDateString(settingsLocale()) : "\u2014";
}

function settingsFormatDateTime(value) {
  return value ? new Date(value).toLocaleString(settingsLocale()) : "";
}

function voiceDiagnosticState(payload) {
  const raw = String(payload?.state || (payload?.ok ? "ready" : "blocked")).toLowerCase();
  if (raw === "ready" || raw === "ok") return "ready";
  if (raw === "attention" || raw === "warn" || raw === "warning") return "attention";
  return "blocked";
}

function voiceDiagnosticsChecks(diagnostics) {
  return Array.isArray(diagnostics?.checks) ? diagnostics.checks : [];
}

function voiceDiagnosticsWakeWordOnly(diagnostics) {
  const checks = voiceDiagnosticsChecks(diagnostics);
  if (!checks.length) return false;
  const problemChecks = checks.filter((check) => check?.state && check.state !== "ok");
  return problemChecks.length === 1
    && problemChecks[0]?.id === "wakeword"
    && problemChecks[0]?.state === "warn"
    && !diagnostics?.wakeword?.error;
}

function voiceDiagnosticDisplayState(diagnostics) {
  const state = voiceDiagnosticState(diagnostics);
  if (state === "attention" && voiceDiagnosticsWakeWordOnly(diagnostics)) return "ready";
  return state;
}

function voiceDiagnosticsArchitectureRows(diagnostics) {
  const rows = [];
  const wakeEngine = diagnostics?.wakeword?.wake_engine || diagnostics?.active_wakeword;
  if (wakeEngine?.name) {
    const localState = wakeEngine.local ? "local" : (wakeEngine.legacy ? "legacy" : "not ready");
    const throttle = diagnostics?.wakeword?.fallback_stt_interval_s
      || diagnostics?.wakeword?.fallback_stt_min_interval_s;
    const maxThrottle = diagnostics?.wakeword?.fallback_stt_max_interval_s;
    const throttleText = wakeEngine.uses_stt && throttle
      ? `, STT cadence ${throttle}s${maxThrottle ? ` max ${maxThrottle}s` : ""}`
      : "";
    rows.push({
      id: "wake-engine",
      label: "Wake engine",
      state: wakeEngine.ready === false ? (wakeEngine.legacy ? "warn" : "blocked") : "ok",
      detail: `${wakeEngine.name} (${localState}${throttleText})`,
    });
  }

  const realtime = diagnostics?.realtime;
  if (realtime?.preferred) {
    const preflight = diagnostics?.realtime_preflight || {};
    const blockers = Array.isArray(preflight.blockers) ? preflight.blockers : [];
    const warnings = Array.isArray(preflight.warnings) ? preflight.warnings : [];
    const preflightNote = blockers.length
      ? `; blocker: ${blockers[0]}`
      : warnings.length ? `; warning: ${warnings[0]}` : "";
    const runtimeGate = realtime.runtime_requested
      ? (realtime.runtime_implemented ? "runtime requested" : "runtime pending")
      : "runtime off";
    const realtimeDetail = realtime.runtime_active
      ? `${realtime.active_path || realtime.preferred} active`
      : realtime.configured
        ? `${realtime.preferred} configured, ${runtimeGate}, ${realtime.active_path || "cascaded fallback"} active`
        : "Cascaded fallback active";
    rows.push({
      id: "realtime-provider",
      label: "Realtime provider",
      state: realtime.configured || realtime.runtime_active ? "ok" : "warn",
      detail: realtime.next_action ? `${realtimeDetail}${preflightNote}; ${realtime.next_action}` : `${realtimeDetail}${preflightNote}`,
    });
  }
  return rows;
}

function appendVoiceDiagnosticRow(panelEl, check) {
  const checkState = voiceDiagnosticState({ state: check?.state === "ok" ? "ready" : check?.state });
  const row = document.createElement("div");
  row.className = "voice-diagnostic-check " + (checkState === "attention" ? "warn" : checkState === "blocked" ? "blocked" : "ok");

  const title = document.createElement("div");
  title.className = "voice-diagnostic-check-title";
  title.textContent = translateDiagnosticsText(settingsClip(check?.label || check?.id || "Voice check", 48));
  row.appendChild(title);

  const detail = document.createElement("div");
  detail.className = "voice-diagnostic-check-detail";
  detail.textContent = translateDiagnosticsText(settingsClip(check?.detail || check?.state || "", 160));
  row.appendChild(detail);

  panelEl.appendChild(row);
}

function renderVoiceDiagnostics(diagnostics) {
  const statusEl = document.getElementById("voice-diagnostics-status");
  const summaryEl = document.getElementById("voice-diagnostics-summary");
  const panelEl = document.getElementById("voice-diagnostics-panel");
  if (!statusEl && !summaryEl && !panelEl) return;

  const state = voiceDiagnosticDisplayState(diagnostics);
  const label = state === "ready" ? "READY" : state === "attention" ? "ATTENTION" : "BLOCKED";
  if (statusEl) {
    statusEl.textContent = label;
    statusEl.className = "setting-status" + (state === "blocked" ? " offline" : state === "attention" ? " warning" : "");
  }
  if (summaryEl) {
    const summary = voiceDiagnosticsWakeWordOnly(diagnostics)
      ? "Voice core ready. Wake Word ist ausgeschaltet."
      : diagnostics?.summary || diagnostics?.error || "Voice-Status nicht verfügbar.";
    summaryEl.textContent = settingsClip(summary);
  }
  if (!panelEl) return;

  panelEl.replaceChildren();
  const checks = voiceDiagnosticsChecks(diagnostics);
  checks.forEach((check) => appendVoiceDiagnosticRow(panelEl, check));
  voiceDiagnosticsArchitectureRows(diagnostics)
    .forEach((check) => appendVoiceDiagnosticRow(panelEl, check));
}

async function runVoiceDiagnostics() {
  if (_voiceDiagnosticsRunning) return;
  if (!LexaState.get("backendOnline")) {
    const offline = { ok: false, state: "blocked", summary: "Backend offline.", checks: [] };
    renderVoiceDiagnostics(offline);
    showToast("Voice Diagnostics: Backend offline", "error");
    return;
  }

  const btn = document.querySelector('[data-action="runVoiceDiagnostics"]');
  _voiceDiagnosticsRunning = true;
  setSettingsActionBusy(btn, true);
  showToast("Voice Diagnostics laufen...", "info");
  try {
    const diagnostics = typeof window.lexa.voiceDiagnostics === "function"
      ? await window.lexa.voiceDiagnostics(true)
      : await window.lexa.voiceStatus();
    renderVoiceDiagnostics(diagnostics);
    const state = voiceDiagnosticDisplayState(diagnostics);
    if (state === "ready") {
      showToast("Voice ist bereit.", "success");
    } else if (state === "attention") {
      showToast("Voice braucht Aufmerksamkeit: " + settingsClip(diagnostics?.summary || diagnostics?.error, 120), "warning", 5000);
    } else {
      showToast("Voice blockiert: " + settingsClip(diagnostics?.summary || diagnostics?.error, 120), "error", 6000);
    }
  } catch (e) {
    const error = e.message || String(e);
    renderVoiceDiagnostics({ ok: false, state: "blocked", summary: error, checks: [] });
    showToast("Voice Diagnostics Fehler: " + settingsClip(error, 120), "error");
  } finally {
    _voiceDiagnosticsRunning = false;
    setSettingsActionBusy(btn, false);
  }
}

// ── BACKUP MANAGEMENT (Settings) ─────────────────
function setupBackupControls() {
  // Backup create
  const btnCreate = document.getElementById('btn-backup-create');
  if (btnCreate && !btnCreate._lexaBound) {
    btnCreate._lexaBound = true;
    btnCreate.addEventListener('click', async () => {
      if (btnCreate.disabled || btnCreate.getAttribute("aria-busy") === "true") return;
      setSettingsActionBusy(btnCreate, true);
      showToast(t("settings.backupCreating"), 'info');
      try {
        const result = await window.lexa.backupCreateDb();
        showToast(t("settings.backupCreated", {path: result.path || 'OK'}), 'success');
      } catch (e) {
        showToast(t("settings.backupFailed", {error: e.message}), 'error');
      } finally {
        setSettingsActionBusy(btnCreate, false);
      }
    });
  }

  // List backups
  const btnList = document.getElementById('btn-backup-list');
  if (btnList && !btnList._lexaBound) {
    btnList._lexaBound = true;
    btnList.addEventListener('click', async () => {
      if (btnList.disabled || btnList.getAttribute("aria-busy") === "true") return;
      const container = document.getElementById('backup-list-container');
      if (!container) return;
      setSettingsActionBusy(btnList, true);
      container.replaceChildren(createLoadingState(t("settings.backupsLoading")));
      try {
        const data = await window.lexa.backupListDb();
        if (!data.backups || data.backups.length === 0) {
          container.replaceChildren(createEmptyState('\u{1F4E6}', t("settings.noBackupsTitle"), t("settings.noBackupsHint")));
          return;
        }
        const list = document.createElement('div');
        list.className = 'backup-list';
        data.backups.forEach(b => {
          const item = document.createElement('div');
          item.className = 'backup-item';

          const nameSpan = document.createElement('span');
          nameSpan.className = 'backup-name';
          nameSpan.textContent = b.filename || b.path;
          item.appendChild(nameSpan);

          const metaSpan = document.createElement('span');
          metaSpan.className = 'backup-meta';
          metaSpan.textContent = `${b.size_mb || '?'} MB \u2014 ${settingsFormatDateTime(b.created)}`;
          item.appendChild(metaSpan);

          const restoreBtn = document.createElement('button');
          restoreBtn.type = 'button';
          restoreBtn.className = 'btn-small';
          restoreBtn.textContent = t("settings.restoreBtn");
          restoreBtn.addEventListener('click', async () => {
            if (restoreBtn.disabled || restoreBtn.getAttribute("aria-busy") === "true") return;
            setSettingsActionBusy(restoreBtn, true);
            const fname = b.filename || b.path;
            try {
              const result = await showInputModal(t("common.confirm"), [
                { name: "confirm", label: t("settings.restoreConfirm", {name: fname}), type: "text", required: true }
              ], t("common.confirm"));
              if (!result || result.confirm.toLowerCase() !== "ja") return;
              showToast(t("settings.restoreRunning"), 'info');
              const res = await window.lexa.backupRestoreDb(b.path);
              showToast(res.result || t("settings.restoreRunning"), 'success');
            } catch (e) {
              showToast(t("settings.restoreFailed", {error: e.message}), 'error');
            } finally {
              setSettingsActionBusy(restoreBtn, false);
            }
          });
          item.appendChild(restoreBtn);
          list.appendChild(item);
        });
        container.replaceChildren(list);
      } catch (e) {
        container.replaceChildren(createErrorState(t("settings.backupsLoadError")));
      } finally {
        setSettingsActionBusy(btnList, false);
      }
    });
  }

  // Rebuild FTS index
  const btnFts = document.getElementById('btn-fts-rebuild');
  if (btnFts && !btnFts._lexaBound) {
    btnFts._lexaBound = true;
    btnFts.addEventListener('click', async () => {
      if (btnFts.disabled || btnFts.getAttribute("aria-busy") === "true") return;
      setSettingsActionBusy(btnFts, true);
      showToast(t("settings.ftsRebuilding"), 'info');
      try {
        await window.lexa.rebuildFts();
        showToast(t("settings.ftsRebuilt"), 'success');
      } catch (e) {
        showToast(t("common.error") + ': ' + e.message, 'error');
      } finally {
        setSettingsActionBusy(btnFts, false);
      }
    });
  }
}

// ── VOICE SETTINGS (STT only — TTS is ElevenLabs in its own section) ──
async function loadVoiceSettings() {
  // Load STT models
  try {
    const { models } = await window.lexa.sttModels();
    const select = document.getElementById("stt-model-select");
    if (select && models && models.length) {
      select.replaceChildren();
      models.forEach(m => {
        const opt = document.createElement("option");
        opt.value = m.name;
        opt.textContent = `${m.name} — ${m.quality} (${m.size_mb} MB, ${m.speed})`;
        if (m.active) opt.selected = true;
        select.appendChild(opt);
      });
      const active = models.find(m => m.active);
      const desc = document.getElementById("stt-model-desc");
      if (desc && active) desc.textContent = active.desc;
    }
  } catch (e) { console.warn("[Settings] Failed to load STT models:", e.message || e); }
}

async function changeSttModel(modelName) {
  if (!modelName || _sttModelChangeRunning) return;
  const select = document.getElementById("stt-model-select");
  _sttModelChangeRunning = true;
  setSettingsActionBusy(select, true);
  try {
    showToast(t("settings.sttModelChanged", {model: modelName}), "info");
    const result = await window.lexa.sttSetModel(modelName);
    if (result.success) {
      showToast(t("settings.sttModelSet", {model: modelName}), "success");
      const desc = document.getElementById("stt-model-desc");
      if (desc && result.info) desc.textContent = result.info.desc;
    } else {
      showToast(result.error || t("common.error"), "error");
    }
  } catch (e) {
    showToast(t("common.error") + ": " + e.message, "error");
  } finally {
    _sttModelChangeRunning = false;
    setSettingsActionBusy(select, false);
  }
}

// ── DEEPGRAM + STT ENGINE ────────────────────────
async function changeSttEngine(engine) {
  if (!engine || _sttEngineChangeRunning) return;
  const select = document.getElementById("stt-engine-select");
  _sttEngineChangeRunning = true;
  setSettingsActionBusy(select, true);
  try {
    const res = await window.lexa.sttSetEngine(engine);
    if (res.success) {
      const engineLabel = engine === "openai" ? "OpenAI GPT-4o Transcribe" : engine === "deepgram" ? "Deepgram Nova-3" : engine === "groq" ? "Groq Whisper" : "Lokal";
      showToast(t("settings.sttEngineToast", {engine: engineLabel}), "success");
      // Show/hide Deepgram key group
      const dgKeyGroup = document.getElementById("deepgram-key-group");
      if (dgKeyGroup) dgKeyGroup.classList.toggle("hidden", engine !== "deepgram");
    } else {
      showToast(res.error || t("settings.errorGeneric"), "error");
    }
  } catch (e) {
    showToast(t("settings.errorPrefix", {message: e.message}), "error");
  } finally {
    _sttEngineChangeRunning = false;
    setSettingsActionBusy(select, false);
  }
}

async function setDeepgramKeyAction() {
  await runSettingsSecretAction(async () => {
    const result = await showInputModal(t("settings.deepgramTitle"), [
      { name: "apiKey", label: t("settings.deepgramKeyLabel"), type: "text", required: true }
    ], t("common.save"));
    if (!result || !result.apiKey) return;

    try {
      const res = await window.lexa.deepgramSetKey(result.apiKey);
      if (res.success) {
        showToast(t("settings.deepgramKeySaved"), "success");
        await refreshSettingsView();
      } else {
        showToast(res.error || t("settings.errorGeneric"), "error");
      }
    } catch (e) { showToast(t("settings.errorPrefix", {message: e.message}), "error"); }
  });
}

async function deleteDeepgramKeyAction() {
  await runSettingsSecretAction(async () => {
    try {
      const res = await window.lexa.deepgramDeleteKey();
      if (res.success) {
        showToast(t("settings.deepgramKeyRemoved"), "info");
        await refreshSettingsView();
      }
    } catch (e) { showToast(t("settings.errorPrefix", {message: e.message}), "error"); }
  });
}

// ── CARTESIA SETTINGS ───────────────────────────

async function setCartesiaKeyAction() {
  await runSettingsSecretAction(async () => {
    const result = await showInputModal("Cartesia API Key", [
      { name: "apiKey", label: "API Key (sk_car_...)", type: "text", required: true }
    ], "Speichern");
    if (!result || !result.apiKey) return;

    try {
      const res = await window.lexa.cartesiaSetKey(result.apiKey);
      if (res.success) {
        showToast("Cartesia Key gespeichert", "success");
        await refreshSettingsView();
      } else {
        showToast(res.error || "Fehler beim Speichern", "error");
      }
    } catch (e) { showToast("Fehler: " + e.message, "error"); }
  });
}

async function deleteCartesiaKeyAction() {
  await runSettingsSecretAction(async () => {
    try {
      const res = await window.lexa.cartesiaDeleteKey();
      if (res.success) {
        showToast("Cartesia Key entfernt", "info");
        await refreshSettingsView();
      }
    } catch (e) { showToast("Fehler: " + e.message, "error"); }
  });
}

// ── ELEVENLABS SETTINGS ─────────────────────────
async function loadElevenLabsSettings(voice) {
  const tts = voice?.tts || {};

  // Status
  const statusEl = document.getElementById("el-status");
  if (statusEl) {
    if (tts.elevenlabs_available) {
      statusEl.textContent = t("settings.elStatusActive");
      statusEl.className = "setting-status";
    } else if (tts.elevenlabs_has_key) {
      statusEl.textContent = t("settings.elStatusDisabled");
      statusEl.className = "setting-status offline";
    } else {
      statusEl.textContent = t("settings.elStatusNoKey");
      statusEl.className = "setting-status offline";
    }
  }

  // Key button text
  const keyBtn = document.getElementById("el-key-btn");
  const keyDesc = document.getElementById("el-key-desc");
  if (keyBtn && tts.elevenlabs_has_key) {
    keyBtn.textContent = t("settings.elKeyChangeBtn");
    if (keyDesc) keyDesc.textContent = t("settings.elKeySaved");
  }

  // Enabled toggle
  const toggle = document.getElementById("el-enabled-toggle");
  if (toggle) toggle.checked = tts.elevenlabs_enabled !== false;

  // Model select
  const modelSelect = document.getElementById("el-model-select");
  if (modelSelect && tts.elevenlabs_model) {
    modelSelect.value = tts.elevenlabs_model;
  }

  // Load voices if key is available
  if (tts.elevenlabs_has_key) {
    try {
      const { voices } = await window.lexa.elevenlabsVoices();
      const select = document.getElementById("el-voice-select");
      if (select && voices && voices.length) {
        select.replaceChildren();
        voices.forEach(v => {
          const opt = document.createElement("option");
          opt.value = v.voice_id;
          const labels = v.labels || {};
          const accent = labels.accent || "";
          const desc = labels.description || v.category || "";
          opt.textContent = `${v.name}${accent ? " (" + accent + ")" : ""}${desc ? " \u2014 " + desc : ""}`;
          if (v.active) opt.selected = true;
          select.appendChild(opt);
        });
        const active = voices.find(v => v.active);
        const descEl = document.getElementById("el-voice-desc");
        if (descEl && active) descEl.textContent = t("settings.elActiveVoice", {name: active.name});
      }
    } catch (e) { console.warn("[Settings] ElevenLabs voices failed:", e.message || e); }
  }
}

async function elevenlabsKeyAction() {
  await runSettingsSecretAction(async () => {
    const result = await showInputModal(t("settings.elKeyTitle"), [
      { name: "apiKey", label: t("settings.elKeyInputLabel"), type: "text", required: true }
    ], t("common.save"));
    if (!result || !result.apiKey) return;

    try {
      const res = await window.lexa.elevenlabsSetKey(result.apiKey);
      if (res.success) {
        showToast(t("settings.elKeySaveSuccess"), "success");
        await refreshSettingsView();
      } else {
        showToast(res.error || t("common.error"), "error");
      }
    } catch (e) {
      showToast(t("common.error") + ": " + e.message, "error");
    }
  });
}

async function elevenlabsToggleAction(enabled) {
  try {
    const res = await window.lexa.elevenlabsToggle(enabled);
    if (res.success) {
      showToast(enabled ? t("settings.elToggleOn") : t("settings.elToggleOff"), "success");
    }
  } catch (e) { console.warn("[Settings] ElevenLabs toggle failed:", e.message || e); }
}

async function elevenlabsVoiceChange(voiceId) {
  if (!voiceId) return;
  try {
    const res = await window.lexa.elevenlabsSetVoice(voiceId);
    if (res.success) {
      showToast(t("settings.elVoiceChanged"), "success");
    } else {
      showToast(res.error || t("common.error"), "error");
    }
  } catch (e) { showToast(t("common.error") + ": " + e.message, "error"); }
}

async function elevenlabsModelChange(model) {
  if (!model) return;
  try {
    const res = await window.lexa.elevenlabsSetModel(model);
    if (res.success) {
      showToast(t("settings.elModelChanged"), "success");
    } else {
      showToast(res.error || t("common.error"), "error");
    }
  } catch (e) { showToast(t("common.error") + ": " + e.message, "error"); }
}

function elevenlabsSettingsChange() {
  const stability = parseFloat(document.getElementById("el-stability-slider")?.value || 0.5);
  const similarity = parseFloat(document.getElementById("el-similarity-slider")?.value || 0.75);
  const stabLabel = document.getElementById("el-stability-label");
  const simLabel = document.getElementById("el-similarity-label");
  if (stabLabel) stabLabel.textContent = stability.toFixed(2);
  if (simLabel) simLabel.textContent = similarity.toFixed(2);

  // Debounce API call
  clearTimeout(elevenlabsSettingsChange._timer);
  elevenlabsSettingsChange._timer = setTimeout(async () => {
    try {
      await window.lexa.elevenlabsSetSettings(stability, similarity, null);
    } catch (e) { console.warn("[Settings] ElevenLabs settings failed:", e.message || e); }
  }, 300);
}

// ── LICENSE & TRIAL STATUS (Phase 39 + 40.3) ────
async function loadLicenseStatus() {
  const planEl = document.getElementById("license-plan");
  const statusEl = document.getElementById("license-status");
  const keyEl = document.getElementById("license-key-display");
  const expiresEl = document.getElementById("license-expires");
  const trialBar = document.getElementById("trial-status-bar");
  if (!planEl) return;

  try {
    const lic = await window.lexa.licenseGet();
    const state = lic._state || "free";
    const daysLeft = lic._days_left || 0;

    // Trial states
    if (state === "trial_active") {
      planEl.textContent = t("settings.licenseTrialPlan");
      statusEl.textContent = t("settings.licenseDaysLeft", {days: daysLeft});
      statusEl.className = "setting-status";
      keyEl.textContent = t("settings.licenseTrialActive");
      expiresEl.textContent = settingsFormatDate(lic.expires);
      _showTrialBar(trialBar, "active", daysLeft);
    } else if (state === "trial_grace") {
      planEl.textContent = t("settings.licenseTrialPlan");
      statusEl.textContent = t("settings.licenseGracePeriod", {days: daysLeft});
      statusEl.className = "setting-status offline";
      keyEl.textContent = t("settings.licenseTrialExpired");
      expiresEl.textContent = settingsFormatDate(lic.expires);
      _showTrialBar(trialBar, "grace", daysLeft);
    } else if (state === "trial_expired") {
      planEl.textContent = t("settings.licenseTrialPlan");
      statusEl.textContent = t("settings.licenseExpired");
      statusEl.className = "setting-status offline";
      keyEl.textContent = t("settings.licensePurchase");
      expiresEl.textContent = settingsFormatDate(lic.expires);
      _showTrialBar(trialBar, "expired", 0);
    } else if (state === "paid_active") {
      const planNames = { pro: "Lexa Pro", ultra: "Lexa Ultra", premium: "Lexa Premium", paid: "Lexa Pro" };
      planEl.textContent = planNames[lic.plan] || lic.plan;
      statusEl.textContent = t("settings.licensePaidActive");
      statusEl.className = "setting-status";
      keyEl.textContent = lic.key || "\u2014";
      expiresEl.textContent = lic.expires ? settingsFormatDate(lic.expires) : t("settings.licenseUnlimited");
      _hideTrialBar(trialBar);
    } else if (state === "paid_expired") {
      const planNames = { pro: "Lexa Pro", ultra: "Lexa Ultra", premium: "Lexa Premium", paid: "Lexa Pro" };
      planEl.textContent = planNames[lic.plan] || lic.plan;
      statusEl.textContent = t("settings.licenseExpired");
      statusEl.className = "setting-status offline";
      keyEl.textContent = lic.key || "\u2014";
      expiresEl.textContent = settingsFormatDate(lic.expires);
      _hideTrialBar(trialBar);
    } else if (state === "paid_unverified") {
      const planNames = { pro: "Lexa Pro", ultra: "Lexa Ultra", premium: "Lexa Premium", paid: "Lexa Pro" };
      planEl.textContent = planNames[lic.plan] || lic.plan;
      statusEl.textContent = t("settings.licenseNeedsReactivation");
      statusEl.className = "setting-status offline";
      keyEl.textContent = lic.key || "\u2014";
      expiresEl.textContent = lic.expires ? settingsFormatDate(lic.expires) : "\u2014";
      _hideTrialBar(trialBar);
    } else {
      // Free / unknown
      planEl.textContent = t("settings.licenseFree");
      statusEl.textContent = t("settings.licenseNotActivated");
      statusEl.className = "setting-status offline";
      keyEl.textContent = t("settings.licenseNoKey");
      expiresEl.textContent = "\u2014";
      _hideTrialBar(trialBar);
    }
  } catch (e) {
    console.warn("[Settings] License load failed:", e.message || e);
  }
}

function _showTrialBar(el, mode, daysLeft) {
  if (!el) return;
  el.classList.remove("hidden");
  el.className = "trial-status-bar trial-" + mode;
  if (mode === "active") {
    const safeDaysLeft = Math.max(0, Math.min(14, Number(daysLeft) || 0));
    const text = document.createElement("span");
    text.textContent = t("settings.trialProgress", {days: safeDaysLeft});
    const bar = document.createElement("div");
    bar.className = "trial-progress";
    const fill = document.createElement("div");
    fill.className = "trial-progress-fill trial-progress-days-" + safeDaysLeft;
    bar.appendChild(fill);
    el.replaceChildren(text, bar);
  } else if (mode === "grace") {
    el.textContent = t("settings.graceProgress", {days: daysLeft});
  } else {
    const text = document.createElement("span");
    text.textContent = t("settings.trialExpiredText");
    const link = document.createElement("a");
    link.href = "#";
    link.textContent = t("settings.upgradeNow");
    link.addEventListener("click", (e) => { e.preventDefault(); activateLicense(); });
    el.replaceChildren(text, link);
  }
}

function _hideTrialBar(el) {
  if (el) el.classList.add("hidden");
}

async function activateLicense() {
  await runSettingsLicenseAction(async () => {
    const result = await showInputModal(t("settings.licenseActivateTitle"), [
      { name: "key", label: t("settings.licenseKeyLabel"), type: "text", required: true }
    ], t("settings.licenseActivateBtn"));
    if (!result || !result.key) return;

    // Interne Whitespaces (Leerzeichen/Umbrüche aus Copy & Paste) entfernen,
    // bevor das strikte Format geprüft wird.
    const key = result.key.replace(/\s+/g, "").toUpperCase();
    if (!/^LEXA-[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}-[A-F0-9]{5}$/.test(key)) {
      showToast(t("license.invalidFormat"), "error");
      return;
    }

    showToast(t("license.checking"), "info");
    try {
      const activation = await window.lexa.licenseActivate(key);
      if (activation.valid && activation.success !== false) {
        showToast(t("license.activated", {plan: (activation.plan || "pro").toUpperCase()}), "success");
        await loadLicenseStatus();
      } else {
        showToast(activation.error || t("license.invalid"), "error");
      }
    } catch (e) {
      showToast(t("license.validationError", {error: e.message}), "error");
    }
  });
}

async function removeLicense() {
  await runSettingsLicenseAction(async () => {
    const result = await showInputModal(t("settings.licenseRemoveTitle"), [
      { name: "confirm", label: t("settings.licenseRemoveConfirm"), type: "text", required: true }
    ], t("settings.licenseRemoveBtn"));
    if (!result || result.confirm.toLowerCase() !== "ja") return;

    try {
      await window.lexa.licenseSet({ key: "", plan: "free", status: "inactive", expires: null });
      showToast(t("license.removed"), "info");
      await loadLicenseStatus();
    } catch (e) {
      showToast(t("common.error") + ": " + settingsClip(e.message || e, 120), "error");
    }
  });
}

async function saveProfile() {
  const nameEl = document.getElementById("profile-name");
  const langEl = document.getElementById("profile-language");
  if (!nameEl && !langEl) return;
  const name = nameEl ? nameEl.value.trim() : "";
  const lang = langEl ? langEl.value.trim() : "";
  try {
    if (name) await window.lexa.setProfile("name", name);
    if (lang) await window.lexa.setProfile("language", lang);
    showToast(t("toast.profileSaved"), "success");
  } catch (e) {
    showToast(t("common.error") + ": " + settingsClip(e.message || e, 120), "error");
  }
}

// ── LANGUAGE / i18n (Phase 42.1) ─────────────────
async function loadLanguagePreference() {
  const lang = settingsSafeLanguage(lexaStorageGet("lexa-lang", "de"));
  const select = document.getElementById("language-select");
  if (select) select.value = lang;
  // Initialize i18n system — MUST await to prevent raw key display
  if (typeof LexaI18n !== "undefined") {
    await LexaI18n.init(lang);
    LexaI18n.translatePage();
  }
}

async function changeLanguage(lang) {
  if (!lang) return;
  const safeLang = settingsSafeLanguage(lang);
  if (typeof LexaI18n !== "undefined") {
    await LexaI18n.setLanguage(safeLang);
    LexaI18n.translatePage();
    showToast(safeLang === "de" ? t("settings.langDe") : t("settings.langEn"), "success", 2000);
  }
  lexaStorageSet("lexa-lang", safeLang);
}

// ── THEME & PERSONALIZATION (Phase 15) ──────────
function toggleTheme(isDark) {
  document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");
  lexaStorageSet("lexa-theme", isDark ? "dark" : "light");
  showToast(isDark ? t("settings.darkModeActivated") : t("settings.lightModeActivated"), "info", 2000);
}

function setAccentColor(color) {
  const safeColor = settingsSafeAccent(color);
  // Remove old accent, set new
  if (safeColor === "purple") {
    document.documentElement.removeAttribute("data-accent");
  } else {
    document.documentElement.setAttribute("data-accent", safeColor);
  }
  lexaStorageSet("lexa-accent", safeColor);

  // Update picker UI
  document.querySelectorAll(".accent-dot").forEach(d => {
    const isActive = d.dataset.accent === safeColor;
    d.classList.toggle("active", isActive);
    d.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function setFontSize(size) {
  const safeSize = settingsSafeFontSize(size);
  document.documentElement.setAttribute("data-font-size", safeSize);
  lexaStorageSet("lexa-fontsize", safeSize);
}

function loadThemePreferences() {
  // Theme
  const theme = settingsSafeTheme(lexaStorageGet("lexa-theme", "dark"));
  document.documentElement.setAttribute("data-theme", theme);
  const themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) themeToggle.checked = theme === "dark";

  // Accent
  const accent = settingsSafeAccent(lexaStorageGet("lexa-accent", "purple"));
  if (accent !== "purple") {
    document.documentElement.setAttribute("data-accent", accent);
  } else {
    document.documentElement.removeAttribute("data-accent");
  }
  document.querySelectorAll(".accent-dot").forEach(d => {
    const isActive = d.dataset.accent === accent;
    d.classList.toggle("active", isActive);
    d.setAttribute("aria-pressed", isActive ? "true" : "false");
  });

  // Font size
  const fontSize = lexaStorageGet("lexa-fontsize", "");
  if (fontSize) {
    const safeFontSize = settingsSafeFontSize(fontSize);
    document.documentElement.setAttribute("data-font-size", safeFontSize);
    const fontSelect = document.getElementById("fontsize-select");
    if (fontSelect) fontSelect.value = safeFontSize;
  }
}

// ── VOICE TEST (Settings Page) ────────────────────
function settingsPreferredVoiceMimeType() {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return "";
  return [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
  ].find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

async function testVoice() {
  showToast("Stimme wird getestet...", "info");
  try {
    const audioUrl = await window.lexa.tts("Hallo! Ich bin Lexa, dein KI-Assistent. Die Sprachausgabe funktioniert einwandfrei.");
    if (audioUrl) {
      const audio = new Audio(audioUrl);
      const revoke = () => URL.revokeObjectURL(audioUrl);
      audio.onended = revoke;
      audio.onerror = revoke;
      audio.play().catch((e) => {
        revoke();
        showToast("TTS-Test Fehler: " + (e.message || e), "error");
      });
      showToast("TTS funktioniert!", "success");
    } else {
      showToast("TTS-Test fehlgeschlagen: Kein Audio erhalten", "error");
    }
  } catch (e) {
    showToast("TTS-Test Fehler: " + (e.message || e), "error");
  }
}

async function testMicrophone() {
  showToast("Mikrofon wird getestet (3 Sekunden)...", "info");
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    showToast("Spracherkennung nicht verfügbar.", "error");
    return;
  }

  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = settingsPreferredVoiceMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks = [];
    recorder.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
      if (blob.size < 100) {
        showToast("Kein Audio aufgenommen", "error");
        return;
      }
      showToast("Transkribiere...", "info");
      try {
        const result = await window.lexa.stt(blob);
        if (result.text) {
          showToast("Erkannt: " + result.text, "success", 5000);
        } else {
          showToast("Keine Sprache erkannt (Hintergrundgeraeusche?)", "warning");
        }
      } catch (e) {
        showToast("STT-Test Fehler: " + (e.message || e), "error");
      }
    };
    recorder.start();
    setTimeout(() => { if (recorder.state !== "inactive") recorder.stop(); }, 3000);
  } catch (e) {
    if (stream) stream.getTracks().forEach(t => t.stop());
    showToast("Mikrofon-Zugriff verweigert: " + (e.message || e), "error");
  }
}
