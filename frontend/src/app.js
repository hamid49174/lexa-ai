/* ════════════════════════════════════════════════
   LEXA AI — Frontend Application Logic v0.13
   Phase 13+14: Search & Export, AI Titles,
   Model Selection, Smart Conversations
   ════════════════════════════════════════════════ */

const chatMessages = document.getElementById("chat-messages");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const statusBadge = document.getElementById("status-badge");
const micBtn = document.getElementById("mic-btn");
const ttsToggle = document.getElementById("tts-toggle");
const connBanner = document.getElementById("connection-banner");

let isLoading = false;
let currentView = "chat";
let ttsEnabled = true;
let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let backendOnline = false;
let reconnectAttempts = 0;
let sidebarCollapsed = false;
let notificationsEnabled = true;
let dashboardInterval = null;
let currentConversationId = null;
let conversationsList = [];

const VIEW_KEYS = ["dashboard", "chat", "system", "commands", "browser", "files", "media", "memory", "settings"];

// ── TOAST SYSTEM ─────────────────────────────────
function showToast(message, type = "info", duration = 3500) {
  const container = document.getElementById("toast-container");
  const icons = { success: "\u2713", error: "\u2717", warning: "\u26A0", info: "\u2139" };
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || icons.info}</span>
    <span class="toast-text">${message}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("toast-out");
    toast.addEventListener("animationend", () => toast.remove());
  }, duration);
}

// ── INIT ─────────────────────────────────────────
async function init() {
  await checkHealth();
  setInterval(checkHealth, 8000);
  setInterval(updateSystemStats, 5000);
  setupSidebar();
  setupVoice();
  setupKeyboardShortcuts();
  setupDesktopIntegration();
  setupDragDrop();
  loadThemePreferences();
  loadSidebarState();
  updateSystemStats();
  await loadConversations();
}

// ── DESKTOP INTEGRATION (Phase 8) ───────────────
function setupDesktopIntegration() {
  // Load notification preference
  const savedNotif = localStorage.getItem("lexa-notifications");
  notificationsEnabled = savedNotif !== "0";

  // Listen for tray menu view switches
  if (window.lexa.onSwitchView) {
    window.lexa.onSwitchView((view) => switchView(view));
  }
}

function sendNotification(title, body) {
  if (!notificationsEnabled) return;
  try { window.lexa.notify(title, body); } catch {}
}

function toggleAutostart(enabled) {
  window.lexa.setAutostart(enabled);
  showToast(enabled ? "Autostart aktiviert" : "Autostart deaktiviert", "info");
  sendNotification("Lexa AI", enabled ? "Autostart aktiviert" : "Autostart deaktiviert");
}

function toggleNotifications(enabled) {
  notificationsEnabled = enabled;
  localStorage.setItem("lexa-notifications", enabled ? "1" : "0");
  showToast(enabled ? "Benachrichtigungen aktiviert" : "Benachrichtigungen deaktiviert", "info");
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

    // Escape: Back to chat + focus input
    if (e.key === "Escape") {
      if (currentView !== "chat") {
        switchView("chat");
      }
      chatInput.focus();
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

    // Ctrl+M: Toggle mic
    if (e.ctrlKey && e.key === "m") {
      e.preventDefault();
      toggleRecording();
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
  });
}

function clearChat() {
  const msgs = chatMessages.querySelectorAll(".message");
  msgs.forEach((m, i) => { if (i > 0) m.remove(); });
  localStorage.removeItem("lexa-chat-history");
  hideSuggestions();
  // Also clear conversation messages
  if (currentConversationId) {
    window.lexa.conversationUpdate(currentConversationId, { messages: [] }).catch(() => {});
  }
  showToast("Chat gel\u00f6scht", "info", 2000);
}

// ── CHAT PERSISTENCE ─────────────────────────────
function saveChatHistory() {
  const messages = [];
  chatMessages.querySelectorAll(".message").forEach((msg, i) => {
    if (i === 0) return;
    const text = msg.querySelector(".msg-text")?.textContent || "";
    const type = msg.classList.contains("user-message") ? "user" : "system";
    if (text) messages.push({ text, type });
  });
  const toSave = messages.slice(-50);
  try {
    localStorage.setItem("lexa-chat-history", JSON.stringify(toSave));
  } catch {}
}

function loadChatHistory() {
  try {
    const saved = localStorage.getItem("lexa-chat-history");
    if (!saved) return;
    const messages = JSON.parse(saved);
    if (!Array.isArray(messages) || messages.length === 0) return;
    messages.forEach((m) => {
      addMessage(m.text, m.type, null, false, true);
    });
  } catch {}
}

// ── SIDEBAR TOGGLE ───────────────────────────────
function toggleSidebar() {
  sidebarCollapsed = !sidebarCollapsed;
  const sidebar = document.querySelector(".sidebar");
  sidebar.classList.toggle("collapsed", sidebarCollapsed);
  localStorage.setItem("lexa-sidebar-collapsed", sidebarCollapsed ? "1" : "0");
}

function loadSidebarState() {
  const saved = localStorage.getItem("lexa-sidebar-collapsed");
  if (saved === "1") {
    sidebarCollapsed = true;
    document.querySelector(".sidebar").classList.add("collapsed");
  }
}

// ── HEALTH CHECK + RECONNECT ─────────────────────
async function checkHealth() {
  try {
    const res = await window.lexa.health();
    if (res.status === "ok") {
      if (!backendOnline) {
        showToast("Backend verbunden", "success");
        reconnectAttempts = 0;
      }
      backendOnline = true;
      statusBadge.innerHTML = `
        <span class="status-dot online"></span>
        <span class="status-text">Online</span>
      `;
      connBanner.classList.remove("visible");
    } else {
      handleOffline();
    }
  } catch {
    handleOffline();
  }
}

function handleOffline() {
  if (backendOnline) {
    showToast("Backend-Verbindung verloren", "error");
    sendNotification("Lexa AI", "Backend-Verbindung verloren!");
  }
  backendOnline = false;
  reconnectAttempts++;
  statusBadge.innerHTML = `
    <span class="status-dot offline"></span>
    <span class="status-text">Offline</span>
  `;
  connBanner.classList.add("visible");
}

// ── SYSTEM STATS ─────────────────────────────────
async function updateSystemStats() {
  if (!backendOnline) return;
  try {
    const res = await window.lexa.execute("system_info");
    if (res.success && res.data) {
      const d = res.data;
      document.getElementById("stat-cpu").textContent = d.cpu_percent + "%";
      document.getElementById("stat-ram").textContent = d.ram_percent + "%";
      document.getElementById("stat-disk").textContent = d.disk_percent + "%";
      colorStat("stat-cpu", d.cpu_percent);
      colorStat("stat-ram", d.ram_percent);
      colorStat("stat-disk", d.disk_percent);
    }
  } catch {}
}

function colorStat(id, value) {
  const el = document.getElementById(id);
  if (value > 80) el.style.color = "var(--error)";
  else if (value > 60) el.style.color = "var(--warning)";
  else el.style.color = "var(--accent2)";
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
  currentView = view;

  // Stop dashboard auto-refresh when leaving
  if (dashboardInterval) {
    clearInterval(dashboardInterval);
    dashboardInterval = null;
  }

  document.querySelectorAll(".sidebar-btn").forEach((b) => b.classList.remove("active"));
  document.querySelector(`[data-view="${view}"]`)?.classList.add("active");

  document.querySelector(".chat-container").style.display = "none";
  document.querySelectorAll(".system-view, .commands-view, .tool-view").forEach((v) => {
    v.classList.remove("active");
  });

  if (view === "dashboard") {
    document.getElementById("dashboard-view").classList.add("active");
    refreshDashboard();
    dashboardInterval = setInterval(refreshDashboard, 10000);
  } else if (view === "chat") {
    document.querySelector(".chat-container").style.display = "flex";
  } else if (view === "system") {
    let sv = document.querySelector(".system-view");
    if (!sv) {
      sv = createSystemView();
      document.querySelector(".content").appendChild(sv);
    }
    sv.classList.add("active");
    refreshSystemView();
  } else if (view === "commands") {
    let cv = document.querySelector(".commands-view");
    if (!cv) {
      cv = createCommandsView();
      document.querySelector(".content").appendChild(cv);
    }
    cv.classList.add("active");
  } else if (view === "browser") {
    document.getElementById("browser-view").classList.add("active");
  } else if (view === "files") {
    document.getElementById("files-view").classList.add("active");
  } else if (view === "media") {
    document.getElementById("media-view").classList.add("active");
  } else if (view === "memory") {
    document.getElementById("memory-view").classList.add("active");
    refreshMemoryView();
  } else if (view === "settings") {
    document.getElementById("settings-view").classList.add("active");
    refreshSettingsView();
  }
}

