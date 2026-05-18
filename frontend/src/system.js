/* ════════════════════════════════════════════════
   LEXA AI — System Module
   System Monitor view, System Tools (Window management,
   Autostart, Services, Port check, Uptime)
   Extracted from tools.js
   ════════════════════════════════════════════════ */

// ── SYSTEM VIEW ──────────────────────────────────
let systemAuditRefreshSeq = 0;

function createSystemView() {
  const div = document.createElement("div");
  div.className = "system-view active";
  div.innerHTML = `
    <div class="view-title">System <span>Monitor</span></div>
    <div class="info-grid" id="system-grid"></div>
    <div class="system-audit-panel">
      <div class="system-audit-header">
        <div>
          <div class="system-audit-kicker">${escapeHtml(t("system.trust"))}</div>
          <h3 class="section-title">${escapeHtml(t("system.recentToolActivity"))}</h3>
        </div>
        <button type="button" class="action-btn action-btn-sm" data-action="refreshSystemAuditActivity">${escapeHtml(t("system.refresh"))}</button>
      </div>
      <div class="system-audit-list" id="system-audit-list" role="list" aria-live="polite" aria-busy="false"></div>
    </div>
  `;
  return div;
}

async function refreshSystemView() {
  const grid = document.getElementById("system-grid");
  if (!grid) return;
  if (!LexaState.get("backendOnline")) {
    grid.innerHTML = '<div class="info-card"><div class="info-card-value text-error fs-16">' + escapeHtml(t("system.backendUnreachable")) + '</div></div>';
    setSystemAuditMessage(t("common.backendOffline"), "bad");
    return;
  }
  try {
    const res = await window.lexa.execute("system_info");
    if (!res.success) return;
    const d = res.data;
    const infoBar = (pct, color) => {
      const safePct = Math.min(100, pct);
      const tone = pct > 80 ? "meter-error" : pct > 60 ? "meter-warning" : color === "success" ? "meter-success" : "meter-accent";
      return `<div class="info-card-bar meter-width-${percentBucket(safePct)} ${tone}"></div>`;
    };
    grid.innerHTML = `
      <div class="info-card">
        <div class="info-card-label">${escapeHtml(t("system.cpuUsage"))}</div>
        <div class="info-card-value">${d.cpu_percent}%</div>
        <div class="info-card-sub">${escapeHtml(t("system.cores", {cores: d.cpu_cores, freq: d.cpu_freq_mhz || "?"}))}</div>
        <div class="info-card-bar-track">${infoBar(d.cpu_percent, "accent")}</div>
      </div>
      <div class="info-card">
        <div class="info-card-label">${escapeHtml(t("system.ram"))}</div>
        <div class="info-card-value">${d.ram_used_gb} GB</div>
        <div class="info-card-sub">${escapeHtml(t("system.ofTotal", {total: d.ram_total_gb, percent: d.ram_percent}))}</div>
        <div class="info-card-bar-track">${infoBar(d.ram_percent, "accent")}</div>
      </div>
      <div class="info-card">
        <div class="info-card-label">${escapeHtml(t("system.disk"))}</div>
        <div class="info-card-value">${d.disk_used_gb} GB</div>
        <div class="info-card-sub">${escapeHtml(t("system.ofTotal", {total: d.disk_total_gb, percent: d.disk_percent}))}</div>
        <div class="info-card-bar-track">${infoBar(d.disk_percent, "success")}</div>
      </div>
      <div class="info-card">
        <div class="info-card-label">${escapeHtml(t("system.battery"))}</div>
        <div class="info-card-value">${d.battery_percent !== null ? d.battery_percent + "%" : "N/A"}</div>
        <div class="info-card-sub">${d.battery_plugged ? escapeHtml(t("system.charging")) : escapeHtml(t("system.onBattery"))}</div>
        ${d.battery_percent !== null ? `<div class="info-card-bar-track">${infoBar(d.battery_percent, "success")}</div>` : ""}
      </div>
    `;
    refreshSystemAuditActivity();
  } catch (e) {
    console.warn("[System] Failed to refresh system view:", e.message || e);
    grid.innerHTML = ""; const errCard = document.createElement("div"); errCard.className = "info-card"; const errVal = document.createElement("div"); errVal.className = "info-card-value text-error fs-16"; errVal.textContent = t("toast.loadError"); errCard.appendChild(errVal); grid.appendChild(errCard);
    setSystemAuditMessage(t("toast.loadError"), "bad");
  }
}

function systemAuditStatusClass(status) {
  const value = String(status || "").toLowerCase();
  if (value.includes("blocked") || value.includes("error") || value.includes("failed")) return "bad";
  if (value.includes("await") || value.includes("confirm") || value.includes("warn")) return "warn";
  if (value.includes("dry_run") || value.includes("read") || value.includes("lexa_code_loop")) return "info";
  return "good";
}

