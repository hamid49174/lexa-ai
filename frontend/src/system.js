/* LEXA AI - System Module
   System Monitor view, System Tools (Window management,
   Autostart, Services, Port check, Uptime)
   Extracted from tools.js
*/

// SYSTEM VIEW
let systemViewRefreshSeq = 0;
let systemAuditRefreshSeq = 0;
let startupHealthRefreshSeq = 0;
let hermesOverviewRefreshSeq = 0;

function systemDisplayNumber(value, fallback = "0") {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return String(Math.round(num * 10) / 10);
}

function systemDisplayPercent(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return 0;
  return Math.max(0, Math.min(100, num));
}

function systemDisplayCount(value, fallback = "0") {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  return String(Math.max(0, Math.floor(num)));
}

function systemBootTimeLabel(value) {
  if (!value) return "?";
  return String(value).split(" ")[1] || "?";
}

function createSystemQuickStat(value, label) {
  const card = document.createElement("div");
  card.className = "prod-stat-card";
  const valueEl = document.createElement("div");
  valueEl.className = "prod-stat-value";
  valueEl.textContent = String(value || "?");
  const labelEl = document.createElement("div");
  labelEl.className = "prod-stat-label";
  labelEl.textContent = String(label || "");
  card.append(valueEl, labelEl);
  return card;
}

function createSystemInfoBar(percent, color = "accent") {
  const safePct = systemDisplayPercent(percent);
  const tone = safePct > 80 ? "meter-error" : safePct > 60 ? "meter-warning" : color === "success" ? "meter-success" : "meter-accent";
  const bar = document.createElement("div");
  bar.className = `info-card-bar meter-width-${percentBucket(safePct)} ${tone}`;
  return bar;
}

function createSystemInfoCard(label, value, subText, percent = null, color = "accent", extraValueClass = "") {
  const card = document.createElement("div");
  card.className = "info-card";
  const labelEl = document.createElement("div");
  labelEl.className = "info-card-label";
  labelEl.textContent = String(label || "");
  const valueEl = document.createElement("div");
  valueEl.className = extraValueClass ? `info-card-value ${extraValueClass}` : "info-card-value";
  valueEl.textContent = String(value || "");
  card.append(labelEl, valueEl);
  if (subText) {
    const subEl = document.createElement("div");
    subEl.className = "info-card-sub";
    subEl.textContent = String(subText);
    card.appendChild(subEl);
  }
  if (percent !== null && percent !== undefined) {
    const track = document.createElement("div");
    track.className = "info-card-bar-track";
    track.appendChild(createSystemInfoBar(percent, color));
    card.appendChild(track);
  }
  return card;
}

function createSystemTextElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = String(text || "");
  return element;
}

function createSystemActionButton(action, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "action-btn action-btn-sm";
  button.dataset.action = action;
  button.textContent = label;
  return button;
}

function createSystemLoadingContent(id, className = "system-overview-content") {
  const content = document.createElement("div");
  content.id = id;
  content.className = className;
  content.setAttribute("aria-live", "polite");
  content.setAttribute("aria-busy", "false");
  content.appendChild(createSystemTextElement("div", "system-audit-empty", t("common.loading")));
  return content;
}

function createSystemPanelHeader(kickerText, titleText, actions) {
  const header = document.createElement("div");
  header.className = "system-audit-header";
  const copy = document.createElement("div");
  copy.append(
    createSystemTextElement("div", "system-audit-kicker", kickerText),
    createSystemTextElement("h3", "section-title", titleText)
  );
  header.appendChild(copy);
  if (actions?.length) {
    const actionsWrap = document.createElement("div");
    actionsWrap.className = "system-overview-actions";
    actionsWrap.append(...actions);
    header.appendChild(actionsWrap);
  }
  return header;
}

