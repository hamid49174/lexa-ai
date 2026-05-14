/* ════════════════════════════════════════════════
   LEXA AI — Frontend Application Logic v0.20
   Main orchestrator — loads after module scripts:
   modals.js, chat.js, productivity.js, dashboard.js,
   system.js, commands.js, memory.js, settings.js, devtools.js
   ════════════════════════════════════════════════ */

// ── GLOBAL ERROR HANDLER (debug aid) ────────────
window.onerror = (msg, src, line, col, err) => {
  console.error(`[LEXA ERROR] ${msg} at ${src}:${line}:${col}`, err);
  const c = document.getElementById("toast-container");
  if (c) {
    const el = document.createElement("div");
    el.className = "toast error";
    const icon = document.createElement("span"); icon.className = "toast-icon"; icon.textContent = "\u2717";
    const text = document.createElement("span"); text.className = "toast-text"; text.textContent = "JS Error: " + String(msg).substring(0, 200);
    el.appendChild(icon); el.appendChild(text);
    c.appendChild(el);
    setTimeout(() => { el.classList.add("toast-out"); el.addEventListener("animationend", () => el.remove()); }, 8000);
  }
};

window.addEventListener("unhandledrejection", (e) => {
  console.error("[LEXA] Unhandled Promise:", e.reason);
});

// ── GLOBAL DOM REFERENCES ────────────────────────
const chatMessages = document.getElementById("chat-messages");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const statusBadge = document.getElementById("status-badge");
const micBtn = document.getElementById("mic-btn");
const ttsToggle = document.getElementById("tts-toggle");
const connBanner = document.getElementById("connection-banner");
const navStatus = document.getElementById("nav-status");

// ── GLOBAL STATE ─────────

function setNavStatus(text, state = "idle") {
  if (!navStatus) return;
  navStatus.textContent = text;
  navStatus.dataset.state = state;
}

function updateCommandCount(total) {
  if (!Number.isFinite(total)) return;
  const navCount = document.getElementById("nav-commands-count");
  if (navCount) navCount.textContent = total;
  const greetingCount = document.getElementById("greeting-cmd-count");
  if (greetingCount) greetingCount.textContent = t("app.commandsReady", {count: total});
  const settingsCount = document.getElementById("settings-cmd-count");
  if (settingsCount) settingsCount.textContent = t("app.commandsRegistered", {count: total});
}

function updateConversationCount(count = LexaState.get("conversationsList").length) {
  const safeCount = Number.isFinite(count) ? count : 0;
  const greetingCount = document.getElementById("greeting-conv-count");
  if (greetingCount) greetingCount.textContent = t("app.chatsSaved", {count: safeCount});
}

function normalizeUiCopy() {
  const wakewordIndicator = document.getElementById("wakeword-indicator");
  if (wakewordIndicator && !LexaState.get("wakeWordActive")) {
    wakewordIndicator.title = t("nav.wakeWordTooltip");
  }

  const memoryButton = document.querySelector('[data-arg="memory"]');
  if (memoryButton) {
    memoryButton.title = t("nav.memory");
  }

  const focusModeText = document.querySelector("#focus-mode-banner .focus-mode-banner-text");
  if (focusModeText) {
    focusModeText.textContent = t("focus.bannerText");
  }
}

// ── WAKE WORD STATE (wakeWordActive in LexaState) ──
// Module-local polling intervals (not shared):
let _wakeWordPollInterval = null;

const VIEW_KEYS = ["dashboard", "chat", "system", "commands", "productivity", "memory", "settings"];

// ── EVENT DELEGATION (replaces all inline onclick/onchange/oninput in HTML) ──────
function _initDelegation() {
  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    _dispatch(el, el.dataset, null);
  });
  document.addEventListener("change", (e) => {
    const el = e.target;
    if (!el.dataset || !el.dataset.action) return;
    _dispatch(el, el.dataset, el.type === "checkbox" ? el.checked : el.value);
  });
  document.addEventListener("input", (e) => {
    const el = e.target;
    if (!el.dataset || !el.dataset.action) return;
    _dispatch(el, el.dataset, el.value);
  });
}

