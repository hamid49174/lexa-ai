// ── MCP-Server-Verwaltung (Settings) ─────────────────────────────
// Liste konfigurierter MCP-Server mit Status + Verbinden/Trennen/Entfernen/
// Hinzufuegen. CSP-sicher (nur DOM-APIs, data-action-Dispatch, kein innerHTML
// mit Fremddaten). Add/Remove laufen ueber kritische, presence-gegatete Bridges.

let _mcpActionRunning = false;

function mcpParseArgs(text) {
  return String(text || "")
    .split(/\r?\n/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function mcpParseEnv(text) {
  const env = {};
  for (const line of String(text || "").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const key = trimmed.slice(0, eq).trim();
    if (key) env[key] = trimmed.slice(eq + 1).trim();
  }
  return env;
}

function mcpStatusLabel(st) {
  if (st === "connected") return t("mcp.statusConnected");
  if (st === "error") return t("mcp.statusError");
  return t("mcp.statusDisconnected");
}

function mcpEmptyRow(message) {
  const el = document.createElement("div");
  el.className = "mcp-empty";
  el.textContent = message;
  return el;
}

function mcpActionButton(label, action, arg, extraClass) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "action-btn action-btn-sm" + (extraClass ? " " + extraClass : "");
  btn.dataset.action = action;
  btn.dataset.arg = arg;
  btn.textContent = label;
  return btn;
}

function mcpServerRow(server) {
  const row = document.createElement("div");
  row.className = "mcp-server-row";

  const info = document.createElement("div");
  info.className = "mcp-server-info";
  const name = document.createElement("div");
  name.className = "mcp-server-name";
  name.textContent = server.name || "";
  const cmd = document.createElement("div");
  cmd.className = "mcp-server-cmd";
  const argList = Array.isArray(server.args) ? server.args : [];
  cmd.textContent = [server.command || "", ...argList].join(" ").trim();
  const status = document.createElement("span");
  const st = server.status || (server.connected ? "connected" : "disconnected");
  status.className = "mcp-status mcp-status-" + st;
  status.textContent = mcpStatusLabel(st);
  info.append(name, cmd, status);

  const actions = document.createElement("div");
  actions.className = "mcp-server-actions";
  if (st === "connected") {
    actions.appendChild(mcpActionButton(t("mcp.disconnect"), "mcpDisconnectServer", server.name));
  } else {
    actions.appendChild(mcpActionButton(t("mcp.connect"), "mcpConnectServer", server.name));
  }
  actions.appendChild(mcpActionButton(t("mcp.remove"), "mcpRemoveServer", server.name, "action-btn-danger"));

  row.append(info, actions);
  return row;
}

function renderMcpServerList(listEl, data) {
  if (!listEl) return;
  if (!data || data.enabled === false) {
    listEl.replaceChildren(mcpEmptyRow(t("mcp.disabled")));
    return;
  }
  const servers = Array.isArray(data.servers) ? data.servers : [];
  if (!servers.length) {
    listEl.replaceChildren(mcpEmptyRow(t("mcp.empty")));
    return;
  }
  const frag = document.createDocumentFragment();
  for (const server of servers) frag.appendChild(mcpServerRow(server));
  listEl.replaceChildren(frag);
}

async function refreshMcpServers() {
  const listEl = document.getElementById("mcp-server-list");
  if (!listEl) return;
  try {
    const data = await window.lexa.mcpServers();
    renderMcpServerList(listEl, data);
  } catch (e) {
    listEl.replaceChildren(mcpEmptyRow(t("mcp.loadFailed")));
  }
}

async function _mcpRun(fn) {
  if (_mcpActionRunning) return;
  _mcpActionRunning = true;
  try {
    await fn();
  } catch (e) {
    showToast(t("settings.errorPrefix", { message: e.message || e }), "error");
  } finally {
    _mcpActionRunning = false;
  }
}

async function mcpConnectServerAction(name) {
  await _mcpRun(async () => {
    const res = await window.lexa.mcpConnect(name);
    if (res && (res.status === "connected" || res.success)) {
      showToast(t("mcp.connectedToast", { name }), "success");
    } else {
      showToast(res?.detail || res?.error || t("settings.errorGeneric"), "error");
    }
    await refreshMcpServers();
  });
}

async function mcpDisconnectServerAction(name) {
  await _mcpRun(async () => {
    await window.lexa.mcpDisconnect(name);
    showToast(t("mcp.disconnectedToast", { name }), "info");
    await refreshMcpServers();
  });
}

async function mcpRemoveServerAction(name) {
  await _mcpRun(async () => {
    const confirmed = await showInputModal(t("mcp.removeConfirm", { name }), [], t("mcp.remove"));
    if (!confirmed) return;
    const res = await window.lexa.mcpRemoveServer(name);
    if (res && (res.status === "removed" || res.success)) {
      showToast(t("mcp.removed", { name }), "info");
    } else {
      showToast(res?.detail || res?.error || t("settings.errorGeneric"), "error");
    }
    await refreshMcpServers();
  });
}

async function mcpAddServerAction() {
  await _mcpRun(async () => {
    const result = await showInputModal(t("mcp.addTitle"), [
      { name: "name", label: t("mcp.fieldName"), type: "text", required: true },
      { name: "command", label: t("mcp.fieldCommand"), type: "text", required: true },
      { name: "args", label: t("mcp.fieldArgs"), type: "textarea" },
      { name: "env", label: t("mcp.fieldEnv"), type: "textarea" },
    ], t("common.save"));
    if (!result || !result.name || !result.command) return;
    const config = {
      command: result.command.trim(),
      args: mcpParseArgs(result.args),
      env: mcpParseEnv(result.env),
      enabled: true,
    };
    const res = await window.lexa.mcpAddServer(result.name.trim(), config);
    if (res && (res.status === "added" || res.success)) {
      showToast(t("mcp.added", { name: result.name.trim() }), "success");
    } else {
      showToast(res?.detail || res?.error || t("settings.errorGeneric"), "error");
    }
    await refreshMcpServers();
  });
}
