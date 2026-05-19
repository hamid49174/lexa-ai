/**
 * Electron smoke test for preload bridge presence challenges.
 * Run with: frontend\node_modules\electron\dist\electron.exe tests\electron_presence_challenge_smoke.js
 */

const { app, BrowserWindow, ipcMain } = require("electron");
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

process.env.LEXA_ELECTRON_SMOKE_TEST = "1";
delete process.env.LEXA_ELECTRON_SMOKE_MOCK;

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

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-presence-smoke-"));
const auditPath = path.join(tmpDir, "bridge-audit.log");
const challenges = new Map();
let presenceMode = "deny";
let presenceRequests = 0;
let autostartWrites = 0;

function writeAudit(event) {
  fs.appendFileSync(auditPath, `${JSON.stringify(event)}\n`, "utf8");
}

ipcMain.handle("local-auth-token", () => "test-local-token");
ipcMain.handle("bridge:audit", (_event, payload = {}) => {
  writeAudit({
    method: String(payload.method || ""),
    risk: String(payload.risk || ""),
    base_risk: String(payload.base_risk || ""),
    effective_risk: String(payload.effective_risk || ""),
    allowed: Boolean(payload.allowed),
    reason: String(payload.reason || ""),
    args_hash: String(payload.args_hash || "").slice(0, 16),
    arg_keys: Array.isArray(payload.arg_keys) ? payload.arg_keys : [],
    classification_reason: String(payload.classification_reason || ""),
  });
  return { ok: true };
});

ipcMain.handle("bridge:presence:request", (_event, payload = {}) => {
  presenceRequests += 1;
  writeAudit({
    method: payload.method,
    risk: payload.risk,
    allowed: presenceMode === "allow",
    reason: `presence_${presenceMode}`,
    args_hash: String(payload.args_hash || "").slice(0, 16),
    arg_keys: Array.isArray(payload.arg_keys) ? payload.arg_keys : [],
  });
  if (presenceMode === "deny") return { ok: false, reason: "user_denied" };

  const id = presenceMode === "replay" ? "replay-challenge" : crypto.randomBytes(12).toString("hex");
  const record = {
    method: String(payload.method || ""),
    argsHash: String(payload.args_hash || ""),
    used: presenceMode === "replay",
    expiresAt: presenceMode === "expired" ? Date.now() - 1 : Date.now() + 60000,
  };
  if (presenceMode === "wrong_args") record.argsHash = "0".repeat(64);
  challenges.set(id, record);
  return { ok: true, challenge_id: id, expires_at: new Date(Date.now() + 60000).toISOString() };
});

ipcMain.handle("bridge:presence:consume", (_event, payload = {}) => {
  const id = String(payload.challenge_id || "");
  const record = challenges.get(id);
  if (!record) return { ok: false, reason: "challenge_missing_or_expired" };
  if (record.used) return { ok: false, reason: "challenge_replay" };
  if (record.expiresAt <= Date.now()) return { ok: false, reason: "challenge_expired" };
  if (record.method !== payload.method) return { ok: false, reason: "method_mismatch" };
  if (record.argsHash !== payload.args_hash) return { ok: false, reason: "args_hash_mismatch" };
  record.used = true;
  challenges.delete(id);
  return { ok: true };
});

ipcMain.on("get-autostart", (event) => {
  event.returnValue = false;
});
ipcMain.on("set-autostart", (_event, enabled) => {
  autostartWrites += enabled ? 1 : 0;
});

async function runRenderer(win, script) {
  return win.webContents.executeJavaScript(script, true);
}

async function expectRejected(win, desc, script, expectedError = "") {
  const result = await runRenderer(win, `
    (async () => {
      try {
        await (${script});
        return { ok: true };
      } catch (error) {
        return { ok: false, code: error && error.code, message: String(error && error.message || "") };
      }
    })();
  `);
  const matchesExpected = !expectedError
    || result.code === expectedError
    || String(result.message || "").includes(expectedError);
  assert(desc, result.ok === false && matchesExpected, JSON.stringify(result));
}

async function main() {
  await app.whenReady();
  const rendererErrors = [];
  const smokeHtml = path.join(tmpDir, "presence-smoke.html");
  fs.writeFileSync(smokeHtml, "<!doctype html><html><body>presence smoke</body></html>", "utf8");
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
    if (level >= 2) rendererErrors.push(String(message || "").slice(0, 300));
  });
  await win.loadFile(smokeHtml);
  let bridgeReady = false;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    bridgeReady = await runRenderer(win, "Boolean(window.lexa && window.lexa.setAutostart && window.lexa.getAutostart)");
    if (bridgeReady) break;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  assert("preload exposes window.lexa in Electron smoke", bridgeReady, rendererErrors.join(" | "));
  if (!bridgeReady) {
    win.destroy();
    app.quit();
    process.exit(1);
  }

  presenceMode = "deny";
  await expectRejected(win, "high-risk bridge call without challenge is blocked", "window.lexa.setAutostart(true)", "explicit user presence");

  const beforeReads = presenceRequests;
  const readResult = await runRenderer(win, "window.lexa.getAutostart()");
  assert("read-only autostart status works without presence dialog", readResult === false && presenceRequests === beforeReads);

  presenceMode = "allow";
  await runRenderer(win, "window.lexa.setAutostart(true)");
  assert("high-risk bridge call with challenge is allowed once", autostartWrites === 1);

  presenceMode = "replay";
  await expectRejected(win, "replayed challenge is rejected", "window.lexa.setAutostart(true)", "challenge could not be consumed");

  presenceMode = "wrong_args";
  await expectRejected(win, "challenge bound to another args_hash is rejected", "window.lexa.setAutostart(true)", "challenge could not be consumed");

  presenceMode = "expired";
  await expectRejected(win, "expired challenge is rejected", "window.lexa.setAutostart(true)", "challenge could not be consumed");

  await expectRejected(
    win,
    "executeBatch mutating command is blocked before backend call",
    "window.lexa.executeBatch([{ command: 'file_write', params: { token: 'SECRET_TOKEN_FROM_SMOKE' } }])",
    "executeBatch only allows explicitly read-only companion commands",
  );

  await new Promise((resolve) => setTimeout(resolve, 100));
  const auditText = fs.existsSync(auditPath) ? fs.readFileSync(auditPath, "utf8") : "";
  assert("bridge audit log is written during smoke", auditText.includes("setAutostart") && auditText.includes("executeBatch"));
  assert("bridge audit log does not contain secret argument values", !auditText.includes("SECRET_TOKEN_FROM_SMOKE"));

  win.destroy();
  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  app.quit();
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  app.quit();
  process.exit(1);
});
