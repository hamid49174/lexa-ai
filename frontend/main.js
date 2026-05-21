// Install this before Electron registers its own main-process exception dialog.
// Broken stdio pipes are not app crashes; they happen when a launcher/test shell closes.
function lexaIsBrokenPipeError(error) {
  const message = String(error?.message || error || "");
  return error?.code === "EPIPE" || /EPIPE|broken pipe/i.test(message);
}

function lexaWrapBrokenPipeCallback(stream, callback, mark) {
  if (typeof callback !== "function") return callback;
  return (error, ...rest) => {
    if (lexaIsBrokenPipeError(error)) {
      mark(stream);
      callback();
      return;
    }
    callback(error, ...rest);
  };
}

function installPreElectronPipeGuard() {
  const mark = (stream) => {
    try { stream.__lexaBrokenPipe = true; } catch (_error) {}
  };
  const guardStream = (stream) => {
    if (!stream || stream.__lexaEarlyPipeGuardInstalled || typeof stream.write !== "function") return;
    try { stream.__lexaEarlyPipeGuardInstalled = true; } catch (_error) {}
    const originalWrite = stream.write.bind(stream);
    stream.write = (...args) => {
      if (stream.__lexaBrokenPipe) return false;
      const safeArgs = [...args];
      const last = safeArgs.length - 1;
      if (last >= 0) safeArgs[last] = lexaWrapBrokenPipeCallback(stream, safeArgs[last], mark);
      try {
        return originalWrite(...safeArgs);
      } catch (error) {
        if (lexaIsBrokenPipeError(error)) {
          mark(stream);
          return false;
        }
        throw error;
      }
    };
    stream.on?.("error", (error) => {
      if (lexaIsBrokenPipeError(error)) {
        mark(stream);
        return;
      }
      throw error;
    });
  };

  guardStream(process.stdout);
  guardStream(process.stderr);

  const net = require("net");
  if (!net.Socket.prototype.__lexaStdioWriteGuardInstalled) {
    Object.defineProperty(net.Socket.prototype, "__lexaStdioWriteGuardInstalled", {
      value: true,
      enumerable: false,
      configurable: false,
    });
    const originalSocketWrite = net.Socket.prototype._write;
    const originalSocketWritev = net.Socket.prototype._writev;
    const isStdioSocket = (socket) => socket === process.stdout || socket === process.stderr || socket?.fd === 1 || socket?.fd === 2;
    net.Socket.prototype._write = function guardedSocketWrite(chunk, encoding, callback) {
      const safeCallback = isStdioSocket(this) ? lexaWrapBrokenPipeCallback(this, callback, mark) : callback;
      if (isStdioSocket(this) && this.__lexaBrokenPipe) {
        if (typeof safeCallback === "function") safeCallback();
        return;
      }
      try {
        return originalSocketWrite.call(this, chunk, encoding, safeCallback);
      } catch (error) {
        if (isStdioSocket(this) && lexaIsBrokenPipeError(error)) {
          mark(this);
          if (typeof safeCallback === "function") safeCallback();
          return;
        }
        throw error;
      }
    };
    if (typeof originalSocketWritev === "function") {
      net.Socket.prototype._writev = function guardedSocketWritev(chunks, callback) {
        const safeCallback = isStdioSocket(this) ? lexaWrapBrokenPipeCallback(this, callback, mark) : callback;
        if (isStdioSocket(this) && this.__lexaBrokenPipe) {
          if (typeof safeCallback === "function") safeCallback();
          return;
        }
        try {
          return originalSocketWritev.call(this, chunks, safeCallback);
        } catch (error) {
          if (isStdioSocket(this) && lexaIsBrokenPipeError(error)) {
            mark(this);
            if (typeof safeCallback === "function") safeCallback();
            return;
          }
          throw error;
        }
      };
    }
  }

  const originalEmit = process.emit.bind(process);
  process.emit = (eventName, ...args) => {
    if ((eventName === "uncaughtException" || eventName === "uncaughtExceptionMonitor") && lexaIsBrokenPipeError(args[0])) {
      mark(process.stdout);
      mark(process.stderr);
      return true;
    }
    return originalEmit(eventName, ...args);
  };
}

installPreElectronPipeGuard();

const electron = require("electron");

if (!electron || typeof electron === "string" || !electron.app) {
  throw new Error(
    "Electron main-process API unavailable. Clear ELECTRON_RUN_AS_NODE and launch via the npm scripts."
  );
}

const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, Notification, dialog, session } = electron;
const { spawn } = require("child_process");
const crypto = require("crypto");
const http = require("http");
const path = require("path");
const fs = require("fs");
const https = require("https");
const { fileURLToPath } = require("url");

// Suppress broken stdout/stderr pipes when launched from transient shells or tests.
let safeConsoleFallbackWriter = null;
const MAIN_PROCESS_LOG_MAX_BYTES = 1024 * 1024;

function isBrokenPipeError(error) {
  return lexaIsBrokenPipeError(error);
}

function wrapBrokenPipeCallback(stream, callback) {
  return lexaWrapBrokenPipeCallback(stream, callback, markBrokenPipe);
}

function markBrokenPipe(stream) {
  try {
    Object.defineProperty(stream, "__lexaBrokenPipe", {
      value: true,
      enumerable: false,
      configurable: true,
    });
  } catch (_error) {
    try { stream.__lexaBrokenPipe = true; } catch (_ignored) {}
  }
}

