/**
 * Electron streaming robustness smoke.
 * Uses the real renderer scripts with isolated userData and mocked chat streams.
 * Run with: node tests\electron_streaming_robustness_smoke.js
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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-streaming-robustness-"));
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
ipcMain.handle("local-auth-token", () => "streaming-robustness-smoke-token");
ipcMain.handle("bridge:audit", () => ({ ok: true }));
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "streaming_robustness_smoke_denied" }));
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
    if (/SSE parse error/i.test(text)) return;
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
      const splitEvery = (text, sizes) => {
        const parts = [];
        let index = 0;
        let sizeIndex = 0;
        while (index < text.length) {
          const size = sizes[sizeIndex % sizes.length];
          parts.push(text.slice(index, index + size));
          index += size;
          sizeIndex += 1;
        }
        return parts;
      };
      const streamFromParts = (parts, options = {}) => new ReadableStream({
        start(controller) {
          let index = 0;
          const push = () => {
            if (index >= parts.length) {
              if (options.close !== false) controller.close();
              return;
            }
            controller.enqueue(encoder.encode(parts[index]));
            index += 1;
            setTimeout(push, options.delayMs || 0);
          };
          if (options.signal) {
            options.signal.addEventListener("abort", () => {
              try { controller.error(new DOMException("Aborted", "AbortError")); } catch (_) {}
            }, { once: true });
          }
          push();
        },
      });
      const responseForStream = (stream) => new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
      const okJsonResponse = () => new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });

      async function resetChat() {
        clearRenderedChatMessages();
        clearChatVolatileState();
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
        await new Promise((resolve) => setTimeout(resolve, 40));
      }

      async function submitScenario(name, prompt, streamHandler, duringStream) {
        await resetChat();
        const fetchCalls = [];
        window.fetch = async (url, options = {}) => {
          const urlText = String(url || "");
          const bodyText = typeof options.body === "string" ? options.body : "";
          fetchCalls.push({ url: urlText, body: bodyText });
          if (urlText.endsWith("/chat/stream")) {
            return streamHandler(options);
          }
          return okJsonResponse();
        };
        const input = document.getElementById("chat-input");
        const send = document.getElementById("send-btn");
        input.value = prompt;
        input.dispatchEvent(new Event("input", { bubbles: true }));
        send.click();
        if (duringStream) await duringStream();
        const wait = await waitFor(() => !LexaState.get("isLoading") && !document.querySelector(".streaming-text"), 7000);
        await new Promise((resolve) => setTimeout(resolve, 100));
        const assistantMessages = Array.from(document.querySelectorAll(".system-message:not(.typing-message) .msg-text"));
        const assistant = assistantMessages.at(-1) || null;
        const container = assistant?.closest(".message") || null;
        const streamCall = fetchCalls.find((call) => call.url.endsWith("/chat/stream"));
        let streamBody = {};
        try { streamBody = JSON.parse(streamCall?.body || "{}"); } catch (_) {}
        const history = typeof chatCachedHistorySnapshot === "function" ? chatCachedHistorySnapshot() : [];
        return {
          name,
          waitOk: wait.ok,
          streamRequested: Boolean(streamCall),
          streamPrompt: streamBody.message || "",
          text: assistant?.textContent || "",
          html: assistant?.innerHTML || "",
          rawPersisted: container?.dataset?.persistText || "",
          strongCount: assistant?.querySelectorAll("strong").length || 0,
          linkCount: assistant?.querySelectorAll("a[href]").length || 0,
          codeCount: assistant?.querySelectorAll("pre code, code").length || 0,
          tableCount: assistant?.querySelectorAll("table").length || 0,
          scriptTags: assistant?.querySelectorAll("script").length || 0,
          unsafeImages: assistant?.querySelectorAll("img[onerror]").length || 0,
          warningText: assistant?.querySelector(".stream-warning")?.textContent || "",
          systemMessageCount: assistantMessages.length,
          sendEnabled: send.disabled === false,
          inputCleared: input.value === "",
          loading: LexaState.get("isLoading") === true,
          historyCount: Array.isArray(history) ? history.length : -1,
          expected: {
            stopped: t("chat.responseStopped"),
            timeout: t("chat.connectionTimeout"),
            interrupted: t("chat.connectionInterrupted"),
            lostRetry: t("chat.connectionLostRetry"),
          },
        };
      }

      const splitMarkdownText = [
        sse({ c: "Chunked **bo" }),
        sse({ c: "ld** link [safe " }),
        sse({ c: "site](https://example.com) and code:\\n\\x60\\x60\\x60js\\ncon" }),
        sse({ c: "sole.log(\\"<tag>\\");\\n\\x60\\x60\\x60\\n| Name | Value |\\n" }),
        sse({ c: "|---|---|\\n| <img src=x onerror=alert(1)> | ok |" }),
        sse({ done: true, action: null, rc: false }),
      ].join("");
      const chunkBoundary = await submitScenario(
        "chunk-boundary",
        "Chunk boundary smoke",
        () => responseForStream(streamFromParts(splitEvery(splitMarkdownText, [3, 11, 2, 17, 5]))),
      );

      const malformedNoFinalText = [
        "event: ignored\\n",
        "data: {not valid json}\\n\\n",
        sse({ c: "Recovered after malformed " }),
        "data: \\n\\n",
        sse({ c: "**event** without final marker <script>alert(1)</script>" }),
      ].join("");
      const malformedNoFinal = await submitScenario(
        "malformed-no-final",
        "Malformed stream smoke",
        () => responseForStream(streamFromParts(splitEvery(malformedNoFinalText, [9, 1, 14, 6]))),
      );

      const streamError = await submitScenario(
        "stream-error",
        "Stream error smoke",
        () => responseForStream(new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode(sse({ c: "Partial answer before stream failure" })));
            setTimeout(() => controller.error(new Error("simulated_stream_failure_secret_detail")), 40);
          },
        })),
      );

      const userAbort = await submitScenario(
        "user-abort",
        "Abort stream smoke",
        (options) => responseForStream(new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode(sse({ c: "Abort partial answer" })));
            options.signal.addEventListener("abort", () => {
              try { controller.error(new DOMException("Aborted", "AbortError")); } catch (_) {}
            }, { once: true });
          },
        })),
        async () => {
          const ready = await waitFor(() => window._lexaStreamAbort && document.querySelector(".streaming-text") && /Abort partial answer/.test(document.querySelector(".streaming-text")?.textContent || ""), 2500);
          if (ready.ok && window._lexaStreamAbort) {
            window._lexaStreamAbortReason = "user";
            window._lexaStreamAbort.abort();
          }
        },
      );

      const timeoutBeforeResponse = await submitScenario(
        "timeout-before-response",
        "Timeout stream smoke",
        () => new Promise((_resolve, reject) => {
          setTimeout(() => {
            window._lexaStreamAbortReason = "timeout";
            reject(new DOMException("simulated_timeout_secret_detail", "AbortError"));
          }, 30);
        }),
      );

      window.fetch = originalFetch;
      window.playTTS = originalTts;
      return { chunkBoundary, malformedNoFinal, streamError, userAbort, timeoutBeforeResponse };
    })();
  `);

  const chunk = result.chunkBoundary || {};
  console.log("\nStreaming chunk boundaries:");
  assert("split stream chunks complete through the real send button", chunk.waitOk === true && chunk.streamRequested === true && chunk.streamPrompt === "Chunk boundary smoke", JSON.stringify(chunk));
  assert("split markdown renders as one coherent assistant message", /Chunked bold link safe site and code/.test(chunk.text || "") && (chunk.text.match(/Chunked/g) || []).length === 1 && chunk.systemMessageCount === 1, chunk.text);
  assert("split markdown retains final formatting", Number(chunk.strongCount || 0) >= 1 && Number(chunk.linkCount || 0) >= 1 && Number(chunk.codeCount || 0) >= 1 && Number(chunk.tableCount || 0) >= 1, chunk.html);
  assert("split stream unsafe HTML remains contained", Number(chunk.scriptTags || 0) === 0 && Number(chunk.unsafeImages || 0) === 0 && !/<img/i.test(chunk.html || ""), chunk.html);
  assert("split stream clears loading state and preserves raw text", chunk.sendEnabled === true && chunk.inputCleared === true && chunk.loading === false && /onerror=alert/.test(chunk.rawPersisted || ""), JSON.stringify(chunk));

  const malformed = result.malformedNoFinal || {};
  console.log("\nMalformed stream events:");
  assert("malformed SSE does not crash or drop later content", malformed.waitOk === true && /Recovered after malformed event without final marker/.test(malformed.text || ""), malformed.text);
  assert("stream without final marker recovers to usable state", malformed.sendEnabled === true && malformed.inputCleared === true && malformed.loading === false && malformed.systemMessageCount === 1, JSON.stringify(malformed));
  assert("malformed stream unsafe HTML remains text", Number(malformed.scriptTags || 0) === 0 && !/<script/i.test(malformed.html || "") && /alert/.test(malformed.text || ""), malformed.html);

  const interrupted = result.streamError || {};
  console.log("\nStreaming error recovery:");
  assert("stream read error keeps partial answer and adds safe warning", interrupted.waitOk === true && /Partial answer before stream failure/.test(interrupted.text || "") && /simulated_stream_failure_secret_detail/.test(interrupted.text || "") === false && /simulated_stream_failure_secret_detail/.test(interrupted.html || "") === false && (interrupted.warningText || "").includes(interrupted.expected?.interrupted || "__missing__"), JSON.stringify(interrupted));
  assert("stream read error recovers controls without duplicate assistant messages", interrupted.sendEnabled === true && interrupted.inputCleared === true && interrupted.loading === false && interrupted.systemMessageCount === 1, JSON.stringify(interrupted));

  const aborted = result.userAbort || {};
  console.log("\nStreaming user abort:");
  assert("user abort during streaming leaves stable partial response", aborted.waitOk === true && /Abort partial answer/.test(aborted.text || "") && aborted.warningText === aborted.expected?.stopped, JSON.stringify(aborted));
  assert("user abort restores composer controls", aborted.sendEnabled === true && aborted.inputCleared === true && aborted.loading === false && aborted.systemMessageCount === 1, JSON.stringify(aborted));

  const timeout = result.timeoutBeforeResponse || {};
  console.log("\nStreaming timeout recovery:");
  assert("simulated stream timeout shows safe timeout message", timeout.waitOk === true && timeout.text === timeout.expected?.timeout && !/simulated_timeout_secret_detail/i.test(timeout.text || ""), JSON.stringify(timeout));
  assert("simulated stream timeout restores usable state", timeout.sendEnabled === true && timeout.inputCleared === true && timeout.loading === false && timeout.systemMessageCount === 1, JSON.stringify(timeout));
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