// ── SYSTEM VIEW ──────────────────────────────────
function createSystemView() {
  const div = document.createElement("div");
  div.className = "system-view active";
  div.innerHTML = `
    <div class="view-title">System <span>Monitor</span></div>
    <div class="info-grid" id="system-grid"></div>
  `;
  return div;
}

async function refreshSystemView() {
  const grid = document.getElementById("system-grid");
  if (!grid) return;
  if (!backendOnline) {
    grid.innerHTML = '<div class="info-card"><div class="info-card-value" style="font-size:16px;color:var(--error)">Backend nicht erreichbar</div></div>';
    return;
  }
  try {
    const res = await window.lexa.execute("system_info");
    if (!res.success) return;
    const d = res.data;
    grid.innerHTML = `
      <div class="info-card">
        <div class="info-card-label">CPU AUSLASTUNG</div>
        <div class="info-card-value">${d.cpu_percent}%</div>
        <div class="info-card-sub">${d.cpu_cores} Kerne @ ${d.cpu_freq_mhz || "?"} MHz</div>
      </div>
      <div class="info-card">
        <div class="info-card-label">RAM</div>
        <div class="info-card-value">${d.ram_used_gb} GB</div>
        <div class="info-card-sub">von ${d.ram_total_gb} GB (${d.ram_percent}%)</div>
      </div>
      <div class="info-card">
        <div class="info-card-label">FESTPLATTE</div>
        <div class="info-card-value">${d.disk_used_gb} GB</div>
        <div class="info-card-sub">von ${d.disk_total_gb} GB (${d.disk_percent}%)</div>
      </div>
      <div class="info-card">
        <div class="info-card-label">BATTERIE</div>
        <div class="info-card-value">${d.battery_percent !== null ? d.battery_percent + "%" : "N/A"}</div>
        <div class="info-card-sub">${d.battery_plugged ? "Wird geladen" : "Akku-Betrieb"}</div>
      </div>
    `;
  } catch {
    grid.innerHTML = '<div class="info-card"><div class="info-card-value" style="font-size:16px;color:var(--error)">Fehler beim Laden</div></div>';
  }
}

// ── COMMANDS VIEW (with search) ─────────────────
const ALL_COMMANDS = [
  { name: "app_open", desc: "App per Name starten", status: "allowed", cat: "BASIS" },
  { name: "app_list", desc: "Laufende Apps auflisten", status: "allowed", cat: "BASIS" },
  { name: "system_info", desc: "CPU, RAM, Disk Info", status: "allowed", cat: "BASIS" },
  { name: "screenshot", desc: "Desktop-Screenshot", status: "allowed", cat: "BASIS" },
  { name: "process_list", desc: "Prozesse anzeigen", status: "allowed", cat: "BASIS" },
  { name: "process_kill", desc: "Prozess beenden", status: "confirm", cat: "BASIS" },
  { name: "clipboard_read", desc: "Clipboard lesen", status: "allowed", cat: "BASIS" },
  { name: "clipboard_write", desc: "In Clipboard schreiben", status: "allowed", cat: "BASIS" },
  { name: "volume_set", desc: "Lautst\u00e4rke setzen", status: "allowed", cat: "BASIS" },
  { name: "volume_mute", desc: "Stummschalten", status: "allowed", cat: "BASIS" },
  { name: "file_search", desc: "Dateien suchen", status: "allowed", cat: "BASIS" },
  { name: "window_list", desc: "Fenster auflisten", status: "allowed", cat: "BASIS" },
  { name: "window_focus", desc: "Fenster fokussieren", status: "allowed", cat: "BASIS" },
  { name: "brightness_set", desc: "Helligkeit setzen", status: "allowed", cat: "BASIS" },
  { name: "wifi_status", desc: "WLAN-Status", status: "allowed", cat: "BASIS" },
  { name: "battery_status", desc: "Akku-Info", status: "allowed", cat: "BASIS" },
  { name: "timer_set", desc: "Timer stellen", status: "allowed", cat: "BASIS" },
  { name: "browser_open", desc: "URL \u00f6ffnen", status: "allowed", cat: "BASIS" },
  { name: "shutdown", desc: "PC herunterfahren", status: "confirm", cat: "BASIS" },
  { name: "restart", desc: "PC neustarten", status: "confirm", cat: "BASIS" },
  { name: "youtube_search", desc: "YouTube durchsuchen", status: "allowed", cat: "BROWSER" },
  { name: "youtube_play", desc: "YouTube-Video abspielen", status: "allowed", cat: "BROWSER" },
  { name: "web_open", desc: "URL im Browser \u00f6ffnen", status: "allowed", cat: "BROWSER" },
  { name: "web_screenshot", desc: "Website-Screenshot", status: "allowed", cat: "BROWSER" },
  { name: "web_pdf", desc: "Website als PDF", status: "allowed", cat: "BROWSER" },
  { name: "web_scrape", desc: "Text extrahieren", status: "allowed", cat: "BROWSER" },
  { name: "price_check", desc: "Preis pr\u00fcfen", status: "allowed", cat: "BROWSER" },
  { name: "browser_close", desc: "Browser schlie\u00dfen", status: "allowed", cat: "BROWSER" },
  { name: "find_duplicates", desc: "Doppelte Dateien finden", status: "confirm", cat: "DATEIEN" },
  { name: "batch_rename", desc: "Dateien umbenennen", status: "confirm", cat: "DATEIEN" },
  { name: "organize_downloads", desc: "Downloads sortieren", status: "confirm", cat: "DATEIEN" },
  { name: "merge_pdfs", desc: "PDFs zusammenf\u00fcgen", status: "confirm", cat: "DATEIEN" },
  { name: "split_pdf", desc: "PDF aufteilen", status: "confirm", cat: "DATEIEN" },
  { name: "disk_analysis", desc: "Speicher-Analyse", status: "allowed", cat: "DATEIEN" },
  { name: "clean_temp", desc: "Temp bereinigen", status: "confirm", cat: "DATEIEN" },
  { name: "media_play_pause", desc: "Play/Pause", status: "allowed", cat: "MEDIA" },
  { name: "media_next", desc: "N\u00e4chster Track", status: "allowed", cat: "MEDIA" },
  { name: "media_prev", desc: "Vorheriger Track", status: "allowed", cat: "MEDIA" },
  { name: "media_stop", desc: "Stoppen", status: "allowed", cat: "MEDIA" },
  { name: "spotify_open", desc: "Spotify \u00f6ffnen", status: "allowed", cat: "MEDIA" },
  { name: "convert_media", desc: "Format konvertieren", status: "allowed", cat: "MEDIA" },
  { name: "extract_audio", desc: "Audio extrahieren", status: "allowed", cat: "MEDIA" },
  { name: "screen_record", desc: "Bildschirmaufnahme", status: "allowed", cat: "MEDIA" },
  { name: "email_read", desc: "E-Mails lesen", status: "allowed", cat: "KOMMUNIKATION" },
  { name: "email_send", desc: "E-Mail senden", status: "confirm", cat: "KOMMUNIKATION" },
  { name: "telegram_read", desc: "Telegram lesen", status: "allowed", cat: "KOMMUNIKATION" },
  { name: "telegram_send", desc: "Telegram senden", status: "confirm", cat: "KOMMUNIKATION" },
  { name: "discord_send", desc: "Discord senden", status: "confirm", cat: "KOMMUNIKATION" },
  { name: "note_create", desc: "Notiz erstellen", status: "allowed", cat: "GED\u00c4CHTNIS" },
  { name: "note_read", desc: "Notiz lesen", status: "allowed", cat: "GED\u00c4CHTNIS" },
  { name: "note_list", desc: "Notizen auflisten", status: "allowed", cat: "GED\u00c4CHTNIS" },
  { name: "note_delete", desc: "Notiz l\u00f6schen", status: "confirm", cat: "GED\u00c4CHTNIS" },
  { name: "memory_search", desc: "Ged\u00e4chtnis durchsuchen", status: "allowed", cat: "GED\u00c4CHTNIS" },
  { name: "memory_add", desc: "Erinnerung hinzuf\u00fcgen", status: "allowed", cat: "GED\u00c4CHTNIS" },
  { name: "summarize", desc: "Text zusammenfassen", status: "allowed", cat: "GED\u00c4CHTNIS" },
  { name: "routine_create", desc: "Routine erstellen", status: "confirm", cat: "GED\u00c4CHTNIS" },
  { name: "routine_list", desc: "Routinen auflisten", status: "allowed", cat: "GED\u00c4CHTNIS" },
  { name: "routine_delete", desc: "Routine l\u00f6schen", status: "confirm", cat: "GED\u00c4CHTNIS" },
  { name: "routine_toggle", desc: "Routine an/aus", status: "confirm", cat: "GED\u00c4CHTNIS" },
];

