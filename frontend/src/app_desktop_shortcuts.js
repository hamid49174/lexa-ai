/* App desktop integration, shortcuts, screenshot, and navigation helpers. Classic script loaded before app.js. */

const VIEW_KEYS = ["dashboard", "chat", "system", "commands", "productivity", "memory", "personal-os", "settings"];

function setupDesktopIntegration() {
  // Load notification preference
  const savedNotif = lexaStorageGet("lexa-notifications", "1");
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
  lexaStorageSet("lexa-notifications", enabled ? "1" : "0");
  showToast(enabled ? t("settings.notificationsOn") : t("settings.notificationsOff"), "info");
}

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

function visionStatusPayload(result) {
  return result?.data && typeof result.data === "object" ? result.data : (result || {});
}

function visionIsReady(status) {
  return Boolean(status?.available);
}

async function triggerScreenshotAnalysis() {
  try {
    if (window.lexa && typeof window.lexa.visionStatus === "function") {
      const statusResult = await window.lexa.visionStatus();
      const status = visionStatusPayload(statusResult);
      if (!visionIsReady(status)) {
        const message = t("vision.providerRequiredChat");
        if (typeof addMessage === "function") addMessage(message, "system");
        if (typeof showToast === "function") showToast(t("vision.providerRequiredToast"), "info");
        return;
      }
    }

    if (typeof showToast === "function") showToast(t("vision.analyzing"), "info");
    const result = await window.lexa.visionAnalyze("Beschreibe detailliert was auf diesem Screenshot zu sehen ist. Antworte auf Deutsch.");
    if (result && result.success && result.data && result.data.analysis) {
      if (typeof addMessage === "function") {
        addMessage(result.data.analysis, "system");
      }
      if (typeof showToast === "function") showToast(t("vision.analysisComplete"), "success");
    } else {
      if (typeof showToast === "function") showToast(t("vision.analysisFailed"), "error");
    }
  } catch (e) {
    console.error("[Vision] Screenshot analysis failed:", e);
    if (typeof showToast === "function") showToast(t("vision.analysisFailed"), "error");
  }
}

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
