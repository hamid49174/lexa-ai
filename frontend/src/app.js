/* ════════════════════════════════════════════════
   LEXA AI — Frontend Application Logic v0.6
   Phase 7: Keyboard Shortcuts, Chat Persistence,
   Command Search, Sidebar Toggle
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

const VIEW_KEYS = ["chat", "system", "commands", "browser", "files", "media", "memory", "settings"];

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
  loadChatHistory();
  loadSidebarState();
  updateSystemStats();
}

// ── KEYBOARD SHORTCUTS ───────────────────────────
function setupKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    // Ctrl+1-8: Switch views
    if (e.ctrlKey && !e.shiftKey && !e.altKey) {
      const num = parseInt(e.key);
      if (num >= 1 && num <= 8) {
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
  });
}

function clearChat() {
  const msgs = chatMessages.querySelectorAll(".message");
  msgs.forEach((m, i) => { if (i > 0) m.remove(); });
  localStorage.removeItem("lexa-chat-history");
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

  document.querySelectorAll(".sidebar-btn").forEach((b) => b.classList.remove("active"));
  document.querySelector(`[data-view="${view}"]`)?.classList.add("active");

  document.querySelector(".chat-container").style.display = "none";
  document.querySelectorAll(".system-view, .commands-view, .tool-view").forEach((v) => {
    v.classList.remove("active");
  });

  if (view === "chat") {
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

  msg.innerHTML = `
    <div class="msg-avatar ${avatarClass}">${avatarIcon}</div>
    <div class="msg-body">
      <div class="msg-name">${nameText}</div>
      <div class="msg-text">${formatMessage(text)}</div>
      ${actionHtml}
      ${confirmHtml}
    </div>`;

  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  if (!silent) saveChatHistory();
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
  return text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
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

  addMessage(text, "user");
  chatInput.value = "";
  chatInput.style.height = "auto";
  isLoading = true;
  sendBtn.disabled = true;
  showTyping();

  try {
    const res = await window.lexa.chat(text);
    hideTyping();
    handleChatResponse(res);
  } catch (err) {
    hideTyping();
    addMessage("Backend nicht erreichbar. Ist der Server gestartet?", "system");
    showToast("Chat-Fehler: Backend offline", "error");
  }

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
}

async function saveProfile() {
  const name = document.getElementById("profile-name").value.trim();
  const lang = document.getElementById("profile-language").value.trim();
  if (name) await window.lexa.setProfile("name", name);
  if (lang) await window.lexa.setProfile("language", lang);
  showToast("Profil gespeichert", "success");
}

// ── START ────────────────────────────────────────
init();