function createCommandsView() {
  const div = document.createElement("div");
  div.className = "commands-view active";
  div.innerHTML = `
    <div class="view-title">Alle <span>Befehle</span></div>
    <div class="cmd-search-bar">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" id="cmd-search" class="cmd-search-input" placeholder="Befehl suchen... (Ctrl+K)" oninput="filterCommands(this.value)">
      <span class="cmd-count" id="cmd-count-badge">${ALL_COMMANDS.length} Befehle</span>
    </div>
    <div id="cmd-results"></div>
  `;
  setTimeout(() => renderCommands(""), 0);
  return div;
}

function filterCommands(query) {
  renderCommands(query.toLowerCase().trim());
}

function renderCommands(query) {
  const container = document.getElementById("cmd-results");
  if (!container) return;

  const statusLabel = { allowed: "ERLAUBT", confirm: "BEST\u00c4TIGUNG", blocked: "BLOCKIERT" };
  const filtered = query
    ? ALL_COMMANDS.filter(c => c.name.includes(query) || c.desc.toLowerCase().includes(query) || c.cat.toLowerCase().includes(query))
    : ALL_COMMANDS;

  const badge = document.getElementById("cmd-count-badge");
  if (badge) badge.textContent = `${filtered.length} Befehle`;

  const grouped = {};
  for (const c of filtered) {
    if (!grouped[c.cat]) grouped[c.cat] = [];
    grouped[c.cat].push(c);
  }

  let html = "";
  for (const [cat, cmds] of Object.entries(grouped)) {
    html += `<div class="cmd-category"><div class="cmd-category-title">${cat}</div><div class="cmd-list">`;
    for (const c of cmds) {
      const highlight = query ? c.name.replace(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, "gi"), '<mark>$1</mark>') : c.name;
      html += `
        <div class="cmd-item" onclick="insertCommand('${c.name}')">
          <div class="cmd-name">${highlight}</div>
          <div class="cmd-desc">${c.desc}</div>
          <span class="cmd-badge ${c.status}">${statusLabel[c.status]}</span>
        </div>`;
    }
    html += `</div></div>`;
  }

  if (filtered.length === 0) {
    html = '<div class="empty-state">Kein Befehl gefunden.</div>';
  }
  container.innerHTML = html;
}

function insertCommand(cmd) {
  switchView("chat");
  chatInput.value = cmd.replace(/_/g, " ");
  chatInput.focus();
}

// ── TOOL QUICK ACTIONS ──────────────────────────
async function quickAction(command, promptText, paramKey) {
  if (!backendOnline) { showToast("Backend nicht verbunden", "error"); return; }
  const value = prompt(promptText);
  if (!value && value !== "") return;

  let params = {};
  if (paramKey === "pdf_paths") {
    params[paramKey] = value.split(",").map((s) => s.trim());
  } else {
    params[paramKey] = value;
  }

  switchView("chat");
  addMessage(`${command}: ${value}`, "user");
  showTyping();

  try {
    const res = await window.lexa.execute(command, params, true);
    hideTyping();
    if (res.success) {
      const summary = typeof res.data === "string" ? res.data : JSON.stringify(res.data, null, 2).substring(0, 500);
      addMessage(summary, "system");
      showToast(`${command} erfolgreich`, "success");
      sendNotification("Lexa AI", `${command} erfolgreich ausgef\u00fchrt`);
    } else {
      addMessage("Fehler: " + (res.error || "Unbekannter Fehler"), "system");
      showToast(`${command} fehlgeschlagen`, "error");
    }
  } catch (err) {
    hideTyping();
    addMessage("Fehler: " + err.message, "system");
    showToast("Verbindungsfehler", "error");
  }
}

async function runTool(command, params = {}) {
  if (!backendOnline) { showToast("Backend nicht verbunden", "error"); return; }
  switchView("chat");
  addMessage(`Starte ${command}...`, "user");
  showTyping();

  try {
    const res = await window.lexa.execute(command, params, true);
    hideTyping();
    if (res.success) {
      const summary = typeof res.data === "string" ? res.data : JSON.stringify(res.data, null, 2).substring(0, 500);
      addMessage(summary, "system");
      showToast(`${command} erledigt`, "success");
      sendNotification("Lexa AI", `${command} erledigt`);
    } else {
      addMessage("Fehler: " + (res.error || "Unbekannter Fehler"), "system");
      showToast(`${command} fehlgeschlagen`, "error");
    }
  } catch (err) {
    hideTyping();
    addMessage("Fehler: " + err.message, "system");
    showToast("Verbindungsfehler", "error");
  }
}

// ── CHAT ─────────────────────────────────────────
function addMessage(text, type = "system", action = null, requiresConfirmation = false, silent = false) {
  const msg = document.createElement("div");
  msg.className = `message ${type}-message`;

  const isUser = type === "user";
  const avatarClass = isUser ? "user" : "system";
  const avatarIcon = isUser ? "&#128100;" : "&#9889;";
  const nameText = isUser ? "Du" : "Lexa";

  let actionHtml = "";
  if (action) {
    actionHtml = `
      <div class="msg-action">
        <div class="action-label">AKTION</div>
        <div class="action-cmd">${action.action}(${JSON.stringify(action.params || {})})</div>
      </div>`;
  }

  let confirmHtml = "";
  if (requiresConfirmation && action) {
    const actionStr = encodeURIComponent(JSON.stringify(action));
    confirmHtml = `
      <button class="confirm-btn" onclick="confirmAction(this, '${actionStr}')">Best\u00e4tigen</button>
      <button class="deny-btn" onclick="denyAction(this)">Abbrechen</button>`;
  }

  const timeStr = new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });

  msg.innerHTML = `
    <div class="msg-avatar ${avatarClass}">${avatarIcon}</div>
    <div class="msg-body">
      <div class="msg-header">
        <span class="msg-name">${nameText}</span>
        <span class="msg-time">${timeStr}</span>
        <button class="msg-copy-btn" onclick="copyMessage(this)" title="Kopieren">&#128203;</button>
      </div>
      <div class="msg-text">${formatMessage(text)}</div>
      ${actionHtml}
      ${confirmHtml}
    </div>`;

  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  if (!silent) saveChatHistory();
}

function copyMessage(btn) {
  const text = btn.closest(".msg-body").querySelector(".msg-text")?.textContent || "";
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = "\u2713";
    setTimeout(() => { btn.textContent = "\u{1F4CB}"; }, 1500);
  });
}

function denyAction(btn) {
  const parent = btn.parentElement;
  parent.querySelector(".confirm-btn")?.remove();
  btn.textContent = "Abgebrochen";
  btn.disabled = true;
  btn.style.color = "var(--text-muted)";
  showToast("Aktion abgebrochen", "warning");
}

function formatMessage(text) {
  // Code blocks (triple backticks)
  text = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const escaped = code.replace(/</g, "&lt;").replace(/>/g, "&gt;").trim();
    return `<pre class="code-block"><code>${escaped}</code></pre>`;
  });
  // Inline code
  text = text.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
  // Bold
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // Italic
  text = text.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  // Links
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="chat-link" target="_blank">$1</a>');
  // Newlines
  text = text.replace(/\n/g, "<br>");
  return text;
}