function systemAuditTime(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return String(timestamp || "");
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function setSystemAuditMessage(message, tone = "muted", busy = false) {
  const list = document.getElementById("system-audit-list");
  if (!list) return;
  list.setAttribute("aria-busy", busy ? "true" : "false");
  const row = document.createElement("div");
  row.className = `system-audit-empty system-audit-${tone}`;
  row.textContent = message;
  list.replaceChildren(row);
}

function renderSystemAuditEntries(payload) {
  const list = document.getElementById("system-audit-list");
  if (!list) return;
  if (!payload || payload.ok === false) {
    setSystemAuditMessage(payload?.error || t("system.auditUnavailable"), "bad");
    return;
  }
  const entries = Array.isArray(payload.entries) ? payload.entries : [];
  if (entries.length === 0) {
    const skipped = Number(payload.skipped_noise || 0);
    const message = skipped > 0 ? t("system.auditNoiseOnly", {count: skipped}) : t("system.auditEmpty");
    setSystemAuditMessage(message, "muted");
    return;
  }

  const fragment = document.createDocumentFragment();
  entries.slice(0, 12).forEach((entry) => {
    const row = document.createElement("div");
    row.className = "system-audit-row";
    row.setAttribute("role", "listitem");

    const tone = systemAuditStatusClass(entry.status);
    const dot = document.createElement("span");
    dot.className = `system-audit-dot system-audit-${tone}`;
    dot.setAttribute("aria-hidden", "true");

    const main = document.createElement("div");
    main.className = "system-audit-main";

    const top = document.createElement("div");
    top.className = "system-audit-top";

    const command = document.createElement("span");
    command.className = "system-audit-command";
    command.textContent = entry.command || "unknown";
    command.title = command.textContent;

    const status = document.createElement("span");
    status.className = `system-audit-status system-audit-${tone}`;
    status.textContent = entry.status || "unknown";
    status.title = status.textContent;

    const time = document.createElement("span");
    time.className = "system-audit-time";
    time.textContent = systemAuditTime(entry.timestamp);
    time.title = entry.timestamp || time.textContent;
    row.setAttribute(
      "aria-label",
      [command.textContent, status.textContent, time.textContent, entry.redacted ? t("system.auditDetailsRedacted") : ""]
        .filter(Boolean)
        .join(" - ")
    );

    top.append(command, status, time);
    main.appendChild(top);

    if (entry.details || entry.redacted) {
      const details = document.createElement("div");
      details.className = "system-audit-details";
      if (entry.redacted) {
        const privacy = document.createElement("span");
        privacy.className = "system-audit-redacted";
        privacy.textContent = t("system.auditDetailsRedacted");
        privacy.title = privacy.textContent;
        details.appendChild(privacy);
      }
      if (entry.details) {
        const text = document.createElement("span");
        text.className = "system-audit-details-text";
        text.textContent = entry.details;
        text.title = entry.details;
        details.appendChild(text);
      }
      main.appendChild(details);
    }

    row.append(dot, main);
    fragment.appendChild(row);
  });
  list.setAttribute("aria-busy", "false");
  list.replaceChildren(fragment);
}

async function refreshSystemAuditActivity() {
  const list = document.getElementById("system-audit-list");
  if (!list) return;
  const requestId = ++systemAuditRefreshSeq;
  if (!LexaState.get("backendOnline")) {
    setSystemAuditMessage(t("common.backendOffline"), "bad");
    return;
  }
  if (!window.lexa?.companionAuditRecent) {
    setSystemAuditMessage(t("system.auditUnavailable"), "bad");
    return;
  }
  setSystemAuditMessage(t("common.loading"), "muted", true);
  try {
    const payload = await window.lexa.companionAuditRecent(12, true);
    if (requestId !== systemAuditRefreshSeq) return;
    renderSystemAuditEntries(payload);
  } catch (e) {
    if (requestId !== systemAuditRefreshSeq) return;
    console.warn("[System] Failed to refresh tool activity:", e.message || e);
    setSystemAuditMessage(e.message || t("system.auditUnavailable"), "bad");
  }
}

// ── SYSTEM TOOLS (Phase 21: PC-Kontrolle erweitert) ──

async function refreshSysQuickBar() {
  if (!LexaState.get("backendOnline")) return;
  try {
    const res = await window.lexa.execute("system_uptime");
    const bar = document.getElementById("sys-quick-bar");
    if (!bar) return;
    if (res.success && res.data) {
      const d = res.data;
      bar.innerHTML = `
        <div class="prod-stat-card">
          <div class="prod-stat-value">${escapeHtml(String(d.formatted || "?"))}</div>
          <div class="prod-stat-label">Uptime</div>
        </div>
        <div class="prod-stat-card">
          <div class="prod-stat-value">${d.boot_time ? escapeHtml(d.boot_time.split(" ")[1] || "?") : "?"}</div>
          <div class="prod-stat-label">${escapeHtml(t("system.bootTime"))}</div>
        </div>
      `;
    }
  } catch (e) { console.warn("[System] Failed to refresh sys quick bar:", e.message || e); }
}

// ── Window Management ──

async function windowLayoutAction(layout) {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  try {
    const res = await window.lexa.execute("window_layout", { layout });
    showToast(res.success ? t("system.layoutSet", {layout}) : t("system.layoutError"), res.success ? "success" : "error");
  } catch (e) { console.warn("[System] windowLayoutAction failed:", e.message || e); showToast(t("common.connectionError"), "error"); }
}

async function windowMoveAction() {
  const vals = await showInputModal(t("system.moveWindowTitle"), [
    { id: "title", label: t("system.windowTitleLabel"), type: "text", placeholder: "Chrome", required: true },
    { id: "x", label: t("system.xPosition"), type: "number", default: 0 },
    { id: "y", label: t("system.yPosition"), type: "number", default: 0 }
  ], t("system.moveBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("system.moveWindowMsg", {title: vals.title, x: vals.x, y: vals.y}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("window_move", { title: vals.title, x: Number(vals.x), y: Number(vals.y) });
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("system.windowMoved") : t("common.error"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function windowResizeAction() {
  const vals = await showInputModal(t("system.resizeWindowTitle"), [
    { id: "title", label: t("system.windowTitleLabel"), type: "text", placeholder: "Chrome", required: true },
    { id: "width", label: t("system.widthLabel"), type: "number", default: 1024, min: 100 },
    { id: "height", label: t("system.heightLabel"), type: "number", default: 768, min: 100 }
  ], t("system.adjustBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("system.resizeWindowMsg", {title: vals.title, width: vals.width, height: vals.height}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("window_resize", { title: vals.title, width: Number(vals.width), height: Number(vals.height) });
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("system.sizeChanged") : t("common.error"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

// ── Autostart ──

async function viewAutostartList() {
  switchView("chat");
  addMessage(t("system.loadingAutostart"), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("autostart_list");
    hideTyping();
    if (res.success && Array.isArray(res.data) && res.data.length > 0) {
      const list = res.data.map(e =>
        `\u2022 ${e.name} \u2014 ${e.value?.substring(0, 80)}${e.value?.length > 80 ? "..." : ""}`
      ).join("\n");
      addMessage(t("system.autostartEntries", {count: res.data.length, list}), "system");
    } else {
      addMessage(t("empty.noAutostart"), "system");
    }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function autostartAddAction() {
  const vals = await showInputModal(t("system.addAutostartTitle"), [
    { id: "name", label: t("system.entryNameLabel"), type: "text", placeholder: "MeinProgramm", required: true },
    { id: "path", label: t("system.exePathLabel"), type: "text", placeholder: "C:\\Program Files\\App\\app.exe", required: true }
  ], t("system.addBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("system.addAutostartMsg", {name: vals.name}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("autostart_add", { name: vals.name, path: vals.path }, true);
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("system.autostartAdded") : t("common.error"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

// ── Services ──

async function viewServiceList() {
  switchView("chat");
  addMessage(t("system.loadingServices"), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("service_list", { filter_status: "running" });
    hideTyping();
    if (res.success && Array.isArray(res.data) && res.data.length > 0) {
      const list = res.data.slice(0, 30).map(s =>
        `${s.status === "Running" ? "\u{1F7E2}" : "\u{1F534}"} ${s.display_name} [${s.name}] \u2014 ${s.start_type}`
      ).join("\n");
      addMessage(t("system.runningServices", {count: res.data.length, list}), "system");
    } else {
      addMessage(t("empty.noServices"), "system");
    }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

// ── Port Check ──

async function portCheckAction() {
  const vals = await showInputModal(t("system.portCheckTitle"), [
    { id: "host", label: "Host", type: "text", placeholder: "127.0.0.1", default: "127.0.0.1", required: true },
    { id: "port", label: "Port", type: "number", default: 80, min: 1, max: 65535, required: true }
  ], t("system.checkBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("system.portCheckMsg", {host: vals.host, port: vals.port}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("port_check", { host: vals.host, port: Number(vals.port) });
    hideTyping();
    if (res.success) {
      const d = res.data;
      addMessage(d.open ? t("system.portOpen", {port: d.port, host: d.host}) : t("system.portClosed", {port: d.port, host: d.host}), "system");
      showToast(t("system.portStatus", {port: d.port, status: d.status}), d.open ? "success" : "warning");
    } else {
      addMessage(t("common.error") + ": " + res.error, "system");
    }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}