function createSystemView() {
  const div = document.createElement("div");
  div.className = "system-view active";

  const title = document.createElement("div");
  title.className = "view-title";
  title.append(document.createTextNode("System "), createSystemTextElement("span", "", "Monitor"));

  const grid = document.createElement("div");
  grid.className = "info-grid";
  grid.id = "system-grid";

  const startupPanel = document.createElement("div");
  startupPanel.className = "system-startup-panel";
  startupPanel.id = "startup-health-panel";
  startupPanel.append(
    createSystemPanelHeader(t("system.startupHealthKicker"), t("system.startupHealthTitle"), [
      createSystemActionButton("refreshStartupHealth", t("system.refresh")),
    ]),
    createSystemLoadingContent("startup-health-content", "system-overview-content system-startup-content")
  );

  const hermesPanel = document.createElement("div");
  hermesPanel.className = "system-overview-panel";
  hermesPanel.id = "hermes-overview-panel";
  hermesPanel.append(
    createSystemPanelHeader(t("system.hermesCockpitKicker"), t("system.hermesCockpitTitle"), [
      createSystemActionButton("hermesOverviewAskInChat", t("system.hermesAskChat")),
      createSystemActionButton("refreshHermesOverview", t("system.refresh")),
    ]),
    createSystemLoadingContent("hermes-overview-content")
  );

  const auditPanel = document.createElement("div");
  auditPanel.className = "system-audit-panel";
  auditPanel.appendChild(createSystemPanelHeader(t("system.trust"), t("system.recentToolActivity"), [
    createSystemActionButton("refreshSystemAuditActivity", t("system.refresh")),
  ]));
  const auditList = document.createElement("div");
  auditList.className = "system-audit-list";
  auditList.id = "system-audit-list";
  auditList.setAttribute("role", "list");
  auditList.setAttribute("aria-live", "polite");
  auditList.setAttribute("aria-busy", "false");
  auditPanel.appendChild(auditList);

  div.append(title, grid, startupPanel, hermesPanel, auditPanel);
  return div;
}

async function refreshSystemView() {
  const grid = document.getElementById("system-grid");
  if (!grid) return;
  const requestId = ++systemViewRefreshSeq;
  if (!LexaState.get("backendOnline")) {
    grid.replaceChildren(createSystemInfoCard("", t("system.backendUnreachable"), "", null, "accent", "text-error fs-16"));
    setStartupHealthMessage(t("common.backendOffline"), "bad");
    setHermesOverviewMessage(t("common.backendOffline"), "bad");
    setSystemAuditMessage(t("common.backendOffline"), "bad");
    return;
  }
  try {
    const res = typeof window.requestSystemInfoCached === "function"
      ? await window.requestSystemInfoCached({ maxAgeMs: 5000, force: true })
      : await window.lexa.execute("system_info");
    if (requestId !== systemViewRefreshSeq || !LexaState.get("backendOnline")) return;
    if (!res.success) {
      refreshStartupHealth();
      refreshHermesOverview();
      return;
    }
    const d = res.data;
    const cpuPercent = systemDisplayPercent(d.cpu_percent);
    const cpuCores = systemDisplayNumber(d.cpu_cores, "?");
    const cpuFreq = systemDisplayNumber(d.cpu_freq_mhz, "?");
    const ramUsed = systemDisplayNumber(d.ram_used_gb);
    const ramTotal = systemDisplayNumber(d.ram_total_gb);
    const ramPercent = systemDisplayPercent(d.ram_percent);
    const diskUsed = systemDisplayNumber(d.disk_used_gb);
    const diskTotal = systemDisplayNumber(d.disk_total_gb);
    const diskPercent = systemDisplayPercent(d.disk_percent);
    const batteryPercent = d.battery_percent !== null && d.battery_percent !== undefined
      ? systemDisplayPercent(d.battery_percent)
      : null;
    grid.replaceChildren(
      createSystemInfoCard(t("system.cpuUsage"), `${cpuPercent}%`, t("system.cores", {cores: cpuCores, freq: cpuFreq}), cpuPercent),
      createSystemInfoCard(t("system.ram"), `${ramUsed} GB`, t("system.ofTotal", {total: ramTotal, percent: ramPercent}), ramPercent),
      createSystemInfoCard(t("system.disk"), `${diskUsed} GB`, t("system.ofTotal", {total: diskTotal, percent: diskPercent}), diskPercent, "success"),
      createSystemInfoCard(
        t("system.battery"),
        batteryPercent !== null ? `${batteryPercent}%` : "N/A",
        d.battery_plugged ? t("system.charging") : t("system.onBattery"),
        batteryPercent,
        "success"
      )
    );
    refreshStartupHealth();
    refreshHermesOverview();
    refreshSystemAuditActivity();
  } catch (e) {
    if (requestId !== systemViewRefreshSeq || !LexaState.get("backendOnline")) return;
    console.warn("[System] Failed to refresh system view:", e.message || e);
    grid.replaceChildren(createSystemInfoCard("", t("toast.loadError"), "", null, "accent", "text-error fs-16"));
    refreshStartupHealth();
    setSystemAuditMessage(t("toast.loadError"), "bad");
    refreshHermesOverview();
  }
}