function showTyping() {
  const div = document.createElement("div");
  div.className = "message system-message";
  div.id = "typing-indicator";
  div.innerHTML = `
    <div class="msg-avatar system">&#9889;</div>
    <div class="msg-body">
      <div class="typing-indicator"><span></span><span></span><span></span></div>
    </div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideTyping() {
  document.getElementById("typing-indicator")?.remove();
}

async function sendMessage() {
  const text = chatInput.value.trim();
  if (!text || isLoading) return;
  if (!backendOnline) { showToast("Backend nicht verbunden", "error"); return; }

  // Auto-create conversation if none active
  if (!currentConversationId) {
    try {
      const result = await window.lexa.conversationCreate("Neuer Chat");
      currentConversationId = result.id;
      localStorage.setItem("lexa-active-conversation", result.id);
      const data = await window.lexa.conversations();
      conversationsList = data.conversations || [];
      renderConversationList();
    } catch {}
  }

  // Auto-title from first message
  const isFirstMessage = chatMessages.querySelectorAll(".user-message").length === 0;

  addMessage(text, "user");
  chatInput.value = "";
  chatInput.style.height = "auto";
  isLoading = true;
  sendBtn.disabled = true;
  hideSuggestions();

  if (isFirstMessage) autoTitleConversation(text);

  // Create streaming message element
  const msgEl = document.createElement("div");
  msgEl.className = "message system-message";
  const timeStr = new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  msgEl.innerHTML = `
    <div class="msg-avatar system">&#9889;</div>
    <div class="msg-body">
      <div class="msg-header">
        <span class="msg-name">Lexa</span>
        <span class="msg-time">${timeStr}</span>
        <button class="msg-copy-btn" onclick="copyMessage(this)" title="Kopieren">&#128203;</button>
      </div>
      <div class="msg-text streaming-text"><span class="streaming-cursor"></span></div>
    </div>`;
  chatMessages.appendChild(msgEl);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  const textEl = msgEl.querySelector(".msg-text");
  let fullText = "";
  let actionData = null;
  let requiresConfirmation = false;

  try {
    const response = await fetch("http://127.0.0.1:8000/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });

    if (!response.ok) {
      // Fallback to non-streaming
      const errData = await response.json().catch(() => ({}));
      textEl.classList.remove("streaming-text");
      textEl.innerHTML = formatMessage(errData.detail || "Fehler beim Verbinden.");
      isLoading = false;
      sendBtn.disabled = false;
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;

        try {
          const data = JSON.parse(raw);
          if (data.c) {
            fullText += data.c;
            textEl.innerHTML = formatMessage(fullText) + '<span class="streaming-cursor"></span>';
            chatMessages.scrollTop = chatMessages.scrollHeight;
          }
          if (data.done) {
            actionData = data.action;
            requiresConfirmation = data.rc;
          }
        } catch {}
      }
    }

    // Finalize: remove cursor, apply formatting
    textEl.classList.remove("streaming-text");
    textEl.innerHTML = formatMessage(fullText);

    // Handle action
    if (actionData) {
      const actionHtml = `
        <div class="msg-action">
          <div class="action-label">AKTION</div>
          <div class="action-cmd">${actionData.action}(${JSON.stringify(actionData.params || {})})</div>
        </div>`;
      const body = msgEl.querySelector(".msg-body");

      if (requiresConfirmation) {
        const actionStr = encodeURIComponent(JSON.stringify(actionData));
        body.insertAdjacentHTML("beforeend", actionHtml + `
          <button class="confirm-btn" onclick="confirmAction(this, '${actionStr}')">Best\u00e4tigen</button>
          <button class="deny-btn" onclick="denyAction(this)">Abbrechen</button>`);
      } else {
        body.insertAdjacentHTML("beforeend", actionHtml);
        try {
          const execResult = await window.lexa.execute(actionData.action, actionData.params || {});
          if (execResult.success && execResult.data) {
            const summary = typeof execResult.data === "string" ? execResult.data : JSON.stringify(execResult.data).substring(0, 200);
            addMessage("Ausgef\u00fchrt: " + summary, "system");
            showToast(`${actionData.action} erledigt`, "success", 2500);
            sendNotification("Lexa AI", `${actionData.action} erledigt`);
          }
        } catch {}
      }
    }

    // TTS
    playTTS(actionData?.message || fullText);

    // Smart Suggestions
    showSuggestions(fullText, actionData);

  } catch (err) {
    textEl.classList.remove("streaming-text");
    textEl.innerHTML = "Backend nicht erreichbar. Ist der Server gestartet?";
    showToast("Chat-Fehler: Backend offline", "error");
  }

  saveChatHistory();
  saveCurrentConversation();
  isLoading = false;
  sendBtn.disabled = false;
}

async function confirmAction(btn, actionStr) {
  const action = JSON.parse(decodeURIComponent(actionStr));
  btn.textContent = "Wird ausgef\u00fchrt...";
  btn.disabled = true;

  try {
    const res = await window.lexa.execute(action.action, action.params || {}, true);
    if (res.success) {
      addMessage(`Ausgef\u00fchrt: ${JSON.stringify(res.data).substring(0, 200)}`, "system");
      showToast(`${action.action} ausgef\u00fchrt`, "success");
    } else {
      addMessage(`Fehler: ${res.error}`, "system");
      showToast(`${action.action} fehlgeschlagen`, "error");
    }
  } catch {
    addMessage("Fehler bei der Ausf\u00fchrung.", "system");
    showToast("Ausf\u00fchrungsfehler", "error");
  }
}

// ── EVENT LISTENERS ──────────────────────────────
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
});
sendBtn.addEventListener("click", sendMessage);

// ── VOICE ────────────────────────────────────────
function setupVoice() {
  ttsToggle.classList.toggle("active", ttsEnabled);
  ttsToggle.addEventListener("click", () => {
    ttsEnabled = !ttsEnabled;
    ttsToggle.classList.toggle("active", ttsEnabled);
    showToast(ttsEnabled ? "Sprachausgabe aktiviert" : "Sprachausgabe deaktiviert", "info", 2000);
  });
  micBtn.addEventListener("click", toggleRecording);
}

async function toggleRecording() {
  if (isRecording) stopRecording(); else startRecording();
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
    audioChunks = [];
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(audioChunks, { type: "audio/webm" });
      await processVoiceInput(blob);
    };
    mediaRecorder.start();
    isRecording = true;
    micBtn.classList.add("recording");
    document.getElementById("voice-status-hint").textContent = "Aufnahme l\u00e4uft... Klicke zum Stoppen";
    // Orb animation
    const orb = document.getElementById("voice-orb");
    const orbLabel = document.getElementById("voice-orb-label");
    if (orb) orb.classList.add("listening");
    if (orbLabel) orbLabel.textContent = "H\u00f6re zu...";
    showToast("Aufnahme gestartet", "info", 2000);
  } catch (err) {
    addMessage("Mikrofon-Zugriff verweigert. Bitte erlaube den Zugriff.", "system");
    showToast("Mikrofon blockiert", "error");
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
  isRecording = false;
  micBtn.classList.remove("recording");
  document.getElementById("voice-status-hint").textContent = "Mikrofon: klicken zum Sprechen";
  // Orb reset
  const orb = document.getElementById("voice-orb");
  const orbLabel = document.getElementById("voice-orb-label");
  if (orb) orb.classList.remove("listening");
  if (orbLabel) orbLabel.textContent = "Klicken zum Sprechen";
}

async function processVoiceInput(audioBlob) {
  showTyping();
  try {
    const result = await window.lexa.stt(audioBlob);
    hideTyping();
    if (result.success && result.text) {
      addMessage(result.text, "user");
      isLoading = true; sendBtn.disabled = true; showTyping();
      const chatRes = await window.lexa.chat(result.text);
      hideTyping();
      handleChatResponse(chatRes);
    } else {
      addMessage("Konnte nichts verstehen. Bitte nochmal versuchen.", "system");
      showToast("Spracherkennung: nichts erkannt", "warning");
    }
  } catch {
    hideTyping();
    addMessage("Spracherkennung nicht verf\u00fcgbar.", "system");
    showToast("STT nicht verf\u00fcgbar", "error");
  }
  isLoading = false; sendBtn.disabled = false;
}

async function playTTS(text) {
  if (!ttsEnabled) return;
  try {
    const audioUrl = await window.lexa.tts(text);
    if (audioUrl) new Audio(audioUrl).play();
  } catch {}
}

function handleChatResponse(res) {
  if (res.detail) {
    addMessage(res.detail, "system");
    if (res.detail.includes("Zu viele")) showToast("Rate Limit erreicht", "warning");
  } else {
    addMessage(res.reply, "system", res.action, res.requires_confirmation);
    playTTS(res.reply);
    if (res.action && !res.requires_confirmation) {
      window.lexa.execute(res.action.action, res.action.params || {}).then((execResult) => {
        if (execResult.success && execResult.data) {
          const summary = typeof execResult.data === "string" ? execResult.data : JSON.stringify(execResult.data).substring(0, 200);
          addMessage("Ausgef\u00fchrt: " + summary, "system");
          showToast(`${res.action.action} erledigt`, "success", 2500);
        }
      }).catch(() => showToast("Ausf\u00fchrungsfehler", "error"));
    }
  }
}

// ── MEMORY VIEW ──────────────────────────────────
async function refreshMemoryView() {
  if (!backendOnline) return;

  const stats = await window.lexa.memoryStats();
  const statsGrid = document.getElementById("memory-stats-grid");
  if (statsGrid) {
    statsGrid.innerHTML = `
      <div class="info-card"><div class="info-card-label">NOTIZEN</div><div class="info-card-value">${stats.notes || 0}</div></div>
      <div class="info-card"><div class="info-card-label">ERINNERUNGEN</div><div class="info-card-value">${stats.memories || 0}</div></div>
      <div class="info-card"><div class="info-card-label">INTERAKTIONEN</div><div class="info-card-value">${stats.interactions || 0}</div></div>
      <div class="info-card"><div class="info-card-label">ROUTINEN</div><div class="info-card-value">${stats.routines || 0}</div></div>
    `;
  }

  const notesData = await window.lexa.notes();
  const notesList = document.getElementById("notes-list");
  if (notesList) {
    notesList.innerHTML = (notesData.notes?.length > 0)
      ? notesData.notes.map(n => `<div class="note-card"><div class="note-title">${n.title}</div><div class="note-meta">${n.category} &middot; ${n.created_at || ""}</div></div>`).join("")
      : '<div class="empty-state">Keine Notizen. Sag Lexa "Erstelle eine Notiz..."</div>';
  }

  // Snippets
  try {
    const snippetsData = await window.lexa.snippets();
    const snippetsList = document.getElementById("snippets-list");
    if (snippetsList) {
      snippetsList.innerHTML = (snippetsData.snippets?.length > 0)
        ? snippetsData.snippets.map(s => `
          <div class="note-card snippet-card" onclick="useSnippet('${escapeHtml(s.text).replace(/'/g, "\\'")}')">
            <div class="note-title">${escapeHtml(s.name)}</div>
            <div class="note-meta">${s.text.length > 50 ? escapeHtml(s.text.substring(0, 50)) + "\u2026" : escapeHtml(s.text)}</div>
            <button class="snippet-delete" onclick="event.stopPropagation();deleteSnippet('${escapeHtml(s.name).replace(/'/g, "\\'")}')">\u00d7</button>
          </div>`).join("")
        : '<div class="empty-state">Keine Snippets. Erstelle wiederverwendbare Textbausteine.</div>';
    }
  } catch {}

  const aiStatus = await window.lexa.aiStatus();
  const aiPanel = document.getElementById("ai-status-panel");
  if (aiPanel) {
    const ga = aiStatus.groq?.available, oa = aiStatus.ollama?.available, models = aiStatus.ollama?.models || [];
    aiPanel.innerHTML = `
      <div class="info-card provider-card"><span class="provider-dot ${ga ? "active" : "inactive"}"></span><div><div style="font-weight:600;color:var(--text)">Groq API</div><div style="font-size:11px;color:var(--text-muted)">Llama 3.3 70B &middot; ${ga ? "Verbunden" : "Offline"}</div></div></div>
      <div class="info-card provider-card"><span class="provider-dot ${oa ? "active" : "inactive"}"></span><div><div style="font-weight:600;color:var(--text)">Ollama (Lokal)</div><div style="font-size:11px;color:var(--text-muted)">${oa ? models.join(", ") || "Bereit" : "Nicht gestartet"}</div></div></div>
    `;
  }

  const routinesData = await window.lexa.routines();
  const routinesList = document.getElementById("routines-list");
  if (routinesList) {
    routinesList.innerHTML = (routinesData.routines?.length > 0)
      ? routinesData.routines.map(r => `<div class="routine-card"><div class="routine-info"><div class="routine-name">${r.name}</div><div class="routine-schedule">${r.schedule} ${r.description ? "&middot; " + r.description : ""}</div></div><div class="routine-toggle ${r.enabled ? "enabled" : ""}" onclick="toggleRoutine('${r.name}')"></div></div>`).join("")
      : '<div class="empty-state">Keine Routinen. Sag Lexa "Erstelle eine Morgenroutine..."</div>';
  }
}

async function createNote() {
  const title = prompt("Notiz-Titel:"); if (!title) return;
  const content = prompt("Notiz-Inhalt:"); if (!content) return;
  await window.lexa.execute("note_create", { title, content }, true);
  showToast("Notiz erstellt", "success");
  refreshMemoryView();
}

async function createRoutine() {
  switchView("chat");
  chatInput.value = "Erstelle eine neue Routine f\u00fcr mich";
  chatInput.focus();
}

async function toggleRoutine(name) {
  await window.lexa.execute("routine_toggle", { name }, true);
  showToast(`Routine "${name}" umgeschaltet`, "info");
  refreshMemoryView();
}

// ── SETTINGS VIEW ────────────────────────────────
async function refreshSettingsView() {
  // Desktop settings (work even when backend is offline)
  try {
    const autostartToggle = document.getElementById("autostart-toggle");
    if (autostartToggle) autostartToggle.checked = window.lexa.getAutostart();
  } catch {}
  const notifToggle = document.getElementById("notifications-toggle");
  if (notifToggle) notifToggle.checked = notificationsEnabled;

  if (!backendOnline) return;

  const ai = await window.lexa.aiStatus();
  const groqEl = document.getElementById("groq-status");
  const ollamaEl = document.getElementById("ollama-status");
  if (groqEl) { groqEl.textContent = ai.groq?.available ? "Verbunden" : "Offline"; groqEl.className = "setting-status" + (ai.groq?.available ? "" : " offline"); }
  if (ollamaEl) { ollamaEl.textContent = ai.ollama?.available ? "Bereit" : "Nicht gestartet"; ollamaEl.className = "setting-status" + (ai.ollama?.available ? "" : " offline"); }

  const voice = await window.lexa.voiceStatus();
  const ttsEl = document.getElementById("tts-status"), sttEl = document.getElementById("stt-status");
  if (ttsEl) { ttsEl.textContent = voice.tts?.ready ? "Bereit" : "Nicht verf\u00fcgbar"; ttsEl.className = "setting-status" + (voice.tts?.ready ? "" : " offline"); }
  if (sttEl) { sttEl.textContent = voice.stt?.ready ? "Bereit" : "Nicht verf\u00fcgbar"; sttEl.className = "setting-status" + (voice.stt?.ready ? "" : " offline"); }

  const health = await window.lexa.health();
  const versionEl = document.getElementById("settings-version");
  if (versionEl && health.version) versionEl.textContent = `v${health.version}`;

  try {
    const res = await fetch("http://127.0.0.1:8000/companion/commands");
    const data = await res.json();
    const countEl = document.getElementById("settings-cmd-count");
    if (countEl) countEl.textContent = `${data.total} registriert`;
  } catch {}

  const mem = await window.lexa.memoryStats();
  const dbEl = document.getElementById("settings-db-path");
  if (dbEl && mem.db_path) dbEl.textContent = mem.db_path;

  // Load model selection + theme preferences
  loadModelSelection();
  loadThemePreferences();
}

async function saveProfile() {
  const name = document.getElementById("profile-name").value.trim();
  const lang = document.getElementById("profile-language").value.trim();
  if (name) await window.lexa.setProfile("name", name);
  if (lang) await window.lexa.setProfile("language", lang);
  showToast("Profil gespeichert", "success");
}

// ── DASHBOARD ───────────────────────────────────
async function refreshDashboard() {
  // Greeting based on time of day
  const hour = new Date().getHours();
  let greeting = "Guten Tag";
  if (hour < 6) greeting = "Gute Nacht";
  else if (hour < 12) greeting = "Guten Morgen";
  else if (hour < 18) greeting = "Guten Tag";
  else greeting = "Guten Abend";

  const greetEl = document.getElementById("dash-greeting");
  if (greetEl) greetEl.textContent = `${greeting}, Chef!`;

  if (!backendOnline) {
    document.getElementById("dash-ai-status").innerHTML = '<span style="color:var(--error)">Backend offline</span>';
    return;
  }

  // System stats
  try {
    const res = await window.lexa.execute("system_info");
    if (res.success && res.data) {
      const d = res.data;
      const setDash = (id, val) => {
        const el = document.getElementById(id);
        if (el) { el.textContent = val + "%"; el.style.color = val > 80 ? "var(--error)" : val > 60 ? "var(--warning)" : "var(--accent2)"; }
      };
      setDash("dash-cpu", d.cpu_percent);
      setDash("dash-ram", d.ram_percent);
      setDash("dash-disk", d.disk_percent);
      const battEl = document.getElementById("dash-battery");
      if (battEl) {
        const bv = d.battery_percent !== null ? d.battery_percent : "--";
        battEl.textContent = bv + "%";
        if (bv !== "--") battEl.style.color = bv > 30 ? "var(--success)" : "var(--error)";
      }
    }
  } catch {}

  // AI status
  try {
    const ai = await window.lexa.aiStatus();
    const aiEl = document.getElementById("dash-ai-status");
    if (aiEl) {
      const groqDot = ai.groq?.available ? '<span class="dash-dot active"></span>' : '<span class="dash-dot"></span>';
      const ollamaDot = ai.ollama?.available ? '<span class="dash-dot active"></span>' : '<span class="dash-dot"></span>';
      aiEl.innerHTML = `
        <div class="dash-ai-row">${groqDot} Groq <span class="dash-ai-tag">${ai.groq?.available ? "Verbunden" : "Offline"}</span></div>
        <div class="dash-ai-row">${ollamaDot} Ollama <span class="dash-ai-tag">${ai.ollama?.available ? "Bereit" : "Aus"}</span></div>
        <div class="dash-ai-provider">Aktiv: <strong>${ai.active_provider}</strong></div>
      `;
    }
  } catch {}

  // Memory stats
  try {
    const mem = await window.lexa.memoryStats();
    const memEl = document.getElementById("dash-memory-stats");
    if (memEl) {
      memEl.innerHTML = `
        <div class="dash-mem-grid">
          <div class="dash-mem-item"><span class="dash-mem-num">${mem.notes || 0}</span>Notizen</div>
          <div class="dash-mem-item"><span class="dash-mem-num">${mem.memories || 0}</span>Erinnerungen</div>
          <div class="dash-mem-item"><span class="dash-mem-num">${mem.interactions || 0}</span>Chats</div>
          <div class="dash-mem-item"><span class="dash-mem-num">${mem.routines || 0}</span>Routinen</div>
        </div>
      `;
    }
  } catch {}

  // Routines
  try {
    const routinesData = await window.lexa.routines();
    const routEl = document.getElementById("dash-routines-list");
    if (routEl) {
      if (routinesData.routines?.length > 0) {
        routEl.innerHTML = routinesData.routines.map(r => `
          <div class="dash-routine-item">
            <span class="dash-routine-dot ${r.enabled ? "active" : ""}"></span>
            <span class="dash-routine-name">${r.name}</span>
            <span class="dash-routine-time">${r.schedule}</span>
          </div>
        `).join("");
      } else {
        routEl.innerHTML = '<div class="dash-empty">Keine Routinen aktiv</div>';
      }
    }
  } catch {}
}

// ── COMMAND PALETTE (Ctrl+P) ────────────────────
function setupCommandPalette() {
  let paletteEl = document.getElementById("command-palette");
  if (!paletteEl) {
    paletteEl = document.createElement("div");
    paletteEl.id = "command-palette";
    paletteEl.className = "cmd-palette-overlay";
    paletteEl.innerHTML = `
      <div class="cmd-palette">
        <input type="text" id="palette-input" class="palette-input" placeholder="Befehl oder Aktion suchen..." autocomplete="off">
        <div id="palette-results" class="palette-results"></div>
      </div>
    `;
    document.body.appendChild(paletteEl);

    paletteEl.addEventListener("click", (e) => {
      if (e.target === paletteEl) closePalette();
    });

    document.getElementById("palette-input").addEventListener("input", (e) => {
      renderPaletteResults(e.target.value.toLowerCase().trim());
    });

    document.getElementById("palette-input").addEventListener("keydown", (e) => {
      if (e.key === "Escape") closePalette();
      if (e.key === "Enter") {
        const first = document.querySelector(".palette-item.selected") || document.querySelector(".palette-item");
        if (first) first.click();
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        navigatePalette(e.key === "ArrowDown" ? 1 : -1);
      }
    });
  }
}

function openPalette() {
  setupCommandPalette();
  const overlay = document.getElementById("command-palette");
  overlay.classList.add("visible");
  const input = document.getElementById("palette-input");
  input.value = "";
  input.focus();
  renderPaletteResults("");
}

function closePalette() {
  document.getElementById("command-palette")?.classList.remove("visible");
}

function navigatePalette(dir) {
  const items = [...document.querySelectorAll(".palette-item")];
  const current = items.findIndex(i => i.classList.contains("selected"));
  items.forEach(i => i.classList.remove("selected"));
  const next = Math.max(0, Math.min(items.length - 1, current + dir));
  items[next]?.classList.add("selected");
  items[next]?.scrollIntoView({ block: "nearest" });
}

function renderPaletteResults(query) {
  const container = document.getElementById("palette-results");
  if (!container) return;

  // Combine views + commands
  const viewItems = VIEW_KEYS.map(v => ({
    type: "view", name: v, desc: `Wechsle zu ${v}`, icon: "\u{1F4CB}"
  }));
  const cmdItems = ALL_COMMANDS.map(c => ({
    type: "cmd", name: c.name, desc: c.desc, icon: c.status === "confirm" ? "\u26A0" : "\u26A1", cat: c.cat
  }));
  const allItems = [...viewItems, ...cmdItems];

  const filtered = query
    ? allItems.filter(i => i.name.includes(query) || i.desc.toLowerCase().includes(query) || (i.cat || "").toLowerCase().includes(query))
    : allItems.slice(0, 15);

  container.innerHTML = filtered.slice(0, 20).map((item, i) => `
    <div class="palette-item ${i === 0 ? "selected" : ""}" onclick="${item.type === "view" ? `switchView('${item.name}');closePalette()` : `insertCommand('${item.name}');closePalette()`}">
      <span class="palette-icon">${item.icon}</span>
      <div class="palette-item-info">
        <span class="palette-name">${item.name}</span>
        <span class="palette-desc">${item.desc}</span>
      </div>
      <span class="palette-type">${item.type === "view" ? "VIEW" : item.cat || "CMD"}</span>
    </div>
  `).join("");

  if (filtered.length === 0) {
    container.innerHTML = '<div class="palette-empty">Nichts gefunden</div>';
  }
}

// ── CONVERSATIONS ───────────────────────────────
async function loadConversations() {
  try {
    const data = await window.lexa.conversations();
    conversationsList = data.conversations || [];
    renderConversationList();

    // Load last active conversation or start fresh
    const lastId = parseInt(localStorage.getItem("lexa-active-conversation"));
    if (lastId && conversationsList.find(c => c.id === lastId)) {
      await switchConversation(lastId, false);
    } else if (conversationsList.length > 0) {
      await switchConversation(conversationsList[0].id, false);
    }
  } catch {
    // Fallback: load from localStorage (legacy)
    loadChatHistory();
  }
}

function renderConversationList() {
  const container = document.getElementById("conversation-list");
  if (!container) return;

  if (conversationsList.length === 0) {
    container.innerHTML = '<div class="conv-empty">Kein Chatverlauf</div>';
    return;
  }

  container.innerHTML = conversationsList.map(c => {
    const isActive = c.id === currentConversationId;
    const title = c.title.length > 28 ? c.title.substring(0, 28) + "\u2026" : c.title;
    const count = c.message_count || 0;
    return `
      <div class="conv-item ${isActive ? "active" : ""}" data-conv-id="${c.id}" onclick="switchConversation(${c.id})">
        <div class="conv-item-content">
          <div class="conv-title">${escapeHtml(title)}</div>
          <div class="conv-meta">${count} Nachrichten</div>
        </div>
        <div class="conv-actions">
          <button class="conv-action-btn" onclick="event.stopPropagation();exportConversation(${c.id})" title="Exportieren">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          </button>
          <button class="conv-delete-btn" onclick="event.stopPropagation();deleteConversation(${c.id})" title="L\u00f6schen">\u00d7</button>
        </div>
      </div>`;
  }).join("");
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function newConversation() {
  try {
    const result = await window.lexa.conversationCreate("Neuer Chat");
    currentConversationId = result.id;
    localStorage.setItem("lexa-active-conversation", result.id);

    // Clear chat UI
    const msgs = chatMessages.querySelectorAll(".message");
    msgs.forEach((m, i) => { if (i > 0) m.remove(); });
    hideSuggestions();

    // Clear backend history
    try { await fetch("http://127.0.0.1:8000/history", { method: "DELETE" }); } catch {}

    // Refresh list
    const data = await window.lexa.conversations();
    conversationsList = data.conversations || [];
    renderConversationList();

    switchView("chat");
    chatInput.focus();
    showToast("Neuer Chat gestartet", "info", 2000);
  } catch {
    showToast("Fehler beim Erstellen", "error");
  }
}

async function switchConversation(convId, notify = true) {
  if (convId === currentConversationId && notify) return;

  // Save current conversation before switching
  await saveCurrentConversation();

  currentConversationId = convId;
  localStorage.setItem("lexa-active-conversation", convId);

  try {
    // Load conversation from backend
    const conv = await window.lexa.conversationGet(convId);
    if (!conv || conv.detail) {
      if (notify) showToast("Conversation nicht gefunden", "error");
      return;
    }

    // Load backend chat history
    await window.lexa.conversationLoad(convId);

    // Clear chat UI and load messages
    const msgs = chatMessages.querySelectorAll(".message");
    msgs.forEach((m, i) => { if (i > 0) m.remove(); });
    hideSuggestions();

    // Render messages
    const messages = conv.messages || [];
    for (const msg of messages) {
      addMessage(msg.content, msg.role === "user" ? "user" : "system", null, false, true);
    }

    // Update sidebar highlight
    renderConversationList();

    if (notify) {
      switchView("chat");
      showToast(`Chat: ${conv.title}`, "info", 1500);
    }
  } catch {
    if (notify) showToast("Fehler beim Laden", "error");
  }
}

async function saveCurrentConversation() {
  if (!currentConversationId) return;

  // Collect messages from chat UI
  const messages = [];
  chatMessages.querySelectorAll(".message").forEach((msg, i) => {
    if (i === 0) return; // Skip welcome message
    const text = msg.querySelector(".msg-text")?.textContent || "";
    const role = msg.classList.contains("user-message") ? "user" : "assistant";
    if (text) messages.push({ role, content: text });
  });

  try {
    await window.lexa.conversationUpdate(currentConversationId, { messages });
  } catch {}
}

async function deleteConversation(convId) {
  try {
    await window.lexa.conversationDelete(convId);

    // If deleting active conversation, switch to another or create new
    if (convId === currentConversationId) {
      currentConversationId = null;
    }

    // Refresh list
    const data = await window.lexa.conversations();
    conversationsList = data.conversations || [];
    renderConversationList();

    if (convId === parseInt(localStorage.getItem("lexa-active-conversation"))) {
      if (conversationsList.length > 0) {
        await switchConversation(conversationsList[0].id);
      } else {
        await newConversation();
      }
    }

    showToast("Chat gel\u00f6scht", "info", 2000);
  } catch {
    showToast("Fehler beim L\u00f6schen", "error");
  }
}

async function autoTitleConversation(userMessage) {
  if (!currentConversationId) return;

  // Quick fallback title while AI generates
  let title = userMessage.trim();
  if (title.length > 40) title = title.substring(0, 40) + "\u2026";
  if (!title) title = "Neuer Chat";

  // Set fallback immediately
  try {
    await window.lexa.conversationUpdate(currentConversationId, { title });
    const conv = conversationsList.find(c => c.id === currentConversationId);
    if (conv) conv.title = title;
    renderConversationList();
  } catch {}

  // Then generate AI title asynchronously
  try {
    const result = await window.lexa.generateTitle(userMessage);
    if (result.title && result.title !== title) {
      title = result.title;
      await window.lexa.conversationUpdate(currentConversationId, { title });
      const conv = conversationsList.find(c => c.id === currentConversationId);
      if (conv) conv.title = title;
      renderConversationList();
    }
  } catch {}
}

// ── DRAG & DROP + FILE UPLOAD ────────────────────
let dragCounter = 0;

function setupDragDrop() {
  const chatContainer = document.getElementById("chat-container");
  const overlay = document.getElementById("drop-zone-overlay");
  if (!chatContainer || !overlay) return;

  chatContainer.addEventListener("dragenter", (e) => {
    e.preventDefault();
    dragCounter++;
    overlay.classList.add("visible");
  });

  chatContainer.addEventListener("dragleave", (e) => {
    e.preventDefault();
    dragCounter--;
    if (dragCounter <= 0) {
      dragCounter = 0;
      overlay.classList.remove("visible");
    }
  });

  chatContainer.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  });

  chatContainer.addEventListener("drop", (e) => {
    e.preventDefault();
    dragCounter = 0;
    overlay.classList.remove("visible");
    const files = e.dataTransfer.files;
    if (files.length > 0) handleFileUpload(files[0]);
  });
}

function triggerFileUpload() {
  document.getElementById("file-input")?.click();
}

function handleFileSelect(event) {
  const file = event.target.files?.[0];
  if (file) handleFileUpload(file);
  event.target.value = ""; // Reset for re-upload
}

async function handleFileUpload(file) {
  if (!backendOnline) { showToast("Backend nicht verbunden", "error"); return; }

  const maxSize = 2 * 1024 * 1024;
  if (file.size > maxSize) {
    showToast("Datei zu gro\u00df (max 2 MB)", "error");
    return;
  }

  // Auto-create conversation if needed
  if (!currentConversationId) {
    try {
      const result = await window.lexa.conversationCreate("Neuer Chat");
      currentConversationId = result.id;
      localStorage.setItem("lexa-active-conversation", result.id);
      const data = await window.lexa.conversations();
      conversationsList = data.conversations || [];
      renderConversationList();
    } catch {}
  }

  // Show file card as user message
  const sizeStr = file.size < 1024 ? file.size + " B"
    : file.size < 1048576 ? (file.size / 1024).toFixed(1) + " KB"
    : (file.size / 1048576).toFixed(1) + " MB";
  const ext = file.name.includes(".") ? file.name.split(".").pop().toUpperCase() : "FILE";
  const fileCardHtml = `<div class="file-card"><div class="file-card-icon">${getFileIcon(ext)}</div><div class="file-card-info"><div class="file-card-name">${escapeHtml(file.name)}</div><div class="file-card-meta">${ext} \u00b7 ${sizeStr}</div></div></div>`;

  const userMsg = chatInput.value.trim();
  addMessage(fileCardHtml + (userMsg ? `<br>${formatMessage(userMsg)}` : ""), "user");
  chatInput.value = "";
  chatInput.style.height = "auto";

  // Auto-title
  const isFirst = chatMessages.querySelectorAll(".user-message").length <= 1;
  if (isFirst) autoTitleConversation(file.name);

  isLoading = true;
  sendBtn.disabled = true;
  hideSuggestions();
  showTyping();

  try {
    const res = await window.lexa.chatFile(file, userMsg || "");
    hideTyping();

    if (res.detail) {
      addMessage(res.detail, "system");
      showToast("Datei-Fehler", "error");
    } else {
      // Show file info + AI response
      let infoHtml = "";
      if (res.file_info) {
        const fi = res.file_info;
        infoHtml = `<div class="file-info-badge">${fi.type.toUpperCase()} \u00b7 ${fi.size_kb} KB${fi.line_count ? " \u00b7 " + fi.line_count + " Zeilen" : ""}</div>`;
      }
      addMessage(infoHtml + formatMessage(res.reply), "system", res.action, res.requires_confirmation);

      if (res.action && !res.requires_confirmation) {
        try {
          const execResult = await window.lexa.execute(res.action.action, res.action.params || {});
          if (execResult.success && execResult.data) {
            const summary = typeof execResult.data === "string" ? execResult.data : JSON.stringify(execResult.data).substring(0, 200);
            addMessage("Ausgef\u00fchrt: " + summary, "system");
          }
        } catch {}
      }

      playTTS(res.reply);
      showSuggestions(res.reply, res.action);
    }
  } catch (err) {
    hideTyping();
    addMessage("Fehler beim Hochladen: " + err.message, "system");
    showToast("Upload-Fehler", "error");
  }

  saveChatHistory();
  saveCurrentConversation();
  isLoading = false;
  sendBtn.disabled = false;
}

function getFileIcon(ext) {
  const icons = {
    PY: "\u{1F40D}", JS: "\u{1F7E8}", TS: "\u{1F535}", HTML: "\u{1F310}", CSS: "\u{1F3A8}",
    JSON: "\u{1F4CB}", MD: "\u{1F4DD}", TXT: "\u{1F4C4}", CSV: "\u{1F4CA}", LOG: "\u{1F4DC}",
    PDF: "\u{1F4D5}", PNG: "\u{1F5BC}", JPG: "\u{1F5BC}", JPEG: "\u{1F5BC}", GIF: "\u{1F5BC}",
    SVG: "\u{1F5BC}", SQL: "\u{1F5C3}", XML: "\u{1F4C3}", YAML: "\u2699", YML: "\u2699",
  };
  return icons[ext] || "\u{1F4CE}";
}

// ── GLOBAL SEARCH OVERLAY (Phase 13) ────────────
let searchDebounce = null;

function openSearchOverlay() {
  let overlay = document.getElementById("search-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "search-overlay";
    overlay.className = "search-overlay";
    overlay.innerHTML = `
      <div class="search-panel">
        <div class="search-header">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="text" id="search-input" class="search-input" placeholder="Chats, Notizen, Erinnerungen durchsuchen..." autocomplete="off">
          <button class="search-close-btn" onclick="closeSearchOverlay()">\u00d7</button>
        </div>
        <div id="search-results" class="search-results">
          <div class="search-empty">Suchbegriff eingeben...</div>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeSearchOverlay();
    });

    document.getElementById("search-input").addEventListener("input", (e) => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => performSearch(e.target.value.trim()), 300);
    });

    document.getElementById("search-input").addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeSearchOverlay();
    });
  }

  overlay.classList.add("visible");
  const input = document.getElementById("search-input");
  input.value = "";
  input.focus();
  document.getElementById("search-results").innerHTML = '<div class="search-empty">Suchbegriff eingeben...</div>';
}

