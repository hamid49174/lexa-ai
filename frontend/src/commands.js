/* ════════════════════════════════════════════════
   LEXA AI — Commands Module
   Commands view (search, filter, render), Quick actions,
   Recently used commands, Dashboard quick actions
   Extracted from tools.js
   ════════════════════════════════════════════════ */

// ── COMMANDS DATA (static, descriptions resolved via t() at render time) ──
const ALL_COMMANDS_DATA = [
  { name: "app_open", status: "allowed", cat: "basis" },
  { name: "app_list", status: "allowed", cat: "basis" },
  { name: "system_info", status: "allowed", cat: "basis" },
  { name: "screenshot", status: "allowed", cat: "basis" },
  { name: "process_list", status: "allowed", cat: "basis" },
  { name: "process_kill", status: "confirm", cat: "basis" },
  { name: "clipboard_read", status: "allowed", cat: "basis" },
  { name: "clipboard_write", status: "allowed", cat: "basis" },
  { name: "volume_set", status: "allowed", cat: "basis" },
  { name: "volume_mute", status: "allowed", cat: "basis" },
  { name: "file_search", status: "allowed", cat: "basis" },
  { name: "window_list", status: "allowed", cat: "basis" },
  { name: "window_focus", status: "allowed", cat: "basis" },
  { name: "brightness_set", status: "allowed", cat: "basis" },
  { name: "wifi_status", status: "allowed", cat: "basis" },
  { name: "battery_status", status: "allowed", cat: "basis" },
  { name: "timer_set", status: "allowed", cat: "basis" },
  { name: "browser_open", status: "allowed", cat: "basis" },
  { name: "shutdown", status: "confirm", cat: "basis" },
  { name: "restart", status: "confirm", cat: "basis" },
  { name: "youtube_search", status: "allowed", cat: "browser" },
  { name: "youtube_play", status: "allowed", cat: "browser" },
  { name: "web_open", status: "allowed", cat: "browser" },
  { name: "web_screenshot", status: "allowed", cat: "browser" },
  { name: "web_pdf", status: "allowed", cat: "browser" },
  { name: "web_scrape", status: "allowed", cat: "browser" },
  { name: "price_check", status: "allowed", cat: "browser" },
  { name: "browser_close", status: "allowed", cat: "browser" },
  { name: "find_duplicates", status: "confirm", cat: "dateien" },
  { name: "batch_rename", status: "confirm", cat: "dateien" },
  { name: "organize_downloads", status: "confirm", cat: "dateien" },
  { name: "merge_pdfs", status: "confirm", cat: "dateien" },
  { name: "split_pdf", status: "confirm", cat: "dateien" },
  { name: "disk_analysis", status: "allowed", cat: "dateien" },
  { name: "clean_temp", status: "confirm", cat: "dateien" },
  { name: "media_play_pause", status: "allowed", cat: "media" },
  { name: "media_next", status: "allowed", cat: "media" },
  { name: "media_prev", status: "allowed", cat: "media" },
  { name: "media_stop", status: "allowed", cat: "media" },
  { name: "spotify_open", status: "allowed", cat: "media" },
  { name: "convert_media", status: "allowed", cat: "media" },
  { name: "extract_audio", status: "allowed", cat: "media" },
  { name: "screen_record", status: "allowed", cat: "media" },
  { name: "email_read", status: "allowed", cat: "kommunikation" },
  { name: "email_send", status: "confirm", cat: "kommunikation" },
  { name: "telegram_read", status: "allowed", cat: "kommunikation" },
  { name: "telegram_send", status: "confirm", cat: "kommunikation" },
  { name: "discord_send", status: "confirm", cat: "kommunikation" },
  { name: "note_create", status: "allowed", cat: "gedaechtnis" },
  { name: "note_read", status: "allowed", cat: "gedaechtnis" },
  { name: "note_list", status: "allowed", cat: "gedaechtnis" },
  { name: "note_delete", status: "confirm", cat: "gedaechtnis" },
  { name: "memory_search", status: "allowed", cat: "gedaechtnis" },
  { name: "memory_add", status: "allowed", cat: "gedaechtnis" },
  { name: "summarize", status: "allowed", cat: "gedaechtnis" },
  { name: "routine_create", status: "confirm", cat: "gedaechtnis" },
  { name: "routine_list", status: "allowed", cat: "gedaechtnis" },
  { name: "routine_delete", status: "confirm", cat: "gedaechtnis" },
  { name: "routine_toggle", status: "confirm", cat: "gedaechtnis" },
  // Productivity
  { name: "todo_create", status: "allowed", cat: "produktivitaet" },
  { name: "todo_list", status: "allowed", cat: "produktivitaet" },
  { name: "todo_update", status: "allowed", cat: "produktivitaet" },
  { name: "todo_complete", status: "allowed", cat: "produktivitaet" },
  { name: "todo_delete", status: "confirm", cat: "produktivitaet" },
  { name: "pomodoro_start", status: "allowed", cat: "produktivitaet" },
  { name: "pomodoro_stop", status: "allowed", cat: "produktivitaet" },
  { name: "pomodoro_status", status: "allowed", cat: "produktivitaet" },
  { name: "habit_create", status: "allowed", cat: "produktivitaet" },
  { name: "habit_log", status: "allowed", cat: "produktivitaet" },
  { name: "habit_list", status: "allowed", cat: "produktivitaet" },
  { name: "habit_delete", status: "confirm", cat: "produktivitaet" },
  { name: "time_tracking_start", status: "allowed", cat: "produktivitaet" },
  { name: "time_tracking_stop", status: "allowed", cat: "produktivitaet" },
  { name: "time_tracking_report", status: "allowed", cat: "produktivitaet" },
  { name: "focus_mode_on", status: "confirm", cat: "produktivitaet" },
  { name: "focus_mode_off", status: "confirm", cat: "produktivitaet" },
  // Files extended
  { name: "archive_create", status: "confirm", cat: "dateien" },
  { name: "archive_extract", status: "confirm", cat: "dateien" },
  { name: "archive_list", status: "allowed", cat: "dateien" },
  { name: "backup_create", status: "confirm", cat: "dateien" },
  { name: "backup_list", status: "allowed", cat: "dateien" },
  { name: "backup_restore", status: "confirm", cat: "dateien" },
  { name: "image_convert", status: "allowed", cat: "dateien" },
  { name: "image_resize", status: "allowed", cat: "dateien" },
  { name: "image_batch_resize", status: "confirm", cat: "dateien" },
  { name: "image_info", status: "allowed", cat: "dateien" },
  { name: "file_info", status: "allowed", cat: "dateien" },
  { name: "folder_size", status: "allowed", cat: "dateien" },
  // System extended
  { name: "window_move", status: "allowed", cat: "system" },
  { name: "window_resize", status: "allowed", cat: "system" },
  { name: "window_minimize", status: "allowed", cat: "system" },
  { name: "window_maximize", status: "allowed", cat: "system" },
  { name: "window_layout", status: "allowed", cat: "system" },
  { name: "autostart_list", status: "allowed", cat: "system" },
  { name: "autostart_add", status: "confirm", cat: "system" },
  { name: "autostart_remove", status: "confirm", cat: "system" },
  { name: "service_list", status: "allowed", cat: "system" },
  { name: "service_info", status: "allowed", cat: "system" },
  { name: "service_start", status: "confirm", cat: "system" },
  { name: "service_stop", status: "confirm", cat: "system" },
  { name: "env_list", status: "blocked", cat: "system" },
  { name: "env_get", status: "confirm", cat: "system" },
  { name: "env_set", status: "confirm", cat: "system" },
  { name: "system_uptime", status: "allowed", cat: "system" },
  { name: "installed_apps", status: "allowed", cat: "system" },
  { name: "ping", status: "allowed", cat: "netzwerk" },
  { name: "dns_lookup", status: "allowed", cat: "netzwerk" },
  { name: "port_check", status: "allowed", cat: "netzwerk" },
  { name: "network_info", status: "allowed", cat: "netzwerk" },
  { name: "public_ip", status: "allowed", cat: "netzwerk" },
  { name: "traceroute", status: "allowed", cat: "netzwerk" },
  { name: "flush_dns", status: "confirm", cat: "netzwerk" },
  // Developer tools
  { name: "git_status", status: "allowed", cat: "entwickler" },
  { name: "git_log", status: "allowed", cat: "entwickler" },
  { name: "git_diff", status: "allowed", cat: "entwickler" },
  { name: "git_branch_list", status: "allowed", cat: "entwickler" },
  { name: "git_add", status: "confirm", cat: "entwickler" },
  { name: "git_commit", status: "confirm", cat: "entwickler" },
  { name: "git_pull", status: "confirm", cat: "entwickler" },
  { name: "git_push", status: "confirm", cat: "entwickler" },
  { name: "docker_ps", status: "allowed", cat: "entwickler" },
  { name: "docker_images", status: "allowed", cat: "entwickler" },
  { name: "docker_stats", status: "allowed", cat: "entwickler" },
  { name: "docker_logs", status: "allowed", cat: "entwickler" },
  { name: "docker_start", status: "confirm", cat: "entwickler" },
  { name: "docker_stop", status: "confirm", cat: "entwickler" },
  { name: "http_request", status: "allowed", cat: "entwickler" },
  { name: "log_analyze", status: "allowed", cat: "entwickler" },
  { name: "server_check", status: "allowed", cat: "entwickler" },
  { name: "multi_server_check", status: "allowed", cat: "entwickler" },
  { name: "json_format", status: "allowed", cat: "entwickler" },
  { name: "regex_test", status: "allowed", cat: "entwickler" },
  { name: "base64_encode", status: "allowed", cat: "entwickler" },
  { name: "base64_decode", status: "allowed", cat: "entwickler" },
  { name: "hash_text", status: "allowed", cat: "entwickler" },
  { name: "generate_uuid", status: "allowed", cat: "entwickler" },
  { name: "timestamp_convert", status: "allowed", cat: "entwickler" },
];

