/* ════════════════════════════════════════════════
   LEXA AI — Settings Module
   Settings view, Theme/Accent/Font preferences,
   Voice settings (TTS + STT), Backup management,
   Profile saving
   Extracted from tools.js
   ════════════════════════════════════════════════ */

// ── SETTINGS VIEW ────────────────────────────────
async function refreshSettingsView() {
  // Desktop settings (work even when backend is offline)
  try {
    const autostartToggle = document.getElementById("autostart-toggle");
    if (autostartToggle) autostartToggle.checked = window.lexa.getAutostart();
  } catch (e) { console.warn("[Settings] Failed to get autostart status:", e.message || e); }
  const notifToggle = document.getElementById("notifications-toggle");
  if (notifToggle) notifToggle.checked = LexaState.get("notificationsEnabled");

  // License status works offline (reads local file via IPC)
  loadLicenseStatus();

  if (!LexaState.get("backendOnline")) return;

  const [aiRes, voiceRes, healthRes, memRes, cmdsRes] = await Promise.allSettled([
    window.lexa.aiStatus(),
    window.lexa.voiceStatus(),
    window.lexa.health(),
    window.lexa.memoryStats(),
    window.lexa.commands(),
  ]);

  const ai = aiRes.status === "fulfilled" ? aiRes.value : { groq: {}, openai: {}, gemini: {} };
  const voice = voiceRes.status === "fulfilled" ? voiceRes.value : { tts: {}, stt: {} };
  const health = healthRes.status === "fulfilled" ? healthRes.value : {};
  const mem = memRes.status === "fulfilled" ? memRes.value : {};

  const groqEl = document.getElementById("groq-status");
  const openaiEl = document.getElementById("openai-status");
  const geminiEl = document.getElementById("gemini-status");
  if (groqEl) { groqEl.textContent = ai.groq?.available ? t("settings.connected") : t("settings.offline"); groqEl.className = "setting-status" + (ai.groq?.available ? "" : " offline"); }
  if (openaiEl) { openaiEl.textContent = ai.openai?.available ? t("settings.connected") : t("settings.offline"); openaiEl.className = "setting-status" + (ai.openai?.available ? "" : " offline"); }
  if (geminiEl) { geminiEl.textContent = ai.gemini?.available ? t("settings.connected") : t("settings.offline"); geminiEl.className = "setting-status" + (ai.gemini?.available ? "" : " offline"); }

  // TTS Status — Cartesia (Primary) + ElevenLabs (Fallback)
  const cartesiaStatusEl = document.getElementById("cartesia-status");
  if (cartesiaStatusEl) {
    const cartesiaOk = voice.tts?.cartesia_available;
    cartesiaStatusEl.textContent = cartesiaOk ? "Verbunden — " + (voice.tts?.cartesia_model || "sonic-2") : "Kein API Key";
    cartesiaStatusEl.className = "setting-status" + (cartesiaOk ? "" : " offline");
  }
  const ttsEl = document.getElementById("tts-status") || document.getElementById("el-status");
  if (ttsEl) {
    const elOk = voice.tts?.elevenlabs_available;
    ttsEl.textContent = elOk ? "Verbunden" : "Kein API Key";
    ttsEl.className = "setting-status" + (elOk ? "" : " offline");
  }

  // STT Status — Deepgram (Primary) + Groq (Fallback) + Local
  const sttEl = document.getElementById("stt-status");
  const sttEngine = voice.stt?.engine || "deepgram";
  const sttLabels = { deepgram: "Deepgram Nova-3", groq: "Groq Whisper", local: "Lokal" };
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
    const dgOk = voice.stt?.deepgram_available ? "Deepgram OK" : "Kein Deepgram Key";
    const groqOk = voice.stt?.groq_available ? "Groq OK" : "Kein Groq Key";
    sttDesc.textContent = dgOk + " | " + groqOk + " | Engine: " + sttLabel;
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
  setupBackupControls();
}

