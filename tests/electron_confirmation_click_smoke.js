/**
 * Electron confirmation click smoke.
 * Uses the real renderer scripts with isolated userData and mock confirmation calls.
 * Run with: node tests\electron_confirmation_click_smoke.js
 */

const path = require("path");

if (!process.versions.electron) {
  const { spawnSync } = require("child_process");
  const electronBinary = process.platform === "win32" ? "electron.exe" : "electron";
  const electronPath = path.join(__dirname, "..", "frontend", "node_modules", "electron", "dist", electronBinary);
  const env = { ...process.env, LEXA_ELECTRON_SMOKE_TEST: "1", LEXA_ELECTRON_SMOKE_MOCK: "1" };
  delete env.ELECTRON_RUN_AS_NODE;
  const result = spawnSync(electronPath, [__filename], {
    cwd: path.join(__dirname, ".."),
    env,
    stdio: "inherit",
  });
  process.exit(result.status ?? (result.signal ? 1 : 0));
}

const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const os = require("os");

process.env.LEXA_ELECTRON_SMOKE_TEST = "1";
process.env.LEXA_ELECTRON_SMOKE_MOCK = "1";

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-confirmation-click-smoke-"));
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

function runRenderer(win, script) {
  return win.webContents.executeJavaScript(script, true);
}

ipcMain.handle("i18n-load", (_event, lang) => {
  const safeLang = lang === "en" ? "en" : "de";
  const filePath = path.join(__dirname, "..", "frontend", "src", "i18n", `${safeLang}.json`);
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
});
ipcMain.handle("local-auth-token", () => "confirmation-click-smoke-token");
ipcMain.handle("bridge:audit", () => ({ ok: true }));
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "confirmation_click_smoke_denied" }));
ipcMain.handle("bridge:presence:consume", () => ({ ok: false, reason: "challenge_missing_or_expired" }));
ipcMain.on("get-autostart", (event) => { event.returnValue = false; });
ipcMain.on("set-autostart", () => {});

