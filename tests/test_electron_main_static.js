/**
 * Static smoke tests for Electron main-process dev ergonomics.
 * Run with: node tests/test_electron_main_static.js
 */

const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "main.js"),
  "utf8"
);

let passed = 0;
let failed = 0;
function assert(desc, ok, detail = "") {
  if (ok) {
    console.log(`  ok: ${desc}`);
    passed += 1;
  } else {
    console.error(`  FAIL: ${desc}${detail ? " - " + detail : ""}`);
    failed += 1;
  }
}

console.log("\nElectron main dev auto-reload:");
assert("defines frontend auto-reload setup", src.includes("function setupFrontendAutoReload()"));
assert("keeps watcher out of packaged builds", src.includes("if (app.isPackaged) return;"));
assert("watches frontend src directory", src.includes('path.join(__dirname, "src")'));
assert("filters reloads to frontend source assets", src.includes("(?:js|css|html)"));
assert("debounces reloads", src.includes("setTimeout") && src.includes("350"));
assert("reloads renderer without cache", src.includes("reloadIgnoringCache()"));
assert("closes watcher with the main window", src.includes('mainWindow?.on("closed"'));
assert("loads renderer index through encoded file URL", src.includes("function rendererIndexUrl()") && src.includes("pathToFileURL(rendererIndexPath()).href") && src.includes("function loadRendererIndex(win)") && src.includes("win.loadURL(rendererIndexUrl())"));
assert("enables watcher after loading index", src.indexOf("loadRendererIndex(mainWindow)") < src.indexOf("setupFrontendAutoReload();"));

console.log("\nElectron backend recovery:");
assert("defines backend restart delay", src.includes("BACKEND_RESTART_DELAY_MS"));
assert("caps backend health response body", src.includes("HEALTH_CHECK_BODY_LIMIT") && src.includes("body.length > HEALTH_CHECK_BODY_LIMIT"));
assert("uses named backend health timeout", src.includes("HEALTH_CHECK_TIMEOUT_MS") && src.includes("req.setTimeout(HEALTH_CHECK_TIMEOUT_MS"));
assert("settles backend health checks once", src.includes("let settled = false") && src.includes("if (settled) return;"));
assert("recognizes tokenless Lexa backends without trusting them by default", src.includes("EXTERNAL_LEXA_BACKEND") && src.includes('data.service === "lexa-ai"') && src.includes("function allowTokenlessBackendReuse"));
assert("does not trust leaked health instance tokens", !src.includes("data.instance_token"));
assert("sends local auth token as health header", src.includes('"X-Lexa-Local-Token": INSTANCE_TOKEN'));
assert("injects local auth header into renderer backend requests", src.includes("function installLocalAuthRequestHeaders") && src.includes("ses.webRequest.onBeforeSendHeaders") && src.includes('"http://127.0.0.1:8000/*"') && src.includes("requestHeaders[LOCAL_AUTH_HEADER] = INSTANCE_TOKEN") && src.includes("installLocalAuthRequestHeaders();"));
assert("installs HttpOnly local auth cookie for renderer fetches", src.includes('const LOCAL_AUTH_COOKIE = "lexa_local_auth"') && src.includes("function installLocalAuthCookie") && src.includes("httpOnly: true") && src.includes("session.defaultSession.cookies.set") && src.includes('url: "http://127.0.0.1:8000"') && src.includes("await installLocalAuthCookie();"));
assert("reuses tokenless Lexa backend only by explicit dev opt-in", src.includes("LEXA_ALLOW_TOKENLESS_BACKEND_REUSE") && src.includes("reusing by explicit dev opt-in") && src.includes("refusing to reuse"));
assert("does not treat tokenless Lexa health as backend-ready by default", src.includes("token === INSTANCE_TOKEN || (token === EXTERNAL_LEXA_BACKEND && allowTokenlessBackendReuse())"));
assert("captures spawned backend child", src.includes("const child = backendProcess;"));
assert("does not restart while quitting", src.includes("if (!app.isQuitting)") && src.includes("if (app.isQuitting || backendProcess) return;"));
assert("restarts backend after unexpected exit", src.includes("startBackend().catch") && src.includes("Restart failed"));
assert("only clears matching backend child", src.includes("if (backendProcess === child) backendProcess = null;"));
assert("bounds backend restart retries", src.includes("BACKEND_RESTART_MAX_ATTEMPTS") && src.includes("backendRestartAttempts >= BACKEND_RESTART_MAX_ATTEMPTS"));
assert("uses exponential backend restart backoff", src.includes("function backendRestartDelayMs") && src.includes("2 ** exponent") && src.includes("BACKEND_RESTART_MAX_DELAY_MS"));
assert("resets backend restart backoff after health success", src.includes("function resetBackendRestartBackoff") && src.includes("if (ready) resetBackendRestartBackoff();"));
assert("enforces a single desktop app instance before backend startup", src.includes("const gotSingleInstanceLock = app.requestSingleInstanceLock();") && src.includes("if (!gotSingleInstanceLock)") && src.includes("app.quit();") && src.includes("if (!gotSingleInstanceLock) return;") && src.indexOf("app.requestSingleInstanceLock()") < src.indexOf("app.whenReady().then"));
assert("focuses the existing window when a second instance starts", src.includes("function focusMainWindow()") && src.includes('app.on("second-instance"') && src.includes("mainWindow.restore()") && src.includes("mainWindow.focus();"));

