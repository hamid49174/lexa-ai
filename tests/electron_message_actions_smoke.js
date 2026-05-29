/**
 * Electron message action controller smoke.
 * Uses the real renderer with isolated userData and mocks action side effects.
 * Run with: node tests\electron_message_actions_smoke.js
 */

const path = require("path");
require("./electron_smoke_safe_io");

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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-message-actions-"));
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
ipcMain.handle("local-auth-token", () => "message-actions-smoke-token");
ipcMain.handle("bridge:audit", () => ({ ok: true }));
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "message_actions_smoke_denied" }));
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

      await waitFor(() =>
        window.lexa
        && typeof addMessage === "function"
        && typeof createMessageActionOverflowMenu === "function"
        && typeof clearRenderedChatMessages === "function"
        && typeof clearChatVolatileState === "function"
        && typeof getChatDraft === "function"
        && document.getElementById("chat-input")
      );

      clearRenderedChatMessages();
      clearChatVolatileState();
      if (typeof LexaState !== "undefined") {
        LexaState.set("backendOnline", true);
        LexaState.set("isLoading", false);
        LexaState.set("currentConversationId", "message-actions-smoke");
        LexaState.set("conversationsList", []);
        LexaState.set("ttsEnabled", false);
      }

      const fetchCalls = [];
      const sendCalls = [];
      const regenerateCalls = [];
      const clipboardWrites = [];
      const anchorClicks = [];
      const objectUrls = [];
      const revokedUrls = [];

      const originalFetch = window.fetch;
      const originalSendAgentMessage = window.sendAgentMessage;
      const originalRegenerateMessage = window.regenerateMessage;
      const originalCreateObjectURL = URL.createObjectURL;
      const originalRevokeObjectURL = URL.revokeObjectURL;
      const originalAnchorClick = HTMLAnchorElement.prototype.click;

      window.fetch = async (url, options = {}) => {
        fetchCalls.push({ url: String(url || ""), body: typeof options.body === "string" ? options.body : "" });
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      };
      sendAgentMessage = async (prompt, options = {}) => {
        sendCalls.push({ prompt: String(prompt || ""), displayText: String(options.displayText || "") });
        return true;
      };
      window.sendAgentMessage = sendAgentMessage;
      regenerateMessage = async (prompt) => {
        regenerateCalls.push(String(prompt || ""));
        return true;
      };
      window.regenerateMessage = regenerateMessage;
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: {
          writeText: async (text) => {
            clipboardWrites.push(String(text || ""));
          },
        },
      });
      URL.createObjectURL = (blob) => {
        objectUrls.push({ type: blob?.type || "", size: Number(blob?.size || 0) });
        return "blob:lexa-message-action-smoke";
      };
      URL.revokeObjectURL = (url) => {
        revokedUrls.push(String(url || ""));
      };
      HTMLAnchorElement.prototype.click = function click() {
        anchorClicks.push({ href: this.href || "", download: this.download || "" });
      };

      addMessage("Original user prompt with <script>alert(1)</script>", "user");
      addMessage("Assistant **answer** with <img src=x onerror=alert(1)>", "system");
      const assistant = Array.from(document.querySelectorAll(".system-message")).at(-1);
      const msgText = assistant?.querySelector(".msg-text") || null;

      const initial = {
        hasAssistant: Boolean(assistant),
        copy: Boolean(assistant?.querySelector(".msg-copy-btn")),
        continueBtn: Boolean(assistant?.querySelector(".msg-continue-btn")),
        verify: Boolean(assistant?.querySelector(".msg-verify-btn")),
        exportBtn: Boolean(assistant?.querySelector(".msg-export-btn")),
        more: Boolean(assistant?.querySelector(".msg-more-btn")),
        memory: Boolean(assistant?.querySelector(".msg-thumbs-btn")),
        workspace: Boolean(assistant?.querySelector(".msg-workspace-btn")),
        regen: Boolean(assistant?.querySelector(".msg-regen-btn")),
        unsafeNodes: (msgText?.querySelectorAll("script,img[onerror]").length || 0),
      };

      assistant.querySelector(".msg-copy-btn")?.click();
      await waitFor(() => clipboardWrites.length >= 1);

      assistant.querySelector(".msg-export-btn")?.click();
      await waitFor(() => anchorClicks.length >= 1);

      assistant.querySelector(".msg-continue-btn")?.click();
      await waitFor(() => document.getElementById("chat-input").value.includes("Assistant **answer**"));
      const continueDraft = {
        input: document.getElementById("chat-input").value,
        stored: getChatDraft() || "",
        sendCalls: sendCalls.length,
        fetchCalls: fetchCalls.length,
      };

      assistant.querySelector(".msg-verify-btn")?.click();
      await waitFor(() => sendCalls.length >= 1);
      const verifyCall = sendCalls.at(-1) || {};

      assistant.querySelector(".msg-workspace-btn")?.click();
      await waitFor(() => sendCalls.length >= 2);
      const workspaceCall = sendCalls.at(-1) || {};

      assistant.querySelector(".msg-regen-btn")?.click();
      await waitFor(() => regenerateCalls.length >= 1);

      window.fetch = originalFetch;
      window.sendAgentMessage = originalSendAgentMessage;
      window.regenerateMessage = originalRegenerateMessage;
      URL.createObjectURL = originalCreateObjectURL;
      URL.revokeObjectURL = originalRevokeObjectURL;
      HTMLAnchorElement.prototype.click = originalAnchorClick;

      return {
        initial,
        copy: { writes: clipboardWrites },
        exportResult: { anchorClicks, objectUrls, revokedUrls },
        continueDraft,
        verifyCall,
        workspaceCall,
        regenerateCalls,
        fetchCalls,
        sendCalls,
      };
    })();
  `);

  console.log("\nMessage action render surface:");
  assert("assistant message action controls render", result.initial?.hasAssistant && result.initial.copy && result.initial.continueBtn && result.initial.verify && result.initial.exportBtn && result.initial.more && result.initial.memory && result.initial.workspace && result.initial.regen, JSON.stringify(result.initial));
  assert("unsafe assistant action source stays non-executable", Number(result.initial?.unsafeNodes || 0) === 0, JSON.stringify(result.initial));

  console.log("\nMessage action side-effect mocks:");
  assert("copy action writes raw persisted answer to mocked clipboard", Array.isArray(result.copy?.writes) && /Assistant \*\*answer\*\*/.test(result.copy.writes[0] || "") && /onerror=alert/.test(result.copy.writes[0] || ""), JSON.stringify(result.copy));
  assert("export action creates markdown blob and download name without real navigation", result.exportResult?.anchorClicks?.length === 1 && /\.md$/.test(result.exportResult.anchorClicks[0].download || "") && result.exportResult?.objectUrls?.[0]?.type === "text/markdown;charset=utf-8", JSON.stringify(result.exportResult));
  assert("continue action places prompt in composer without auto-send", /Assistant \*\*answer\*\*/.test(result.continueDraft?.input || "") && result.continueDraft.input === result.continueDraft.stored && result.continueDraft.sendCalls === 0, JSON.stringify(result.continueDraft));
  assert("verify action calls only mocked agent handoff", /Assistant \*\*answer\*\*/.test(result.verifyCall?.prompt || "") && /verify|research|claims|quellen|source/i.test(result.verifyCall?.prompt || ""), JSON.stringify(result.verifyCall));
  assert("workspace action calls only mocked agent handoff", /workspace/i.test(result.workspaceCall?.prompt || "") && /Assistant \*\*answer\*\*/.test(result.workspaceCall?.prompt || ""), JSON.stringify(result.workspaceCall));
  assert("regenerate action uses previous user prompt through mocked regenerate", Array.isArray(result.regenerateCalls) && /Original user prompt/.test(result.regenerateCalls[0] || ""), JSON.stringify(result.regenerateCalls));
  assert("message actions do not call renderer fetch in this mocked path", Array.isArray(result.fetchCalls) && result.fetchCalls.length === 0, JSON.stringify(result.fetchCalls));
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