function installSafeStreamWrite(stream) {
  if (!stream || stream.__lexaSafeWriteInstalled || typeof stream.write !== "function") return;
  const originalWrite = stream.write.bind(stream);
  const originalChunkWrite = typeof stream._write === "function" ? stream._write.bind(stream) : null;
  const originalVectorWrite = typeof stream._writev === "function" ? stream._writev.bind(stream) : null;
  Object.defineProperty(stream, "__lexaSafeWriteInstalled", {
    value: true,
    enumerable: false,
    configurable: false,
  });
  stream.write = (...args) => {
    if (stream.__lexaBrokenPipe) return false;
    const safeArgs = [...args];
    const last = safeArgs.length - 1;
    if (last >= 0) safeArgs[last] = wrapBrokenPipeCallback(stream, safeArgs[last]);
    try {
      return originalWrite(...safeArgs);
    } catch (error) {
      if (isBrokenPipeError(error)) {
        markBrokenPipe(stream);
        return false;
      }
      throw error;
    }
  };
  if (originalChunkWrite) {
    stream._write = (chunk, encoding, callback) => {
      const safeCallback = wrapBrokenPipeCallback(stream, callback);
      if (stream.__lexaBrokenPipe) {
        if (typeof safeCallback === "function") safeCallback();
        return;
      }
      try {
        return originalChunkWrite(chunk, encoding, safeCallback);
      } catch (error) {
        if (isBrokenPipeError(error)) {
          markBrokenPipe(stream);
          if (typeof safeCallback === "function") safeCallback();
          return;
        }
        throw error;
      }
    };
  }
  if (originalVectorWrite) {
    stream._writev = (chunks, callback) => {
      const safeCallback = wrapBrokenPipeCallback(stream, callback);
      if (stream.__lexaBrokenPipe) {
        if (typeof safeCallback === "function") safeCallback();
        return;
      }
      try {
        return originalVectorWrite(chunks, safeCallback);
      } catch (error) {
        if (isBrokenPipeError(error)) {
          markBrokenPipe(stream);
          if (typeof safeCallback === "function") safeCallback();
          return;
        }
        throw error;
      }
    };
  }
  stream.on?.("error", (error) => {
    if (isBrokenPipeError(error)) {
      markBrokenPipe(stream);
      return;
    }
    throw error;
  });
}

function installSafeProcessStreams() {
  installSafeStreamWrite(process.stdout);
  installSafeStreamWrite(process.stderr);
}

function installSafeConsole() {
  const original = {
    log: console.log.bind(console),
    info: console.info.bind(console),
    warn: console.warn.bind(console),
    error: console.error.bind(console),
  };
  const safeCall = (method, args) => {
    try {
      original[method](...args);
    } catch (error) {
      if (!isBrokenPipeError(error)) throw error;
      markBrokenPipe(process.stdout);
      markBrokenPipe(process.stderr);
      try { safeConsoleFallbackWriter?.(method, args, error); } catch (_ignored) {}
    }
  };
  console.log = (...args) => safeCall("log", args);
  console.info = (...args) => safeCall("info", args);
  console.warn = (...args) => safeCall("warn", args);
  console.error = (...args) => safeCall("error", args);
}

installSafeProcessStreams();
installSafeConsole();
process.on("uncaughtException", (error) => {
  if (isBrokenPipeError(error)) return;
  try { console.error("[Main] Uncaught exception:", error); } catch (_e) {}
  app.exit(1);
});