console.log("\nElectron tray labels:");
assert("keeps main process source ASCII-only", !/[^\x00-\x7F]/.test(src));
assert("uses ASCII tray tooltip", src.includes('tray.setToolTip("Lexa AI - Lokaler KI-Assistent")'));
assert("uses ASCII tray open label", src.includes('label: "Lexa AI oeffnen"'));
assert("does not keep mojibake tray text", !src.includes("Lexa AI \u00e2\u20ac\u201d") && !src.includes("\u00c3\u00b6ffnen"));

console.log("\nElectron backend log labels:");
assert("uses ASCII backend reuse log", src.includes("Our backend already running - reusing"));
assert("uses ASCII secured backend mismatch log", src.includes("another secured Lexa instance - cannot authenticate"));
assert("uses ASCII non-Lexa port warning", src.includes("non-Lexa process - backend may not work"));
assert("uses ASCII backend ready log", src.includes("Health check passed - backend is ready"));

console.log("\nElectron broken pipe logging:");
assert("detects broken pipe console errors", src.includes("function isBrokenPipeError") && src.includes('error?.code === "EPIPE"') && src.includes("broken pipe"));
assert("installs pipe guard before Electron can register its error dialog", src.indexOf("installPreElectronPipeGuard();") >= 0 && src.indexOf("installPreElectronPipeGuard();") < src.indexOf('const electron = require("electron")') && src.includes("lexaIsBrokenPipeError"));
assert("patches stdout and stderr writes below console", src.includes("function installSafeStreamWrite") && src.includes("__lexaSafeWriteInstalled") && src.includes("stream.write = (...args)") && src.includes("return originalWrite(...safeArgs)") && src.includes("installSafeProcessStreams();"));
assert("wraps async broken-pipe write callbacks", src.includes("function lexaWrapBrokenPipeCallback") && src.includes("wrapBrokenPipeCallback(stream, callback)") && src.includes("safeArgs[last] = wrapBrokenPipeCallback(stream, safeArgs[last])"));
assert("patches low-level stream writers so cached Electron console paths cannot throw", src.includes("markBrokenPipe(stream)") && src.includes("stream.__lexaBrokenPipe") && src.includes("originalChunkWrite") && src.includes("stream._write = (chunk, encoding, callback)") && src.includes("originalVectorWrite") && src.includes("stream._writev = (chunks, callback)"));
assert("patches stdio socket prototype for Electron cached console writers", src.includes('const net = require("net")') && src.includes("net.Socket.prototype._write") && src.includes("isStdioSocket") && src.includes("socket?.fd === 1") && src.includes("socket?.fd === 2"));
assert("wraps main process console methods safely", src.includes("function installSafeConsole()") && src.includes('console.warn = (...args) => safeCall("warn", args)') && src.includes('console.error = (...args) => safeCall("error", args)'));
assert("keeps EPIPE fallback logs under userData, not repo audit.log", src.includes("safeConsoleFallbackWriter") && src.includes("function appendSafeMainProcessLog") && src.includes("MAIN_PROCESS_LOG_MAX_BYTES") && src.includes('app.getPath("userData")') && src.includes('"main-process.log"'));
assert("swallows uncaught EPIPE exceptions before Electron dialog listeners", src.includes("process.emit = (eventName, ...args)") && src.includes('eventName === "uncaughtException"') && src.includes("return true") && src.includes('process.on("uncaughtException"') && src.includes("if (isBrokenPipeError(error)) return"));
assert("prevents renderer console forwarding from using Electron default pipe writer", src.includes("function installRendererConsoleGuard") && src.includes("function normalizeRendererConsoleMessage") && src.includes('webContents.on("console-message", (event, ...legacyConsoleArgs) =>') && src.includes("details.lineNumber") && src.includes("event.preventDefault?.()") && src.includes("installRendererConsoleGuard(mainWindow.webContents);") && src.indexOf("installRendererConsoleGuard(mainWindow.webContents);") < src.indexOf("loadRendererIndex(mainWindow)"));

