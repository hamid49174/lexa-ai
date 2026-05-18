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
let _ambientCanvasRaf = 0;

function initLexaAmbientCanvas() {
  const canvas = document.getElementById("lexa-ambient-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;

  const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  let width = 0;
  let height = 0;
  let frame = 0;

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = Math.max(1, window.innerWidth);
    height = Math.max(1, window.innerHeight);
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };

  const draw = (time = 0) => {
    frame += 1;
    const tWave = reducedMotion ? 18 : time * 0.00035;
    ctx.clearRect(0, 0, width, height);

    const bg = ctx.createLinearGradient(0, 0, width, height);
    bg.addColorStop(0, "rgba(7, 11, 18, 0.96)");
    bg.addColorStop(0.48, "rgba(9, 9, 16, 0.98)");
    bg.addColorStop(1, "rgba(7, 15, 18, 0.96)");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);

    const gap = 44;
    ctx.lineWidth = 1;
    ctx.strokeStyle = "rgba(255, 255, 255, 0.018)";
    for (let x = -gap; x < width + gap; x += gap) {
      const drift = Math.sin(tWave + x * 0.01) * 8;
      ctx.beginPath();
      ctx.moveTo(x + drift, 0);
      ctx.lineTo(x - drift * 0.3, height);
      ctx.stroke();
    }
    for (let y = -gap; y < height + gap; y += gap) {
      const drift = Math.cos(tWave + y * 0.012) * 7;
      ctx.beginPath();
      ctx.moveTo(0, y + drift);
      ctx.lineTo(width, y - drift * 0.25);
      ctx.stroke();
    }

    const waveColors = [
      "rgba(91, 124, 250, 0.085)",
      "rgba(16, 185, 129, 0.06)",
      "rgba(194, 77, 224, 0.055)",
    ];
    for (let line = 0; line < 8; line += 1) {
      const base = height * (0.28 + line * 0.07);
      ctx.beginPath();
      for (let x = -20; x <= width + 20; x += 18) {
        const y = base
          + Math.sin(x * 0.009 + tWave * (1.6 + line * 0.08) + line) * (18 + line * 2)
          + Math.cos(x * 0.004 + tWave * 1.2) * 12;
        if (x === -20) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = waveColors[line % waveColors.length];
      ctx.lineWidth = line % 3 === 0 ? 0.85 : 0.62;
      ctx.stroke();
    }

    const topShade = ctx.createLinearGradient(0, 0, 0, height * 0.22);
    topShade.addColorStop(0, "rgba(5, 6, 11, 0.72)");
    topShade.addColorStop(1, "rgba(5, 6, 11, 0)");
    ctx.fillStyle = topShade;
    ctx.fillRect(0, 0, width, height * 0.24);

    const vignette = ctx.createRadialGradient(width * 0.5, height * 0.42, 0, width * 0.5, height * 0.42, Math.max(width, height) * 0.72);
    vignette.addColorStop(0, "rgba(255, 255, 255, 0.035)");
    vignette.addColorStop(0.58, "rgba(0, 0, 0, 0.02)");
    vignette.addColorStop(1, "rgba(0, 0, 0, 0.46)");
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, width, height);

    window.__lexaAmbientDebug = { frame, width, height, reducedMotion: Boolean(reducedMotion) };
    if (!reducedMotion) _ambientCanvasRaf = requestAnimationFrame(draw);
  };

  resize();
  window.addEventListener("resize", () => {
    resize();
    if (reducedMotion) draw(0);
  });
  if (_ambientCanvasRaf) cancelAnimationFrame(_ambientCanvasRaf);
  draw(0);
}

// ── GLOBAL STATE ─────────

function _chatInputShouldSendOnEnter(e) {
  if (!chatInput || e.key !== "Enter" || e.isComposing) return false;
  if (window.ctrlEnterMode) return e.ctrlKey || e.metaKey;
  return !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey;
}

function _chatInputAtHistoryBoundary(direction) {
  if (!chatInput) return false;
  const value = chatInput.value || "";
  if (value.trim() === "") return true;
  const start = typeof chatInput.selectionStart === "number" ? chatInput.selectionStart : value.length;
  const end = typeof chatInput.selectionEnd === "number" ? chatInput.selectionEnd : value.length;
  if (direction === "up") return start === 0 && end === 0;
  return start === value.length && end === value.length;
}