function hermesOverviewTone(state) {
  const value = String(state || "").toLowerCase();
  if (value === "ok" || value === "ready" || value === "enabled") return "good";
  if (value === "warn" || value === "warning" || value === "attention") return "warn";
  if (value === "offline" || value === "error" || value === "failed" || value === "blocked") return "bad";
  return "info";
}

function setHermesOverviewMessage(message, tone = "muted", busy = false) {
  const target = document.getElementById("hermes-overview-content");
  if (!target) return;
  target.setAttribute("aria-busy", busy ? "true" : "false");
  const row = document.createElement("div");
  row.className = `system-audit-empty system-audit-${tone}`;
  row.textContent = message;
  target.replaceChildren(row);
}

function systemErrorMessage(payload, fallback) {
  const text = payload?.error || payload?.message || payload?.summary || fallback;
  const requestId = String(payload?.requestId || payload?.request_id || "").replace(/\s+/g, " ").trim();
  return requestId ? `${text} (Request ID: ${requestId.slice(0, 80)})` : text;
}

function setStartupHealthMessage(message, tone = "muted", busy = false) {
  const target = document.getElementById("startup-health-content");
  if (!target) return;
  target.setAttribute("aria-busy", busy ? "true" : "false");
  const row = document.createElement("div");
  row.className = `system-audit-empty system-audit-${tone}`;
  row.textContent = message;
  target.replaceChildren(row);
}

function startupHealthMetric(counts) {
  return `${systemDisplayCount(counts?.ok)} / ${systemDisplayCount(counts?.warn)} / ${systemDisplayCount(counts?.blocked)}`;
}

function createSystemOverviewSummary(state, tone, summary) {
  const row = document.createElement("div");
  row.className = "system-overview-summary";
  const stateEl = document.createElement("span");
  stateEl.className = `system-overview-state system-audit-${tone}`;
  stateEl.textContent = String(state || "unknown");
  const summaryEl = document.createElement("div");
  summaryEl.className = "system-overview-summary-text";
  summaryEl.textContent = String(summary || "");
  row.append(stateEl, summaryEl);
  return row;
}

function createSystemOverviewMetric(label, value) {
  const item = document.createElement("div");
  item.className = "system-overview-metric";
  const labelEl = document.createElement("span");
  labelEl.textContent = String(label || "");
  const valueEl = document.createElement("strong");
  valueEl.textContent = String(value || "");
  item.append(labelEl, valueEl);
  return item;
}

function createSystemOverviewMuted(message) {
  const muted = document.createElement("div");
  muted.className = "system-overview-muted";
  muted.textContent = String(message || "");
  return muted;
}

function createSystemOverviewCheckRow(check) {
  const tone = hermesOverviewTone(check?.state);
  const row = document.createElement("div");
  row.className = "system-overview-check";
  const dot = document.createElement("span");
  dot.className = `system-audit-dot system-audit-${tone}`;
  dot.setAttribute("aria-hidden", "true");
  const label = document.createElement("span");
  label.className = "system-overview-check-label";
  label.textContent = String(check?.label || check?.id || "Check");
  const status = document.createElement("span");
  status.className = `system-audit-status system-audit-${tone}`;
  status.textContent = String(check?.state || "unknown");
  row.append(dot, label, status);
  return row;
}

function createSystemOverviewCapabilityGapRow(gap) {
  const tone = hermesOverviewTone(gap?.state);
  const row = document.createElement("div");
  row.className = "system-overview-check system-overview-capability-gap";
  const dot = document.createElement("span");
  dot.className = `system-audit-dot system-audit-${tone}`;
  dot.setAttribute("aria-hidden", "true");
  const label = document.createElement("span");
  label.className = "system-overview-check-label";
  const next = gap?.nextAction ? ` - ${gap.nextAction}` : "";
  label.textContent = `${String(gap?.label || gap?.id || "Capability")} (${String(gap?.lexaSurface || "unknown")})${next}`;
  const status = document.createElement("span");
  status.className = `system-audit-status system-audit-${tone}`;
  status.textContent = String(gap?.state || "unknown");
  row.append(dot, label, status);
  return row;
}

