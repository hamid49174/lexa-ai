/**
 * Electron chat local-action block smoke.
 * Uses the real renderer scripts and verifies chat does not surface native
 * Allow/Deny confirmation or execute local tools from normal chat.
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

      let nativeConfirmCalls = 0;
      const originalConfirm = window.confirm;
      window.confirm = () => {
        nativeConfirmCalls += 1;
        return true;
      };

      let prepareCalls = 0;
      let executeWithConfirmationCalls = 0;
      const originalPrepare = window.lexa.prepareCompanionExecute;
      const originalExecuteWithConfirmation = window.lexa.executeWithConfirmation;
      try { window.lexa.prepareCompanionExecute = () => { prepareCalls += 1; return Promise.resolve({ success: false }); }; } catch (_) {}
      try { window.lexa.executeWithConfirmation = () => { executeWithConfirmationCalls += 1; return Promise.resolve({ success: false }); }; } catch (_) {}

      const action = {
        action: "personal_os_write",
        params: {
          path: "<img src=x onerror=alert(1)>",
          body: "Draft <script>alert(1)</script>",
        },
      };

      addMessage("Local tool action from chat", "system", action, true, true);
      const message = Array.from(document.querySelectorAll(".system-message")).at(-1);
      const actionCard = message?.querySelector(".msg-action") || null;
      const actionCmd = actionCard?.querySelector(".action-cmd") || null;
      const actionDetail = actionCard?.querySelector(".action-detail") || null;
      const rendered = {
        label: actionCard?.querySelector(".action-label")?.textContent || "",
        actionText: actionCmd?.textContent || "",
        actionHtml: actionCmd?.innerHTML || "",
        detailText: actionDetail?.textContent || "",
        detailHtml: actionDetail?.innerHTML || "",
        confirmButtons: message?.querySelectorAll(".confirm-btn").length || 0,
        denyButtons: message?.querySelectorAll(".deny-btn").length || 0,
        unsafeNodes: message?.querySelectorAll(".msg-action img,.msg-action script").length || 0,
      };

      const fakeButton = document.createElement("button");
      fakeButton.textContent = "compat";
      document.body.appendChild(fakeButton);
      if (typeof confirmAction === "function") {
        await confirmAction(fakeButton, encodeURIComponent(JSON.stringify(action)));
      }
      const compatibility = {
        buttonDisabled: fakeButton.disabled === true,
        buttonText: fakeButton.textContent || "",
        clearCalls: fetchCalls.filter((call) => call.url.endsWith("/chat/confirm-clear")).length,
        nativeConfirmCalls,
        prepareCalls,
        executeWithConfirmationCalls,
        executedMessages: Array.from(document.querySelectorAll(".system-message .msg-text")).filter((el) => /Ausgef|Executed/i.test(el.textContent || "")).length,
      };

      try { window.lexa.prepareCompanionExecute = originalPrepare; } catch (_) {}
      try { window.lexa.executeWithConfirmation = originalExecuteWithConfirmation; } catch (_) {}
      window.confirm = originalConfirm;
      window.fetch = originalFetch;
      return { rendered, compatibility };
    })();
  `);

  const rendered = result.rendered || {};
  console.log("\nChat local-action block render:");
  assert("chat renders a blocked local-action card", /BLOCKIERT|BLOCKED/i.test(rendered.label || "") && /personal_os_write/.test(rendered.actionText || ""), JSON.stringify(rendered));
  assert("chat action card exposes parameter keys but not unsafe values", /body/.test(rendered.actionText || "") && /path/.test(rendered.actionText || "") && !/onerror=alert|<script/i.test(rendered.actionText || "") && !/onerror=alert|<script/i.test(rendered.actionHtml || ""), JSON.stringify(rendered));
  assert("chat action card has no confirm or deny controls", Number(rendered.confirmButtons || 0) === 0 && Number(rendered.denyButtons || 0) === 0, JSON.stringify(rendered));
  assert("unsafe action values are contained", Number(rendered.unsafeNodes || 0) === 0 && !/<img|<script/i.test(rendered.detailHtml || ""), JSON.stringify(rendered));

  const compatibility = result.compatibility || {};
  console.log("\nConfirm-action compatibility path:");
  assert("legacy confirmAction fails closed without native confirm", compatibility.buttonDisabled === true && compatibility.nativeConfirmCalls === 0 && compatibility.executedMessages === 0, JSON.stringify(compatibility));
  assert("legacy confirmAction does not prepare or execute companion action", compatibility.prepareCalls === 0 && compatibility.executeWithConfirmationCalls === 0, JSON.stringify(compatibility));
  assert("legacy confirmAction only clears stale pending confirmation state", compatibility.clearCalls === 1, JSON.stringify(compatibility));
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