async function main() {
  await app.whenReady();

  const rendererErrors = [];
  const win = new BrowserWindow({
    width: 1100,
    height: 760,
    show: false,
    backgroundColor: "#071018",
    webPreferences: {
      preload: path.join(__dirname, "..", "frontend", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.webContents.on("console-message", (_event, level, message, line, sourceId) => {
    const text = String(message || "");
    if (/frame-ancestors.+meta/i.test(text)) return;
    if (level >= 3 || /\b(LEXA ERROR|Unhandled|TypeError|ReferenceError|SyntaxError|RangeError)\b/i.test(text)) {
      rendererErrors.push({ level, message: text.slice(0, 500), line, sourceId });
    }
  });
  win.webContents.on("render-process-gone", (_event, details) => {
    rendererErrors.push({ level: 3, message: `render-process-gone: ${details?.reason || "unknown"}` });
  });
  win.webContents.on("did-fail-load", (_event, code, description, url) => {
    rendererErrors.push({ level: 3, message: `did-fail-load ${code}: ${description || ""} ${url || ""}`.trim() });
  });

  await win.loadFile(path.join(__dirname, "..", "frontend", "src", "index.html"));
  await new Promise((resolve) => setTimeout(resolve, 1400));

  const result = await runRenderer(win, `
    (async () => {
      const waitFor = (predicate, timeoutMs = 5000) => new Promise((resolve) => {
        const started = Date.now();
        const tick = () => {
          let value = false;
          try { value = predicate(); } catch (_) { value = false; }
          if (value) { resolve({ ok: true }); return; }
          if (Date.now() - started > timeoutMs) { resolve({ ok: false, timeoutMs }); return; }
          setTimeout(tick, 40);
        };
        tick();
      });

      await waitFor(() => window.lexa && typeof addMessage === "function" && typeof clearRenderedChatMessages === "function");
      clearRenderedChatMessages();
      LexaState.set("backendOnline", true);
      LexaState.set("isLoading", false);
      LexaState.set("ttsEnabled", false);

      const fetchCalls = [];
      const originalFetch = window.fetch;
      window.fetch = async (url, options = {}) => {
        fetchCalls.push({ url: String(url || ""), method: String(options?.method || "GET") });
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      };

      const action = {
        action: "personal_os_write",
        params: {
          path: "<img src=x onerror=alert(1)>",
          body: "Draft <script>alert(1)</script>",
        },
      };

      addMessage("Approval path needs confirmation", "system", action, true, true);
      const approvalMessage = Array.from(document.querySelectorAll(".system-message")).at(-1);
      const approvalCmd = approvalMessage?.querySelector(".action-cmd") || null;
      const approvalButton = approvalMessage?.querySelector(".confirm-btn") || null;
      const approvalBefore = {
        actionText: approvalCmd?.textContent || "",
        actionHtml: approvalCmd?.innerHTML || "",
        confirmButtons: approvalMessage?.querySelectorAll(".confirm-btn").length || 0,
        denyButtons: approvalMessage?.querySelectorAll(".deny-btn").length || 0,
        clearCalls: fetchCalls.filter((call) => call.url.endsWith("/chat/confirm-clear")).length,
      };
      const confirmPrompts = [];
      const originalConfirm = window.confirm;
      window.confirm = (message) => {
        confirmPrompts.push(String(message || ""));
        return true;
      };
      approvalButton?.click();
      approvalButton?.click();
      const approvalWait = await waitFor(() => Array.from(document.querySelectorAll(".system-message .msg-text")).some((el) => /Ausgef|Executed/i.test(el.textContent || "")));
      window.confirm = originalConfirm;
      const approvalAfter = {
        waitOk: approvalWait.ok,
        buttonDisabled: approvalButton?.disabled === true,
        buttonText: approvalButton?.textContent || "",
        clearCalls: fetchCalls.filter((call) => call.url.endsWith("/chat/confirm-clear")).length,
        executedMessages: Array.from(document.querySelectorAll(".system-message .msg-text")).filter((el) => /Ausgef|Executed/i.test(el.textContent || "")).length,
        confirmPrompts,
      };

      clearRenderedChatMessages();
      fetchCalls.length = 0;
      addMessage("Deny path needs confirmation", "system", action, true, true);
      const denyMessage = Array.from(document.querySelectorAll(".system-message")).at(-1);
      const denyCmd = denyMessage?.querySelector(".action-cmd") || null;
      const denyButton = denyMessage?.querySelector(".deny-btn") || null;
      const denyBefore = {
        actionText: denyCmd?.textContent || "",
        actionHtml: denyCmd?.innerHTML || "",
        confirmButtons: denyMessage?.querySelectorAll(".confirm-btn").length || 0,
        denyButtons: denyMessage?.querySelectorAll(".deny-btn").length || 0,
        clearCalls: fetchCalls.filter((call) => call.url.endsWith("/chat/confirm-clear")).length,
      };
      denyButton?.click();
      const denyAfter = {
        denyDisabled: denyButton?.disabled === true,
        denyText: denyButton?.textContent || "",
        confirmButtons: denyMessage?.querySelectorAll(".confirm-btn").length || 0,
        denyButtons: denyMessage?.querySelectorAll(".deny-btn").length || 0,
        clearCalls: fetchCalls.filter((call) => call.url.endsWith("/chat/confirm-clear")).length,
        executedMessages: Array.from(document.querySelectorAll(".system-message .msg-text")).filter((el) => /Ausgef|Executed/i.test(el.textContent || "")).length,
        actionCards: denyMessage?.querySelectorAll(".msg-action").length || 0,
      };

      clearRenderedChatMessages();
      fetchCalls.length = 0;
      addMessage("Window confirm cancel path", "system", action, true, true);
      const cancelMessage = Array.from(document.querySelectorAll(".system-message")).at(-1);
      const cancelButton = cancelMessage?.querySelector(".confirm-btn") || null;
      const cancelPrompts = [];
      window.confirm = (message) => {
        cancelPrompts.push(String(message || ""));
        return false;
      };
      cancelButton?.click();
      const cancelWait = await waitFor(() => Array.from(document.querySelectorAll(".system-message .msg-text")).some((el) => /Abgebrochen|Cancelled/i.test(el.textContent || "")));
      window.confirm = originalConfirm;
      const cancelAfter = {
        waitOk: cancelWait.ok,
        buttonDisabled: cancelButton?.disabled === true,
        clearCalls: fetchCalls.filter((call) => call.url.endsWith("/chat/confirm-clear")).length,
        cancelledMessages: Array.from(document.querySelectorAll(".system-message .msg-text")).filter((el) => /Abgebrochen|Cancelled/i.test(el.textContent || "")).length,
        executedMessages: Array.from(document.querySelectorAll(".system-message .msg-text")).filter((el) => /Ausgef|Executed/i.test(el.textContent || "")).length,
        confirmPrompts: cancelPrompts,
      };

      window.fetch = originalFetch;
      return { approvalBefore, approvalAfter, denyBefore, denyAfter, cancelAfter };
    })();
  `);

  console.log("\nConfirmation approval click:");
  assert("approval confirmation renders escaped action params before click", /personal_os_write/.test(result.approvalBefore?.actionText || "") && /onerror=alert/.test(result.approvalBefore?.actionText || "") && !/<img|<script/i.test(result.approvalBefore?.actionHtml || "") && result.approvalBefore?.confirmButtons === 1 && result.approvalBefore?.denyButtons === 1, JSON.stringify(result.approvalBefore));
  assert("approval click clears pending confirmation once", result.approvalBefore?.clearCalls === 0 && result.approvalAfter?.clearCalls === 1, JSON.stringify(result.approvalAfter));
  assert("approval click uses mocked confirmation execution", result.approvalAfter?.waitOk === true && result.approvalAfter?.executedMessages === 1 && result.approvalAfter?.buttonDisabled === true, JSON.stringify(result.approvalAfter));
  assert("approval prompt contains safe command summary", Array.isArray(result.approvalAfter?.confirmPrompts) && result.approvalAfter.confirmPrompts.length === 1 && /Command: personal_os_write/.test(result.approvalAfter.confirmPrompts[0] || "") && /Params:/.test(result.approvalAfter.confirmPrompts[0] || ""), JSON.stringify(result.approvalAfter?.confirmPrompts));

  console.log("\nConfirmation deny button click:");
  assert("deny confirmation renders escaped action params before click", /personal_os_write/.test(result.denyBefore?.actionText || "") && /onerror=alert/.test(result.denyBefore?.actionText || "") && !/<img|<script/i.test(result.denyBefore?.actionHtml || "") && result.denyBefore?.confirmButtons === 1 && result.denyBefore?.denyButtons === 1, JSON.stringify(result.denyBefore));
  assert("deny click clears pending confirmation once", result.denyBefore?.clearCalls === 0 && result.denyAfter?.clearCalls === 1, JSON.stringify(result.denyAfter));
  assert("deny click updates UI without execution", result.denyAfter?.denyDisabled === true && result.denyAfter?.confirmButtons === 0 && result.denyAfter?.denyButtons === 1 && result.denyAfter?.executedMessages === 0, JSON.stringify(result.denyAfter));

  console.log("\nWindow confirm cancel path:");
  assert("window cancel clears pending confirmation but does not execute", result.cancelAfter?.waitOk === true && result.cancelAfter?.clearCalls === 1 && result.cancelAfter?.cancelledMessages === 1 && result.cancelAfter?.executedMessages === 0 && result.cancelAfter?.buttonDisabled === true, JSON.stringify(result.cancelAfter));
  assert("window cancel prompt contains safe command summary", Array.isArray(result.cancelAfter?.confirmPrompts) && result.cancelAfter.confirmPrompts.length === 1 && /Command: personal_os_write/.test(result.cancelAfter.confirmPrompts[0] || ""), JSON.stringify(result.cancelAfter?.confirmPrompts));
  assert("renderer produced no fatal console errors", rendererErrors.length === 0, JSON.stringify(rendererErrors));

  win.destroy();
  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  app.quit();
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((error) => {
  console.error(error && (error.stack || error.message) || error);
  app.exit(1);
});