function createSystemOverviewFileRow(label, code) {
  const row = document.createElement("div");
  row.className = "system-overview-file";
  const labelEl = document.createElement("span");
  labelEl.textContent = String(label || "");
  const codeEl = document.createElement("code");
  codeEl.textContent = String(code || "");
  row.append(labelEl, codeEl);
  return row;
}

function createSystemOverviewSection(label, contentClass, children) {
  const section = document.createElement("section");
  section.className = "system-overview-section";
  section.setAttribute("aria-label", String(label || ""));
  const title = document.createElement("div");
  title.className = "system-overview-section-title";
  title.textContent = String(label || "");
  const body = document.createElement("div");
  body.className = contentClass;
  body.append(...children);
  section.append(title, body);
  return section;
}

function createSystemOverviewTaskList(tasks, fallback) {
  const list = document.createElement("ul");
  list.className = "system-overview-tasks";
  const rows = tasks.length ? tasks : [fallback];
  rows.forEach((task) => {
    const item = document.createElement("li");
    item.textContent = String(task || "");
    list.appendChild(item);
  });
  return list;
}

function renderStartupHealth(payload) {
  const target = document.getElementById("startup-health-content");
  if (!target) return;
  if (!payload || payload.ok === false) {
    setStartupHealthMessage(systemErrorMessage(payload, t("system.startupHealthUnavailable")), "bad");
    return;
  }

  const checks = Array.isArray(payload.checks) ? payload.checks.slice(0, 8) : [];
  const counts = payload.counts || {};
  const groups = payload.groups || {};
  const providers = Array.isArray(groups.providers?.available) ? groups.providers.available : [];
  const tools = groups.tools || {};
  const stateTone = hermesOverviewTone(payload.state);
  const toolsPct = systemDisplayNumber(systemDisplayPercent(tools.healthPct));
  const providerCount = systemDisplayCount(providers.length);

  target.setAttribute("aria-busy", "false");
  const metrics = document.createElement("div");
  metrics.className = "system-overview-metrics";
  metrics.append(
    createSystemOverviewMetric(t("system.startupMetricChecks"), startupHealthMetric(counts)),
    createSystemOverviewMetric(t("system.startupMetricProviders"), `${providerCount}/4`),
    createSystemOverviewMetric(t("system.startupMetricTools"), `${toolsPct}%`)
  );

  const checkRows = checks.length
    ? checks.map((check) => createSystemOverviewCheckRow(check))
    : [createSystemOverviewMuted(t("system.startupHealthNoSummary"))];
  const providerRows = providers.length
    ? providers.map((provider) => createSystemOverviewFileRow(provider, groups.providers?.selected === provider ? "selected" : "available"))
    : [createSystemOverviewMuted(t("system.startupNoProviders"))];
  const nextText = document.createTextNode(String(payload.nextAction || t("system.startupNoNextAction")));

  const grid = document.createElement("div");
  grid.className = "system-overview-grid";
  grid.append(
    createSystemOverviewSection(t("system.startupChecks"), "system-overview-checks", checkRows),
    createSystemOverviewSection(t("system.startupProviders"), "system-overview-files", providerRows),
    createSystemOverviewSection(t("system.startupNextAction"), "system-overview-next", [nextText])
  );

  target.replaceChildren(
    createSystemOverviewSummary(payload.state, stateTone, payload.summary || t("system.startupHealthNoSummary")),
    metrics,
    grid
  );
}

async function refreshStartupHealth() {
  const target = document.getElementById("startup-health-content");
  if (!target) return;
  const requestId = ++startupHealthRefreshSeq;
  if (!LexaState.get("backendOnline")) {
    setStartupHealthMessage(t("common.backendOffline"), "bad");
    return;
  }
  if (!window.lexa?.startupHealth) {
    setStartupHealthMessage(t("system.startupHealthUnavailable"), "bad");
    return;
  }
  setStartupHealthMessage(t("common.loading"), "muted", true);
  try {
    const payload = await window.lexa.startupHealth({ probeVoice: false });
    if (requestId !== startupHealthRefreshSeq) return;
    renderStartupHealth(payload);
  } catch (e) {
    if (requestId !== startupHealthRefreshSeq) return;
    console.warn("[System] Failed to refresh startup health:", e.message || e);
    setStartupHealthMessage(e.message || t("system.startupHealthUnavailable"), "bad");
  }
}