// Category key mapping (internal cat key -> i18n key)
const CMD_CAT_KEYS = {
  basis: "cmd.cat.basis",
  browser: "cmd.cat.browser",
  dateien: "cmd.cat.dateien",
  media: "cmd.cat.media",
  kommunikation: "cmd.cat.kommunikation",
  gedaechtnis: "cmd.cat.gedaechtnis",
  produktivitaet: "cmd.cat.produktivitaet",
  system: "cmd.cat.system",
  netzwerk: "cmd.cat.netzwerk",
  entwickler: "cmd.cat.entwickler",
};

// Build translated commands list (call at render time so t() returns current locale)
function getAllCommands() {
  return ALL_COMMANDS_DATA.map(c => ({
    name: c.name,
    desc: t("cmd.desc." + c.name),
    status: c.status,
    cat: t(CMD_CAT_KEYS[c.cat] || c.cat),
  }));
}

// Keep backward-compatible reference for .length checks
const ALL_COMMANDS = ALL_COMMANDS_DATA;

function createCommandSearchIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("aria-hidden", "true");
  const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  circle.setAttribute("cx", "11");
  circle.setAttribute("cy", "11");
  circle.setAttribute("r", "8");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.setAttribute("x1", "21");
  line.setAttribute("y1", "21");
  line.setAttribute("x2", "16.65");
  line.setAttribute("y2", "16.65");
  svg.append(circle, line);
  return svg;
}

