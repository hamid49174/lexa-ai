/**
 * Electron core chat flow integration smoke.
 * Uses the real renderer scripts with isolated userData and a mocked chat stream.
 * Run with: node tests\electron_core_chat_flow_smoke.js
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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-core-chat-flow-"));
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
ipcMain.handle("local-auth-token", () => "core-chat-flow-smoke-token");
ipcMain.handle("bridge:audit", () => ({ ok: true }));
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "core_flow_smoke_denied" }));
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

      await waitFor(() => window.lexa && typeof sendMessage === "function" && document.getElementById("chat-input") && document.getElementById("send-btn"));
      if (typeof clearRenderedChatMessages === "function") clearRenderedChatMessages();
      try {
        localStorage.removeItem("lexa-chat-history");
        localStorage.removeItem("lexa-chat-draft");
        localStorage.removeItem("lexa-active-conversation");
      } catch (_) {}
      if (typeof LexaState !== "undefined") {
        LexaState.set("backendOnline", true);
        LexaState.set("isLoading", false);
        LexaState.set("currentConversationId", null);
        LexaState.set("conversationsList", []);
        LexaState.set("ttsEnabled", false);
      }

      const fetchCalls = [];
      const originalFetch = window.fetch;
      window.fetch = async (url, options = {}) => {
        const urlText = String(url || "");
        const bodyText = typeof options.body === "string" ? options.body : "";
        fetchCalls.push({ url: urlText, body: bodyText });
        if (urlText.endsWith("/chat/stream")) {
          const encoder = new TextEncoder();
          const chunks = [
            { c: "Mocked assistant response with <img src=x onerror=alert(1)> " },
            { c: "**safe markdown** and a source-backed note." },
            { done: true, action: null, rc: false },
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
      input.value = "Write a stable internal smoke response";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      send.click();
      const sendWait = await waitFor(() =>
        !LexaState.get("isLoading")
        && document.querySelectorAll(".user-message").length >= 1
        && document.querySelectorAll(".system-message .msg-text").length >= 1
        && !document.querySelector(".streaming-text")
      );

      const userMessage = document.querySelector(".user-message .msg-text");
      const assistantMessage = Array.from(document.querySelectorAll(".system-message .msg-text")).at(-1);
      const assistantContainer = assistantMessage?.closest(".message") || null;
      const history = JSON.parse(localStorage.getItem("lexa-chat-history") || "[]");
      const streamCall = fetchCalls.find((call) => call.url.endsWith("/chat/stream"));
      const streamBody = streamCall ? JSON.parse(streamCall.body || "{}") : {};
      const actionButtons = assistantContainer ? {
        copy: !assistantContainer.querySelector(".msg-copy-btn")?.disabled,
        continue: !assistantContainer.querySelector(".msg-continue-btn")?.disabled,
        verify: !assistantContainer.querySelector(".msg-verify-btn")?.disabled,
        export: !assistantContainer.querySelector(".msg-export-btn")?.disabled,
      } : {};
      const coreFlow = {
        waitOk: sendWait.ok,
        streamRequested: Boolean(streamCall),
        streamMessage: streamBody.message || "",
        userText: userMessage?.textContent || "",
        assistantText: assistantMessage?.textContent || "",
        assistantHtml: assistantMessage?.innerHTML || "",
        scriptTags: assistantMessage?.querySelectorAll("script").length || 0,
        unsafeImages: assistantMessage?.querySelectorAll("img[onerror]").length || 0,
        strongCount: assistantMessage?.querySelectorAll("strong").length || 0,
        rawPersisted: assistantContainer?.dataset?.persistText || "",
        history,
        actionButtons,
        inputCleared: input.value === "",
        sendEnabled: send.disabled === false,
      };

      if (typeof clearRenderedChatMessages === "function") clearRenderedChatMessages();
      const persistedSource = "## Reloaded Answer\\n\\n<script>alert(1)</script>\\n\\n- still text";
      if (typeof renderPersistedConversationMessages === "function") {
        renderPersistedConversationMessages([
          { role: "user", content: "Reload this thread" },
          { role: "assistant", content: persistedSource },
        ], 9001);
      }
      const reloadedAssistant = Array.from(document.querySelectorAll(".system-message .msg-text")).at(-1);
      const reloadedContainer = reloadedAssistant?.closest(".message") || null;
      const historyFlow = {
        userCount: document.querySelectorAll(".user-message").length,
        assistantCount: document.querySelectorAll(".system-message").length,
        headingCount: reloadedAssistant?.querySelectorAll("h1,h2,h3").length || 0,
        scriptTags: reloadedAssistant?.querySelectorAll("script").length || 0,
        text: reloadedAssistant?.textContent || "",
        rawPersisted: reloadedContainer?.dataset?.persistText || "",
      };

      window.fetch = originalFetch;
      return { coreFlow, historyFlow };
    })();
  `);

  const core = result.coreFlow || {};
  console.log("\nCore chat flow integration:");
  assert("send handler completes with mocked stream", core.waitOk === true, JSON.stringify(core));
  assert("chat stream receives submitted input", core.streamRequested === true && core.streamMessage === "Write a stable internal smoke response", JSON.stringify(core));
  assert("user message is rendered", /stable internal smoke response/.test(core.userText || ""), core.userText);
  assert("assistant streamed response renders", /Mocked assistant response/.test(core.assistantText || "") && /safe markdown/.test(core.assistantText || ""), core.assistantText);
  assert("assistant markdown is formatted", Number(core.strongCount || 0) >= 1, core.assistantHtml);
  assert("unsafe assistant HTML is text, not executable DOM", Number(core.scriptTags || 0) === 0 && Number(core.unsafeImages || 0) === 0 && !/<img/i.test(core.assistantHtml || ""), core.assistantHtml);
  assert("assistant raw persisted text is retained for history/actions", /onerror=alert/.test(core.rawPersisted || "") && /safe markdown/.test(core.rawPersisted || ""), core.rawPersisted);
  assert("local chat history persists user and assistant messages", Array.isArray(core.history) && core.history.length >= 2 && core.history.some((msg) => msg.type === "user") && core.history.some((msg) => msg.type === "system" && /Mocked assistant response/.test(msg.text || "")), JSON.stringify(core.history));
  assert("answer action buttons are enabled after response", core.actionButtons?.copy && core.actionButtons?.continue && core.actionButtons?.verify && core.actionButtons?.export, JSON.stringify(core.actionButtons));
  assert("composer resets after submit", core.inputCleared === true && core.sendEnabled === true, JSON.stringify({ inputCleared: core.inputCleared, sendEnabled: core.sendEnabled }));

  const history = result.historyFlow || {};
  console.log("\nConversation render boundary:");
  assert("persisted conversation messages hydrate into chat DOM", history.userCount === 1 && history.assistantCount === 1, JSON.stringify(history));
  assert("persisted markdown renders formatted output", Number(history.headingCount || 0) >= 1 && /Reloaded Answer/.test(history.text || ""), history.text);
  assert("persisted unsafe HTML is not executable", Number(history.scriptTags || 0) === 0, history.text);
  assert("persisted raw markdown remains available on the message", history.rawPersisted === "## Reloaded Answer\n\n<script>alert(1)</script>\n\n- still text", history.rawPersisted);
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