function hermesDraftMetric(counts) {
  const drafts = counts?.drafts || {};
  return `${systemDisplayCount(drafts.pending)} / ${systemDisplayCount(drafts.approved)} / ${systemDisplayCount(drafts.rejected)}`;
}

function hermesCapabilityMetric(capCounts) {
  const ready = systemDisplayCount(capCounts?.ready);
  const total = systemDisplayCount(capCounts?.total);
  const weak = systemDisplayCount(capCounts?.weakLexaSurface);
  const missing = systemDisplayCount(capCounts?.missingLexaSurface);
  return `${ready}/${total} ready, ${weak}/${missing} weak/missing`;
}

function hermesProviderMetric(providerCounts) {
  const ready = systemDisplayCount(providerCounts?.fallbacksReady);
  const total = systemDisplayCount(providerCounts?.fallbacks);
  return `${ready}/${total} fallbacks`;
}

function createHermesProviderRows(providerStatus) {
  if (!providerStatus || typeof providerStatus !== "object") {
    return [createSystemOverviewMuted(t("system.hermesNoProviderStatus"))];
  }
  const rows = [];
  const primary = providerStatus.primary || {};
  const primaryProvider = primary.effectiveProviderHint || primary.provider || primary.providerId || "auto";
  const primaryModel = primary.model || primary.provider || "auto";
  rows.push(createSystemOverviewFileRow(t("system.hermesPrimaryProvider"), `${primaryModel} via ${primaryProvider}`));
  const fallbacks = Array.isArray(providerStatus.fallbacks) ? providerStatus.fallbacks.slice(0, 4) : [];
  if (!fallbacks.length) {
    rows.push(createSystemOverviewMuted(providerStatus.nextAction || t("system.hermesNoFallbacks")));
    return rows;
  }
  fallbacks.forEach((entry, index) => {
    const state = entry.credentialReady ? "ready" : "needs credentials";
    rows.push(createSystemOverviewFileRow(
      `${t("system.hermesFallbackProvider")} ${index + 1}`,
      `${entry.model || "model"} via ${entry.provider || entry.providerId || "provider"} (${state})`
    ));
  });
  return rows;
}