function createCommandsView() {
  const div = document.createElement("div");
  div.className = "tool-view commands-view active";
  const title = document.createElement("div");
  title.className = "view-title";
  title.textContent = t("commands.allCommands");
  const searchBar = document.createElement("div");
  searchBar.className = "cmd-search-bar";
  const input = document.createElement("input");
  const searchLabel = t("commands.search");
  input.type = "text";
  input.id = "cmd-search";
  input.className = "cmd-search-input";
  input.placeholder = searchLabel;
  input.setAttribute("aria-label", searchLabel);
  input.dataset.action = "filterCommands";
  const count = document.createElement("span");
  count.className = "cmd-count";
  count.id = "cmd-count-badge";
  count.textContent = `${ALL_COMMANDS_DATA.length} ${t("nav.commands")}`;
  searchBar.append(createCommandSearchIcon(), input, count);
  const results = document.createElement("div");
  results.id = "cmd-results";
  div.append(title, searchBar, results);
  setTimeout(() => renderCommands(""), 0);
  return div;
}

function filterCommands(query) {
  renderCommands(query.toLowerCase().trim());
}

// ── RECENTLY USED COMMANDS ───────────────────────
const MAX_RECENT_CMDS = 6;
function getRecentCommands() {
  const parsed = lexaStorageJson("lexa-recent-cmds", []);
  return Array.isArray(parsed) ? parsed : [];
}
function trackRecentCommand(name) {
  let recent = getRecentCommands().filter(n => n !== name);
  recent.unshift(name);
  recent = recent.slice(0, MAX_RECENT_CMDS);
  lexaStorageSet("lexa-recent-cmds", JSON.stringify(recent));
}

