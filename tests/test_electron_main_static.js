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
assert("enables watcher after loading index", src.indexOf("mainWindow.loadFile") < src.indexOf("setupFrontendAutoReload();"));

console.log("\nElectron backend recovery:");
assert("defines backend restart delay", src.includes("BACKEND_RESTART_DELAY_MS"));
assert("caps backend health response body", src.includes("HEALTH_CHECK_BODY_LIMIT") && src.includes("body.length > HEALTH_CHECK_BODY_LIMIT"));
assert("uses named backend health timeout", src.includes("HEALTH_CHECK_TIMEOUT_MS") && src.includes("req.setTimeout(HEALTH_CHECK_TIMEOUT_MS"));
assert("settles backend health checks once", src.includes("let settled = false") && src.includes("if (settled) return;"));
assert("recognizes tokenless Lexa backends", src.includes("EXTERNAL_LEXA_BACKEND") && src.includes('data.service === "lexa-ai"'));
assert("does not trust leaked health instance tokens", !src.includes("data.instance_token"));
assert("sends local auth token as health header", src.includes('"X-Lexa-Local-Token": INSTANCE_TOKEN'));
assert("reuses tokenless Lexa backend on occupied port", src.includes("without instance token") && src.includes("token === EXTERNAL_LEXA_BACKEND"));
assert("treats tokenless Lexa health as backend-ready", src.includes("token === INSTANCE_TOKEN || token === EXTERNAL_LEXA_BACKEND"));
assert("captures spawned backend child", src.includes("const child = backendProcess;"));
assert("does not restart while quitting", src.includes("if (!app.isQuitting)") && src.includes("if (app.isQuitting || backendProcess) return;"));
assert("restarts backend after unexpected exit", src.includes("startBackend().catch") && src.includes("Restart failed"));
assert("only clears matching backend child", src.includes("if (backendProcess === child) backendProcess = null;"));

console.log("\nElectron tray labels:");
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
assert("patches stdout and stderr writes below console", src.includes("function installSafeStreamWrite") && src.includes("__lexaSafeWriteInstalled") && src.includes("stream.write = (...args)") && src.includes("return originalWrite(...args)") && src.includes("installSafeProcessStreams();"));
assert("patches low-level stream writers so cached Electron console paths cannot throw", src.includes("markBrokenPipe(stream)") && src.includes("stream.__lexaBrokenPipe") && src.includes("originalChunkWrite") && src.includes("stream._write = (chunk, encoding, callback)") && src.includes("originalVectorWrite") && src.includes("stream._writev = (chunks, callback)"));
assert("patches stdio socket prototype for Electron cached console writers", src.includes('const net = require("net")') && src.includes("net.Socket.prototype._write") && src.includes("isStdioSocket") && src.includes("socket?.fd === 1") && src.includes("socket?.fd === 2"));
assert("wraps main process console methods safely", src.includes("function installSafeConsole()") && src.includes('console.warn = (...args) => safeCall("warn", args)') && src.includes('console.error = (...args) => safeCall("error", args)'));
assert("swallows uncaught EPIPE exceptions before Electron dialog listeners", src.includes("process.emit = (eventName, ...args)") && src.includes('eventName === "uncaughtException"') && src.includes("return true") && src.includes('process.on("uncaughtException"') && src.includes("if (isBrokenPipeError(error)) return"));
assert("prevents renderer console forwarding from using Electron default pipe writer", src.includes("function installRendererConsoleGuard") && src.includes('webContents.on("console-message"') && src.includes("event.preventDefault?.()") && src.includes("installRendererConsoleGuard(mainWindow.webContents);") && src.indexOf("installRendererConsoleGuard(mainWindow.webContents);") < src.indexOf("mainWindow.loadFile"));

console.log("\nElectron renderer security guards:");
assert("installs renderer security guards before loading index", src.includes("function installElectronSecurityGuards") && src.indexOf("installElectronSecurityGuards(mainWindow);") > 0 && src.indexOf("installElectronSecurityGuards(mainWindow);") < src.indexOf("mainWindow.loadFile"));
assert("denies renderer-created windows", src.includes("setWindowOpenHandler") && src.includes('return { action: "deny" };'));
assert("opens only safe external URLs outside Lexa webContents", src.includes("function safeExternalUrl") && src.includes('["http:", "https:", "mailto:"]') && src.includes("electron.shell.openExternal"));
assert("blocks unsafe renderer navigation", src.includes('webContents.on("will-navigate"') && src.includes("event.preventDefault();") && src.includes("isTrustedRendererUrl(url)"));
assert("limits trusted renderer URLs to frontend src files", src.includes("fileURLToPath") && src.includes('path.join(__dirname, "src")') && src.includes("isPathInside"));
assert("defaults permission requests to deny except trusted audio capture", src.includes("setPermissionRequestHandler") && src.includes('permission === "media"') && src.includes('mediaTypes.includes("audio")') && src.includes('!mediaTypes.includes("video")') && src.includes("callback(Boolean(allowAudioCapture))"));

console.log("\nElectron bridge audit and smoke guard:");
assert("rotates bridge audit log under userData", src.includes("BRIDGE_AUDIT_MAX_BYTES") && src.includes("function rotateBridgeAuditIfNeeded") && src.includes('app.getPath("userData")') && src.includes("`${auditPath}.1`"));
assert("bridge audit records effective risk classification", src.includes("base_risk") && src.includes("effective_risk") && src.includes("classification_reason"));
assert("smoke mock is fail-closed outside non-packaged smoke tests", src.includes("function hardenSmokeMockEnvironment") && src.includes("app.isPackaged") && src.includes("delete process.env.LEXA_ELECTRON_SMOKE_MOCK") && src.includes("function isElectronSmokeTestContext"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