console.log("\nElectron renderer security guards:");
assert("installs renderer security guards before loading index", src.includes("function installElectronSecurityGuards") && src.indexOf("installElectronSecurityGuards(mainWindow);") > 0 && src.indexOf("installElectronSecurityGuards(mainWindow);") < src.indexOf("loadRendererIndex(mainWindow)"));
assert("denies renderer-created windows", src.includes("setWindowOpenHandler") && src.includes('return { action: "deny" };'));
assert("opens only safe external URLs outside Lexa webContents", src.includes("function safeExternalUrl") && src.includes('["http:", "https:", "mailto:"]') && src.includes("electron.shell.openExternal"));
assert("blocks unsafe renderer navigation", src.includes('webContents.on("will-navigate"') && src.includes("event.preventDefault();") && src.includes("isTrustedRendererUrl(url)"));
assert("limits trusted renderer URLs to frontend src files", src.includes("fileURLToPath") && src.includes('path.join(__dirname, "src")') && src.includes("isPathInside"));
assert("sends frame-ancestors through a response header, not meta CSP", src.includes("RENDERER_CSP_HEADER") && src.includes("frame-ancestors 'none'") && src.includes("ses.webRequest.onHeadersReceived") && src.includes('responseHeaders["Content-Security-Policy"] = [RENDERER_CSP_HEADER]') && src.includes('details.resourceType === "mainFrame"'));
assert("defaults permission requests to deny except trusted audio capture", src.includes("setPermissionRequestHandler") && src.includes('permission === "media"') && src.includes('mediaTypes.includes("audio")') && src.includes('!mediaTypes.includes("video")') && src.includes("callback(Boolean(allowAudioCapture))"));

console.log("\nElectron bridge audit and smoke guard:");
assert("rotates bridge audit log under userData", src.includes("BRIDGE_AUDIT_MAX_BYTES") && src.includes("function rotateBridgeAuditIfNeeded") && src.includes('app.getPath("userData")') && src.includes("`${auditPath}.1`"));
assert("bridge audit records effective risk classification", src.includes("base_risk") && src.includes("effective_risk") && src.includes("classification_reason"));
assert("smoke mock is fail-closed outside non-packaged smoke tests", src.includes("function hardenSmokeMockEnvironment") && src.includes("app.isPackaged") && src.includes("delete process.env.LEXA_ELECTRON_SMOKE_MOCK") && src.includes("function isElectronSmokeTestContext"));

console.log("\nElectron update checks:");
assert("uses expected GitHub owner and repo constants", src.includes('const UPDATE_GITHUB_OWNER = "hamid49174"') && src.includes('const UPDATE_GITHUB_REPO = "lexa-ai"'));
assert("validates GitHub release API path parts", src.includes("function githubLatestReleasePath") && src.includes("UPDATE_GITHUB_NAME_PATTERN.test"));
assert("redacts unexpected update URLs", src.includes("function isExpectedGitHubReleaseUrl") && src.includes('url.hostname === "github.com"') && src.includes("isExpectedGitHubReleaseUrl(release.html_url) ? release.html_url : \"\""));

console.log("\nElectron IPC error containment:");
assert("defines safe IPC wrappers", src.includes("function safeIpcHandle(channel, handler, options = {})") && src.includes("function safeIpcOn(channel, handler, options = {})"));
assert("safe IPC handlers return structured failures instead of throwing to replyWithError", src.includes("function structuredIpcFailure") && src.includes("main_ipc_handler_failed") && src.includes("return structuredIpcFailure(channel, error);") && src.includes("auditMainIpcFailure(channel, error, args);"));
assert("bridge presence handlers use safe IPC wrapper", src.includes('safeIpcHandle("bridge:presence:request"') && src.includes('safeIpcHandle("bridge:presence:consume"') && src.includes('safeIpcHandle("bridge:audit"'));
assert("local auth and i18n handlers fail closed through safe IPC wrapper", src.includes('safeIpcHandle("local-auth-token"') && src.includes('failureValue: ""') && src.includes('safeIpcHandle("i18n-load"') && src.includes("failureValue: null"));
assert("window and autostart sync IPC handlers are wrapped", src.includes('safeIpcOn("window-minimize"') && src.includes('safeIpcOn("window-maximize"') && src.includes('safeIpcOn("window-close"') && src.includes('safeIpcOn("get-autostart"') && src.includes("returnValue: false"));
assert("bridge presence handlers are not registered directly", !src.includes('ipcMain.handle("bridge:presence:request"') && !src.includes('ipcMain.handle("bridge:presence:consume"') && !src.includes('ipcMain.handle("bridge:audit"'));
assert("bridge presence no longer uses native confirmation dialogs", !src.includes("dialog.showMessageBox") && !src.includes("Confirm Lexa action") && !src.includes("Allow once") && src.includes("trusted_renderer_auto_challenge"));

console.log("\nElectron license hardening:");
assert("recognizes server-backed pro and ultra licenses", src.includes("function _normalizeLicensePlan") && src.includes('"pro"') && src.includes('"ultra"') && src.includes("function _isPaidLicensePlan"));
assert("paid license state requires server activation proof", src.includes("function _hasServerLicenseProof") && src.includes('validation_source === "server"') && src.includes('_state: "paid_unverified"'));
assert("license activation is owned by main process", src.includes('safeIpcHandle("license-activate"') && src.includes("async function _activateLicenseKey") && src.includes('requestBackendJson("/license/validate"') && src.includes('method: "POST"') && src.includes("license_key: key"));
assert("license-set cannot write paid plans directly", src.includes('safeIpcHandle("license-set"') && src.includes("Use license activation for paid plans") && src.includes("const success = _clearStoredLicense();"));
assert("trial is created only when no stored license state exists", src.includes("if (existing) return existing;") && src.includes("Create trial only on the first launch without any stored license state") && !src.includes('existing && existing.plan !== "free"'));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