function _setChatInputValue(value) {
  if (!chatInput) return;
  chatInput.value = value;
  const cursor = chatInput.value.length;
  if (typeof chatInput.setSelectionRange === "function") chatInput.setSelectionRange(cursor, cursor);
  if (typeof syncChatInputSize === "function") syncChatInputSize();
}

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
let _wakeWordNextStatusCheck = 0;
let _wakeWordRestartTimer = null;
let _wakeWordRestartAttempts = 0;
let _orbRealtimeVoiceActive = false;

const VIEW_KEYS = ["dashboard", "chat", "system", "commands", "productivity", "memory", "personal-os", "settings"];

// ── EVENT DELEGATION (replaces all inline onclick/onchange/oninput in HTML) ──────
function _isKeyboardActionTarget(el) {
  if (!el?.dataset?.action) return false;
  const tag = String(el.tagName || "").toUpperCase();
  if (["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA", "OPTION"].includes(tag)) return false;
  return el.getAttribute("role") === "button" || el.tabIndex >= 0;
}

function _keyboardActionShouldActivate(e) {
  return e.key === "Enter" || e.key === " ";
}

function _isNativeInteractiveAction(el) {
  const tag = String(el?.tagName || "").toUpperCase();
  return ["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA", "OPTION", "LABEL"].includes(tag);
}

function _prepareActionElement(el) {
  if (!el?.dataset?.action || _isNativeInteractiveAction(el)) return;
  if (!el.hasAttribute("role")) el.setAttribute("role", "button");
  if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
}

function _setupActionAccessibility(root = document) {
  root.querySelectorAll?.("[data-action]").forEach(_prepareActionElement);
}

function _safeDispatch(el, ds, value) {
  try {
    _dispatch(el, ds, value);
  } catch (e) {
    const action = ds?.action || "unknown";
    console.warn("[Action] Handler failed:", action, e.message || e);
    if (typeof showToast === "function") {
      showToast(t("toast.executionError"), "error", 3000);
    }
  }
}

