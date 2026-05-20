/**
 * Electron startup/runtime health smoke for release-candidate checks.
 * It uses isolated userData and a local mock /health server, but exercises the
 * real preload bridge and main-process presence IPC denial path.
 * Run with: node tests\electron_startup_health_smoke.js
 */

const path = require("path");

if (!process.versions.electron) {
  const { spawnSync } = require("child_process");
  const electronBinary = process.platform === "win32" ? "electron.exe" : "electron";
  const electronPath = path.join(__dirname, "..", "frontend", "node_modules", "electron", "dist", electronBinary);
  const env = { ...process.env, LEXA_ELECTRON_SMOKE_TEST: "1" };
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.LEXA_ELECTRON_SMOKE_MOCK;
  const result = spawnSync(electronPath, [__filename], {
    cwd: path.join(__dirname, ".."),
    env,
    stdio: "inherit",
  });
  process.exit(result.status ?? (result.signal ? 1 : 0));
}

const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const http = require("http");
const os = require("os");

process.env.LEXA_ELECTRON_SMOKE_TEST = "1";
delete process.env.LEXA_ELECTRON_SMOKE_MOCK;

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-startup-health-smoke-"));
app.setPath("userData", smokeUserData);
app.on("window-all-closed", () => {});

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

function writeAudit(payload = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    method: String(payload.method || "").slice(0, 80),
    risk: String(payload.risk || payload.effective_risk || "").slice(0, 30),
    allowed: Boolean(payload.allowed),
    reason: String(payload.reason || "").slice(0, 100),
    args_hash: String(payload.args_hash || "").slice(0, 16),
    arg_keys: Array.isArray(payload.arg_keys) ? payload.arg_keys.slice(0, 20) : [],
  };
  fs.appendFileSync(path.join(app.getPath("userData"), "bridge-audit.log"), `${JSON.stringify(entry)}\n`, "utf8");
}

function startHealthServer() {
  const server = http.createServer((req, res) => {
    res.setHeader("content-type", "application/json");
    if (req.url.startsWith("/health/startup")) {
      res.end(JSON.stringify({ ok: true, status: "ok", state: "ready", safeForCockpit: true }));
      return;
    }
    if (req.url === "/health") {
      res.end(JSON.stringify({ service: "lexa-ai", ready: true, auth_required: true, instance_authenticated: true }));
      return;
    }
    res.statusCode = 404;
    res.end(JSON.stringify({ ok: false, detail: "not found" }));
  });
  return new Promise((resolve) => {
    server.once("error", () => resolve(null));
    server.listen(8000, "127.0.0.1", () => resolve(server));
  });
}

async function runRenderer(win, script) {
  return win.webContents.executeJavaScript(script, true);
}

async function main() {
  const healthServer = await startHealthServer();
  const rendererErrors = [];

  ipcMain.handle("local-auth-token", () => "startup-smoke-local-token");
  ipcMain.handle("bridge:audit", (_event, payload = {}) => {
    writeAudit(payload);
    return { ok: true };
  });
  ipcMain.handle("bridge:presence:request", (_event, payload = {}) => {
    writeAudit({ ...payload, allowed: false, reason: "startup_smoke_denied" });
    return { ok: false, reason: "startup_smoke_denied" };
  });
  ipcMain.handle("bridge:presence:consume", () => ({ ok: false, reason: "challenge_missing_or_expired" }));
  ipcMain.handle("i18n-load", () => ({}));
  ipcMain.on("get-autostart", (event) => { event.returnValue = false; });
  ipcMain.on("set-autostart", () => { throw new Error("set-autostart must not execute in startup smoke"); });

  await app.whenReady();
  const smokeHtml = path.join(smokeUserData, "startup-health-smoke.html");
  fs.writeFileSync(smokeHtml, "<!doctype html><html><body>startup smoke</body></html>", "utf8");

  const win = new BrowserWindow({
    width: 640,
    height: 420,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "frontend", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.webContents.on("console-message", (_event, level, message) => {
    const text = String(message || "");
    if (level >= 3 || /\b(Uncaught|TypeError|ReferenceError|replyWithError|EPIPE)\b/i.test(text)) {
      rendererErrors.push(text.slice(0, 300));
    }
  });

  await win.loadFile(smokeHtml);
  let bridgeReady = false;
  for (let attempt = 0; attempt < 30; attempt += 1) {
    bridgeReady = await runRenderer(win, "Boolean(window.lexa && window.lexa.health && window.lexa.setAutostart)");
    if (bridgeReady) break;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  assert("preload exposes window.lexa", bridgeReady);

  const health = await runRenderer(win, "window.lexa.health()");
  assert("read-only health works", Boolean(health && (health.ready === true || health.service === "lexa-ai")), JSON.stringify(health));

  const startup = await runRenderer(win, "window.lexa.startupHealth()");
  assert("startup health works", Boolean(startup && (startup.ok === true || startup.status === "ok")), JSON.stringify(startup));

  const highRisk = await runRenderer(win, `
    (async () => {
      try {
        await window.lexa.setAutostart(true);
        return { ok: true };
      } catch (error) {
        return { ok: false, code: error && error.code, message: String(error && error.message || "") };
      }
    })();
  `);
  assert("high-risk bridge call without gate is blocked", highRisk.ok === false && /presence|denied/i.test(`${highRisk.code || ""} ${highRisk.message || ""}`), JSON.stringify(highRisk));

  await new Promise((resolve) => setTimeout(resolve, 100));
  const auditPath = path.join(app.getPath("userData"), "bridge-audit.log");
  const auditText = fs.existsSync(auditPath) ? fs.readFileSync(auditPath, "utf8") : "";
  assert("bridge-audit.log lands under isolated userData", auditPath.startsWith(smokeUserData) && fs.existsSync(auditPath));
  assert("repo bridge-audit.log was not created", !fs.existsSync(path.join(__dirname, "..", "bridge-audit.log")));
  assert("bridge audit does not contain local auth token", !auditText.includes("startup-smoke-local-token"));
  assert("no renderer EPIPE/replyWithError/main error noise", rendererErrors.length === 0, rendererErrors.join(" | "));

  win.destroy();
  if (healthServer) await new Promise((resolve) => healthServer.close(resolve));

  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  app.quit();
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((error) => {
  console.error(error && (error.stack || error.message) || error);
  app.exit(1);
});