function bindCommandItemAction(el, handler, label) {
  if (!el || typeof handler !== "function") return;
  if (label) el.setAttribute("aria-label", label);
  if (!el.hasAttribute("role")) el.setAttribute("role", "button");
  if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
  el.addEventListener("keydown", (event) => {
    if (event.target !== el) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handler(event);
    }
  });
  el.addEventListener("click", handler);
}

async function copyCommandName(btn, name) {
  if (btn?.disabled) return;
  const commandName = String(name || "").trim();
  if (!commandName) return;
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    if (typeof copyTextToClipboard === "function") {
      await copyTextToClipboard(commandName);
    } else if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(commandName);
    } else {
      throw new Error("clipboard_unavailable");
    }
    showToast(t("commands.copied", { name: commandName }), "success", 2000);
  } catch (e) {
    console.warn("[Commands] Copy command failed:", e.message || e);
    showToast(t("toast.copyFailed") || "Kopieren fehlgeschlagen", "warning", 2000);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}

function createCommandEmptyState(message) {
  const emptyDiv = document.createElement("div");
  emptyDiv.className = "empty-state";
  emptyDiv.textContent = message || "";
  return emptyDiv;
}

function renderCommands(query) {
  const container = document.getElementById("cmd-results");
  if (!container) return;

  const commands = getAllCommands();
  const statusLabel = { allowed: t("cmd.status.allowed"), confirm: t("cmd.status.confirm"), blocked: t("cmd.status.blocked") };
  const filtered = query
    ? commands.filter(c => c.name.includes(query) || c.desc.toLowerCase().includes(query) || c.cat.toLowerCase().includes(query))
    : commands;

  const badge = document.getElementById("cmd-count-badge");
  if (badge) badge.textContent = filtered.length + " " + t("nav.commands");

  container.replaceChildren();

  if (filtered.length === 0) {
    container.replaceChildren(createCommandEmptyState(t("common.noResults")));
    return;
  }

  // Show recently used section when no query
  if (!query) {
    const recent = getRecentCommands();
    const recentCmds = recent.map(n => commands.find(c => c.name === n)).filter(Boolean);
    if (recentCmds.length > 0) {
      const section = document.createElement("div");
      section.className = "cmd-category";
      const titleDiv = document.createElement("div");
      titleDiv.className = "cmd-category-title cmd-recent-title";
      titleDiv.textContent = "\u23F1 " + t("cmd.recentlyUsed");
      section.appendChild(titleDiv);
      const list = document.createElement("div");
      list.className = "cmd-list";
      recentCmds.forEach(c => {
        list.appendChild(buildCmdItem(c, "", statusLabel));
      });
      section.appendChild(list);
      container.appendChild(section);
    }
  }

  const grouped = {};
  for (const c of filtered) {
    if (!grouped[c.cat]) grouped[c.cat] = [];
    grouped[c.cat].push(c);
  }

  for (const [cat, cmds] of Object.entries(grouped)) {
    const section = document.createElement("div");
    section.className = "cmd-category";
    const title = document.createElement("div");
    title.className = "cmd-category-title";
    title.textContent = cat;
    section.appendChild(title);
    const list = document.createElement("div");
    list.className = "cmd-list";
    cmds.forEach(c => list.appendChild(buildCmdItem(c, query, statusLabel)));
    section.appendChild(list);
    container.appendChild(section);
  }
}

