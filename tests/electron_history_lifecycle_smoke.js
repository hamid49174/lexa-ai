/**
 * Electron conversation history lifecycle smoke.
 * Uses the real renderer scripts with isolated userData and mock bridge conversations.
 * Run with: node tests\electron_history_lifecycle_smoke.js
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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-history-lifecycle-smoke-"));
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
ipcMain.handle("local-auth-token", () => "history-lifecycle-smoke-token");
ipcMain.handle("bridge:audit", () => ({ ok: true }));
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "history_lifecycle_smoke_denied" }));
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
        && typeof renderConversationList === "function"
        && typeof switchConversation === "function"
        && typeof deleteConversation === "function"
        && typeof clearRenderedChatMessages === "function"
        && typeof clearChatVolatileState === "function"
        && typeof chatGetActiveConversationId === "function"
      );

      clearRenderedChatMessages();
      clearChatVolatileState();
      LexaState.set("backendOnline", true);
      LexaState.set("isLoading", false);
      LexaState.set("currentConversationId", null);
      LexaState.set("conversationsList", []);
      LexaState.set("conversationAttentionOnly", false);
      LexaState.set("ttsEnabled", false);
      renderConversationList();
      const initialEmpty = {
        text: document.querySelector("#conversation-list .conv-empty")?.textContent || "",
        html: document.querySelector("#conversation-list .conv-empty")?.innerHTML || "",
        rowCount: document.querySelectorAll("#conversation-list .conv-item").length,
      };

      const first = await window.lexa.conversationCreate("Unsafe <img src=x onerror=alert(1)> Conversation Title");
      const second = await window.lexa.conversationCreate("Second Safe Conversation");
      const firstMessages = [
        { role: "user", content: "First user <script>alert(1)</script>" },
        { role: "assistant", content: "First assistant **response**" },
        {
          role: "assistant",
          content: "First unsafe preview <img src=x onerror=alert(1)>",
          action: { action: "personal_os_write", params: { path: "<script>bad</script>" } },
          requires_confirmation: true,
        },
      ];
      const secondMessages = [
        { role: "user", content: "Second user question" },
        { role: "assistant", content: "Second assistant **answer** with <script>alert(2)</script>" },
      ];
      await window.lexa.conversationUpdate(first.id, {
        title: "Unsafe <img src=x onerror=alert(1)> Conversation Title",
        messages: firstMessages,
      });
      await window.lexa.conversationUpdate(second.id, {
        title: "Second Safe Conversation",
        messages: secondMessages,
      });

      const conversations = await window.lexa.conversations();
      LexaState.set("conversationsList", conversations.conversations || []);
      LexaState.set("currentConversationId", null);
      renderConversationList();

      const firstRowBeforeSwitch = document.querySelector('#conversation-list .conv-item[data-conv-id="' + first.id + '"]');
      const listFlow = {
        rowCount: document.querySelectorAll("#conversation-list .conv-item").length,
        firstTitleText: firstRowBeforeSwitch?.querySelector(".conv-title")?.textContent || "",
        firstTitleHtml: firstRowBeforeSwitch?.querySelector(".conv-title")?.innerHTML || "",
        firstRowTitle: firstRowBeforeSwitch?.title || "",
        firstPreviewText: firstRowBeforeSwitch?.querySelector(".conv-preview")?.textContent || "",
        firstPreviewHtml: firstRowBeforeSwitch?.querySelector(".conv-preview")?.innerHTML || "",
        firstAriaCurrent: firstRowBeforeSwitch?.getAttribute("aria-current") || "",
      };

      const firstSwitch = await switchConversation(first.id, false);
      const firstMessagesRendered = Array.from(document.querySelectorAll("#chat-messages .message")).map((message) => ({
        className: message.className,
        text: message.querySelector(".msg-text")?.textContent || "",
        html: message.querySelector(".msg-text")?.innerHTML || "",
        hasBold: Boolean(message.querySelector(".msg-text strong")),
        confirmButtons: message.querySelectorAll(".confirm-btn").length,
        actionCards: message.querySelectorAll(".msg-action").length,
        unsafeNodes: message.querySelectorAll(".msg-text img,.msg-text script").length,
      }));
      const firstActiveRow = document.querySelector('#conversation-list .conv-item[data-conv-id="' + first.id + '"]');
      const firstSelected = {
        switchResult: firstSwitch === true,
        current: String(LexaState.get("currentConversationId") || ""),
        stored: chatGetActiveConversationId() || "",
        activeClass: Boolean(firstActiveRow?.classList.contains("active")),
        ariaCurrent: firstActiveRow?.getAttribute("aria-current") || "",
      };

      const secondSwitch = await switchConversation(second.id, false);
      const secondMessagesRendered = Array.from(document.querySelectorAll("#chat-messages .message")).map((message) => ({
        className: message.className,
        text: message.querySelector(".msg-text")?.textContent || "",
        html: message.querySelector(".msg-text")?.innerHTML || "",
        hasBold: Boolean(message.querySelector(".msg-text strong")),
        unsafeNodes: message.querySelectorAll(".msg-text img,.msg-text script").length,
      }));
      const firstRowAfterSecond = document.querySelector('#conversation-list .conv-item[data-conv-id="' + first.id + '"]');
      const secondActiveRow = document.querySelector('#conversation-list .conv-item[data-conv-id="' + second.id + '"]');
      const secondSelected = {
        switchResult: secondSwitch === true,
        current: String(LexaState.get("currentConversationId") || ""),
        stored: chatGetActiveConversationId() || "",
        firstActiveClass: Boolean(firstRowAfterSecond?.classList.contains("active")),
        secondActiveClass: Boolean(secondActiveRow?.classList.contains("active")),
        secondAriaCurrent: secondActiveRow?.getAttribute("aria-current") || "",
      };

      const deleteButton = firstRowAfterSecond?.querySelector(".conv-delete-btn") || null;
      if (deleteButton) await deleteConversation(first.id, deleteButton);
      const afterDelete = {
        firstStillVisible: Boolean(document.querySelector('#conversation-list .conv-item[data-conv-id="' + first.id + '"]')),
        secondStillVisible: Boolean(document.querySelector('#conversation-list .conv-item[data-conv-id="' + second.id + '"]')),
        rowIds: Array.from(document.querySelectorAll("#conversation-list .conv-item")).map((row) => row.dataset?.convId || ""),
        current: String(LexaState.get("currentConversationId") || ""),
        stored: chatGetActiveConversationId() || "",
        rowCount: document.querySelectorAll("#conversation-list .conv-item").length,
        emptyText: document.querySelector("#conversation-list .conv-empty")?.textContent || "",
      };

      return {
        ids: { first: String(first.id), second: String(second.id) },
        initialEmpty,
        listFlow,
        firstSelected,
        firstMessagesRendered,
        secondSelected,
        secondMessagesRendered,
        afterDelete,
      };
    })();
  `);

  console.log("\nHistory initial and sidebar state:");
  assert("initial empty history state renders", result.initialEmpty?.rowCount === 0 && String(result.initialEmpty?.text || "").trim().length > 0 && !/<script|<img/i.test(result.initialEmpty?.html || ""), JSON.stringify(result.initialEmpty));
  assert("mocked conversations appear in sidebar", result.listFlow?.rowCount >= 2, JSON.stringify(result.listFlow));
  assert("conversation title renders as safe text", /Unsafe <img/.test(result.listFlow?.firstTitleText || "") && !/<img/i.test(result.listFlow?.firstTitleHtml || ""), JSON.stringify(result.listFlow));
  assert("conversation preview renders as safe text", /First unsafe preview <img/.test(result.listFlow?.firstPreviewText || "") && !/<img/i.test(result.listFlow?.firstPreviewHtml || ""), JSON.stringify(result.listFlow));
  assert("inactive conversations are not marked current", result.listFlow?.firstAriaCurrent === "false", JSON.stringify(result.listFlow));

  const firstMessages = Array.isArray(result.firstMessagesRendered) ? result.firstMessagesRendered : [];
  console.log("\nHistory switch to first conversation:");
  assert("selecting first conversation updates active state", result.firstSelected?.switchResult === true && result.firstSelected?.current === result.ids?.first && result.firstSelected?.stored === result.ids?.first && result.firstSelected?.activeClass === true && result.firstSelected?.ariaCurrent === "page", JSON.stringify(result.firstSelected));
  assert("first conversation hydrates messages in order", firstMessages.length === 3 && /user-message/.test(firstMessages[0]?.className || "") && /system-message/.test(firstMessages[1]?.className || "") && /system-message/.test(firstMessages[2]?.className || ""), JSON.stringify(firstMessages));
  assert("first conversation markdown renders and unsafe message HTML is contained", firstMessages[1]?.hasBold === true && firstMessages.every((message) => Number(message.unsafeNodes || 0) === 0 && !/<script/i.test(message.html || "") && !/<img/i.test(message.html || "")), JSON.stringify(firstMessages));
  assert("history load does not turn action-like messages into live tool controls", firstMessages.every((message) => Number(message.confirmButtons || 0) === 0 && Number(message.actionCards || 0) === 0), JSON.stringify(firstMessages));

  const secondMessages = Array.isArray(result.secondMessagesRendered) ? result.secondMessagesRendered : [];
  console.log("\nHistory switch to second conversation:");
  assert("switching to second conversation updates selected state", result.secondSelected?.switchResult === true && result.secondSelected?.current === result.ids?.second && result.secondSelected?.stored === result.ids?.second && result.secondSelected?.secondActiveClass === true && result.secondSelected?.firstActiveClass === false && result.secondSelected?.secondAriaCurrent === "page", JSON.stringify(result.secondSelected));
  assert("second conversation replaces rendered transcript", secondMessages.length === 2 && /Second user question/.test(secondMessages[0]?.text || "") && /Second assistant answer/.test(secondMessages[1]?.text || "") && secondMessages[1]?.hasBold === true, JSON.stringify(secondMessages));
  assert("second conversation unsafe HTML is contained", secondMessages.every((message) => Number(message.unsafeNodes || 0) === 0 && !/<script/i.test(message.html || "")), JSON.stringify(secondMessages));

  console.log("\nHistory delete mock conversation:");
  assert("mock delete removes inactive conversation from sidebar", result.afterDelete?.firstStillVisible === false && result.afterDelete?.secondStillVisible === true && !String(result.afterDelete?.rowIds || "").includes(result.ids?.first || ""), JSON.stringify(result.afterDelete));
  assert("mock delete preserves active second conversation", result.afterDelete?.current === result.ids?.second && result.afterDelete?.stored === result.ids?.second, JSON.stringify(result.afterDelete));
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
