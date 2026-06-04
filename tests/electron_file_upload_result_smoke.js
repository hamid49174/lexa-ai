/**
 * Electron render-only file upload/result display smoke.
 * Uses the real renderer scripts with isolated userData and in-memory File objects only.
 * Run with: node tests\electron_file_upload_result_smoke.js
 */

const path = require("path");
const { normalizeElectronConsoleMessage } = require("./electron_smoke_safe_io");

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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-file-display-smoke-"));
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
ipcMain.handle("local-auth-token", () => "file-display-smoke-token");
ipcMain.handle("bridge:audit", (_event, payload = {}) => {
  bridgeAudits.push(payload);
  return { ok: true };
});
ipcMain.handle("bridge:presence:request", (_event, payload = {}) => {
  presenceRequests.push(payload);
  return { ok: false, reason: "file_display_smoke_denied" };
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

      await waitFor(() =>
        window.lexa
        && typeof clearRenderedChatMessages === "function"
        && typeof addFileUploadMessage === "function"
        && typeof addFileUploadResponse === "function"
        && typeof buildFileUploadCard === "function"
        && typeof buildFileInfoBadge === "function"
        && typeof fileUploadSizeLabel === "function"
        && typeof fileInfoBadgeText === "function"
        && typeof clearChatVolatileState === "function"
        && document.getElementById("chat-input")
      );

      const originalFetch = window.fetch;
      const fetchCalls = [];
      window.fetch = async (url, options = {}) => {
        fetchCalls.push({ url: String(url || ""), method: options?.method || "GET" });
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      };

      clearRenderedChatMessages();
      clearChatVolatileState();
      LexaState.set("backendOnline", true);
      LexaState.set("isLoading", false);
      LexaState.set("currentConversationId", null);
      LexaState.set("conversationsList", []);
      LexaState.set("ttsEnabled", false);

      const unsafeName = "report <img src=x onerror=alert(1)>.md";
      const file = new File(["# Report\\n<script>alert(1)</script>"], unsafeName, { type: "text/markdown" });
      addFileUploadMessage(file, "Please inspect this attachment.");

      const userMsg = document.querySelector("#chat-messages .message.user-message:last-child");
      const fileCard = userMsg?.querySelector(".file-card");
      const fileName = fileCard?.querySelector(".file-card-name");
      const fileMeta = fileCard?.querySelector(".file-card-meta");

      const pngBytes = Uint8Array.from(
        atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="),
        (char) => char.charCodeAt(0)
      );
      const imageFile = new File([pngBytes], "screen.png", { type: "image/png" });
      addFileUploadMessage(imageFile, "");
      const imageMsg = document.querySelector("#chat-messages .message.user-message:last-child");
      const imageCard = imageMsg?.querySelector(".file-card");
      const imagePreview = imageCard?.querySelector(".file-card-preview");

      addFileUploadResponse({
        reply: "Attachment result <script>alert(1)</script> with **markdown**.",
        file_info: {
          type: "md<script>",
          size_kb: "12<script>",
          line_count: 3,
        },
      });

      const systemMsg = document.querySelector("#chat-messages .message.system-message:last-child");
      const fileBadge = systemMsg?.querySelector(".file-info-badge");
      const systemText = systemMsg?.querySelector(".msg-text");

      addFileUploadResponse({
        reply: "Upload failed: <img src=x onerror=alert(2)>",
        file_info: {
          type: "error<img>",
          size_kb: 0,
        },
      });
      const failedMsg = document.querySelector("#chat-messages .message.system-message:last-child");

      addFileUploadResponse({
        reply: "Fuehre 'file_info' aus.",
        action: {
          action: "file_info",
          params: { path: "C:\\\\Users\\\\admin\\\\secret.png" },
        },
        requires_confirmation: true,
        file_info: {
          type: "png",
          size_kb: 258.8,
        },
      });
      const suppressedActionMsg = document.querySelector("#chat-messages .message.system-message:last-child");

      addFileUploadResponse({
        analysis_status: "vision_provider_required",
        reply: "Fuehre 'vision_analyze' aus.",
        file_info: {
          filename: "screen <img src=x onerror=alert(3)>.png",
          type: "png",
          size_kb: 258.8,
          analysis_status: "vision_provider_required",
        },
      });
      const visionPendingMsg = document.querySelector("#chat-messages .message.system-message:last-child");
      const visionPendingBadge = visionPendingMsg?.querySelector(".file-info-badge");
      const visionPendingText = visionPendingMsg?.querySelector(".msg-text");

      clearRenderedChatMessages();
      renderPersistedConversationMessages([
        { role: "user", content: "Attachment history <button data-action='confirm-action'>Run</button> <script>alert(1)</script>" },
        { role: "assistant", content: "Result history <img src=x onerror=alert(1)> **safe**" },
      ]);
      const historyState = {
        actionControls: document.querySelectorAll("#chat-messages [data-action='confirm-action'], #chat-messages .action-card").length,
        text: document.getElementById("chat-messages")?.textContent || "",
        html: document.getElementById("chat-messages")?.innerHTML || "",
      };

      const unsafeNodes = document.querySelectorAll("#chat-messages script, #chat-messages img[onerror]").length;
      const displayHelpers = {
        size: fileUploadSizeLabel(file),
        extension: fileUploadExtension(file),
        badge: fileInfoBadgeText({ type: "txt", size_kb: 2, line_count: 4 }),
        visionBadge: fileInfoBadgeText({ type: "png", size_kb: 258.8, analysis_status: "vision_provider_required" }),
      };

      window.fetch = originalFetch;
      return {
        fileCard: {
          exists: Boolean(fileCard),
          nameText: fileName?.textContent || "",
          nameHtml: fileName?.innerHTML || "",
          metaText: fileMeta?.textContent || "",
        },
        imagePreview: {
          exists: Boolean(imagePreview),
          src: imagePreview?.getAttribute("src") || "",
          ariaHidden: imagePreview?.getAttribute("aria-hidden") || "",
          cardClass: imageCard?.className || "",
        },
        resultBadge: {
          text: fileBadge?.textContent || "",
          html: fileBadge?.innerHTML || "",
          systemText: systemText?.textContent || "",
          systemHtml: systemText?.innerHTML || "",
        },
        failedResult: {
          text: failedMsg?.textContent || "",
          html: failedMsg?.innerHTML || "",
        },
        suppressedAction: {
          text: suppressedActionMsg?.textContent || "",
          html: suppressedActionMsg?.innerHTML || "",
          actionControls: suppressedActionMsg?.querySelectorAll("[data-action='confirm-action'], .msg-action, .action-card").length || 0,
        },
        visionPending: {
          text: visionPendingMsg?.textContent || "",
          html: visionPendingMsg?.innerHTML || "",
          badgeText: visionPendingBadge?.textContent || "",
          bodyText: visionPendingText?.textContent || "",
          bodyHtml: visionPendingText?.innerHTML || "",
        },
        historyState,
        unsafeNodes,
        fetchCalls,
        displayHelpers,
      };
    })();
  `);

  await new Promise((resolve) => setTimeout(resolve, 120));

  console.log("\nFile upload/result display smoke:");
  const fileCard = result.fileCard || {};
  assert("in-memory file upload card renders", fileCard.exists === true, JSON.stringify(fileCard));
  assert("unsafe file name is displayed as text", fileCard.nameText.includes("<img src=x onerror=alert(1)>") && /&lt;img src=x onerror=alert\(1\)&gt;/.test(fileCard.nameHtml || "") && !/<img/i.test(fileCard.nameHtml || ""), JSON.stringify(fileCard));
  assert("file metadata renders extension and size", /MD/i.test(fileCard.metaText || "") && /\d+(\.\d+)?\s*(B|KB)/.test(fileCard.metaText || ""), JSON.stringify(fileCard));
  assert("image file upload card renders a local preview", result.imagePreview?.exists === true && /^blob:/.test(result.imagePreview?.src || "") && result.imagePreview?.ariaHidden === "true" && /file-card-with-preview/.test(result.imagePreview?.cardClass || ""), JSON.stringify(result.imagePreview || {}));

  const resultBadge = result.resultBadge || {};
  assert("file result badge renders metadata safely", resultBadge.text.includes("MD<SCRIPT>") && resultBadge.text.includes("12<script> KB") && resultBadge.text.includes("3") && !/<script/i.test(resultBadge.html || ""), JSON.stringify(resultBadge));
  assert("file result content remains escaped while markdown renders", resultBadge.systemText.includes("Attachment result") && resultBadge.systemText.includes("alert(1)") && !/<script/i.test(resultBadge.systemHtml || "") && /<strong>markdown<\/strong>/i.test(resultBadge.systemHtml || ""), JSON.stringify(resultBadge));

  const failedResult = result.failedResult || {};
  assert("failed file result display is safe and non-executable", failedResult.text.includes("Upload failed") && failedResult.text.includes("<img src=x onerror=alert(2)>") && /&lt;img src=x onerror=alert\(2\)&gt;/.test(failedResult.html || "") && !/<img src=x/i.test(failedResult.html || ""), JSON.stringify(failedResult));

  const suppressedAction = result.suppressedAction || {};
  assert("file upload tool fallback is product-friendly and not technical", /Anhang|attachment/i.test(suppressedAction.text || "") && !/file_info|Fuehre|FÃ¼hre/i.test(suppressedAction.text || "") && Number(suppressedAction.actionControls || 0) === 0, JSON.stringify(suppressedAction));

  const visionPending = result.visionPending || {};
  assert("image upload without provider uses honest vision-ready fallback", /Vision|Bildanalyse|image analysis/i.test(visionPending.bodyText || "") && /screen <img src=x onerror=alert\(3\)>\.png/.test(visionPending.bodyText || "") && /Vision bereit|Vision ready/i.test(visionPending.badgeText || ""), JSON.stringify(visionPending));
  assert("vision fallback image name remains escaped", /&lt;img src=x onerror=alert\(3\)&gt;/.test(visionPending.bodyHtml || "") && !/<img src=x/i.test(visionPending.bodyHtml || ""), JSON.stringify(visionPending));

  const historyState = result.historyState || {};
  assert("attachment-like history does not create live controls", Number(historyState.actionControls || 0) === 0 && historyState.text.includes("Attachment history") && /&lt;button/i.test(historyState.html || ""), JSON.stringify(historyState));
  assert("unsafe file/history content does not create executable nodes", Number(result.unsafeNodes || 0) === 0, JSON.stringify(result.unsafeNodes));
  assert("display helpers are available without upload execution", result.displayHelpers?.extension === "MD" && /4/.test(result.displayHelpers?.badge || "") && /Vision bereit|Vision ready/i.test(result.displayHelpers?.visionBadge || ""), JSON.stringify(result.displayHelpers || {}));
  assert("render-only file display smoke did not perform renderer fetch calls", Array.isArray(result.fetchCalls) && result.fetchCalls.length === 0, JSON.stringify(result.fetchCalls || []));
  const forbiddenBridgeMethods = new Set([
    "chatFile",
    "execute",
    "executeWithConfirmation",
    "prepareCompanionExecute",
    "personalOsCreateDraft",
    "personalOsApplyDraft",
    "setAiModel",
    "elevenlabsSetKey",
    "deepgramSetKey",
    "cartesiaSetKey",
  ]);
  assert("render-only file display smoke did not call upload/tool/provider/OS bridge methods", bridgeAudits.every((entry) => !forbiddenBridgeMethods.has(entry?.method)) && presenceRequests.length === 0, JSON.stringify({ bridgeAudits, presenceRequests }));
  assert("renderer stayed free of fatal errors", rendererErrors.length === 0, JSON.stringify(rendererErrors));

  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  await win.close();
  app.exit(failed > 0 ? 1 : 0);
}

main().catch(async (error) => {
  console.error(error);
  app.exit(1);
});
