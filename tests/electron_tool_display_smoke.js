/**
 * Electron render-only tool display smoke.
 * Uses the real renderer scripts with isolated userData and mocked tool execution.
 * Run with: node tests\electron_tool_display_smoke.js
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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-tool-display-smoke-"));
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
ipcMain.handle("local-auth-token", () => "tool-display-smoke-token");
ipcMain.handle("bridge:audit", () => ({ ok: true }));
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "tool_display_smoke_denied" }));
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

      await waitFor(() => window.lexa && typeof sendMessage === "function" && typeof clearRenderedChatMessages === "function" && document.getElementById("chat-input") && document.getElementById("send-btn"));

      const encoder = new TextEncoder();
      const originalFetch = window.fetch;
      const originalTts = window.playTTS;
      if (typeof window.playTTS === "function") window.playTTS = () => {};

      const sse = (payload) => "data: " + JSON.stringify(payload) + "\\n\\n";
      const okJsonResponse = () => new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      const streamResponse = (action, reply = "Tool placeholder before execution") => new Response(new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(sse({ c: reply })));
          controller.enqueue(encoder.encode(sse({ done: true, action, rc: false })));
          controller.close();
        },
      }), { status: 200, headers: { "content-type": "text/event-stream" } });

      async function resetChat() {
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
        LexaState.set("ttsEnabled", false);
        window._lexaStreamAbort = null;
        window._lexaStreamAbortReason = "";
        const input = document.getElementById("chat-input");
        const send = document.getElementById("send-btn");
        input.value = "";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        send.disabled = false;
      }

      async function runToolScenario(prompt, action, reply) {
        await resetChat();
        const fetchCalls = [];
        window.fetch = async (url, options = {}) => {
          const urlText = String(url || "");
          fetchCalls.push({ url: urlText, body: typeof options.body === "string" ? options.body : "" });
          if (urlText.endsWith("/chat/stream")) return streamResponse(action, reply);
          return okJsonResponse();
        };
        const input = document.getElementById("chat-input");
        const send = document.getElementById("send-btn");
        input.value = prompt;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        send.click();
        const wait = await waitFor(() => !LexaState.get("isLoading") && !document.querySelector(".streaming-text"), 7000);
        await new Promise((resolve) => setTimeout(resolve, 120));
        const systemMessages = Array.from(document.querySelectorAll(".system-message:not(.typing-message)"));
        const message = systemMessages.at(-1) || null;
        const textEl = message?.querySelector(".msg-text") || null;
        const history = JSON.parse(localStorage.getItem("lexa-chat-history") || "[]");
        return {
          waitOk: wait.ok,
          fetchCalls: fetchCalls.length,
          text: textEl?.textContent || "",
          html: textEl?.innerHTML || "",
          rawPersisted: message?.dataset?.persistText || "",
          scriptTags: textEl?.querySelectorAll("script").length || 0,
          unsafeImages: textEl?.querySelectorAll("img[onerror]").length || 0,
          confirmButtons: message?.querySelectorAll(".confirm-btn").length || 0,
          denyButtons: message?.querySelectorAll(".deny-btn").length || 0,
          actionCards: message?.querySelectorAll(".msg-action").length || 0,
          actionText: message?.querySelector(".action-cmd")?.textContent || "",
          actionHtml: message?.querySelector(".action-cmd")?.innerHTML || "",
          actionDetailHtml: message?.querySelector(".action-detail")?.innerHTML || "",
          systemMessageCount: systemMessages.length,
          sendEnabled: send.disabled === false,
          inputCleared: input.value === "",
          historyCount: Array.isArray(history) ? history.length : -1,
        };
      }

      const successAction = {
        action: "system_info",
        params: { query: "Berlin <script>alert('param')</script>" },
      };
      const successFlow = await runToolScenario("Show mocked system info tool", successAction);

      const noDisplayAction = {
        action: "unknown_tool<script>alert('cmd')</script>",
        params: { path: "C:/not-real/<img src=x onerror=alert(1)>" },
      };
      const noDisplayFlow = await runToolScenario("Show mocked no-result tool", noDisplayAction);

      const technicalAction = {
        action: "app_open",
        params: { name: "notepad" },
      };
      const technicalFallbackFlow = await runToolScenario("Open a local app", technicalAction, "Fuehre 'app_open' aus.");

      await resetChat();
      renderPersistedConversationMessages([
        { role: "user", content: "History request" },
        { role: "assistant", content: "Persisted tool result <img src=x onerror=alert(1)>", action: successAction, requires_confirmation: false },
      ], "tool-history-smoke");
      const historyMessage = Array.from(document.querySelectorAll(".system-message")).at(-1);
      const historyText = historyMessage?.querySelector(".msg-text") || null;
      const historyFlow = {
        text: historyText?.textContent || "",
        html: historyText?.innerHTML || "",
        scriptTags: historyText?.querySelectorAll("script").length || 0,
        unsafeImages: historyText?.querySelectorAll("img[onerror]").length || 0,
        confirmButtons: historyMessage?.querySelectorAll(".confirm-btn").length || 0,
        actionCards: historyMessage?.querySelectorAll(".msg-action").length || 0,
      };

      window.fetch = originalFetch;
      window.playTTS = originalTts;
      return { successFlow, noDisplayFlow, technicalFallbackFlow, historyFlow };
    })();
  `);

  const success = result.successFlow || {};
  console.log("\nNon-confirmed tool action display:");
  assert("non-confirmed smoke uses mocked stream and smoke bridge only", success.waitOk === true && success.fetchCalls === 1, JSON.stringify(success));
  assert("chat does not auto-execute non-confirmed tool actions", success.waitOk === true && /Tool placeholder/.test(success.text || "") && success.actionCards === 0, JSON.stringify(success));
  assert("non-confirmed tool action renders no confirm controls", success.confirmButtons === 0 && success.denyButtons === 0, JSON.stringify(success));
  assert("non-confirmed tool action details stay invisible", !success.actionText && !success.actionHtml && !success.actionDetailHtml, JSON.stringify(success));
  assert("non-confirmed tool action recovers composer state", success.sendEnabled === true && success.inputCleared === true && success.systemMessageCount === 1, JSON.stringify(success));

  const noDisplay = result.noDisplayFlow || {};
  console.log("\nNon-confirmed unsafe tool action display:");
  assert("mocked no-result tool keeps safe placeholder text", noDisplay.waitOk === true && /Tool placeholder/.test(noDisplay.text || "") && Number(noDisplay.scriptTags || 0) === 0 && !/<script|<img/i.test(noDisplay.html || ""), JSON.stringify(noDisplay));
  assert("mocked no-result tool display creates no live or blocked action card", noDisplay.confirmButtons === 0 && noDisplay.denyButtons === 0 && noDisplay.actionCards === 0 && noDisplay.systemMessageCount === 1, JSON.stringify(noDisplay));
  assert("unsafe action name and params stay invisible", !noDisplay.actionText && !noDisplay.actionHtml && !noDisplay.actionDetailHtml, JSON.stringify(noDisplay));

  const technical = result.technicalFallbackFlow || {};
  console.log("\nTechnical local action fallback display:");
  assert("technical local action fallback is product-friendly", technical.waitOk === true && /Ich bin da|I am here/i.test(technical.text || "") && !/app_open|Fuehre|Führe|LOKALE AKTION BLOCKIERT|lokale Aktion|local action|PC-Aktionen|PC actions/i.test(technical.text || "") && technical.actionCards === 0, JSON.stringify(technical));
  assert("technical local action fallback keeps action details invisible", technical.confirmButtons === 0 && technical.denyButtons === 0 && !technical.actionText && !technical.actionHtml && !technical.actionDetailHtml, JSON.stringify(technical));

  const history = result.historyFlow || {};
  console.log("\nPersisted tool result display:");
  assert("history render does not create live action controls", history.confirmButtons === 0 && history.actionCards === 0, JSON.stringify(history));
  assert("history tool-like content remains escaped text", /Persisted tool result/.test(history.text || "") && Number(history.scriptTags || 0) === 0 && Number(history.unsafeImages || 0) === 0 && !/<img/i.test(history.html || ""), JSON.stringify(history));
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