function _dispatch(el, ds, value) {
  const a = ds.action;
  const arg = ds.arg;
  const cmd = ds.cmd;
  switch (a) {
    // Window controls (through preload bridge)
    case "lexa-minimize": window.lexa.minimize(); break;
    case "lexa-maximize": window.lexa.maximize(); break;
    case "lexa-close": window.lexa.close(); break;
    // Parameterized tool/action calls
    case "runTool": {
      const params = ds.params ? JSON.parse(ds.params) : {};
      runTool(cmd, params, ds.confirm === "true");
      break;
    }
    case "quickAction": quickAction(cmd, ds.prompt, ds.param); break;
    case "switchView": switchView(arg || ds.view); break;
    case "toggleNavMenu": toggleNavMenu(); break;
    case "toggleChatView": toggleChatView(); break;
    case "windowLayoutAction": windowLayoutAction(arg); break;
    case "gitPullPushAction": gitPullPushAction(arg); break;
    case "dockerStartStopAction": dockerStartStopAction(arg); break;
    case "setAccentColor": setAccentColor(arg); break;
    case "toggleWakeWord": toggleWakeWord(); break;
    // Value-passing handlers (from change / input events)
    case "changeAiModel": changeAiModel(value); break;
    case "changeSttModel": changeSttModel(value); break;
    case "changeSttEngine": changeSttEngine(value); break;
    case "setDeepgramKey": setDeepgramKeyAction(); break;
    case "deleteDeepgramKey": deleteDeepgramKeyAction(); break;
    case "setCartesiaKey": setCartesiaKeyAction(); break;
    case "deleteCartesiaKey": deleteCartesiaKeyAction(); break;
    case "elevenlabsKeyAction": elevenlabsKeyAction(); break;
    case "elevenlabsToggleAction": elevenlabsToggleAction(value); break;
    case "elevenlabsVoiceChange": elevenlabsVoiceChange(value); break;
    case "elevenlabsModelChange": elevenlabsModelChange(value); break;
    case "elevenlabsSettingsChange": elevenlabsSettingsChange(); break;
    case "setFontSize": setFontSize(value); break;
    case "toggleTheme": toggleTheme(value); break;
    case "changeLanguage": changeLanguage(value); break;
    case "applySendModeToggle": applySendModeToggle(value); break;
    case "toggleAutostart": toggleAutostart(value); break;
    case "toggleNotifications": toggleNotifications(value); break;
    case "filterTodosLocal": filterTodosLocal(value); break;
    case "filterNotes": filterNotes(value); break;
    case "filterCommands": filterCommands(value); break;
    case "visionScreenshot": triggerScreenshotAnalysis(); break;
    // Chat inline-handler replacements (CSP-safe)
    case "copy-code": copyCode(el); break;
    case "copy-message": copyMessage(el); break;
    case "confirm-action": confirmAction(el, el.dataset.payload); break;
    case "deny-action": denyAction(el); break;
    // Zero-arg functions — dispatch by name via window global
    default: {
      const fn = window[a];
      if (typeof fn === "function") fn();
    }
  }
}

// Settings — isFocusMode is in LexaState

// 3D Orbs
window.dashboardOrb = null;

// Audio Context globals
window.audioContext = null;
window.analyser = null;
window.dataArray = null;
window.isAudioInitialized = false;

