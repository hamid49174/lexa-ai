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
assert("uses ASCII external backend reuse log", src.includes("another Lexa instance - reusing"));
assert("uses ASCII non-Lexa port warning", src.includes("non-Lexa process - backend may not work"));
assert("uses ASCII backend ready log", src.includes("Health check passed - backend is ready"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