function redactMainLogText(value) {
  return String(value ?? "")
    .replace(/(Bearer\s+)[A-Za-z0-9._~+/=-]{12,}/gi, "$1[redacted]")
    .replace(/(token|api[_-]?key|secret|password|authorization)(["':=\s]+)[^\\s,"'}]{4,}/gi, "$1$2[redacted]")
    .slice(0, 500);
}

function appendSafeMainProcessLog(method, args, error) {
  try {
    const logPath = path.join(app.getPath("userData"), "main-process.log");
    if (fs.existsSync(logPath) && fs.statSync(logPath).size > MAIN_PROCESS_LOG_MAX_BYTES) {
      const rotated = `${logPath}.1`;
      if (fs.existsSync(rotated)) fs.unlinkSync(rotated);
      fs.renameSync(logPath, rotated);
    }
    const entry = {
      timestamp: new Date().toISOString(),
      source: "main",
      method: redactMainLogText(method),
      pipe_error: true,
      error: redactMainLogText(error?.code || error?.message || error),
      message: Array.from(args || []).map(redactMainLogText).join(" "),
    };
    fs.appendFileSync(logPath, `${JSON.stringify(entry)}\n`, "utf8");
  } catch (_ignored) {}
}

safeConsoleFallbackWriter = appendSafeMainProcessLog;

function installRendererConsoleGuard(webContents) {
  if (!webContents || webContents.__lexaConsoleGuardInstalled) return;
  Object.defineProperty(webContents, "__lexaConsoleGuardInstalled", {
    value: true,
    enumerable: false,
    configurable: false,
  });
  webContents.on("console-message", (event, level, message, line, sourceId) => {
    event.preventDefault?.();
    if (process.stdout?.__lexaBrokenPipe || process.stderr?.__lexaBrokenPipe) return;
    const prefix = `[Renderer:${level}]`;
    const location = sourceId ? ` ${sourceId}:${line || 0}` : "";
    try { console.log(prefix, String(message || "").trim(), location); } catch (_error) {}
  });
}

// ── BACKEND PROCESS MANAGEMENT ──────────────────
let backendProcess = null;
const BACKEND_RESTART_DELAY_MS = 1500;
const BACKEND_RESTART_MAX_DELAY_MS = 30000;
const BACKEND_RESTART_MAX_ATTEMPTS = 5;
const EXTERNAL_LEXA_BACKEND = "__external_lexa_backend__";
const AUTH_MISMATCH_LEXA_BACKEND = "__auth_mismatch_lexa_backend__";
const HEALTH_CHECK_BODY_LIMIT = 64 * 1024;
const HEALTH_CHECK_TIMEOUT_MS = 2000;
const LOCAL_AUTH_HEADER = "X-Lexa-Local-Token";
const LOCAL_AUTH_COOKIE = "lexa_local_auth";
const INSTANCE_TOKEN = crypto.randomBytes(16).toString("hex");
let backendRestartAttempts = 0;

function installLocalAuthRequestHeaders(ses = session.defaultSession) {
  if (!ses?.webRequest || ses.__lexaLocalAuthHeaderInstalled) return;
  ses.__lexaLocalAuthHeaderInstalled = true;
  ses.webRequest.onBeforeSendHeaders(
    { urls: ["http://127.0.0.1:8000/*", "http://localhost:8000/*"] },
    (details, callback) => {
      const requestHeaders = { ...(details.requestHeaders || {}) };
      requestHeaders[LOCAL_AUTH_HEADER] = INSTANCE_TOKEN;
      callback({ requestHeaders });
    },
  );
}

async function installLocalAuthCookie() {
  await session.defaultSession.cookies.set({
    url: "http://127.0.0.1:8000",
    name: LOCAL_AUTH_COOKIE,
    value: INSTANCE_TOKEN,
    httpOnly: true,
  });
}

function getBackendPath() {
  // In development: use venv python
  const devPython = path.join(__dirname, "..", "venv", "Scripts", "python.exe");
  if (fs.existsSync(devPython)) return { python: devPython, cwd: path.join(__dirname, "..") };

  // In production (packaged): python is bundled alongside
  const prodPython = path.join(process.resourcesPath, "backend-dist", "lexa-backend.exe");
  if (fs.existsSync(prodPython)) return { python: prodPython, cwd: path.join(process.resourcesPath, "backend-dist") };

  // Fallback: system python
  return { python: "python", cwd: path.join(__dirname, "..") };
}

async function isPortInUse(port) {
  return new Promise((resolve) => {
    const net = require("net");
    const server = net.createServer();
    server.once("error", () => resolve(true));
    server.once("listening", () => { server.close(); resolve(false); });
    server.listen(port, "127.0.0.1");
  });
}

function _healthCheck() {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    const req = http.get("http://127.0.0.1:8000/health", {
      headers: { "X-Lexa-Local-Token": INSTANCE_TOKEN },
    }, (res) => {
      let body = "";
      res.on("data", (c) => {
        body += c;
        if (body.length > HEALTH_CHECK_BODY_LIMIT) {
          req.destroy();
          finish(null);
        }
      });
      res.on("end", () => {
        try {
          const data = JSON.parse(body);
          if (data.service === "lexa-ai" && data.instance_authenticated === true) {
            finish(INSTANCE_TOKEN);
          } else if (data.service === "lexa-ai" && data.auth_required === true) {
            finish(AUTH_MISMATCH_LEXA_BACKEND);
          } else if (data.service === "lexa-ai") {
            finish(EXTERNAL_LEXA_BACKEND);
          } else {
            finish(null);
          }
        } catch (e) { console.warn("[Main] Health check JSON parse failed:", e.message || e); finish(null); }
      });
    });
    req.on("error", () => finish(null));
    req.setTimeout(HEALTH_CHECK_TIMEOUT_MS, () => { req.destroy(); finish(null); });
  });
}

async function _waitForBackend(maxRetries = 30) {
  for (let i = 0; i < maxRetries; i++) {
    const token = await _healthCheck();
    if (token === INSTANCE_TOKEN || token === EXTERNAL_LEXA_BACKEND) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function backendRestartDelayMs(attempt) {
  const exponent = Math.max(0, Number(attempt || 0));
  return Math.min(BACKEND_RESTART_DELAY_MS * (2 ** exponent), BACKEND_RESTART_MAX_DELAY_MS);
}

function resetBackendRestartBackoff() {
  backendRestartAttempts = 0;
}

function scheduleBackendRestart(log = console.log) {
  if (backendRestartAttempts >= BACKEND_RESTART_MAX_ATTEMPTS) {
    log("[Backend] Restart limit reached; leaving backend stopped until app restart");
    return;
  }

  const delay = backendRestartDelayMs(backendRestartAttempts);
  backendRestartAttempts += 1;
  setTimeout(() => {
    if (app.isQuitting || backendProcess) return;
    startBackend().catch((err) => log("[Backend] Restart failed:", err.message || err));
  }, delay);
}

async function startBackend() {
  // Check if port is already in use
  if (await isPortInUse(8000)) {
    // Check if it's a Lexa backend and whether it's ours
    const token = await _healthCheck();
    if (token === INSTANCE_TOKEN) {
      console.log("[Backend] Our backend already running - reusing");
      return;
    }
    if (token === EXTERNAL_LEXA_BACKEND) {
      console.warn("[Backend] Port 8000 occupied by Lexa backend without instance token - reusing (dev mode)");
      return;
    }
    if (token === AUTH_MISMATCH_LEXA_BACKEND) {
      console.warn("[Backend] Port 8000 occupied by another secured Lexa instance - cannot authenticate");
      return;
    }
    console.warn("[Backend] Port 8000 occupied by non-Lexa process - backend may not work");
    return;
  }

  const { python, cwd } = getBackendPath();
  const env = { ...process.env, LEXA_INSTANCE_TOKEN: INSTANCE_TOKEN };

  console.log(`[Backend] Starting: ${python} (cwd: ${cwd})`);

  if (python.endsWith(".exe") && !python.includes("python")) {
    // PyInstaller executable
    backendProcess = spawn(python, [], { cwd, stdio: "pipe", windowsHide: true, env });
  } else {
    // Python interpreter
    backendProcess = spawn(python, ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"], { cwd, stdio: "pipe", windowsHide: true, env });
  }

  const _log = (...args) => { try { console.log(...args); } catch (e) { /* console itself failed - nothing to do */ } };
  const child = backendProcess;
  child.stdout?.on("data", (data) => _log("[Backend]", data.toString().trim()));
  child.stderr?.on("data", (data) => _log("[Backend]", data.toString().trim()));
  child.on("error", (err) => _log("[Backend] Failed to start:", err.message));
  child.on("exit", (code) => {
    _log("[Backend] Exited with code:", code);
    if (backendProcess === child) backendProcess = null;
    if (!app.isQuitting) {
      scheduleBackendRestart(_log);
    }
  });

  // Wait for backend to be ready
  const ready = await _waitForBackend();
  if (ready) resetBackendRestartBackoff();
  _log("[Backend]", ready ? "Health check passed - backend is ready" : "Health check failed after 15s");
}

// Fix GPU cache errors on some systems
app.commandLine.appendSwitch("disable-gpu-cache");
app.commandLine.appendSwitch("disable-software-rasterizer");

let mainWindow;
let tray = null;
let frontendWatcher = null;
let frontendReloadTimer = null;

function setupFrontendAutoReload() {
  if (app.isPackaged) return;
  const srcDir = path.join(__dirname, "src");
  if (!fs.existsSync(srcDir)) return;

  const scheduleReload = (filename) => {
    const changed = String(filename || "");
    if (changed && !/\.(?:js|css|html)$/i.test(changed)) return;
    clearTimeout(frontendReloadTimer);
    frontendReloadTimer = setTimeout(() => {
      if (!mainWindow || mainWindow.isDestroyed()) return;
      console.log(`[Frontend] Reloading after source change${changed ? `: ${changed}` : ""}`);
      mainWindow.webContents.reloadIgnoringCache();
    }, 350);
  };

  try {
    frontendWatcher = fs.watch(srcDir, { recursive: true }, (_event, filename) => scheduleReload(filename));
    mainWindow?.on("closed", () => {
      clearTimeout(frontendReloadTimer);
      frontendWatcher?.close();
      frontendWatcher = null;
    });
    console.log("[Frontend] Dev auto-reload watcher active");
  } catch (e) {
    console.warn("[Frontend] Dev auto-reload watcher unavailable:", e.message || e);
  }
}

function isPathInside(childPath, parentPath) {
  const relative = path.relative(parentPath, childPath);
  return relative === "" || (!!relative && !relative.startsWith("..") && !path.isAbsolute(relative));
}

function isTrustedRendererUrl(rawUrl) {
  try {
    const parsed = new URL(String(rawUrl || ""));
    if (parsed.protocol !== "file:") return false;
    const filePath = path.normalize(fileURLToPath(parsed));
    return isPathInside(filePath, path.join(__dirname, "src"));
  } catch (_) {
    return false;
  }
}

function safeExternalUrl(rawUrl) {
  try {
    const parsed = new URL(String(rawUrl || ""));
    if (!["http:", "https:", "mailto:"].includes(parsed.protocol.toLowerCase())) return "";
    return parsed.href;
  } catch (_) {
    return "";
  }
}

function openExternalUrl(rawUrl) {
  const url = safeExternalUrl(rawUrl);
  if (!url) return false;
  electron.shell.openExternal(url).catch((err) => {
    console.warn("[Main] external open failed:", err.message || err);
  });
  return true;
}

const BRIDGE_PRESENCE_TTL_MS = 60 * 1000;
const BRIDGE_PRESENCE_METHODS = new Set([
  "setAutostart",
  "licenseSet",
  "licenseValidate",
  "execute",
  "executeWithConfirmation",
  "executeBatch",
  "voiceRealtimeStart",
  "elevenlabsSetKey",
  "elevenlabsDeleteKey",
  "deepgramSetKey",
  "deepgramDeleteKey",
  "cartesiaSetKey",
  "cartesiaDeleteKey",
  "wakewordStart",
  "conversationStart",
  "memoryCleanup",
  "historyClear",
  "setProfile",
  "conversationUpdate",
  "conversationDelete",
  "conversationExport",
  "calendarConnect",
  "clipboardHistory",
  "clipboardClear",
  "hermesGatewayAutostartSet",
  "backupCreate",
  "backupRestore",
  "backupRestoreDb",
  "visionAnalyze",
  "visionOcr",
  "agentRun",
  "agentChat",
  "mcpConnect",
  "mcpDisconnect",
  "mcpCallTool",
  "personalOsDraftDecision",
  "personalOsDraftApply",
  "personalOsReadFile",
  "personalOsRawSubmit",
]);
const bridgePresenceChallenges = new Map();
const BRIDGE_AUDIT_MAX_BYTES = 3 * 1024 * 1024;

function bridgePresenceIdPrefix(challengeId) {
  return String(challengeId || "").slice(0, 10);
}

function sanitizeBridgeAuditEvent(payload = {}, source = "main") {
  return {
    timestamp: String(payload.timestamp || new Date().toISOString()).slice(0, 80),
    source,
    method: String(payload.method || "unknown").slice(0, 100),
    risk: String(payload.risk || payload.effective_risk || "unknown").slice(0, 30),
    base_risk: String(payload.base_risk || payload.risk || "unknown").slice(0, 30),
    effective_risk: String(payload.effective_risk || payload.risk || "unknown").slice(0, 30),
    action_type: String(payload.action_type || payload.actionType || "unknown").slice(0, 30),
    allowed: Boolean(payload.allowed),
    reason: String(payload.reason || "").slice(0, 160),
    args_hash: String(payload.args_hash || payload.argsHash || "").slice(0, 16),
    arg_keys: Array.isArray(payload.arg_keys || payload.argKeys)
      ? (payload.arg_keys || payload.argKeys).map((key) => String(key || "").slice(0, 80)).slice(0, 40)
      : [],
    classification_reason: String(payload.classification_reason || "").slice(0, 120),
    challenge_id_prefix: bridgePresenceIdPrefix(payload.challenge_id_prefix || payload.challengeId || ""),
  };
}

function bridgeAuditPath() {
  return path.join(app.getPath("userData"), "bridge-audit.log");
}

function rotateBridgeAuditIfNeeded(auditPath = bridgeAuditPath()) {
  try {
    if (!fs.existsSync(auditPath)) return;
    const stat = fs.statSync(auditPath);
    if (stat.size <= BRIDGE_AUDIT_MAX_BYTES) return;
    const rotatedPath = `${auditPath}.1`;
    if (fs.existsSync(rotatedPath)) fs.unlinkSync(rotatedPath);
    fs.renameSync(auditPath, rotatedPath);
    fs.writeFileSync(
      auditPath,
      `${JSON.stringify({ timestamp: new Date().toISOString(), source: "main", method: "bridge_audit", allowed: true, reason: "rotated", previous_size: stat.size })}\n`,
      "utf8",
    );
  } catch (error) {
    console.warn("[BridgePresenceAudit] rotation failed:", String(error?.message || error).slice(0, 120));
  }
}

function writeBridgeAuditEvent(event) {
  try {
    const auditPath = bridgeAuditPath();
    rotateBridgeAuditIfNeeded(auditPath);
    fs.appendFileSync(auditPath, `${JSON.stringify(event)}\n`, "utf8");
  } catch (error) {
    console.warn("[BridgePresenceAudit] write failed:", String(error?.message || error).slice(0, 120));
  }
}

function sanitizeBridgePresenceRequest(payload = {}) {
  const method = String(payload.method || "").trim();
  const risk = String(payload.risk || "unknown").trim();
  const baseRisk = String(payload.base_risk || payload.risk || "unknown").trim();
  const effectiveRisk = String(payload.effective_risk || payload.risk || "unknown").trim();
  const actionType = String(payload.action_type || "unknown").trim();
  const target = String(payload.target || "unknown").trim();
  const argsHash = String(payload.args_hash || "").trim();
  const argKeys = Array.isArray(payload.arg_keys)
    ? payload.arg_keys.map((key) => String(key || "").slice(0, 80)).slice(0, 40)
    : [];
  const classificationReason = String(payload.classification_reason || "").slice(0, 120);
  return { method, risk, baseRisk, effectiveRisk, actionType, target, argsHash, argKeys, classificationReason };
}

function isValidBridgePresenceRequest(payload) {
  return BRIDGE_PRESENCE_METHODS.has(payload.method)
    && ["high", "critical"].includes(payload.risk)
    && /^[a-f0-9]{64}$/i.test(payload.argsHash);
}

function auditBridgePresence(status, payload = {}, reason = "", challengeId = "") {
  const event = sanitizeBridgeAuditEvent({
    timestamp: new Date().toISOString(),
    method: payload.method,
    risk: payload.risk,
    base_risk: payload.baseRisk || payload.base_risk,
    effective_risk: payload.effectiveRisk || payload.effective_risk || payload.risk,
    action_type: payload.actionType || payload.action_type,
    allowed: status === "allowed",
    reason: reason || status,
    args_hash: payload.argsHash || payload.args_hash,
    arg_keys: payload.argKeys || payload.arg_keys,
    classification_reason: payload.classificationReason || payload.classification_reason,
    challenge_id_prefix: bridgePresenceIdPrefix(challengeId),
  }, "main");
  const line = `[BridgePresenceAudit] ${JSON.stringify(event)}`;
  if (event.allowed) console.info(line);
  else console.warn(line);
  writeBridgeAuditEvent(event);
}

function ipcArgKeys(args = []) {
  return Array.from(args).flatMap((arg, index) => {
    if (arg && typeof arg === "object" && !Array.isArray(arg)) {
      const keys = Object.keys(arg).sort().slice(0, 20);
      return keys.length ? keys.map((key) => `arg${index}.${String(key).slice(0, 80)}`) : [`arg${index}:object`];
    }
    return [`arg${index}:${typeof arg}`];
  }).slice(0, 40);
}

function ipcArgShapeHash(args = []) {
  try {
    return crypto.createHash("sha256").update(JSON.stringify(ipcArgKeys(args))).digest("hex");
  } catch (_error) {
    return "";
  }
}

function redactedIpcErrorReason(error) {
  const name = String(error?.name || "Error").replace(/[^\w.-]/g, "").slice(0, 40) || "Error";
  const code = String(error?.code || "").replace(/[^\w.-]/g, "").slice(0, 40);
  return code ? `${name}:${code}` : name;
}

function structuredIpcFailure(channel, error) {
  return {
    ok: false,
    success: false,
    code: "main_ipc_handler_failed",
    reason: "main_ipc_handler_failed",
    error: "Main process IPC handler failed",
    channel: String(channel || "unknown").slice(0, 100),
    error_type: redactedIpcErrorReason(error),
  };
}

function auditMainIpcFailure(channel, error, args = []) {
  const event = sanitizeBridgeAuditEvent({
    timestamp: new Date().toISOString(),
    method: `ipc:${String(channel || "unknown").slice(0, 100)}`,
    risk: "unknown",
    action_type: "ipc",
    allowed: false,
    reason: `handler_exception:${redactedIpcErrorReason(error)}`,
    args_hash: ipcArgShapeHash(args),
    arg_keys: ipcArgKeys(args),
  }, "main");
  try { console.warn(`[MainIPC] ${channel} handler failed: ${event.reason}`); } catch (_ignored) {}
  writeBridgeAuditEvent(event);
}

function safeIpcHandle(channel, handler, options = {}) {
  ipcMain.handle(channel, async (event, ...args) => {
    try {
      return await handler(event, ...args);
    } catch (error) {
      auditMainIpcFailure(channel, error, args);
      if (Object.prototype.hasOwnProperty.call(options, "failureValue")) return options.failureValue;
      return structuredIpcFailure(channel, error);
    }
  });
}

function safeIpcOn(channel, handler, options = {}) {
  ipcMain.on(channel, (event, ...args) => {
    try {
      return handler(event, ...args);
    } catch (error) {
      auditMainIpcFailure(channel, error, args);
      if (Object.prototype.hasOwnProperty.call(options, "returnValue") && event) {
        try { event.returnValue = options.returnValue; } catch (_ignored) {}
      }
      return undefined;
    }
  });
}

function pruneBridgePresenceChallenges(now = Date.now()) {
  for (const [id, record] of bridgePresenceChallenges.entries()) {
    if (!record || record.expiresAt <= now || record.used) {
      bridgePresenceChallenges.delete(id);
    }
  }
}

function bridgePresenceSenderTrusted(event) {
  const frameUrl = event?.senderFrame?.url || event?.sender?.getURL?.() || "";
  return isTrustedRendererUrl(frameUrl);
}

async function showBridgePresenceDialog(payload) {
  const owner = mainWindow && !mainWindow.isDestroyed?.() ? mainWindow : undefined;
  const detail = [
    `Method: ${payload.method}`,
    `Risk: ${payload.risk}`,
    `Type: ${payload.actionType}`,
    `Target: ${payload.target}`,
    payload.argKeys.length ? `Args: ${payload.argKeys.join(", ")}` : "Args: none",
    "This approval is single-use and expires in 60 seconds.",
  ].join("\n");
  const options = {
    type: payload.risk === "critical" ? "warning" : "question",
    buttons: ["Deny", "Allow once"],
    defaultId: 0,
    cancelId: 0,
    noLink: true,
    title: "Confirm Lexa action",
    message: "Allow this high-risk Lexa action?",
    detail,
  };
  const result = owner
    ? await dialog.showMessageBox(owner, options)
    : await dialog.showMessageBox(options);
  return result.response === 1;
}

function installElectronSecurityGuards(win) {
  if (!win?.webContents || win.webContents.__lexaSecurityGuardsInstalled) return;
  win.webContents.__lexaSecurityGuardsInstalled = true;

  win.webContents.setWindowOpenHandler(({ url }) => {
    openExternalUrl(url);
    return { action: "deny" };
  });

  win.webContents.on("will-navigate", (event, url) => {
    if (isTrustedRendererUrl(url)) return;
    event.preventDefault();
    openExternalUrl(url);
  });

  const ses = win.webContents.session;
  if (ses && !ses.__lexaPermissionGuardInstalled) {
    ses.__lexaPermissionGuardInstalled = true;
    ses.setPermissionRequestHandler((webContents, permission, callback, details = {}) => {
      const requestingUrl = details.requestingUrl || webContents?.getURL?.() || "";
      const mediaTypes = Array.isArray(details.mediaTypes) ? details.mediaTypes : [];
      const allowAudioCapture = permission === "media"
        && isTrustedRendererUrl(requestingUrl)
        && mediaTypes.includes("audio")
        && !mediaTypes.includes("video");
      callback(Boolean(allowAudioCapture));
    });
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 750,
    minWidth: 800,
    minHeight: 600,
    frame: false,
    titleBarStyle: "hidden",
    backgroundColor: "#071018",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    ...(fs.existsSync(path.join(__dirname, "src", "icon.png")) ? { icon: path.join(__dirname, "src", "icon.png") } : {}),
  });

  installRendererConsoleGuard(mainWindow.webContents);
  installElectronSecurityGuards(mainWindow);
  mainWindow.loadFile(path.join(__dirname, "src", "index.html"));
  setupFrontendAutoReload();

  // DevTools in development
  if (process.argv.includes("--dev")) {
    mainWindow.webContents.openDevTools();
  }

  // Minimize to tray instead of closing
  mainWindow.on("close", (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

// ── SYSTEM TRAY ──────────────────────────────────
function createTray() {
  // Create a simple 16x16 icon programmatically (orange dot)
  const iconPath = path.join(__dirname, "src", "icon.png");
  let trayIcon;
  try {
    trayIcon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 });
  } catch (e) {
    // Fallback: create a tiny icon if file doesn't exist
    console.warn("[Main] Tray icon load failed, using empty icon:", e.message || e);
    trayIcon = nativeImage.createEmpty();
  }

  tray = new Tray(trayIcon);
  tray.setToolTip("Lexa AI - Lokaler KI-Assistent");

  const contextMenu = Menu.buildFromTemplate([
    {
      label: "Lexa AI oeffnen",
      click: () => {
        mainWindow?.show();
        mainWindow?.focus();
      },
    },
    { type: "separator" },
    {
      label: "System Info",
      click: () => {
        mainWindow?.show();
        mainWindow?.webContents.send("switch-view", "system");
      },
    },
    {
      label: "Befehle",
      click: () => {
        mainWindow?.show();
        mainWindow?.webContents.send("switch-view", "commands");
      },
    },
    { type: "separator" },
    {
      label: "Autostart",
      type: "checkbox",
      checked: app.getLoginItemSettings().openAtLogin,
      click: (menuItem) => {
        app.setLoginItemSettings({ openAtLogin: menuItem.checked });
      },
    },
    { type: "separator" },
    {
      label: "Beenden",
      click: () => {
        app.isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setContextMenu(contextMenu);

  // Click tray icon to show/hide
  tray.on("click", () => {
    if (mainWindow?.isVisible()) {
      mainWindow.hide();
    } else {
      mainWindow?.show();
      mainWindow?.focus();
    }
  });
}

// ── WINDOW CONTROLS ──────────────────────────────
safeIpcOn("window-minimize", () => mainWindow?.minimize());
safeIpcOn("window-maximize", () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});
safeIpcOn("window-close", () => mainWindow?.hide());

// ── LICENSE & TRIAL SYSTEM ───────────────────────
const TRIAL_DAYS = 14;
const GRACE_DAYS = 3;

function _licensePath() {
  return path.join(app.getPath("userData"), "license.json");
}

function _readLicense() {
  try {
    const p = _licensePath();
    if (fs.existsSync(p)) return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch (e) { console.warn("[Main] license read failed:", e.message || e); }
  return null;
}

function _writeLicense(data) {
  try {
    fs.writeFileSync(_licensePath(), JSON.stringify(data, null, 2), "utf8");
    return true;
  } catch (e) {
    console.warn("[Main] license write failed:", e.message || e);
    return false;
  }
}

function _initTrialIfNeeded() {
  const existing = _readLicense();
  if (existing && existing.plan !== "free") return existing;
  // Create trial on first launch
  const now = new Date();
  const expires = new Date(now.getTime() + TRIAL_DAYS * 24 * 60 * 60 * 1000);
  const trial = {
    key: "",
    plan: "trial",
    status: "active",
    trial_started: now.toISOString(),
    expires: expires.toISOString(),
    created_at: now.toISOString(),
  };
  _writeLicense(trial);
  console.log(`[Main] Trial created — expires ${expires.toISOString()}`);
  return trial;
}

function _getLicenseWithState() {
  const lic = _readLicense() || { key: "", plan: "free", status: "inactive", expires: null };
  const now = Date.now();

  // Paid license — check expiry
  if (lic.plan === "paid" || lic.plan === "premium") {
    if (lic.expires) {
      const exp = new Date(lic.expires).getTime();
      if (now > exp) {
        return { ...lic, _state: "paid_expired", _days_left: 0 };
      }
      const daysLeft = Math.ceil((exp - now) / (24 * 60 * 60 * 1000));
      return { ...lic, _state: "paid_active", _days_left: daysLeft };
    }
    return { ...lic, _state: "paid_active", _days_left: -1 }; // perpetual
  }

  // Trial license — compute state
  if (lic.plan === "trial" && lic.expires) {
    const exp = new Date(lic.expires).getTime();
    const graceEnd = exp + GRACE_DAYS * 24 * 60 * 60 * 1000;

    if (now <= exp) {
      const daysLeft = Math.ceil((exp - now) / (24 * 60 * 60 * 1000));
      return { ...lic, _state: "trial_active", _days_left: daysLeft };
    }
    if (now <= graceEnd) {
      const graceDaysLeft = Math.ceil((graceEnd - now) / (24 * 60 * 60 * 1000));
      return { ...lic, _state: "trial_grace", _days_left: graceDaysLeft };
    }
    return { ...lic, _state: "trial_expired", _days_left: 0 };
  }

  // Free / unknown
  return { ...lic, _state: "free", _days_left: 0 };
}

safeIpcHandle("license-get", () => {
  return _getLicenseWithState();
});

safeIpcHandle("license-set", (_event, data) => {
  const success = _writeLicense(data);
  return success ? { success: true } : { success: false, error: "Write failed" };
});

// ── I18N FILE LOADING (Electron IPC — bypasses file:// fetch issues) ──
safeIpcHandle("i18n-load", (_event, lang) => {
  const allowed = ["de", "en"];
  if (!allowed.includes(lang)) return null;
  const filePath = path.join(__dirname, "src", "i18n", `${lang}.json`);
  try {
    const data = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(data);
  } catch (e) {
    console.warn(`[Main] i18n load failed for ${lang}:`, e.message);
    return null;
  }
});

// ── NOTIFICATIONS ────────────────────────────────
safeIpcHandle("local-auth-token", () => INSTANCE_TOKEN, { failureValue: "" });

safeIpcHandle("bridge:audit", (event, rawPayload = {}) => {
  if (!bridgePresenceSenderTrusted(event)) return { ok: false, reason: "untrusted_renderer" };
  const auditEvent = sanitizeBridgeAuditEvent(rawPayload, "preload");
  writeBridgeAuditEvent(auditEvent);
  return { ok: true };
}, { failureValue: null });

safeIpcHandle("bridge:presence:request", async (event, rawPayload = {}) => {
  const payload = sanitizeBridgePresenceRequest(rawPayload);
  pruneBridgePresenceChallenges();

  if (!bridgePresenceSenderTrusted(event)) {
    auditBridgePresence("denied", payload, "untrusted_renderer");
    return { ok: false, reason: "untrusted_renderer" };
  }

  if (!isValidBridgePresenceRequest(payload)) {
    auditBridgePresence("denied", payload, "invalid_presence_request");
    return { ok: false, reason: "invalid_presence_request" };
  }

  let approved = false;
  try {
    approved = await showBridgePresenceDialog(payload);
  } catch (error) {
    auditBridgePresence("denied", payload, `dialog_failed:${String(error?.message || error).slice(0, 80)}`);
    return { ok: false, reason: "dialog_failed" };
  }

  if (!approved) {
    auditBridgePresence("denied", payload, "user_denied");
    return { ok: false, reason: "user_denied" };
  }

  const challengeId = crypto.randomBytes(18).toString("hex");
  const expiresAt = Date.now() + BRIDGE_PRESENCE_TTL_MS;
  bridgePresenceChallenges.set(challengeId, {
    method: payload.method,
    argsHash: payload.argsHash,
    expiresAt,
    used: false,
  });
  auditBridgePresence("allowed", payload, "challenge_created", challengeId);
  return {
    ok: true,
    challenge_id: challengeId,
    expires_at: new Date(expiresAt).toISOString(),
  };
});

safeIpcHandle("bridge:presence:consume", (event, rawPayload = {}) => {
  pruneBridgePresenceChallenges();

  const challengeId = String(rawPayload.challenge_id || "");
  const method = String(rawPayload.method || "").trim();
  const argsHash = String(rawPayload.args_hash || "").trim();
  const payload = { method, risk: "unknown", actionType: "consume", argsHash, argKeys: [] };

  if (!bridgePresenceSenderTrusted(event)) {
    auditBridgePresence("denied", payload, "untrusted_renderer", challengeId);
    return { ok: false, reason: "untrusted_renderer" };
  }

  const record = bridgePresenceChallenges.get(challengeId);
  if (!record) {
    auditBridgePresence("denied", payload, "challenge_missing_or_expired", challengeId);
    return { ok: false, reason: "challenge_missing_or_expired" };
  }
  if (record.used) {
    bridgePresenceChallenges.delete(challengeId);
    auditBridgePresence("denied", payload, "challenge_replay", challengeId);
    return { ok: false, reason: "challenge_replay" };
  }
  if (record.expiresAt <= Date.now()) {
    bridgePresenceChallenges.delete(challengeId);
    auditBridgePresence("denied", payload, "challenge_expired", challengeId);
    return { ok: false, reason: "challenge_expired" };
  }
  if (record.method !== method) {
    auditBridgePresence("denied", payload, "method_mismatch", challengeId);
    return { ok: false, reason: "method_mismatch" };
  }
  if (record.argsHash !== argsHash) {
    auditBridgePresence("denied", payload, "args_hash_mismatch", challengeId);
    return { ok: false, reason: "args_hash_mismatch" };
  }

  record.used = true;
  bridgePresenceChallenges.delete(challengeId);
  auditBridgePresence("allowed", payload, "challenge_consumed", challengeId);
  return { ok: true };
});

safeIpcOn("show-notification", (_event, data) => {
  if (Notification.isSupported()) {
    const notif = new Notification({
      title: data.title || "Lexa AI",
      body: data.body || "",
      silent: data.silent || false,
    });
    notif.show();
  }
});

// ── VIEW SWITCHING FROM TRAY ─────────────────────
safeIpcOn("get-autostart", (event) => {
  event.returnValue = app.getLoginItemSettings().openAtLogin;
}, { returnValue: false });

safeIpcOn("set-autostart", (_event, enabled) => {
  app.setLoginItemSettings({ openAtLogin: enabled });
});

// ── UPDATE CHECK ────────────────────────────────
const UPDATE_GITHUB_OWNER = "alexsprogis";
const UPDATE_GITHUB_REPO = "lexa-ai";
const UPDATE_GITHUB_NAME_PATTERN = /^[A-Za-z0-9_.-]+$/;

function githubLatestReleasePath(owner = UPDATE_GITHUB_OWNER, repo = UPDATE_GITHUB_REPO) {
  if (!UPDATE_GITHUB_NAME_PATTERN.test(owner) || !UPDATE_GITHUB_NAME_PATTERN.test(repo)) return "";
  return `/repos/${owner}/${repo}/releases/latest`;
}

function isExpectedGitHubReleaseUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return url.protocol === "https:" &&
      url.hostname === "github.com" &&
      url.pathname.startsWith(`/${UPDATE_GITHUB_OWNER}/${UPDATE_GITHUB_REPO}/releases/`);
  } catch (_error) {
    return false;
  }
}

function checkForUpdates() {
  let currentVersion;
  try {
    currentVersion = require("./package.json").version;
  } catch (e) {
    console.warn("[Main] Cannot read package.json version, skipping update check:", e.message || e);
    return;
  }

  const releasePath = githubLatestReleasePath();
  if (!releasePath) return;

  const options = {
    hostname: "api.github.com",
    path: releasePath,
    headers: { "User-Agent": "Lexa-AI" },
    timeout: 5000,
  };

  const req = https.get(options, (res) => {
    let data = "";
    res.on("data", (chunk) => (data += chunk));
    res.on("end", () => {
      try {
        const release = JSON.parse(data);
        const latestVersion = (release.tag_name || "").replace(/^v/, "");
        if (latestVersion && latestVersion !== currentVersion) {
          // Send to renderer
          if (mainWindow && mainWindow.webContents) {
            mainWindow.webContents.send("update-available", {
              current: currentVersion,
              latest: latestVersion,
              url: isExpectedGitHubReleaseUrl(release.html_url) ? release.html_url : "",
            });
          }
        }
      } catch (e) {
        // Silent fail — update check is non-critical
      }
    });
  });

  req.on("error", () => {}); // Silent fail
  req.on("timeout", () => req.destroy());
}

// ── APP LIFECYCLE ────────────────────────────────
function isElectronSmokeTestContext() {
  const argvText = Array.isArray(process.argv) ? process.argv.join(" ") : "";
  return process.env.LEXA_ELECTRON_SMOKE_TEST === "1"
    || /electron_(?:ui_visual|presence_challenge)_smoke\.js/i.test(argvText);
}

function hardenSmokeMockEnvironment() {
  if (process.env.LEXA_ELECTRON_SMOKE_MOCK !== "1") return;
  if (!app.isPackaged && isElectronSmokeTestContext()) return;
  console.warn("[App] Ignoring unsafe LEXA_ELECTRON_SMOKE_MOCK outside Electron smoke tests.");
  delete process.env.LEXA_ELECTRON_SMOKE_MOCK;
}

app.whenReady().then(async () => {
  hardenSmokeMockEnvironment();

  // Set data directory for backend (e.g. C:\Users\admin\AppData\Roaming\lexa-ai)
  const dataDir = app.getPath("userData");
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
  process.env.LEXA_DATA_DIR = dataDir;
  console.log("[App] Data directory:", dataDir);
  installLocalAuthRequestHeaders();
  await installLocalAuthCookie();

  // Initialize trial license on first launch
  _initTrialIfNeeded();

  // Start Python backend before creating the window
  await startBackend();

  createWindow();
  createTray();

  // Check for updates after the window has finished loading
  mainWindow.webContents.on("did-finish-load", () => {
    checkForUpdates();
  });
});

app.on("window-all-closed", () => {
  // Don't quit on macOS
  if (process.platform !== "darwin") {
    // Keep running in tray on Windows
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  } else {
    mainWindow?.show();
  }
});

app.on("before-quit", () => {
  app.isQuitting = true;
});

app.on("will-quit", () => {
  if (backendProcess) {
    console.log("[Backend] Shutting down...");
    backendProcess.kill();
    backendProcess = null;
  }
});
