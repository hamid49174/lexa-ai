/**
 * Electron smoke for provider-gated screenshot analysis.
 * Ensures the renderer does not open the critical vision confirmation path when no provider is ready.
 * Run with: node tests\electron_vision_readiness_smoke.js
 */

const path = require("path");
const { loadElectronSmokeFile, normalizeElectronConsoleMessage } = require("./electron_smoke_safe_io");

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
  if (result.error) {
    console.error(`[Electron smoke] Failed to launch Electron at ${electronPath}: ${result.error.message || result.error}`);
    process.exit(1);
  }
  process.exit(result.status ?? 1);
}

const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const os = require("os");

process.env.LEXA_ELECTRON_SMOKE_TEST = "1";
process.env.LEXA_ELECTRON_SMOKE_MOCK = "1";

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-vision-readiness-smoke-"));
app.setPath("userData", smokeUserData);
app.on("window-all-closed", () => {});

let passed = 0;
let failed = 0;
const bridgeAudits = [];
const presenceRequests = [];

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
ipcMain.handle("local-auth-token", () => "vision-readiness-smoke-token");
ipcMain.handle("bridge:audit", (_event, payload = {}) => {
  bridgeAudits.push(payload);
  return { ok: true };
});
ipcMain.handle("bridge:presence:request", (_event, payload = {}) => {
  presenceRequests.push(payload);
  return { ok: false, reason: "vision_readiness_smoke_denied" };
});
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

  win.webContents.on("console-message", (event, ...legacyConsoleArgs) => {
    const { level, message, line, sourceId } = normalizeElectronConsoleMessage(event, ...legacyConsoleArgs);
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

  await loadElectronSmokeFile(win, path.join(__dirname, "..", "frontend", "src", "index.html"));
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

      await waitFor(() =>
        window.lexa
        && typeof window.lexa.visionStatus === "function"
        && typeof window.lexa.visionAnalyze === "function"
        && typeof triggerScreenshotAnalysis === "function"
        && typeof clearRenderedChatMessages === "function"
        && typeof addMessage === "function"
        && document.getElementById("chat-messages")
      );

      clearRenderedChatMessages();
      await triggerScreenshotAnalysis();
      await new Promise((resolve) => setTimeout(resolve, 160));

      const messages = Array.from(document.querySelectorAll("#chat-messages .message.system-message"));
      const latest = messages[messages.length - 1];
      const text = latest?.textContent || "";
      const html = latest?.innerHTML || "";
      const toastText = document.querySelector(".toast-container")?.textContent || "";

      return {
        messageText: text,
        messageHtml: html,
        toastText,
        unsafeNodes: document.querySelectorAll("#chat-messages script, #chat-messages img[onerror]").length,
      };
    })();
  `);

  await new Promise((resolve) => setTimeout(resolve, 120));

  console.log("\nVision readiness smoke:");
  assert("missing vision provider renders friendly chat fallback", /Vision|Bildanalyse|image analysis/i.test(result.messageText || ""), JSON.stringify(result));
  assert("missing vision provider renders provider toast", /Provider|Vision|connected|fehlt/i.test(result.toastText || ""), JSON.stringify(result));
  assert("critical vision analysis is not called when provider is missing", !bridgeAudits.some((entry) => entry?.method === "visionAnalyze") && presenceRequests.length === 0, JSON.stringify({ bridgeAudits, presenceRequests }));
  assert("vision fallback does not create executable nodes", Number(result.unsafeNodes || 0) === 0 && !/<script/i.test(result.messageHtml || ""), JSON.stringify(result));
  assert("renderer stayed free of fatal errors", rendererErrors.length === 0, JSON.stringify(rendererErrors));

  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  await win.close();
  app.exit(failed > 0 ? 1 : 0);
}

main().catch(async (error) => {
  console.error(error);
  app.exit(1);
});