// ── INIT ─────────────────────────────────────────
async function init() {
  _initDelegation(); // Wire all data-action handlers before anything else
  try {
    // Setup UI immediately (don't wait for backend)
    setupSidebar();
    setupVoice();
    setupKeyboardShortcuts();
    setupDesktopIntegration();
    setupDragDrop();
    loadThemePreferences();
    // i18n: MUST await so translations are ready before first render
    await loadLanguagePreference().catch(e => console.warn("[i18n] load failed:", e));
    // normalizeUiCopy uses t() — must run AFTER i18n is loaded
    normalizeUiCopy();
    loadSidebarState();
    applySendModeToggle(localStorage.getItem("lexa-ctrl-enter") === "true");

    // FORCE CHAT VIEW (Next-Level UI) — start in ambient orb mode
    window._chatViewOpen = false;
    switchView("chat");

    // Start Clock
    LexaState.setInterval("clock", updateClock, LexaConfig.CLOCK_INTERVAL);
    updateClock();

    // Init 3D Voice Orbs (Timeout to ensure container is fully rendered)
    setTimeout(() => {
      if (typeof LexaOrb3D !== 'undefined') {
        window.dashboardOrb = new LexaOrb3D('voice-orb-canvas', {
          baseScale: 3.5,
          wobbleSpeed: 0.0005,
          baseWobble: 0.3
        });
      }
    }, 100);

    window.addEventListener("beforeunload", () => {
      if (_wakeWordPollInterval) clearInterval(_wakeWordPollInterval);
      LexaState.clearAllIntervals();
    });

    console.log("Lexa UI fully initialized.");

    // Rotate chat input placeholder hints every 8 seconds
    const PLACEHOLDERS = [
      () => window.ctrlEnterMode ? t("app.placeholderCtrlEnter") : t("app.placeholderDefault"),
      () => t("app.placeholderSpotify"),
      () => t("app.placeholderBattery"),
      () => t("app.placeholderScreenshot"),
      () => t("app.placeholderTodo"),
      () => t("app.placeholderPomodoro"),
      () => t("app.placeholderTime"),
      () => t("app.placeholderGit"),
    ];
    let _phIdx = 0;
    LexaState.setInterval("placeholder", () => {
      if (chatInput && document.activeElement !== chatInput) {
        _phIdx = (_phIdx + 1) % PLACEHOLDERS.length;
        const ph = PLACEHOLDERS[_phIdx];
        chatInput.placeholder = typeof ph === "function" ? ph() : ph;
      }
    }, LexaConfig.PLACEHOLDER_ROTATE_INTERVAL);

    // Then connect to backend
    await checkHealth();
    _initWakeWord();
    LexaState.setInterval("healthCheck", checkHealth, LexaConfig.HEALTH_CHECK_INTERVAL);
    LexaState.setInterval("systemStats", updateSystemStats, LexaConfig.SYSTEM_STATS_INTERVAL);
    // Auto-save active conversation every 60 seconds
    LexaState.setInterval("autoSave", autoSaveConversation, LexaConfig.AUTO_SAVE_INTERVAL);
    // Poll for fired timers every 5 seconds
    LexaState.setInterval("timerCheck", checkTimers, LexaConfig.TIMER_CHECK_INTERVAL);
    updateSystemStats();
    await loadConversations();
    updateConversationCount();
    if (typeof renderConversationStarters === "function") renderConversationStarters();

    // Close nav menu when clicking overlay
    const navOverlay = document.getElementById("nav-overlay");
    if (navOverlay) {
      navOverlay.addEventListener("click", () => toggleNavMenu());
    }

    // Wire up talk-to-lexa button (replaces inline onclick removed from HTML)
    const talkBtn = document.getElementById("talk-to-lexa-btn");
    if (talkBtn) talkBtn.addEventListener("click", () => { startOrbConversation(); });

    // Wire up chat input and send button explicitly
    if (chatInput) {
      // Save draft on every keystroke for crash recovery
      chatInput.addEventListener("input", () => {
        try { localStorage.setItem("lexa-chat-draft", chatInput.value); } catch (_) {}
      });
      chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          if (window.ctrlEnterMode && !e.ctrlKey) return; // Need Ctrl+Enter
          if (!window.ctrlEnterMode && e.ctrlKey) return; // Need just Enter
          e.preventDefault();
          if (typeof sendMessage === "function") sendMessage();
        } else if (e.key === "ArrowUp") {
          if (typeof chatInputHistory !== "undefined" && chatInputHistory.length > 0) {
            e.preventDefault();
            if (chatHistoryIdx === -1) chatInputDraft = chatInput.value;
            chatHistoryIdx = Math.min(chatHistoryIdx + 1, chatInputHistory.length - 1);
            chatInput.value = chatInputHistory[chatHistoryIdx];
          }
        } else if (e.key === "ArrowDown") {
          if (typeof chatInputHistory !== "undefined" && chatHistoryIdx >= 0) {
            e.preventDefault();
            chatHistoryIdx--;
            if (chatHistoryIdx === -1) chatInput.value = chatInputDraft;
            else chatInput.value = chatInputHistory[chatHistoryIdx];
          }
        }
      });
    }

    if (sendBtn) {
      sendBtn.addEventListener("click", () => {
        if (typeof sendMessage === "function") sendMessage();
      });
    }

    // Fetch initial limits
    try {
      const data = await window.lexa.commands();
      if (data.total) {
        updateCommandCount(data.total);
      }
    } catch (e) { console.warn("[Lexa:app] Failed to fetch command count:", e.message || e); }

  } catch (err) {
    console.error("[LEXA] Init error:", err);
    // Still start health checks even if init partially fails
    LexaState.setInterval("healthCheck", checkHealth, LexaConfig.HEALTH_CHECK_INTERVAL);
  }
}

// ── DESKTOP INTEGRATION (Phase 8) ───────────────
function setupDesktopIntegration() {
  // Load notification preference
  const savedNotif = localStorage.getItem("lexa-notifications");
  LexaState.set("notificationsEnabled", savedNotif !== "0");

  // Listen for tray menu view switches
  if (window.lexa && window.lexa.onSwitchView) {
    window.lexa.onSwitchView((view) => switchView(view));
  }

  // Listen for auto-update notifications from main process
  if (window.lexa && window.lexa.onUpdateAvailable) {
    window.lexa.onUpdateAvailable((info) => {
      showToast(
        t("app.updateAvailable", {latest: escapeHtml(info.latest), current: escapeHtml(info.current)}),
        "info",
        8000
      );
      // Also send a desktop notification
      sendNotification("Lexa AI Update", t("app.updateNotification", {latest: info.latest}));
    });
  }
}

function sendNotification(title, body) {
  if (!LexaState.get("notificationsEnabled")) return;
  try { window.lexa.notify(title, body); } catch (e) { console.warn("[Lexa:app] Notification failed:", e.message || e); }
}

function toggleAutostart(enabled) {
  window.lexa.setAutostart(enabled);
  showToast(enabled ? t("settings.autostartOn") : t("settings.autostartOff"), "info");
  sendNotification("Lexa AI", enabled ? t("app.autostartEnabledNotif") : t("app.autostartDisabledNotif"));
}