function renderHermesOverview(payload) {
  const target = document.getElementById("hermes-overview-content");
  if (!target) return;
  if (!payload || payload.ok === false) {
    setHermesOverviewMessage(systemErrorMessage(payload, t("system.hermesOverviewUnavailable")), "bad");
    return;
  }

  const checks = Array.isArray(payload.checks) ? payload.checks.slice(0, 7) : [];
  const files = Array.isArray(payload.contextFiles) ? payload.contextFiles.slice(0, 5) : [];
  const tasks = Array.isArray(payload.nextTasks) ? payload.nextTasks.slice(0, 4) : [];
  const counts = payload.counts || {};
  const capabilityPayload = payload.capabilities || {};
  const capCounts = counts.capabilities || capabilityPayload.counts || {};
  const capGaps = Array.isArray(capabilityPayload.gaps) ? capabilityPayload.gaps.slice(0, 4) : [];
  const providerStatus = payload.providerStatus || {};
  const providerCounts = providerStatus.counts || {};
  const stateTone = hermesOverviewTone(payload.healthState);
  const contextCount = systemDisplayCount(counts.contextFiles ?? files.length ?? 0);

  target.setAttribute("aria-busy", "false");
  const metrics = document.createElement("div");
  metrics.className = "system-overview-metrics";
  metrics.append(
    createSystemOverviewMetric(t("system.hermesMetricDrafts"), hermesDraftMetric(counts)),
    createSystemOverviewMetric(t("system.hermesMetricContext"), contextCount),
    createSystemOverviewMetric(t("system.hermesMetricSafeMode"), payload.safeMode ? t("common.yes") : t("common.no")),
    createSystemOverviewMetric(t("system.hermesMetricCapabilities"), hermesCapabilityMetric(capCounts)),
    createSystemOverviewMetric(t("system.hermesMetricFallbacks"), hermesProviderMetric(providerCounts))
  );

  const checkRows = checks.length
    ? checks.map((check) => createSystemOverviewCheckRow(check))
    : [createSystemOverviewMuted(t("system.startupHealthNoSummary"))];
  const fileRows = files.length
    ? files.map((file) => createSystemOverviewFileRow(file.title || file.path || "OS-Datei", file.path || ""))
    : [createSystemOverviewMuted(t("system.hermesNoContext"))];
  const gapRows = capGaps.length
    ? capGaps.map((gap) => createSystemOverviewCapabilityGapRow(gap))
    : [createSystemOverviewMuted(t("system.hermesNoCapabilityGaps"))];
  const providerRows = createHermesProviderRows(providerStatus);
  const nextText = document.createTextNode(String(payload.nextAction || t("system.hermesNoNextTask")));
  const taskList = createSystemOverviewTaskList(tasks, payload.nextAction || t("system.hermesNoNextTask"));

  const grid = document.createElement("div");
  grid.className = "system-overview-grid";
  grid.append(
    createSystemOverviewSection(t("system.hermesChecks"), "system-overview-checks", checkRows),
    createSystemOverviewSection(t("system.hermesContextFiles"), "system-overview-files", fileRows),
    createSystemOverviewSection(t("system.hermesProviders"), "system-overview-files", providerRows),
    createSystemOverviewSection(t("system.hermesCapabilityGaps"), "system-overview-checks", gapRows),
    createSystemOverviewSection(t("system.hermesNextAction"), "system-overview-next", [nextText, taskList])
  );

  target.replaceChildren(
    createSystemOverviewSummary(payload.healthState, stateTone, payload.summary || t("system.hermesOverviewNoSummary")),
    metrics,
    grid
  );
}

async function refreshHermesOverview() {
  const target = document.getElementById("hermes-overview-content");
  if (!target) return;
  const requestId = ++hermesOverviewRefreshSeq;
  if (!LexaState.get("backendOnline")) {
    setHermesOverviewMessage(t("common.backendOffline"), "bad");
    return;
  }
  if (!window.lexa?.hermesOverview) {
    setHermesOverviewMessage(t("system.hermesOverviewUnavailable"), "bad");
    return;
  }
  setHermesOverviewMessage(t("common.loading"), "muted", true);
  try {
    const payload = await window.lexa.hermesOverview({ includeContext: true });
    if (requestId !== hermesOverviewRefreshSeq) return;
    renderHermesOverview(payload);
  } catch (e) {
    if (requestId !== hermesOverviewRefreshSeq) return;
    console.warn("[System] Failed to refresh Hermes overview:", e.message || e);
    setHermesOverviewMessage(e.message || t("system.hermesOverviewUnavailable"), "bad");
  }
}

function hermesOverviewAskInChat() {
  if (typeof switchView === "function") switchView("chat");
  if (typeof _setChatInputValue === "function") {
    _setChatInputValue("Was ist der Stand von Lexa, Hermes und OS?");
    chatInput?.focus?.();
    showToast(t("system.hermesPromptReady"), "success", 2200);
    return;
  }
  showToast(t("pos.chatInputUnavailable"), "warning", 3000);
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
    setSystemAuditMessage(systemErrorMessage(payload, t("system.auditUnavailable")), "bad");
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

// SYSTEM TOOLS (Phase 21: PC-Kontrolle erweitert)

async function refreshSysQuickBar() {
  if (!LexaState.get("backendOnline")) return;
  try {
    const res = await window.lexa.execute("system_uptime");
    const bar = document.getElementById("sys-quick-bar");
    if (!bar) return;
    if (res.success && res.data) {
      const d = res.data;
      bar.replaceChildren(
        createSystemQuickStat(d.formatted, "Uptime"),
        createSystemQuickStat(systemBootTimeLabel(d.boot_time), t("system.bootTime"))
      );
    }
  } catch (e) { console.warn("[System] Failed to refresh sys quick bar:", e.message || e); }
}

// Window Management

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

// Autostart

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

// Services

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

// Port Check

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