function closeSearchOverlay() {
  document.getElementById("search-overlay")?.classList.remove("visible");
}

async function performSearch(query) {
  const container = document.getElementById("search-results");
  if (!container) return;

  if (!query) {
    container.innerHTML = '<div class="search-empty">Suchbegriff eingeben...</div>';
    return;
  }

  if (query.length < 2) {
    container.innerHTML = '<div class="search-empty">Mindestens 2 Zeichen...</div>';
    return;
  }

  try {
    const data = await window.lexa.search(query);
    let html = "";

    // Conversations
    if (data.conversations?.length > 0) {
      html += '<div class="search-category">CHATS</div>';
      for (const c of data.conversations) {
        html += `
          <div class="search-item" onclick="closeSearchOverlay();switchConversation(${c.id})">
            <span class="search-item-icon">\u{1F4AC}</span>
            <div class="search-item-info">
              <div class="search-item-title">${escapeHtml(c.title)}</div>
              <div class="search-item-meta">${c.message_count || 0} Nachrichten \u00b7 ${c.updated_at || ""}</div>
            </div>
          </div>`;
      }
    }

    // Notes
    if (data.notes?.length > 0) {
      html += '<div class="search-category">NOTIZEN</div>';
      for (const n of data.notes) {
        html += `
          <div class="search-item" onclick="closeSearchOverlay();switchView('memory')">
            <span class="search-item-icon">\u{1F4DD}</span>
            <div class="search-item-info">
              <div class="search-item-title">${escapeHtml(n.title)}</div>
              <div class="search-item-meta">${n.category} \u00b7 ${n.created_at || ""}</div>
            </div>
          </div>`;
      }
    }

    // Memories
    if (data.memories?.length > 0) {
      html += '<div class="search-category">ERINNERUNGEN</div>';
      for (const m of data.memories) {
        const preview = m.content.length > 80 ? m.content.substring(0, 80) + "\u2026" : m.content;
        html += `
          <div class="search-item" onclick="closeSearchOverlay();switchView('memory')">
            <span class="search-item-icon">\u{1F9E0}</span>
            <div class="search-item-info">
              <div class="search-item-title">${escapeHtml(preview)}</div>
              <div class="search-item-meta">${m.category} \u00b7 Wichtigkeit ${m.importance}</div>
            </div>
          </div>`;
      }
    }

    if (!html) {
      html = '<div class="search-empty">Keine Ergebnisse gefunden</div>';
    }

    const total = (data.conversations?.length || 0) + (data.notes?.length || 0) + (data.memories?.length || 0);
    container.innerHTML = `<div class="search-count">${total} Ergebnisse</div>` + html;
  } catch {
    container.innerHTML = '<div class="search-empty">Suchfehler</div>';
  }
}

