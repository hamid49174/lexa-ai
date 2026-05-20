/**
 * Electron conversation history failure-path smoke.
 * Uses the real renderer scripts with isolated userData and mock bridge conversations.
 * Run with: node tests\electron_history_failure_smoke.js
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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-history-failure-smoke-"));
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
ipcMain.handle("local-auth-token", () => "history-failure-smoke-token");
ipcMain.handle("bridge:audit", () => ({ ok: true }));
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "history_failure_smoke_denied" }));
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
        && typeof renderConversationList === "function"
        && typeof switchConversation === "function"
        && typeof loadChatHistory === "function"
        && typeof renderPersistedConversationMessages === "function"
      );

      clearRenderedChatMessages();
      try {
        localStorage.removeItem("lexa-chat-history");
        localStorage.removeItem("lexa-chat-draft");
        localStorage.removeItem("lexa-active-conversation");
      } catch (_) {}
      LexaState.set("backendOnline", true);
      LexaState.set("isLoading", false);
      LexaState.set("currentConversationId", null);
      LexaState.set("conversationsList", []);
      LexaState.set("conversationAttentionOnly", false);
      LexaState.set("ttsEnabled", false);

      let malformedListError = "";
      try {
        LexaState.set("conversationsList", [
          { id: "missing-title", message_count: null, last_message: null },
          { id: "unsafe-title", title: "Unsafe <img src=x onerror=alert(1)>", last_message: "Preview <script>alert(1)</script>", message_count: undefined },
        ]);
        renderConversationList();
      } catch (error) {
        malformedListError = String(error && (error.stack || error.message) || error);
      }

      const missingTitleRow = document.querySelector('#conversation-list .conv-item[data-conv-id="missing-title"]');
      const unsafeTitleRow = document.querySelector('#conversation-list .conv-item[data-conv-id="unsafe-title"]');
      const malformedList = {
        error: malformedListError,
        rowCount: document.querySelectorAll("#conversation-list .conv-item").length,
        missingTitleText: missingTitleRow?.querySelector(".conv-title")?.textContent || "",
        missingTitleHtml: missingTitleRow?.querySelector(".conv-title")?.innerHTML || "",
        unsafeTitleText: unsafeTitleRow?.querySelector(".conv-title")?.textContent || "",
        unsafeTitleHtml: unsafeTitleRow?.querySelector(".conv-title")?.innerHTML || "",
        unsafePreviewText: unsafeTitleRow?.querySelector(".conv-preview")?.textContent || "",
        unsafePreviewHtml: unsafeTitleRow?.querySelector(".conv-preview")?.innerHTML || "",
      };

      clearRenderedChatMessages();
      let malformedMessagesError = "";
      try {
        renderPersistedConversationMessages([
          null,
          {},
          { role: "assistant", content: "Unsafe <img src=x onerror=alert(2)>" },
          { role: "assistant", content: "Action-like history", action: { action: "personal_os_write", params: { path: "<script>bad</script>" } }, requires_confirmation: true },
          { type: "user", text: "Valid user text" },
        ], "malformed-history");
      } catch (error) {
        malformedMessagesError = String(error && (error.stack || error.message) || error);
      }
      const malformedMessages = Array.from(document.querySelectorAll("#chat-messages .message")).map((message) => ({
        className: message.className,
        text: message.querySelector(".msg-text")?.textContent || "",
        html: message.querySelector(".msg-text")?.innerHTML || "",
        unsafeNodes: message.querySelectorAll(".msg-text img,.msg-text script").length,
        confirmButtons: message.querySelectorAll(".confirm-btn").length,
        actionCards: message.querySelectorAll(".msg-action").length,
      }));

      const previous = await window.lexa.conversationCreate("Previous stable conversation");
      await window.lexa.conversationUpdate(previous.id, {
        messages: [
          { role: "user", content: "Previous user" },
          { role: "assistant", content: "Previous assistant **ok**" },
        ],
      });
      LexaState.set("currentConversationId", previous.id);
      localStorage.setItem("lexa-active-conversation", previous.id);
      LexaState.set("conversationsList", (await window.lexa.conversations()).conversations || []);
      clearRenderedChatMessages();
      renderPersistedConversationMessages((await window.lexa.conversationGet(previous.id)).messages, previous.id);
      renderConversationList();
      const beforeMissingSwitchText = document.querySelector("#chat-messages")?.textContent || "";
      const missingSwitchResult = await switchConversation("missing-conversation-id", false);
      const afterMissingSwitchText = document.querySelector("#chat-messages")?.textContent || "";
      const failedLoad = {
        switchResult: missingSwitchResult === false,
        current: String(LexaState.get("currentConversationId") || ""),
        stored: localStorage.getItem("lexa-active-conversation") || "",
        transcriptPreserved: beforeMissingSwitchText === afterMissingSwitchText && /Previous assistant ok/.test(afterMissingSwitchText),
        activeRow: Boolean(document.querySelector('#conversation-list .conv-item[data-conv-id="' + previous.id + '"].active')),
      };

      const oldBackendOnline = LexaState.get("backendOnline");
      const oldCurrent = LexaState.get("currentConversationId");
      clearRenderedChatMessages();
      LexaState.set("backendOnline", false);
      LexaState.set("currentConversationId", null);
      localStorage.setItem("lexa-chat-history", "{not valid json");
      let invalidLocalStorageError = "";
      try {
        await loadChatHistory();
      } catch (error) {
        invalidLocalStorageError = String(error && (error.stack || error.message) || error);
      }
      const invalidLocalStorage = {
        error: invalidLocalStorageError,
        messageCount: document.querySelectorAll("#chat-messages .message").length,
      };
      LexaState.set("backendOnline", oldBackendOnline);
      LexaState.set("currentConversationId", oldCurrent);

      LexaState.set("conversationsList", []);
      renderConversationList();
      const emptyRecovery = {
        rowCount: document.querySelectorAll("#conversation-list .conv-item").length,
        emptyText: document.querySelector("#conversation-list .conv-empty")?.textContent || "",
        emptyHtml: document.querySelector("#conversation-list .conv-empty")?.innerHTML || "",
      };

      return {
        previousId: String(previous.id),
        malformedList,
        malformedMessagesError,
        malformedMessages,
        failedLoad,
        invalidLocalStorage,
        emptyRecovery,
      };
    })();
  `);

  console.log("\nHistory malformed sidebar data:");
  assert("malformed conversation rows do not break renderer", !result.malformedList?.error && result.malformedList?.rowCount >= 2, JSON.stringify(result.malformedList));
  assert("missing title falls back to stable text", String(result.malformedList?.missingTitleText || "").trim().length > 0 && !/<img|<script/i.test(result.malformedList?.missingTitleHtml || ""), JSON.stringify(result.malformedList));
  assert("unsafe title and preview stay text-only", /Unsafe <img/.test(result.malformedList?.unsafeTitleText || "") && /Preview <script>/.test(result.malformedList?.unsafePreviewText || "") && !/<img|<script/i.test(result.malformedList?.unsafeTitleHtml || "") && !/<img|<script/i.test(result.malformedList?.unsafePreviewHtml || ""), JSON.stringify(result.malformedList));

  console.log("\nHistory malformed message data:");
  const malformedMessages = Array.isArray(result.malformedMessages) ? result.malformedMessages : [];
  assert("malformed persisted messages do not break renderer", !result.malformedMessagesError && malformedMessages.length === 3, JSON.stringify({ error: result.malformedMessagesError, malformedMessages }));
  assert("malformed message HTML is contained", malformedMessages.every((message) => Number(message.unsafeNodes || 0) === 0 && !/<img|<script/i.test(message.html || "")), JSON.stringify(malformedMessages));
  assert("action-like malformed history does not create live controls", malformedMessages.every((message) => Number(message.confirmButtons || 0) === 0 && Number(message.actionCards || 0) === 0), JSON.stringify(malformedMessages));

  console.log("\nHistory failure recovery:");
  assert("missing conversation load preserves active conversation", result.failedLoad?.switchResult === true && result.failedLoad?.current === result.previousId && result.failedLoad?.stored === result.previousId && result.failedLoad?.activeRow === true, JSON.stringify(result.failedLoad));
  assert("missing conversation load preserves transcript", result.failedLoad?.transcriptPreserved === true, JSON.stringify(result.failedLoad));
  assert("invalid local history recovers without rendering garbage", !result.invalidLocalStorage?.error && result.invalidLocalStorage?.messageCount === 0, JSON.stringify(result.invalidLocalStorage));
  assert("empty history recovers to stable empty state", result.emptyRecovery?.rowCount === 0 && String(result.emptyRecovery?.emptyText || "").trim().length > 0 && !/<img|<script/i.test(result.emptyRecovery?.emptyHtml || ""), JSON.stringify(result.emptyRecovery));
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