function _initDelegation() {
  _setupActionAccessibility();
  const actionObserver = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => {
        if (!(node instanceof Element)) return;
        _prepareActionElement(node);
        _setupActionAccessibility(node);
      });
    }
  });
  actionObserver.observe(document.body, { childList: true, subtree: true });

  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    _safeDispatch(el, el.dataset, null);
  });
  document.addEventListener("keydown", (e) => {
    if (!_keyboardActionShouldActivate(e)) return;
    const el = e.target.closest("[data-action]");
    if (!_isKeyboardActionTarget(el)) return;
    e.preventDefault();
    _safeDispatch(el, el.dataset, null);
  });
  document.addEventListener("change", (e) => {
    const el = e.target;
    if (!el.dataset || !el.dataset.action) return;
    _safeDispatch(el, el.dataset, el.type === "checkbox" ? el.checked : el.value);
  });
  document.addEventListener("input", (e) => {
    const el = e.target;
    if (!el.dataset || !el.dataset.action) return;
    _safeDispatch(el, el.dataset, el.value);
  });

  window.addEventListener("beforeunload", () => actionObserver.disconnect(), { once: true });
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
      let params = {};
      if (ds.params) {
        try {
          params = JSON.parse(ds.params);
        } catch (e) {
          console.warn("[Action] Invalid data-params for runTool:", e.message || e);
          showToast(t("toast.executionError"), "error", 3000);
          return;
        }
      }
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
    initLexaAmbientCanvas();
    if (typeof setupComposerCommandPalette === "function") setupComposerCommandPalette();
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
      if (_ambientCanvasRaf) cancelAnimationFrame(_ambientCanvasRaf);
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
        if (typeof syncChatInputSize === "function") syncChatInputSize();
        if (typeof updateComposerCommandPaletteFromInput === "function") updateComposerCommandPaletteFromInput();
      });
      chatInput.addEventListener("keydown", (e) => {
        if (typeof handleComposerCommandKeydown === "function" && handleComposerCommandKeydown(e)) return;
        if (e.key === "Enter") {
          if (!_chatInputShouldSendOnEnter(e)) return;
          e.preventDefault();
          if (typeof sendMessage === "function") sendMessage();
        } else if (e.key === "ArrowUp") {
          if (typeof chatInputHistory !== "undefined" && chatInputHistory.length > 0 && _chatInputAtHistoryBoundary("up")) {
            e.preventDefault();
            if (chatHistoryIdx === -1) chatInputDraft = chatInput.value;
            chatHistoryIdx = Math.min(chatHistoryIdx + 1, chatInputHistory.length - 1);
            _setChatInputValue(chatInputHistory[chatHistoryIdx]);
          }
        } else if (e.key === "ArrowDown") {
          if (typeof chatInputHistory !== "undefined" && chatHistoryIdx >= 0 && _chatInputAtHistoryBoundary("down")) {
            e.preventDefault();
            chatHistoryIdx--;
            if (chatHistoryIdx === -1) _setChatInputValue(chatInputDraft);
            else _setChatInputValue(chatInputHistory[chatHistoryIdx]);
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
      if (_wakeWordPreferenceOn() && !LexaState.get("wakeWordActive")) {
        await _ensureWakeWordRunning("Backend healthy");
      }
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
  if (LexaState.get("wakeWordActive")) {
    LexaState.set("wakeWordActive", false);
    _stopWakeWordPolling();
    _updateWakeWordUI();
  }
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
  LexaState.clearInterval("personal-os");
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
  } else if (view === "personal-os") {
    document.getElementById("personal-os-view").classList.add("active");
    refreshPersonalOsView();
    LexaState.setInterval("personal-os", () => {
      if (LexaState.get("currentView") === "personal-os") refreshPersonalOsView({ auto: true });
    }, LexaConfig.MEMORY_REFRESH_INTERVAL);
  } else if (view === "settings") {
    document.getElementById("settings-view").classList.add("active");
    refreshSettingsView();
  }
}

// ── WAKE WORD ────────────────────────────────────
function _wakeWordPreferenceOn() {
  return localStorage.getItem("lexa-wakeword") !== "off";
}

function _setWakeWordPreference(enabled) {
  localStorage.setItem("lexa-wakeword", enabled ? "on" : "off");
}

function _clearWakeWordRestart() {
  if (_wakeWordRestartTimer) {
    clearTimeout(_wakeWordRestartTimer);
    _wakeWordRestartTimer = null;
  }
}

async function _ensureWakeWordRunning(reason = "") {
  if (!_wakeWordPreferenceOn() || LexaState.get("wakeWordActive") || !LexaState.get("backendOnline")) return false;
  try {
    const res = await window.lexa.wakewordStart();
    if (_wakeWordStartOk(res)) {
      _wakeWordRestartAttempts = 0;
      _clearWakeWordRestart();
      LexaState.set("wakeWordActive", true);
      _startWakeWordPolling();
      _updateWakeWordUI();
      return true;
    }
    console.warn("[WakeWord] Auto-restart failed:", res?.error || reason || "unknown");
  } catch (e) {
    console.warn("[WakeWord] Auto-restart failed:", e.message || e);
  }
  return false;
}

function _scheduleWakeWordRestart(reason = "") {
  if (!_wakeWordPreferenceOn() || !LexaState.get("backendOnline") || _wakeWordRestartTimer) return;
  _wakeWordRestartAttempts += 1;
  const baseDelay = LexaConfig.WAKEWORD_RETRY_DELAY || 2000;
  const delay = Math.min(baseDelay * _wakeWordRestartAttempts, 60000);
  _wakeWordRestartTimer = setTimeout(async () => {
    _wakeWordRestartTimer = null;
    const restarted = await _ensureWakeWordRunning(reason);
    if (!restarted && _wakeWordPreferenceOn()) {
      _scheduleWakeWordRestart(reason);
    }
  }, delay);
}

function _wakeWordStartOk(res) {
  return Boolean(res && !res.error && res.status !== "failed" && res.active !== false && res.ready !== false);
}

function _wakeWordErrorText(res) {
  return res?.error || res?.detail || res?.message || "unbekannt";
}

function _markWakeWordInactive(reason = "", options = {}) {
  const keepPreference = Boolean(options.keepPreference);
  const autoRestart = Boolean(options.autoRestart);
  LexaState.set("wakeWordActive", false);
  _stopWakeWordPolling();
  _updateWakeWordUI();
  if (!keepPreference) _setWakeWordPreference(false);
  if (autoRestart) _scheduleWakeWordRestart(reason);
  if (reason) showToast(t("toast.wakewordError", {error: reason}), "warning", 4000);
}

async function toggleWakeWord() {
  try {
    if (LexaState.get("wakeWordActive")) {
      await window.lexa.wakewordStop();
      LexaState.set("wakeWordActive", false);
      _stopWakeWordPolling();
      _clearWakeWordRestart();
      _setWakeWordPreference(false);
      showToast(t("toast.wakewordDisabled"), "info", 2000);
    } else {
      _setWakeWordPreference(true);
      const res = await window.lexa.wakewordStart();
      if (!_wakeWordStartOk(res)) {
        _markWakeWordInactive("", { keepPreference: true, autoRestart: true });
        showToast(t("toast.wakewordError", {error: _wakeWordErrorText(res)}), "error");
        return;
      }
      LexaState.set("wakeWordActive", true);
      _startWakeWordPolling();
      showToast(t("toast.wakewordEnabled"), "success", 3000);
    }
    _updateWakeWordUI();
    const wakewordIndicator = document.getElementById("wakeword-indicator");
    if (wakewordIndicator) {
      wakewordIndicator.title = LexaState.get("wakeWordActive") ? t("nav.wakeWordTooltip") : t("nav.wakeWordTooltip");
    }
  } catch (e) {
    if (_wakeWordPreferenceOn()) {
      _markWakeWordInactive("", { keepPreference: true, autoRestart: true });
    }
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
  _wakeWordNextStatusCheck = 0;
  _wakeWordPollInterval = setInterval(_pollWakeWordEvents, LexaConfig.WAKEWORD_POLL_INTERVAL);
  _pollWakeWordEvents();
}

function _stopWakeWordPolling() {
  if (_wakeWordPollInterval) {
    clearInterval(_wakeWordPollInterval);
    _wakeWordPollInterval = null;
  }
}

async function _pollWakeWordEvents() {
  if (!LexaState.get("backendOnline")) return;
  if (!LexaState.get("wakeWordActive")) {
    if (!_wakeWordPreferenceOn()) return;
    const adopted = await _ensureWakeWordRunning("Wake poll adoption");
    if (!adopted) return;
    return;
  }
  try {
    const now = Date.now();
    if (now >= _wakeWordNextStatusCheck) {
      _wakeWordNextStatusCheck = now + 5000;
      const status = await window.lexa.wakewordStatus();
      if (status?.error || status?.active === false) {
        _markWakeWordInactive(_wakeWordErrorText(status), { keepPreference: true, autoRestart: true });
        return;
      }
    }

    const res = await window.lexa.wakewordEvents();
    if (!res.events || res.events.length === 0) return;

    for (const evt of res.events) {
      switch (evt.type) {
        case "volume":
          // Real-time volume from backend mic → drive 3D orb
          if (window.dashboardOrb) window.dashboardOrb.setVolume(evt.vol || 0);
          _voiceStatusBarEventUpdate({ volume: evt.vol || 0 });
              break;
        case "wake":
          // Wake word heard — show listening on orb
          if (LexaState.get("currentView") !== "chat") switchView("chat");
          _setOrbConversationState("listening");
          _voiceStatusBarEventUpdate({ state: "listening", provider: "Wake Word", transcript: _voiceText("app.voiceWakeHeard", "Wake word heard.") });
          break;
        case "command":
          // User's command captured
          _setOrbConversationState("processing");
          _voiceStatusBarEventUpdate({ state: "processing", provider: "STT -> AI", transcript: evt.text || _voiceText("app.voiceCommandProcessing", "Processing command.") });
          if (evt.text) {
            if (LexaState.get("currentView") !== "chat") switchView("chat");
            if (!window._chatViewOpen && typeof toggleChatView === "function") toggleChatView();
            showOrbTranscript(evt.text, "");
            addMessage(evt.text, "user", null, false, true);
          }
          break;
        case "response":
          // AI response ready
          _voiceStatusBarEventUpdate({
            state: evt.tts_handled ? "speaking" : "processing",
            provider: evt.tts_handled ? _voiceSpeechProviderLabel() : "AI",
            transcript: evt.tts_handled ? _voiceSpeakingResponseLabel() : (evt.text || ""),
          });
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
          _voiceStatusBarEventUpdate({ state: "listening", provider: "Wake Word", transcript: _voiceText("app.voiceListeningForCommand", "Listening for command.") });
          break;
        case "wake_timeout":
          _setOrbConversationState(null);
          if (window.dashboardOrb) window.dashboardOrb.setVolume(0);
          _voiceStatusBarEventUpdate({ state: "idle", provider: "", transcript: "", volume: 0 });
          showToast(_voiceText("app.voiceWakeNoCommand", "Wake word heard. Say the command after Lexa."), "info", 2200);
          break;
        case "conversation_start":
          // conversation mode active
          _updateConversationModeUI(true);
          _setOrbConversationState("listening");
          _voiceStatusBarEventUpdate({ state: "listening", provider: "Conversation", transcript: _voiceText("app.voiceConversationActive", "Conversation mode active.") });
          _stopWakeWordPolling();
          _wakeWordPollInterval = setInterval(_pollWakeWordEvents, LexaConfig.WAKEWORD_FAST_POLL_INTERVAL);
          break;
        case "conversation_end":
          // conversation mode ended
          _updateConversationModeUI(false);
          clearOrbTranscript();
          _setOrbConversationState(null);
          if (window.dashboardOrb) window.dashboardOrb.setVolume(0);
          _voiceStatusBarEventUpdate({ state: "idle", provider: "", transcript: "", volume: 0 });
              showToast(t("toast.conversationEnded"), "info", 2000);
          // Back to normal polling speed
          _stopWakeWordPolling();
          _wakeWordPollInterval = setInterval(_pollWakeWordEvents, LexaConfig.WAKEWORD_POLL_INTERVAL);
          break;
        case "speaking":
          // Lexa is speaking (TTS playing from backend)
          showOrbListening(false);
          _setOrbConversationState("speaking");
          _voiceStatusBarEventUpdate({
            state: "speaking",
            provider: _voiceSpeechProviderLabel(),
            transcript: _voiceSpeakingResponseLabel(),
          });
          break;
        case "bargein":
          // User interrupted Lexa
          _setOrbConversationState("listening");
          showOrbListening(true);
          _voiceStatusBarEventUpdate({ state: "bargein", provider: "Wake Word", transcript: evt.text || _voiceText("app.voiceInterruptedListening", "Interrupted, listening.") });
          break;
        case "error":
          showOrbListening(false);
          _setOrbConversationState(null);
          _voiceStatusBarEventUpdate({ state: "error", provider: "Wake Word", transcript: evt.text || _voiceText("app.voiceWakeError", "Wake word error.") });
          _scheduleWakeWordRestart(evt.text || "wake word event error");
          showToast(t("toast.wakewordError", {error: evt.text || "unbekannt"}), "error");
          break;
      }
    }
  } catch (e) { console.warn("[Lexa:wakeword] Poll error:", e.message || e); }
}

function _voiceStatusBarEventUpdate({ state, provider, transcript, latency, volume } = {}) {
  if (typeof VoiceStatusBar === "undefined") return;
  const safeState = state ? _voiceStatusState(state) : "";
  const volumeOnly = state === undefined
    && provider === undefined
    && transcript === undefined
    && latency === undefined
    && volume !== undefined;
  if (volumeOnly) {
    if (VoiceStatusBar._visible) VoiceStatusBar.setVolume(volume);
    return;
  }
  if (safeState === "speaking") {
    if (!VoiceStatusBar._bar && typeof VoiceStatusBar.init === "function") VoiceStatusBar.init();
    VoiceStatusBar.setState("idle");
    VoiceStatusBar.setProvider("");
    VoiceStatusBar.setTranscript("");
    VoiceStatusBar.setLatency(0);
    VoiceStatusBar.hide();
    return;
  }
  VoiceStatusBar.show();
  if (state) VoiceStatusBar.setState(safeState);
  if (provider !== undefined) VoiceStatusBar.setProvider(provider);
  if (transcript !== undefined) VoiceStatusBar.setTranscript(transcript);
  if (latency !== undefined) VoiceStatusBar.setLatency(latency);
  if (volume !== undefined) VoiceStatusBar.setVolume(volume);
}

function _voiceText(key, fallback, values = {}) {
  try {
    const text = typeof t === "function" ? t(key, values) : "";
    return text && text !== key ? text : fallback;
  } catch (e) {
    return fallback;
  }
}

function _voiceSpeechProviderLabel() {
  return _voiceText("app.voiceProviderSpeech", "Voice");
}

function _voiceSpeakingResponseLabel() {
  return _voiceText("app.voiceSpeakingResponse", "Speaking response.");
}

function _voiceStatusTextClip(value, max = 120) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text;
  return text.slice(0, Math.max(0, max - 12)).trimEnd() + " [truncated]";
}

function _voiceStatusSetText(el, value, max = 120) {
  if (!el) return "";
  const text = String(value || "").replace(/\s+/g, " ").trim();
  const clipped = _voiceStatusTextClip(text, max);
  el.textContent = clipped;
  if (text && clipped !== text) el.title = text;
  else if (typeof el.removeAttribute === "function") el.removeAttribute("title");
  return clipped;
}

function _voiceStatusState(state) {
  const safeStates = new Set(["idle", "listening", "processing", "speaking", "error", "bargein"]);
  const normalized = String(state || "idle").toLowerCase();
  return safeStates.has(normalized) ? normalized : "idle";
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

function _updateOrbActionA11y(active = false) {
  const orbCanvas = document.getElementById("voice-orb-canvas");
  const talkBtn = document.getElementById("talk-to-lexa-btn");
  const controls = [orbCanvas, talkBtn].filter(Boolean);
  if (controls.length === 0) return;
  const isActive = Boolean(active);
  const titleKey = isActive ? "app.orbClickEnd" : "app.orbClickSpeak";
  const labelKey = isActive ? "chat.endConversation" : "chat.talkToLexaBtn";
  const title = _voiceText(titleKey, isActive ? "Click to end" : "Click to speak");
  const label = _voiceText(labelKey, isActive ? "End conversation" : "Talk to Lexa");
  controls.forEach((control) => {
    control.dataset.i18nTitle = titleKey;
    control.dataset.i18nAriaLabel = labelKey;
    control.title = title;
    control.setAttribute("aria-label", label);
    control.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
  if (talkBtn) {
    talkBtn.classList.toggle("listening", isActive);
    const labelEl = talkBtn.querySelector("[data-voice-entry-label]");
    if (labelEl) {
      labelEl.dataset.i18n = labelKey;
      labelEl.textContent = label;
    }
  }
}

function _setOrbConversationState(state) {
  const safeState = state || null;
  const orbCanvas = document.getElementById("voice-orb-canvas");
  const orbContainer = document.getElementById("voice-orb-container");
  const statusEl = document.getElementById("orb-conversation-status");
  if (orbCanvas) {
    orbCanvas.classList.remove("conv-listening", "conv-processing", "conv-speaking", "conv-bargein");
    if (safeState) orbCanvas.classList.add("conv-" + safeState);
  }
  if (orbContainer) {
    orbContainer.classList.toggle("conversation-active", Boolean(safeState));
    if (safeState) orbContainer.dataset.convState = safeState;
    else delete orbContainer.dataset.convState;
  }
  if (statusEl) {
    const labels = {
      listening: _voiceText("app.orbListening", "Listening..."),
      processing: _voiceText("app.orbProcessing", "Processing..."),
      speaking: _voiceText("app.orbSpeaking", "Lexa is speaking..."),
      bargein: _voiceText("app.orbBargein", "Interrupted..."),
    };
    if (safeState && labels[safeState]) {
      statusEl.textContent = labels[safeState];
      statusEl.classList.remove("hidden");
      statusEl.className = "orb-conversation-status conv-status-" + safeState;
    } else {
      statusEl.textContent = "";
      statusEl.classList.add("hidden");
    }
  }
  if (window.dashboardOrb && window.dashboardOrb.setConversationState) {
    window.dashboardOrb.setConversationState(safeState);
  }
}
window.setOrbConversationState = _setOrbConversationState;

async function _initWakeWord() {
  // Auto-enable wake word unless explicitly disabled
  if (_wakeWordPreferenceOn()) {
    // Try up to 3 times with delay (backend may still be starting)
    for (let attempt = 1; attempt <= LexaConfig.WAKEWORD_MAX_RETRIES; attempt++) {
      try {
        const res = await window.lexa.wakewordStart();
        if (_wakeWordStartOk(res)) {
          LexaState.set("wakeWordActive", true);
          _startWakeWordPolling();
          _setWakeWordPreference(true);
          console.log("[WakeWord] Aktiviert (Versuch " + attempt + ")");
          break;
        } else {
          console.warn("[WakeWord] " + t("common.error") + ":", res?.error || "unbekannt");
          if (attempt === 3) {
            showToast(t("toast.wakewordStartFailed", {error: res?.error || "unbekannt"}), "warning", 5000);
            _scheduleWakeWordRestart(res?.error || "wake word start failed");
          }
        }
      } catch (err) {
        console.warn("[WakeWord] Versuch " + attempt + " fehlgeschlagen:", err.message || err);
        if (attempt < LexaConfig.WAKEWORD_MAX_RETRIES) {
          // Wait before retry (backend may not be ready yet)
          await new Promise(r => setTimeout(r, LexaConfig.WAKEWORD_RETRY_DELAY));
        } else {
          showToast(t("toast.wakewordNotAvailable"), "warning", 5000);
          _scheduleWakeWordRestart(err.message || "wake word unavailable");
        }
      }
    }
  }
  _updateWakeWordUI();
}

// ── DIRECT CONVERSATION (Orb Click → same as Mic Button) ────────
// Orb click → start/stop voice recording
function _voicePathLabel(path) {
  if (path === "cascaded_stt_llm_tts") return "STT -> AI -> TTS";
  return path || "Voice";
}

function _voiceRealtimeStarted(res) {
  const sessionState = String(res?.session_state || "").toLowerCase();
  return Boolean(
    res?.ok
    && res?.can_start !== false
    && sessionState !== "blocked"
    && sessionState !== "not_started"
    && sessionState !== "stopped"
  );
}

async function _primeOrbRealtimeBoundary() {
  if (typeof VoiceStatusBar === "undefined" || typeof window.lexa?.voiceRealtimeStart !== "function") return false;
  VoiceStatusBar.show();
  VoiceStatusBar.setState("processing");
  VoiceStatusBar.setProvider(_voiceText("app.voiceRealtimeChecking", "Realtime check"));
  try {
    const res = await window.lexa.voiceRealtimeStart();
    const blockers = Array.isArray(res?.blockers) ? res.blockers : [];
    VoiceStatusBar.setProvider(_voicePathLabel(res?.active_path));
    if (_voiceRealtimeStarted(res)) {
      _orbRealtimeVoiceActive = true;
      _updateOrbActionA11y(true);
      VoiceStatusBar.setState("listening");
      VoiceStatusBar.setTranscript(_voiceText("app.voiceRealtimeReady", "Realtime voice session ready."));
      return true;
    } else {
      const blocker = blockers[0] || _voiceText("app.voiceClassicFallbackActive", "Classic voice fallback active.");
      VoiceStatusBar.setTranscript(_voiceText("app.voiceClassicFallback", "Classic voice active: {{reason}}", { reason: blocker }));
    }
  } catch (e) {
    VoiceStatusBar.setProvider("STT -> AI -> TTS");
    VoiceStatusBar.setTranscript(_voiceText("app.voiceClassicFallbackActive", "Classic voice fallback active."));
  }
  _orbRealtimeVoiceActive = false;
  _updateOrbActionA11y(false);
  return false;
}

async function startOrbConversation() {
  if (_orbRealtimeVoiceActive) {
    await stopOrbConversation();
    return;
  }
  const isRecording = typeof Voice !== "undefined" && Voice.recording;
  if (!isRecording) {
    const realtimeStarted = await _primeOrbRealtimeBoundary();
    if (realtimeStarted) return;
  }
  if (typeof voiceToggle === "function") voiceToggle();
  else showToast("Voice nicht verfuegbar", "error");
}
async function stopOrbConversation() {
  if (typeof voiceStop === "function" && typeof Voice !== "undefined" && Voice.recording) {
    voiceStop();
    return;
  }
  if (!_orbRealtimeVoiceActive || typeof window.lexa?.voiceRealtimeStop !== "function") return;
  try {
    if (typeof VoiceStatusBar !== "undefined") {
      VoiceStatusBar.show();
      VoiceStatusBar.setState("processing");
      VoiceStatusBar.setProvider("Realtime");
      VoiceStatusBar.setTranscript(_voiceText("app.voiceRealtimeStopping", "Stopping realtime voice session."));
    }
    const res = await window.lexa.voiceRealtimeStop();
    _orbRealtimeVoiceActive = false;
    _updateOrbActionA11y(false);
    if (typeof VoiceStatusBar !== "undefined") {
      VoiceStatusBar.setState("idle");
      VoiceStatusBar.setProvider("");
      VoiceStatusBar.setTranscript(res?.session_state === "stopped"
        ? _voiceText("app.voiceRealtimeStopped", "Realtime voice stopped.")
        : _voiceText("app.voiceStopped", "Voice stopped."));
    }
  } catch (e) {
    _orbRealtimeVoiceActive = false;
    _updateOrbActionA11y(false);
    if (typeof VoiceStatusBar !== "undefined") {
      VoiceStatusBar.setState("error");
      VoiceStatusBar.setTranscript(_voiceText("app.voiceRealtimeStopFailed", "Realtime stop failed: {{error}}", { error: e.message || e }));
    }
  }
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
  _state: "idle",

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
    const safeState = _voiceStatusState(state);
    this._state = safeState;
    this._dot.className = "voice-dot " + safeState;
    if (this._bar) this._bar.dataset.state = this._state;
    if (safeState === "speaking" || safeState === "idle") this.clearVolume();
    const labels = {
      idle: _voiceText("app.voiceStateIdle", "Ready"),
      listening: _voiceText("app.voiceStateListening", "Listening"),
      processing: _voiceText("app.voiceStateProcessing", "Processing voice"),
      speaking: _voiceText("app.voiceStateSpeaking", "Lexa is speaking"),
      error: _voiceText("app.voiceStateError", "Error"),
      bargein: _voiceText("app.voiceStateBargein", "Interrupted, listening"),
    };
    _voiceStatusSetText(this._text, labels[safeState] || labels.idle, 48);
    this._refreshA11yLabel();
  },

  clearVolume() {
    if (!this._meterCtx || !this._meter) return;
    this._meterCtx.clearRect(0, 0, this._meter.width, this._meter.height);
  },

  setVolume(vol) {
    if (!this._meterCtx || !this._meter) return;
    const level = Math.max(0, Math.min(1, Number(vol) || 0));
    const ctx = this._meterCtx;
    const w = this._meter.width;
    const h = this._meter.height;
    ctx.clearRect(0, 0, w, h);

    const radius = 5;
    const drawRoundRect = (x, y, width, height, r) => {
      const safeR = Math.min(r, width / 2, height / 2);
      ctx.beginPath();
      ctx.moveTo(x + safeR, y);
      ctx.lineTo(x + width - safeR, y);
      ctx.quadraticCurveTo(x + width, y, x + width, y + safeR);
      ctx.lineTo(x + width, y + height - safeR);
      ctx.quadraticCurveTo(x + width, y + height, x + width - safeR, y + height);
      ctx.lineTo(x + safeR, y + height);
      ctx.quadraticCurveTo(x, y + height, x, y + height - safeR);
      ctx.lineTo(x, y + safeR);
      ctx.quadraticCurveTo(x, y, x + safeR, y);
      ctx.closePath();
    };

    drawRoundRect(0.5, 5.5, w - 1, h - 11, radius);
    ctx.fillStyle = "rgba(255,255,255,0.045)";
    ctx.fill();

    const barW = Math.max(level > 0 ? 3 : 0, level * (w - 1));
    if (barW <= 0) return;
    const gradient = ctx.createLinearGradient(0, 0, w, 0);
    gradient.addColorStop(0, "rgba(139, 146, 255, 0.72)");
    gradient.addColorStop(0.7, "rgba(199, 130, 255, 0.7)");
    gradient.addColorStop(1, "rgba(16, 185, 129, 0.72)");
    drawRoundRect(0.5, 5.5, barW, h - 11, radius);
    ctx.fillStyle = gradient;
    ctx.fill();

    if (level > 0.72) {
      ctx.fillStyle = "rgba(245, 158, 11, 0.75)";
      ctx.fillRect(Math.min(w - 3, barW - 2), 4, 2, h - 8);
    }
  },

  setTranscript(text) {
    if (this._transcript) {
      const clipped = _voiceStatusSetText(this._transcript, text, 140);
      this._transcript.classList.toggle("empty", !clipped);
      this._refreshA11yLabel();
    }
  },

  setLatency(ms) {
    if (this._latency) {
      _voiceStatusSetText(this._latency, Number(ms) > 0 ? `${Math.round(Number(ms))}ms` : "", 32);
      this._refreshA11yLabel();
    }
  },

  setProvider(name) {
    if (this._provider) {
      const clipped = _voiceStatusSetText(this._provider, name, 48);
      this._provider.classList.toggle("empty", !clipped);
      this._refreshA11yLabel();
    }
  },

  _refreshA11yLabel() {
    if (!this._bar) return;
    const parts = [
      this._text?.textContent,
      this._provider?.textContent,
      this._transcript?.textContent,
      this._latency?.textContent,
    ].map((part) => String(part || "").trim()).filter(Boolean);
    if (parts.length) {
      this._bar.setAttribute("aria-label", _voiceStatusTextClip(parts.join(" - "), 180));
    } else if (typeof this._bar.removeAttribute === "function") {
      this._bar.removeAttribute("aria-label");
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