// ── CONVERSATION EXPORT (Phase 13) ──────────────
async function exportConversation(convId, fmt = "markdown") {
  try {
    const data = await window.lexa.conversationExport(convId || currentConversationId, fmt);
    if (!data.text) {
      showToast("Export fehlgeschlagen", "error");
      return;
    }

    // Create download
    const ext = fmt === "markdown" ? "md" : "txt";
    const blob = new Blob([data.text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `lexa-chat-${convId || currentConversationId}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
    showToast(`Chat als ${ext.toUpperCase()} exportiert`, "success");
  } catch {
    showToast("Export-Fehler", "error");
  }
}

// ── AI MODEL SELECTION (Phase 14) ───────────────
async function loadModelSelection() {
  try {
    const data = await window.lexa.aiModels();
    const select = document.getElementById("model-select");
    if (!select || !data.available) return;

    select.innerHTML = "";
    for (const [id, name] of Object.entries(data.available)) {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = name;
      if (id === data.current) opt.selected = true;
      select.appendChild(opt);
    }

    const desc = document.getElementById("model-desc");
    if (desc) desc.textContent = `Aktiv: ${data.current_name}`;
  } catch {}
}

async function changeAiModel(modelId) {
  try {
    const result = await window.lexa.setAiModel(modelId);
    showToast(result.status || "Modell gewechselt", "success");
    const desc = document.getElementById("model-desc");
    if (desc && result.current) desc.textContent = `Aktiv: ${result.current.current_name}`;
  } catch {
    showToast("Modellwechsel fehlgeschlagen", "error");
  }
}

// ── CLIPBOARD HISTORY & SNIPPETS (Phase 16) ─────
async function trackClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text && text.trim()) {
      await window.lexa.clipboardAdd(text.trim().substring(0, 1000));
    }
  } catch {}
}

async function createSnippet() {
  const name = prompt("Snippet-Name:"); if (!name) return;
  const text = prompt("Snippet-Text:"); if (!text) return;
  await window.lexa.snippetCreate(name, text);
  showToast("Snippet gespeichert", "success");
  refreshMemoryView();
}

async function deleteSnippet(name) {
  await window.lexa.snippetDelete(name);
  showToast("Snippet gel\u00f6scht", "info");
  refreshMemoryView();
}

async function useSnippet(text) {
  chatInput.value = text;
  chatInput.focus();
  switchView("chat");
  showToast("Snippet eingef\u00fcgt", "info", 1500);
}

// ── THEME & PERSONALIZATION (Phase 15) ──────────
function toggleTheme(isDark) {
  document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");
  localStorage.setItem("lexa-theme", isDark ? "dark" : "light");
  showToast(isDark ? "Dark Mode aktiviert" : "Light Mode aktiviert", "info", 2000);
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
  document.documentElement.style.fontSize = size + "px";
  localStorage.setItem("lexa-fontsize", size);
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
    document.documentElement.style.fontSize = fontSize + "px";
    const fontSelect = document.getElementById("fontsize-select");
    if (fontSelect) fontSelect.value = fontSize;
  }
}

// ── SMART SUGGESTIONS ───────────────────────────
const SUGGESTION_MAP = {
  system_info: ["screenshot", "process_list", "disk_analysis", "battery_status"],
  screenshot: ["system_info", "screen_record", "web_screenshot"],
  app_open: ["window_list", "app_list", "window_focus"],
  youtube_play: ["media_play_pause", "volume_set", "media_next"],
  volume_set: ["volume_mute", "media_play_pause", "brightness_set"],
  battery_status: ["system_info", "brightness_set", "wifi_status"],
  process_list: ["process_kill", "system_info", "app_list"],
  disk_analysis: ["clean_temp", "find_duplicates", "organize_downloads"],
  organize_downloads: ["disk_analysis", "find_duplicates", "clean_temp"],
  note_create: ["note_list", "memory_search", "note_read"],
  email_read: ["email_send", "telegram_read"],
  media_play_pause: ["media_next", "media_prev", "volume_set", "media_stop"],
};

const DEFAULT_SUGGESTIONS = [
  { label: "\u{1F4BB} System Info", cmd: "system_info" },
  { label: "\u{1F4F7} Screenshot", cmd: "screenshot" },
  { label: "\u{1F3B5} YouTube", cmd: "youtube_play" },
  { label: "\u{1F4C2} Downloads sortieren", cmd: "organize_downloads" },
];

function showSuggestions(responseText, action) {
  const container = document.getElementById("suggestion-chips");
  if (!container) return;

  let chips = [];
  if (action && SUGGESTION_MAP[action.action]) {
    chips = SUGGESTION_MAP[action.action]
      .map((cmd) => ALL_COMMANDS.find((c) => c.name === cmd))
      .filter(Boolean)
      .slice(0, 4)
      .map((c) => ({ label: c.desc, cmd: c.name }));
  }

  if (chips.length === 0) chips = DEFAULT_SUGGESTIONS;

  container.innerHTML = chips
    .map((s) => `<button class="suggestion-chip" onclick="handleSuggestion('${s.cmd}')">${s.label}</button>`)
    .join("");
}

function hideSuggestions() {
  const container = document.getElementById("suggestion-chips");
  if (container) container.innerHTML = "";
}

function handleSuggestion(command) {
  chatInput.value = command.replace(/_/g, " ");
  chatInput.focus();
  hideSuggestions();
}

// ── START ────────────────────────────────────────
init();
