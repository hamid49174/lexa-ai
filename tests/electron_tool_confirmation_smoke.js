/**
 * Electron tool confirmation and history render smoke.
 * Uses the real renderer scripts with isolated userData and mocked chat stream.
 * Run with: node tests\electron_tool_confirmation_smoke.js
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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-tool-confirmation-smoke-"));
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
ipcMain.handle("local-auth-token", () => "tool-confirmation-smoke-token");
ipcMain.handle("bridge:audit", () => ({ ok: true }));
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "tool_confirmation_smoke_denied" }));
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

      await waitFor(() => window.lexa && typeof sendMessage === "function" && typeof addMessage === "function" && typeof renderPersistedConversationMessages === "function" && typeof clearChatVolatileState === "function");
      if (typeof clearRenderedChatMessages === "function") clearRenderedChatMessages();
      clearChatVolatileState();
      if (typeof LexaState !== "undefined") {
        LexaState.set("backendOnline", true);
        LexaState.set("isLoading", false);
        LexaState.set("currentConversationId", null);
        LexaState.set("conversationsList", []);
        LexaState.set("conversationAttentionOnly", false);
        LexaState.set("ttsEnabled", false);
      }

      const fetchCalls = [];
      const originalFetch = window.fetch;
      const toolAction = {
        action: "personal_os_write",
        params: {
          path: "<img src=x onerror=alert(1)>",
          body: "Draft <script>alert(1)</script>",
        },
      };

      window.fetch = async (url, options = {}) => {
        const urlText = String(url || "");
        const bodyText = typeof options.body === "string" ? options.body : "";
        fetchCalls.push({ url: urlText, body: bodyText });
        if (urlText.endsWith("/chat/stream")) {
          const encoder = new TextEncoder();
          const chunks = [
            { c: "I need confirmation before touching anything." },
            { done: true, action: toolAction, rc: true },
          ];
          return new Response(new ReadableStream({
            start(controller) {
              chunks.forEach((chunk) => controller.enqueue(encoder.encode("data: " + JSON.stringify(chunk) + "\\n\\n")));
              controller.close();
            },
          }), { status: 200, headers: { "content-type": "text/event-stream" } });
        }
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      };

      const input = document.getElementById("chat-input");
      const send = document.getElementById("send-btn");
      input.value = "Request a protected OS write";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      send.click();

      const streamWait = await waitFor(() =>
        !LexaState.get("isLoading")
        && document.querySelectorAll(".system-message:not(.typing-message)").length >= 1
        && !document.querySelector(".streaming-text")
      );
      const streamedMessage = Array.from(document.querySelectorAll(".system-message")).at(-1);
      const streamedAction = streamedMessage?.querySelector(".msg-action") || null;
      const streamedCmd = streamedAction?.querySelector(".action-cmd") || null;
      const streamedFlow = {
        waitOk: streamWait.ok,
        assistantText: streamedMessage?.querySelector(".msg-text")?.textContent || "",
        confirmationText: streamedAction?.querySelector(".action-label")?.textContent || "",
        actionText: streamedCmd?.textContent || "",
        actionHtml: streamedCmd?.innerHTML || "",
        detailText: streamedMessage?.querySelector(".action-detail")?.textContent || "",
        detailHtml: streamedMessage?.querySelector(".action-detail")?.innerHTML || "",
        confirmText: streamedMessage?.querySelector(".confirm-btn")?.textContent || "",
        denyText: streamedMessage?.querySelector(".deny-btn")?.textContent || "",
        confirmButtons: streamedMessage?.querySelectorAll(".confirm-btn").length || 0,
        denyButtons: streamedMessage?.querySelectorAll(".deny-btn").length || 0,
        unsafeNodes: streamedMessage?.querySelectorAll(".msg-action img,.msg-action script").length || 0,
        confirmClearCalls: fetchCalls.filter((call) => call.url.endsWith("/chat/confirm-clear")).length,
        streamRequests: fetchCalls.filter((call) => call.url.endsWith("/chat/stream")).length,
      };

      if (typeof clearRenderedChatMessages === "function") clearRenderedChatMessages();
      addMessage("Direct render-only confirmation", "system", toolAction, true, true);
      const directMessage = Array.from(document.querySelectorAll(".system-message")).at(-1);
      const directCmd = directMessage?.querySelector(".action-cmd") || null;
      const directFlow = {
        confirmationText: directMessage?.querySelector(".action-label")?.textContent || "",
        actionText: directCmd?.textContent || "",
        actionHtml: directCmd?.innerHTML || "",
        detailText: directMessage?.querySelector(".action-detail")?.textContent || "",
        detailHtml: directMessage?.querySelector(".action-detail")?.innerHTML || "",
        confirmButtons: directMessage?.querySelectorAll(".confirm-btn").length || 0,
        denyButtons: directMessage?.querySelectorAll(".deny-btn").length || 0,
        unsafeNodes: directMessage?.querySelectorAll(".msg-action img,.msg-action script").length || 0,
      };

      if (typeof clearRenderedChatMessages === "function") clearRenderedChatMessages();
      renderPersistedConversationMessages([
        { role: "user", content: "History user first" },
        { role: "assistant", content: "History assistant **second**" },
        { role: "assistant", content: "History action-like payload", action: toolAction, requires_confirmation: true },
      ], "history-smoke-1");
      const renderedMessages = Array.from(document.querySelectorAll("#chat-messages .message")).map((message) => ({
        className: message.className,
        text: message.querySelector(".msg-text")?.textContent || "",
        hasBold: Boolean(message.querySelector(".msg-text strong")),
        confirmButtons: message.querySelectorAll(".confirm-btn").length,
        actionCards: message.querySelectorAll(".msg-action").length,
      }));

      LexaState.set("currentConversationId", "history-smoke-1");
      LexaState.set("conversationsList", [
        { id: "history-smoke-1", title: "Saved History Conversation", message_count: 3, last_message: "Last <script> preview" },
        { id: "history-smoke-2", title: "Other Conversation", message_count: 1, last_message: "Other" },
      ]);
      if (typeof renderConversationList === "function") renderConversationList();
      const activeRow = document.querySelector('#conversation-list .conv-item[data-conv-id="history-smoke-1"]');
      const selectedFlow = {
        activeExists: Boolean(activeRow),
        activeClass: Boolean(activeRow?.classList.contains("active")),
        ariaCurrent: activeRow?.getAttribute("aria-current") || "",
        titleText: activeRow?.querySelector(".conv-title")?.textContent || "",
        rowTitle: activeRow?.title || "",
        previewText: activeRow?.querySelector(".conv-preview")?.textContent || "",
        previewHtml: activeRow?.querySelector(".conv-preview")?.innerHTML || "",
      };

      LexaState.set("conversationsList", []);
      LexaState.set("currentConversationId", null);
      if (typeof renderConversationList === "function") renderConversationList();
      const emptyFlow = {
        emptyText: document.querySelector("#conversation-list .conv-empty")?.textContent || "",
      };

      window.fetch = originalFetch;
      return { streamedFlow, directFlow, historyFlow: { renderedMessages, selectedFlow, emptyFlow } };
    })();
  `);

  const streamed = result.streamedFlow || {};
  console.log("\nTool confirmation streamed response:");
  assert("mocked stream completes without local-action UI", streamed.waitOk === true && streamed.streamRequests === 1, JSON.stringify(streamed));
  assert("blocked local-action language is not shown in normal chat", !streamed.confirmationText && !streamed.actionText, JSON.stringify(streamed));
  assert("unsafe tool params are not rendered in normal chat", Number(streamed.unsafeNodes || 0) === 0 && !/<img|<script|onerror=alert/i.test(`${streamed.actionHtml || ""} ${streamed.actionText || ""} ${streamed.detailHtml || ""}`), JSON.stringify(streamed));
  assert("chat local-action block does not render confirm or deny controls", streamed.confirmButtons === 0 && streamed.denyButtons === 0 && streamed.confirmText.length === 0 && streamed.denyText.length === 0, JSON.stringify(streamed));
  assert("confirmation smoke does not execute or clear pending tools", streamed.confirmClearCalls === 0, JSON.stringify(streamed));

  const direct = result.directFlow || {};
  console.log("\nTool confirmation direct render:");
  assert("direct addMessage suppresses local-action UI", !direct.confirmationText && !direct.actionText && direct.confirmButtons === 0 && direct.denyButtons === 0, JSON.stringify(direct));
  assert("direct local-action params stay invisible", Number(direct.unsafeNodes || 0) === 0 && !/<img|<script|onerror=alert/i.test(`${direct.actionHtml || ""} ${direct.actionText || ""} ${direct.detailHtml || ""}`), JSON.stringify(direct));

  const history = result.historyFlow || {};
  const rendered = Array.isArray(history.renderedMessages) ? history.renderedMessages : [];
  const selected = history.selectedFlow || {};
  const empty = history.emptyFlow || {};
  console.log("\nConversation history render smoke:");
  assert("persisted messages restore in user-assistant order", rendered.length === 3 && /user-message/.test(rendered[0]?.className || "") && /system-message/.test(rendered[1]?.className || "") && /system-message/.test(rendered[2]?.className || ""), JSON.stringify(rendered));
  assert("persisted assistant markdown remains formatted", rendered[1]?.hasBold === true && /History assistant second/.test(rendered[1]?.text || ""), JSON.stringify(rendered[1]));
  assert("persisted action-like history does not render live confirmation controls", rendered.every((message) => Number(message.confirmButtons || 0) === 0 && Number(message.actionCards || 0) === 0), JSON.stringify(rendered));
  assert("conversation list marks selected conversation", selected.activeExists === true && selected.activeClass === true && selected.ariaCurrent === "page", JSON.stringify(selected));
  assert("conversation title and preview render as text", selected.titleText === "Saved History Conversation" && selected.rowTitle === "Saved History Conversation" && /Last <script> preview/.test(selected.previewText || "") && !/<script/i.test(selected.previewHtml || ""), JSON.stringify(selected));
  assert("empty history state renders", String(empty.emptyText || "").trim().length > 0, JSON.stringify(empty));
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