function toggleNotifications(enabled) {
  LexaState.set("notificationsEnabled", enabled);
  localStorage.setItem("lexa-notifications", enabled ? "1" : "0");
  showToast(enabled ? t("settings.notificationsOn") : t("settings.notificationsOff"), "info");
}

// ── KEYBOARD SHORTCUTS ───────────────────────────
function setupKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    // Ctrl+1-8: Switch views
    if (e.ctrlKey && !e.shiftKey && !e.altKey) {
      const num = parseInt(e.key);
      if (num >= 1 && num <= 9) {
        e.preventDefault();
        switchView(VIEW_KEYS[num - 1]);
        return;
      }
    }

    // Escape: Back to chat + close chat view to ambient mode
    if (e.key === "Escape") {
      if (LexaState.get("currentView") !== "chat") {
        switchView("chat");
      } else if (window._chatViewOpen) {
        // Return to ambient orb mode
        toggleChatView();
      }
      if (chatInput) chatInput.focus();
      return;
    }

    // ArrowDown (outside input): Open chat messages view
    if (e.key === "ArrowDown" && document.activeElement !== chatInput && LexaState.get("currentView") === "chat" && !window._chatViewOpen) {
      e.preventDefault();
      toggleChatView();
      return;
    }

    // ArrowUp (outside input): Close chat messages, return to orb
    if (e.key === "ArrowUp" && document.activeElement !== chatInput && LexaState.get("currentView") === "chat" && window._chatViewOpen) {
      e.preventDefault();
      toggleChatView();
      return;
    }

    // Ctrl+L: Clear chat
    if (e.ctrlKey && e.key === "l") {
      e.preventDefault();
      clearChat();
      return;
    }

    // Ctrl+B: Toggle sidebar
    if (e.ctrlKey && e.key === "b") {
      e.preventDefault();
      toggleSidebar();
      return;
    }

    // Ctrl+K: Focus command search
    if (e.ctrlKey && e.key === "k") {
      e.preventDefault();
      switchView("commands");
      setTimeout(() => {
        const searchInput = document.getElementById("cmd-search");
        if (searchInput) searchInput.focus();
      }, 100);
      return;
    }

    // Ctrl+M: Start/stop conversation with Lexa
    if (e.ctrlKey && e.key === "m") {
      e.preventDefault();
      startOrbConversation();
      return;
    }

    // Ctrl+F: Global Search
    if (e.ctrlKey && e.key === "f") {
      e.preventDefault();
      openSearchOverlay();
      return;
    }

    // Ctrl+N: New Conversation
    if (e.ctrlKey && e.key === "n") {
      e.preventDefault();
      newConversation();
      return;
    }

    // Ctrl+P: Command Palette
    if (e.ctrlKey && e.key === "p") {
      e.preventDefault();
      openPalette();
      return;
    }

    // Ctrl+T: New Todo (quick capture)
    if (e.ctrlKey && e.key === "t" && !e.shiftKey) {
      e.preventDefault();
      dashQuickTodo();
      return;
    }

    // Ctrl+Shift+S: Screenshot Analysis (Vision)
    if (e.ctrlKey && e.shiftKey && e.key === "S") {
      e.preventDefault();
      triggerScreenshotAnalysis();
      return;
    }

    // Ctrl+Shift+N: New Note (quick capture)
    if (e.ctrlKey && e.shiftKey && e.key === "N") {
      e.preventDefault();
      quickCreateNote();
      return;
    }

    // Ctrl+?: Keyboard shortcuts help overlay
    if (e.ctrlKey && e.key === "/") {
      e.preventDefault();
      showShortcutsOverlay();
      return;
    }
  });
}

// ── SCREENSHOT ANALYSIS (Ctrl+Shift+S) ──────────
async function triggerScreenshotAnalysis() {
  if (typeof showToast === "function") showToast("Screenshot wird analysiert...", "info");
  try {
    const result = await window.lexa.visionAnalyze("Beschreibe detailliert was auf diesem Screenshot zu sehen ist. Antworte auf Deutsch.");
    if (result && result.success && result.data && result.data.analysis) {
      if (typeof addMessage === "function") {
        addMessage("[Vision] " + result.data.analysis, "system");
      }
      if (typeof showToast === "function") showToast("Screenshot analysiert", "success");
    } else {
      const errMsg = (result && result.error) ? result.error : "Vision-Analyse fehlgeschlagen";
      if (typeof showToast === "function") showToast(errMsg, "error");
    }
  } catch (e) {
    console.error("[Vision] Screenshot analysis failed:", e);
    if (typeof showToast === "function") showToast("Vision-Analyse Fehler: " + (e.message || e), "error");
  }
}