// ── BACKUP MANAGEMENT (Settings) ─────────────────
function setupBackupControls() {
  // Backup create
  const btnCreate = document.getElementById('btn-backup-create');
  if (btnCreate && !btnCreate._lexaBound) {
    btnCreate._lexaBound = true;
    btnCreate.addEventListener('click', async () => {
      showToast(t("settings.backupCreating"), 'info');
      try {
        const result = await window.lexa.backupCreateDb();
        showToast(t("settings.backupCreated", {path: result.path || 'OK'}), 'success');
      } catch (e) {
        showToast(t("settings.backupFailed", {error: e.message}), 'error');
      }
    });
  }

  // List backups
  const btnList = document.getElementById('btn-backup-list');
  if (btnList && !btnList._lexaBound) {
    btnList._lexaBound = true;
    btnList.addEventListener('click', async () => {
      const container = document.getElementById('backup-list-container');
      if (!container) return;
      container.innerHTML = '';
      container.appendChild(createLoadingState(t("settings.backupsLoading")));
      try {
        const data = await window.lexa.backupListDb();
        container.innerHTML = '';
        if (!data.backups || data.backups.length === 0) {
          container.appendChild(createEmptyState('\u{1F4E6}', t("settings.noBackupsTitle"), t("settings.noBackupsHint")));
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
          metaSpan.textContent = `${b.size_mb || '?'} MB \u2014 ${b.created ? new Date(b.created).toLocaleString('de-DE') : ''}`;
          item.appendChild(metaSpan);

          const restoreBtn = document.createElement('button');
          restoreBtn.className = 'btn-small';
          restoreBtn.textContent = t("settings.restoreBtn");
          restoreBtn.addEventListener('click', async () => {
            const fname = b.filename || b.path;
            const result = await showInputModal(t("common.confirm"), [
              { name: "confirm", label: t("settings.restoreConfirm", {name: fname}), type: "text", required: true }
            ], t("common.confirm"));
            if (!result || result.confirm.toLowerCase() !== "ja") return;
            showToast(t("settings.restoreRunning"), 'info');
            try {
              const res = await window.lexa.backupRestoreDb(b.path);
              showToast(res.result || t("settings.restoreRunning"), 'success');
            } catch (e) {
              showToast(t("settings.restoreFailed", {error: e.message}), 'error');
            }
          });
          item.appendChild(restoreBtn);
          list.appendChild(item);
        });
        container.appendChild(list);
      } catch (e) {
        container.innerHTML = '';
        container.appendChild(createErrorState(t("settings.backupsLoadError")));
      }
    });
  }

  // Rebuild FTS index
  const btnFts = document.getElementById('btn-fts-rebuild');
  if (btnFts && !btnFts._lexaBound) {
    btnFts._lexaBound = true;
    btnFts.addEventListener('click', async () => {
      showToast(t("settings.ftsRebuilding"), 'info');
      try {
        await window.lexa.rebuildFts();
        showToast(t("settings.ftsRebuilt"), 'success');
      } catch (e) {
        showToast(t("common.error") + ': ' + e.message, 'error');
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
      select.innerHTML = "";
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
  if (!modelName) return;
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
  }
}

// ── DEEPGRAM + STT ENGINE ────────────────────────
async function changeSttEngine(engine) {
  if (!engine) return;
  try {
    const res = await window.lexa.sttSetEngine(engine);
    if (res.success) {
      const engineLabel = engine === "deepgram" ? "Deepgram Nova-3" : engine === "groq" ? "Groq Whisper" : "Lokal";
      showToast(t("settings.sttEngineToast", {engine: engineLabel}), "success");
      // Show/hide Deepgram key group
      const dgKeyGroup = document.getElementById("deepgram-key-group");
      if (dgKeyGroup) dgKeyGroup.classList.toggle("hidden", engine !== "deepgram");
    } else {
      showToast(res.error || t("settings.errorGeneric"), "error");
    }
  } catch (e) { showToast(t("settings.errorPrefix", {message: e.message}), "error"); }
}

async function setDeepgramKeyAction() {
  const result = await showInputModal(t("settings.deepgramTitle"), [
    { name: "apiKey", label: t("settings.deepgramKeyLabel"), type: "text", required: true }
  ], t("common.save"));
  if (!result || !result.apiKey) return;

  try {
    const res = await window.lexa.deepgramSetKey(result.apiKey);
    if (res.success) {
      showToast(t("settings.deepgramKeySaved"), "success");
      refreshSettingsView();
    } else {
      showToast(res.error || t("settings.errorGeneric"), "error");
    }
  } catch (e) { showToast(t("settings.errorPrefix", {message: e.message}), "error"); }
}

async function deleteDeepgramKeyAction() {
  try {
    const res = await window.lexa.deepgramDeleteKey();
    if (res.success) {
      showToast(t("settings.deepgramKeyRemoved"), "info");
      refreshSettingsView();
    }
  } catch (e) { showToast(t("settings.errorPrefix", {message: e.message}), "error"); }
}

// ── CARTESIA SETTINGS ───────────────────────────

async function setCartesiaKeyAction() {
  const result = await showInputModal("Cartesia API Key", [
    { name: "apiKey", label: "API Key (sk_car_...)", type: "text", required: true }
  ], "Speichern");
  if (!result || !result.apiKey) return;

  try {
    const res = await window.lexa.cartesiaSetKey(result.apiKey);
    if (res.success) {
      showToast("Cartesia Key gespeichert", "success");
      refreshSettingsView();
    } else {
      showToast(res.error || "Fehler beim Speichern", "error");
    }
  } catch (e) { showToast("Fehler: " + e.message, "error"); }
}

async function deleteCartesiaKeyAction() {
  try {
    const res = await window.lexa.cartesiaDeleteKey();
    if (res.success) {
      showToast("Cartesia Key entfernt", "info");
      refreshSettingsView();
    }
  } catch (e) { showToast("Fehler: " + e.message, "error"); }
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
        select.innerHTML = "";
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
  const result = await showInputModal(t("settings.elKeyTitle"), [
    { name: "apiKey", label: t("settings.elKeyInputLabel"), type: "text", required: true }
  ], t("common.save"));
  if (!result || !result.apiKey) return;

  try {
    const res = await window.lexa.elevenlabsSetKey(result.apiKey);
    if (res.success) {
      showToast(t("settings.elKeySaveSuccess"), "success");
      refreshSettingsView();
    } else {
      showToast(res.error || t("common.error"), "error");
    }
  } catch (e) {
    showToast(t("common.error") + ": " + e.message, "error");
  }
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
      expiresEl.textContent = lic.expires ? new Date(lic.expires).toLocaleDateString("de-DE") : "\u2014";
      _showTrialBar(trialBar, "active", daysLeft);
    } else if (state === "trial_grace") {
      planEl.textContent = t("settings.licenseTrialPlan");
      statusEl.textContent = t("settings.licenseGracePeriod", {days: daysLeft});
      statusEl.className = "setting-status offline";
      keyEl.textContent = t("settings.licenseTrialExpired");
      expiresEl.textContent = lic.expires ? new Date(lic.expires).toLocaleDateString("de-DE") : "\u2014";
      _showTrialBar(trialBar, "grace", daysLeft);
    } else if (state === "trial_expired") {
      planEl.textContent = t("settings.licenseTrialPlan");
      statusEl.textContent = t("settings.licenseExpired");
      statusEl.className = "setting-status offline";
      keyEl.textContent = t("settings.licensePurchase");
      expiresEl.textContent = lic.expires ? new Date(lic.expires).toLocaleDateString("de-DE") : "\u2014";
      _showTrialBar(trialBar, "expired", 0);
    } else if (state === "paid_active") {
      const planNames = { pro: "Lexa Pro", ultra: "Lexa Ultra", premium: "Lexa Premium", paid: "Lexa Pro" };
      planEl.textContent = planNames[lic.plan] || lic.plan;
      statusEl.textContent = t("settings.licensePaidActive");
      statusEl.className = "setting-status";
      keyEl.textContent = lic.key || "\u2014";
      expiresEl.textContent = lic.expires ? new Date(lic.expires).toLocaleDateString("de-DE") : t("settings.licenseUnlimited");
      _hideTrialBar(trialBar);
    } else if (state === "paid_expired") {
      const planNames = { pro: "Lexa Pro", ultra: "Lexa Ultra", premium: "Lexa Premium", paid: "Lexa Pro" };
      planEl.textContent = planNames[lic.plan] || lic.plan;
      statusEl.textContent = t("settings.licenseExpired");
      statusEl.className = "setting-status offline";
      keyEl.textContent = lic.key || "\u2014";
      expiresEl.textContent = lic.expires ? new Date(lic.expires).toLocaleDateString("de-DE") : "\u2014";
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
    el.innerHTML = "";
    const text = document.createElement("span");
    text.textContent = t("settings.trialProgress", {days: daysLeft});
    el.appendChild(text);
    const bar = document.createElement("div");
    bar.className = "trial-progress";
    const fill = document.createElement("div");
    fill.className = "trial-progress-fill trial-progress-days-" + safeDaysLeft;
    bar.appendChild(fill);
    el.appendChild(bar);
  } else if (mode === "grace") {
    el.textContent = t("settings.graceProgress", {days: daysLeft});
  } else {
    el.innerHTML = "";
    const text = document.createElement("span");
    text.textContent = t("settings.trialExpiredText");
    el.appendChild(text);
    const link = document.createElement("a");
    link.href = "#";
    link.textContent = t("settings.upgradeNow");
    link.addEventListener("click", (e) => { e.preventDefault(); activateLicense(); });
    el.appendChild(link);
  }
}

function _hideTrialBar(el) {
  if (el) el.classList.add("hidden");
}

async function activateLicense() {
  const result = await showInputModal(t("settings.licenseActivateTitle"), [
    { name: "key", label: t("settings.licenseKeyLabel"), type: "text", required: true }
  ], t("settings.licenseActivateBtn"));
  if (!result || !result.key) return;

  const key = result.key.trim().toUpperCase();
  if (!key.startsWith("LEXA-") || key.length < 20) {
    showToast(t("license.invalidFormat"), "error");
    return;
  }

  showToast(t("license.checking"), "info");
  try {
    const validation = await window.lexa.licenseValidate(key);
    if (validation.valid) {
      await window.lexa.licenseSet({
        key: key,
        plan: validation.plan || "pro",
        status: validation.status || "active",
        expires: validation.expires || null,
      });
      showToast(t("license.activated", {plan: (validation.plan || "pro").toUpperCase()}), "success");
      loadLicenseStatus();
    } else {
      showToast(validation.error || t("license.invalid"), "error");
    }
  } catch (e) {
    showToast(t("license.validationError", {error: e.message}), "error");
  }
}

async function removeLicense() {
  const result = await showInputModal(t("settings.licenseRemoveTitle"), [
    { name: "confirm", label: t("settings.licenseRemoveConfirm"), type: "text", required: true }
  ], t("settings.licenseRemoveBtn"));
  if (!result || result.confirm.toLowerCase() !== "ja") return;

  await window.lexa.licenseSet({ key: "", plan: "free", status: "inactive", expires: null });
  showToast(t("license.removed"), "info");
  loadLicenseStatus();
}

async function saveProfile() {
  const name = document.getElementById("profile-name").value.trim();
  const lang = document.getElementById("profile-language").value.trim();
  if (name) await window.lexa.setProfile("name", name);
  if (lang) await window.lexa.setProfile("language", lang);
  showToast(t("toast.profileSaved"), "success");
}

// ── LANGUAGE / i18n (Phase 42.1) ─────────────────
async function loadLanguagePreference() {
  const lang = localStorage.getItem("lexa-lang") || "de";
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
  if (typeof LexaI18n !== "undefined") {
    await LexaI18n.setLanguage(lang);
    LexaI18n.translatePage();
    showToast(lang === "de" ? t("settings.langDe") : t("settings.langEn"), "success", 2000);
  }
  localStorage.setItem("lexa-lang", lang);
}

// ── THEME & PERSONALIZATION (Phase 15) ──────────
function toggleTheme(isDark) {
  document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");
  localStorage.setItem("lexa-theme", isDark ? "dark" : "light");
  showToast(isDark ? t("settings.darkModeActivated") : t("settings.lightModeActivated"), "info", 2000);
}

function setAccentColor(color) {
  // Remove old accent, set new
  if (color === "purple") {
    document.documentElement.removeAttribute("data-accent");
  } else {
    document.documentElement.setAttribute("data-accent", color);
  }
  localStorage.setItem("lexa-accent", color);

  // Update picker UI
  document.querySelectorAll(".accent-dot").forEach(d => {
    d.classList.toggle("active", d.dataset.accent === color);
  });
}

function setFontSize(size) {
  const safeSize = ["13", "14", "15", "16"].includes(String(size)) ? String(size) : "14";
  document.documentElement.setAttribute("data-font-size", safeSize);
  localStorage.setItem("lexa-fontsize", safeSize);
}

function loadThemePreferences() {
  // Theme
  const theme = localStorage.getItem("lexa-theme") || "dark";
  document.documentElement.setAttribute("data-theme", theme);
  const themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) themeToggle.checked = theme === "dark";

  // Accent
  const accent = localStorage.getItem("lexa-accent") || "purple";
  if (accent !== "purple") {
    document.documentElement.setAttribute("data-accent", accent);
  }
  document.querySelectorAll(".accent-dot").forEach(d => {
    d.classList.toggle("active", d.dataset.accent === accent);
  });

  // Font size
  const fontSize = localStorage.getItem("lexa-fontsize");
  if (fontSize) {
    const safeFontSize = ["13", "14", "15", "16"].includes(String(fontSize)) ? String(fontSize) : "14";
    document.documentElement.setAttribute("data-font-size", safeFontSize);
    const fontSelect = document.getElementById("fontsize-select");
    if (fontSelect) fontSelect.value = safeFontSize;
  }
}

// ── VOICE TEST (Settings Page) ────────────────────
async function testVoice() {
  showToast("Stimme wird getestet...", "info");
  try {
    const audioUrl = await window.lexa.tts("Hallo! Ich bin Lexa, dein KI-Assistent. Die Sprachausgabe funktioniert einwandfrei.");
    if (audioUrl) {
      const audio = new Audio(audioUrl);
      audio.play();
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
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    const chunks = [];
    recorder.ondataavailable = e => chunks.push(e.data);
    recorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(chunks, { type: "audio/webm" });
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
    setTimeout(() => recorder.stop(), 3000);
  } catch (e) {
    showToast("Mikrofon-Zugriff verweigert: " + (e.message || e), "error");
  }
}