function buildCmdItem(c, query, statusLabel) {
  if (!statusLabel) {
    statusLabel = { allowed: t("cmd.status.allowed"), confirm: t("cmd.status.confirm"), blocked: t("cmd.status.blocked") };
  }
  const item = document.createElement("div");
  item.className = "cmd-item";

  const nameEl = document.createElement("div");
  nameEl.className = "cmd-name";
  if (query) {
    appendHighlightedCommandText(nameEl, c.name, query);
  } else {
    nameEl.textContent = c.name;
  }

  const descEl = document.createElement("div");
  descEl.className = "cmd-desc";
  descEl.textContent = c.desc;

  const badge = document.createElement("span");
  badge.className = `cmd-badge ${c.status}`;
  badge.textContent = statusLabel[c.status] || c.status;

  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = "cmd-copy-btn";
  const copyLabel = t("cmd.copyCommandLabel", { name: c.name });
  copyBtn.title = copyLabel;
  copyBtn.setAttribute("aria-label", copyLabel);
  copyBtn.textContent = "\u2192";

  item.appendChild(nameEl);
  item.appendChild(descEl);
  item.appendChild(badge);
  item.appendChild(copyBtn);

  bindCommandItemAction(item, (e) => {
    if (e.target === copyBtn) return;
    insertCommand(c.name);
  }, t("cmd.insertCommandLabel", { name: c.name }));
  copyBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    copyCommandName(copyBtn, c.name);
  });

  return item;
}

function appendHighlightedCommandText(target, text, query) {
  const source = String(text || "");
  const needle = String(query || "");
  if (!needle) {
    target.textContent = source;
    return;
  }
  const lowerSource = source.toLowerCase();
  const lowerNeedle = needle.toLowerCase();
  let index = 0;
  let matchAt = lowerSource.indexOf(lowerNeedle, index);
  while (matchAt !== -1) {
    if (matchAt > index) target.appendChild(document.createTextNode(source.slice(index, matchAt)));
    const mark = document.createElement("mark");
    mark.textContent = source.slice(matchAt, matchAt + needle.length);
    target.appendChild(mark);
    index = matchAt + needle.length;
    matchAt = lowerSource.indexOf(lowerNeedle, index);
  }
  if (index < source.length) target.appendChild(document.createTextNode(source.slice(index)));
}

function insertCommand(cmd) {
  trackRecentCommand(cmd);
  switchView("chat");
  chatInput.value = cmd.replace(/_/g, " ");
  chatInput.focus();
}

// ── TOOL QUICK ACTIONS ──────────────────────────
async function quickAction(command, promptText, paramKey) {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  const vals = await showInputModal(command, [{ id: "v", label: promptText, type: "text", required: true }], t("cmd.execute"));
  if (!vals) return;
  const value = vals.v;

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
      showToast(t("commands.success", {command}), "success");
      sendNotification("Lexa AI", t("cmd.successNotification", {command}));
    } else {
      addMessage(t("common.error") + ": " + (res.error || ""), "system");
      showToast(t("commands.failed", {command}), "error");
    }
  } catch (err) {
    hideTyping();
    addMessage(t("common.error") + ": " + err.message, "system");
    showToast(t("common.connectionError"), "error");
  }
}

async function runTool(command, params = {}) {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  switchView("chat");
  addMessage(t("cmd.startingCommand", {command}), "user");
  showTyping();

  try {
    const res = await window.lexa.execute(command, params, true);
    hideTyping();
    if (res.success) {
      const summary = typeof res.data === "string" ? res.data : JSON.stringify(res.data, null, 2).substring(0, 500);
      addMessage(summary, "system");
      showToast(t("commands.done", {command}), "success");
      sendNotification("Lexa AI", t("cmd.doneNotification", {command}));
    } else {
      addMessage(t("common.error") + ": " + (res.error || ""), "system");
      showToast(t("commands.failed", {command}), "error");
    }
  } catch (err) {
    hideTyping();
    addMessage(t("common.error") + ": " + err.message, "system");
    showToast(t("common.connectionError"), "error");
  }
}

// ── DASHBOARD QUICK ACTIONS ──────────────────────
function dashQuickTodo() {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  createTodo();
}

async function dashQuickPomodoro() {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  try {
    const status = await window.lexa.pomodoroStatus();
    if (status.running) {
      await window.lexa.pomodoroStop();
      showToast(t("pomodoro.stopped"), "info", 2500);
      const pomoBtn = document.getElementById("dash-btn-pomo");
      if (pomoBtn) pomoBtn.textContent = "\u23F1 Pomodoro";
    } else {
      // Use the new modal instead of prompt
      startPomodoro();
      // button text will be synced on next refreshDashboard
      return;
    }
    refreshDashboard();
  } catch (e) {
    console.warn("[Commands] Pomodoro quick action failed:", e.message || e);
    showToast(t("pomodoro.error"), "error");
  }
}