// ── CLOCK ────────────────────────────────────────
function updateClock() {
  const now = new Date();
  const timeEl = document.getElementById("nav-time");
  if (timeEl) {
    timeEl.textContent = now.toLocaleTimeString(t._locale || "de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  const dashClock = document.getElementById("dash-clock");
  if (dashClock) {
    dashClock.textContent = now.toLocaleTimeString(t._locale || "de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }
  const dashDate = document.getElementById("dash-date");
  if (dashDate) {
    dashDate.textContent = now.toLocaleDateString(t._locale || "de-DE", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  }
}

// ── NAV MENU TOGGLE (slide-out hamburger menu) ──
function toggleNavMenu() {
  const sidebar = document.querySelector(".sidebar");
  const overlay = document.getElementById("nav-overlay");
  const menuBtn = document.getElementById("nav-menu-btn");
  if (!sidebar || !overlay) return;
  const isOpen = sidebar.classList.contains("open");

  if (isOpen) {
    sidebar.classList.remove("open");
    overlay.classList.remove("visible");
    if (menuBtn) menuBtn.setAttribute("aria-expanded", "false");
  } else {
    sidebar.classList.add("open");
    overlay.classList.add("visible");
    if (menuBtn) menuBtn.setAttribute("aria-expanded", "true");
  }
}

function toggleSidebar() {
  toggleNavMenu(); // Redirect to new menu system
}

function loadSidebarState() {
  // No longer needed — sidebar is slide-out overlay now
}

// ── HEALTH CHECK + RECONNECT ─────────────────────
function updateVersionLabels(version) {
  if (!version) return;
  LexaState.set("backendVersion", version);
  document.querySelectorAll('[data-role="backend-version"]').forEach((el) => {
    el.textContent = `v${version}`;
  });
}

async function checkHealth() {
  try {
    const res = await window.lexa.health();
    if (res.status === "ok") {
      if (!LexaState.get("backendOnline")) {
        showToast(t("toast.backendConnected"), "success");
        LexaState.set("reconnectAttempts", 0);
      }
      LexaState.set("backendOnline", true);
      updateVersionLabels(res.version);
      const uptimeLabel = res.uptime ? ` \u00b7 ${res.uptime}` : "";
      statusBadge.innerHTML = `
        <span class="status-dot online"></span>
        <span class="status-text">${t("app.statusOnline")}${uptimeLabel}</span>
      `;
      setNavStatus(t("app.statusOnlineNav"), "online");
      connBanner.classList.remove("visible");
    } else {
      handleOffline();
    }
  } catch (e) {
    console.warn("[Lexa:app] Health check failed:", e.message || e);
    handleOffline();
  }
}

function handleOffline() {
  if (LexaState.get("backendOnline")) {
    showToast(t("toast.backendLost"), "error");
    sendNotification("Lexa AI", t("app.backendLostNotif"));
  }
  LexaState.set("backendOnline", false);
  const attempts = (LexaState.get("reconnectAttempts") || 0) + 1;
  LexaState.set("reconnectAttempts", attempts);
  statusBadge.innerHTML = `
    <span class="status-dot offline"></span>
    <span class="status-text">${t("app.statusOffline", {attempts})}</span>
  `;
  setNavStatus(t("app.statusOfflineNav"), "offline");
  connBanner.classList.add("visible");
  // Show reconnect attempt count in banner
  const bannerText = document.querySelector("#connection-banner .banner-text");
  if (bannerText) {
    bannerText.textContent = t("app.bannerText", {attempts});
  }
}

// ── SYSTEM STATS ─────────────────────────────────
async function updateSystemStats() {
  if (!LexaState.get("backendOnline")) return;
  try {
    const res = await window.lexa.execute("system_info");
    if (res.success && res.data) {
      const d = res.data;

      const navCpu = document.getElementById("nav-cpu-percent");
      if (navCpu) navCpu.textContent = d.cpu_percent + "%";
      if (navCpu) colorStat("nav-cpu-percent", d.cpu_percent);

      // Also update dashboard bars if user is on dashboard
      if (LexaState.get("currentView") === "dashboard") {
        const setBar = (id, val, isGood) => {
          const el = document.getElementById(id);
          const bar = document.getElementById(id + "-bar");
          if (!el) return;
          el.textContent = val + "%";
          applyMetricTone(el, val);
          if (bar) applyMeterClass(bar, val, metricToneClass(val));
        };
        setBar("dash-cpu", d.cpu_percent);
        setBar("dash-ram", d.ram_percent);
        setBar("dash-disk", d.disk_percent);
      }
    }
  } catch (e) { console.warn("[Lexa:app] System stats update failed:", e.message || e); }
}

function colorStat(id, value) {
  const el = document.getElementById(id);
  if (!el) return;
  const cls = value > 80 ? "stat-danger" : value > 60 ? "stat-warn" : "";
  el.classList.remove("stat-danger", "stat-warn");
  if (cls) el.classList.add(cls);
}

// ── SIDEBAR ──────────────────────────────────────
function setupSidebar() {
  document.querySelectorAll(".sidebar-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchView(btn.dataset.view);
    });
  });
}

function switchView(view) {
  // Close nav menu when switching views
  const sidebar = document.querySelector(".sidebar");
  const overlay = document.getElementById("nav-overlay");
  if (sidebar) sidebar.classList.remove("open");
  if (overlay) overlay.classList.remove("visible");

  LexaState.set("currentView", view);

  // Stop all view-specific intervals when switching
  LexaState.clearInterval("dashboard");
  LexaState.clearInterval("memory");
  LexaState.clearInterval("pomodoro");

  document.querySelectorAll(".sidebar-btn").forEach((b) => {
    b.classList.remove("active");
    b.setAttribute("aria-selected", "false");
  });
  const activeBtn = document.querySelector(`[data-view="${view}"]`);
  if (activeBtn) {
    activeBtn.classList.add("active");
    activeBtn.setAttribute("aria-selected", "true");
  }

  const chatContainer = document.querySelector(".chat-container");
  if (chatContainer) chatContainer.classList.add("hidden");
  document.querySelectorAll(".system-view, .commands-view, .tool-view").forEach((v) => {
    v.classList.remove("active");
  });

  if (view === "dashboard") {
    document.getElementById("dashboard-view")?.classList.add("active");
    refreshDashboard();
    LexaState.setInterval("dashboard", refreshDashboard, LexaConfig.DASHBOARD_REFRESH_INTERVAL);
  } else if (view === "chat") {
    if (chatContainer) chatContainer.classList.remove("hidden");
  } else if (view === "system") {
    document.getElementById("system-view-ext").classList.add("active");
    refreshSystemView();
    refreshSysQuickBar();
  } else if (view === "commands") {
    let cv = document.querySelector(".commands-view");
    if (!cv) {
      cv = createCommandsView();
      document.querySelector(".content").appendChild(cv);
    }
    cv.classList.add("active");
  } else if (view === "productivity") {
    document.getElementById("productivity-view").classList.add("active");
    refreshProductivityView();
  } else if (view === "memory") {
    document.getElementById("memory-view").classList.add("active");
    refreshMemoryView();
    // Auto-refresh memory stats every 30s while in memory view
    LexaState.setInterval("memory", () => {
      if (LexaState.get("currentView") === "memory") refreshMemoryView();
    }, LexaConfig.MEMORY_REFRESH_INTERVAL);
  } else if (view === "settings") {
    document.getElementById("settings-view").classList.add("active");
    refreshSettingsView();
  }
}

// ── WAKE WORD ────────────────────────────────────
async function toggleWakeWord() {
  try {
    if (LexaState.get("wakeWordActive")) {
      await window.lexa.wakewordStop();
      LexaState.set("wakeWordActive", false);
      _stopWakeWordPolling();
      showToast(t("toast.wakewordDisabled"), "info", 2000);
    } else {
      const res = await window.lexa.wakewordStart();
      if (res.error) { showToast(t("toast.wakewordError", {error: res.error}), "error"); return; }
      LexaState.set("wakeWordActive", true);
      _startWakeWordPolling();
      showToast(t("toast.wakewordEnabled"), "success", 3000);
    }
    _updateWakeWordUI();
    const wakewordIndicator = document.getElementById("wakeword-indicator");
    if (wakewordIndicator) {
      wakewordIndicator.title = LexaState.get("wakeWordActive") ? t("nav.wakeWordTooltip") : t("nav.wakeWordTooltip");
    }
    localStorage.setItem("lexa-wakeword", LexaState.get("wakeWordActive") ? "on" : "off");
  } catch (e) {
    showToast(t("toast.wakewordUnavailable"), "error");
  }
}

function _updateWakeWordUI() {
  const active = LexaState.get("wakeWordActive");
  const indicator = document.getElementById("wakeword-indicator");
  if (indicator) {
    indicator.classList.toggle("active", active);
    indicator.title = active ? t("app.wakewordActive") : t("app.wakewordInactive");
  }
  const toggle = document.getElementById("wakeword-toggle");
  if (toggle) toggle.checked = active;
}

function _startWakeWordPolling() {
  _stopWakeWordPolling();
  _wakeWordPollInterval = setInterval(_pollWakeWordEvents, LexaConfig.WAKEWORD_POLL_INTERVAL);
}

function _stopWakeWordPolling() {
  if (_wakeWordPollInterval) {
    clearInterval(_wakeWordPollInterval);
    _wakeWordPollInterval = null;
  }
}

async function _pollWakeWordEvents() {
  if (!LexaState.get("wakeWordActive") || !LexaState.get("backendOnline")) return;
  try {
    const res = await window.lexa.wakewordEvents();
    if (!res.events || res.events.length === 0) return;

    for (const evt of res.events) {
      switch (evt.type) {
        case "volume":
          // Real-time volume from backend mic → drive 3D orb
          if (window.dashboardOrb) window.dashboardOrb.setVolume(evt.vol || 0);
              break;
        case "wake":
          // Wake word heard — show listening on orb
          if (LexaState.get("currentView") !== "chat") switchView("chat");
          _setOrbConversationState("listening");
          break;
        case "command":
          // User's command captured
          _setOrbConversationState("processing");
          if (evt.text) {
            if (LexaState.get("currentView") !== "chat") switchView("chat");
            if (!window._chatViewOpen && typeof toggleChatView === "function") toggleChatView();
            showOrbTranscript(evt.text, "");
            addMessage(evt.text, "user", null, false, true);
          }
          break;
        case "response":
          // AI response ready
          if (evt.text) {
            showOrbTranscript(undefined, evt.text);
            addMessage(evt.text, "system", null, false, true);
            if (!evt.tts_handled) {
              playTTS(evt.text);
            }
          }
          break;
        case "listening":
          // Listening for speech
          if (LexaState.get("currentView") !== "chat") switchView("chat");
          _setOrbConversationState("listening");
          break;
        case "conversation_start":
          // conversation mode active
          _updateConversationModeUI(true);
          _setOrbConversationState("listening");
          _stopWakeWordPolling();
          _wakeWordPollInterval = setInterval(_pollWakeWordEvents, LexaConfig.WAKEWORD_FAST_POLL_INTERVAL);
          break;
        case "conversation_end":
          // conversation mode ended
          _updateConversationModeUI(false);
          clearOrbTranscript();
          _setOrbConversationState(null);
          if (window.dashboardOrb) window.dashboardOrb.setVolume(0);
              showToast(t("toast.conversationEnded"), "info", 2000);
          // Back to normal polling speed
          _stopWakeWordPolling();
          _wakeWordPollInterval = setInterval(_pollWakeWordEvents, LexaConfig.WAKEWORD_POLL_INTERVAL);
          break;
        case "speaking":
          // Lexa is speaking (TTS playing from backend)
          showOrbListening(false);
          _setOrbConversationState("speaking");
          break;
        case "bargein":
          // User interrupted Lexa
          _setOrbConversationState("listening");
          showOrbListening(true);
          break;
        case "error":
          showOrbListening(false);
          _setOrbConversationState(null);
          showToast(t("toast.wakewordError", {error: evt.text || "unbekannt"}), "error");
          break;
      }
    }
  } catch (e) { console.warn("[Lexa:wakeword] Poll error:", e.message || e); }
}

function _updateConversationModeUI(active) {
  const orb = document.querySelector(".voice-orb");
  const indicator = document.getElementById("wakeword-indicator");
  if (orb) orb.classList.toggle("conversation-mode", active);
  if (indicator) {
    indicator.title = active ? t("toast.conversationMode") : t("nav.wakeWordTooltip");
  }
  if (active) {
    showToast(t("toast.conversationMode"), "success", 3000);
  }
}

function _setOrbConversationState(state) {
  const orbCanvas = document.getElementById("voice-orb-canvas");
  const statusEl = document.getElementById("orb-conversation-status");
  if (orbCanvas) {
    orbCanvas.classList.remove("conv-listening", "conv-processing", "conv-speaking", "conv-bargein");
    if (state) orbCanvas.classList.add("conv-" + state);
  }
  if (statusEl) {
    const labels = { listening: "Ich h\u00F6re zu...", processing: "Verarbeite...", speaking: "Lexa spricht...", bargein: "Unterbrochen..." };
    if (state && labels[state]) {
      statusEl.textContent = labels[state];
      statusEl.classList.remove("hidden");
      statusEl.className = "orb-conversation-status conv-status-" + state;
    } else {
      statusEl.textContent = "";
      statusEl.classList.add("hidden");
    }
  }
  if (window.dashboardOrb && window.dashboardOrb.setConversationState) {
    window.dashboardOrb.setConversationState(state);
  }
}

async function _initWakeWord() {
  const saved = localStorage.getItem("lexa-wakeword");
  // Auto-enable wake word unless explicitly disabled
  if (saved !== "off") {
    // Try up to 3 times with delay (backend may still be starting)
    for (let attempt = 1; attempt <= LexaConfig.WAKEWORD_MAX_RETRIES; attempt++) {
      try {
        const res = await window.lexa.wakewordStart();
        if (res && !res.error) {
          LexaState.set("wakeWordActive", true);
          _startWakeWordPolling();
          if (!saved) localStorage.setItem("lexa-wakeword", "on");
          console.log("[WakeWord] Aktiviert (Versuch " + attempt + ")");
          break;
        } else {
          console.warn("[WakeWord] " + t("common.error") + ":", res?.error || "unbekannt");
          if (attempt === 3) {
            showToast(t("toast.wakewordStartFailed", {error: res?.error || "unbekannt"}), "warning", 5000);
          }
        }
      } catch (err) {
        console.warn("[WakeWord] Versuch " + attempt + " fehlgeschlagen:", err.message || err);
        if (attempt < LexaConfig.WAKEWORD_MAX_RETRIES) {
          // Wait before retry (backend may not be ready yet)
          await new Promise(r => setTimeout(r, LexaConfig.WAKEWORD_RETRY_DELAY));
        } else {
          showToast(t("toast.wakewordNotAvailable"), "warning", 5000);
        }
      }
    }
  }
  _updateWakeWordUI();
}

// ── DIRECT CONVERSATION (Orb Click → same as Mic Button) ────────
// Orb click → start/stop voice recording
function startOrbConversation() {
  if (typeof voiceToggle === "function") voiceToggle();
  else showToast("Voice nicht verfuegbar", "error");
}
function stopOrbConversation() {
  if (typeof voiceStop === "function" && typeof Voice !== "undefined" && Voice.recording) voiceStop();
}

// ── VoiceStatusBar (stub — kept for compat) ────
const VoiceStatusBar = {
  _bar: null,
  _dot: null,
  _text: null,
  _meter: null,
  _meterCtx: null,
  _transcript: null,
  _latency: null,
  _provider: null,
  _visible: false,

  init() {
    this._bar = document.getElementById("voice-status-bar");
    this._dot = document.getElementById("voice-status-dot");
    this._text = document.getElementById("voice-status-text");
    this._meter = document.getElementById("voice-level-meter");
    this._meterCtx = this._meter?.getContext("2d");
    this._transcript = document.getElementById("voice-live-transcript");
    this._latency = document.getElementById("voice-latency");
    this._provider = document.getElementById("voice-provider-badge");
  },

  show() {
    if (!this._bar) this.init();
    if (this._bar) {
      this._bar.classList.remove("hidden");
      this._bar.classList.add("active");
      this._visible = true;
    }
  },

  hide() {
    if (this._bar) {
      this._bar.classList.add("hidden");
      this._bar.classList.remove("active");
      this._visible = false;
    }
  },

  setState(state) {
    if (!this._dot || !this._text) return;
    this._dot.className = "voice-dot " + state;
    const labels = {
      idle: "Bereit",
      listening: "\uD83C\uDFA4 Ich h\u00F6re zu...",
      processing: "\u26A1 Verarbeite Sprache...",
      speaking: "\uD83D\uDD0A Lexa spricht...",
      error: "\u274C Fehler",
      bargein: "\uD83C\uDFA4 Unterbrochen \u2014 h\u00F6re zu..."
    };
    this._text.textContent = labels[state] || state;
  },

  setVolume(vol) {
    if (!this._meterCtx || !this._meter) return;
    const ctx = this._meterCtx;
    const w = this._meter.width;
    const h = this._meter.height;
    ctx.clearRect(0, 0, w, h);

    // Background
    ctx.fillStyle = "rgba(255,255,255,0.03)";
    ctx.fillRect(0, 0, w, h);

    // Volume bar
    const barW = Math.max(2, vol * w);
    const gradient = ctx.createLinearGradient(0, 0, w, 0);
    gradient.addColorStop(0, "rgba(139, 92, 246, 0.8)");
    gradient.addColorStop(0.6, "rgba(236, 72, 153, 0.8)");
    gradient.addColorStop(1, "rgba(239, 68, 68, 0.8)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 2, barW, h - 4);

    // Peak indicator
    if (vol > 0.5) {
      ctx.fillStyle = "rgba(255, 200, 50, 0.9)";
      ctx.fillRect(barW - 3, 0, 3, h);
    }
  },

  setTranscript(text) {
    if (this._transcript) {
      this._transcript.textContent = text || "";
    }
  },

  setLatency(ms) {
    if (this._latency) {
      this._latency.textContent = ms > 0 ? ms + "ms" : "";
    }
  },

  setProvider(name) {
    if (this._provider) {
      this._provider.textContent = name || "";
    }
  }
};

// ── PERFORMANCE UTILITIES ────────────────────────
// Debounce utility
function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// Lazy load views — only refresh when actually visible
const viewRefreshMap = {
  system: debounce(refreshSystemView, LexaConfig.DEBOUNCE_VIEW_REFRESH),
  memory: debounce(refreshMemoryView, LexaConfig.DEBOUNCE_VIEW_REFRESH),
  settings: debounce(refreshSettingsView, LexaConfig.DEBOUNCE_VIEW_REFRESH),
  dashboard: debounce(refreshDashboard, LexaConfig.DEBOUNCE_VIEW_REFRESH),
};

// ── START ────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  init();
  checkOnboarding();
});
