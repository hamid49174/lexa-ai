/**
 * Electron agent streaming smoke.
 * Uses the real renderer scripts with isolated userData and mocked bridge stream reads.
 * Run with: node tests\electron_agent_streaming_smoke.js
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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-agent-streaming-"));
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
ipcMain.handle("local-auth-token", () => "agent-streaming-smoke-token");
ipcMain.handle("bridge:audit", () => ({ ok: true }));
ipcMain.handle("bridge:presence:request", () => ({ ok: false, reason: "agent_streaming_smoke_denied" }));
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

      await waitFor(() => window.lexa && window.lexaSmoke && typeof sendMessage === "function" && document.getElementById("chat-input") && document.getElementById("send-btn"));
      window.lexaSmoke.reset();
      if (typeof clearRenderedChatMessages === "function") clearRenderedChatMessages();
      if (typeof clearChatVolatileState === "function") clearChatVolatileState();
      if (typeof LexaState !== "undefined") {
        LexaState.set("backendOnline", true);
        LexaState.set("isLoading", false);
        LexaState.set("currentConversationId", null);
        LexaState.set("conversationsList", []);
        LexaState.set("ttsEnabled", false);
      }

      const encoder = new TextEncoder();
      const sse = (payload) => "data: " + JSON.stringify(payload) + "\\n\\n";
      const tail = "data: " + JSON.stringify({
        type: "done",
        run: {
          summary: "Agent final tail summary",
          steps: [{ index: 0, action: "memory_search", status: "success", result: "Found smoke note", duration_ms: 12 }],
          total_duration_ms: 42,
        },
      });
      const bytes = (text) => Array.from(encoder.encode(text));

      window.lexaSmoke.set("agentRun", {
        response: { ok: true, status: 200, statusText: "OK", streamId: "agent-final-tail" },
      });
      window.lexaSmoke.set("agentStreamRead", [
        { response: { done: false, value: bytes(sse({ type: "thinking", message: "Working before final tail" })) } },
        { response: { done: false, value: bytes(tail) } },
        { response: { done: true, value: [] } },
      ]);

      const input = document.getElementById("chat-input");
      const send = document.getElementById("send-btn");
      input.value = "/agent check final stream tail";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      send.click();

      const wait = await waitFor(() =>
        !LexaState.get("isLoading")
        && /Agent final tail summary/.test(Array.from(document.querySelectorAll(".agent-message .agent-summary")).at(-1)?.textContent || "")
      );
      await new Promise((resolve) => setTimeout(resolve, 80));

      const agentMessage = Array.from(document.querySelectorAll(".agent-message")).at(-1);
      const summary = agentMessage?.querySelector(".agent-summary");
      const meta = typeof getMessageAgentRunMeta === "function" ? getMessageAgentRunMeta(agentMessage) : null;
      const firstStep = agentMessage?.querySelector(".agent-step");

      window.lexaSmoke.set("agentRun", {
        response: { ok: true, status: 200, statusText: "OK", streamId: "agent-scoped-step" },
      });
      window.lexaSmoke.set("agentStreamRead", [
        { response: { done: false, value: bytes(sse({ type: "step_start", step: { index: 0, action: "memory_search" } })) } },
        { response: { done: false, value: bytes(sse({ type: "step_done", step: { index: 0, action: "memory_search", status: "success", result: "Second scoped step", duration_ms: 9 } })) } },
        { response: { done: false, value: bytes("data: " + JSON.stringify({
          type: "done",
          run: {
            summary: "Second scoped summary",
            steps: [{ index: 0, action: "memory_search", status: "success", result: "Second scoped step", duration_ms: 9 }],
            total_duration_ms: 24,
          },
        })) } },
        { response: { done: true, value: [] } },
      ]);

      input.value = "/agent check scoped step updates";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      send.click();
      const secondWait = await waitFor(() =>
        !LexaState.get("isLoading")
        && /Second scoped summary/.test(Array.from(document.querySelectorAll(".agent-message .agent-summary")).at(-1)?.textContent || "")
      );
      await new Promise((resolve) => setTimeout(resolve, 80));

      const secondAgentMessage = Array.from(document.querySelectorAll(".agent-message")).at(-1);
      const secondSummary = secondAgentMessage?.querySelector(".agent-summary");
      const secondStep = secondAgentMessage?.querySelector(".agent-step");
      const calls = window.lexaSmoke.calls();
      return {
        waitOk: wait.ok,
        secondWaitOk: secondWait.ok,
        summaryText: summary?.textContent || "",
        secondSummaryText: secondSummary?.textContent || "",
        busy: agentMessage?.getAttribute("aria-busy") || "",
        rawPersisted: agentMessage?.dataset?.persistText || "",
        stepCount: agentMessage?.querySelectorAll(".agent-step").length || 0,
        secondStepCount: secondAgentMessage?.querySelectorAll(".agent-step").length || 0,
        firstStepId: firstStep?.id || "",
        secondStepId: secondStep?.id || "",
        firstStepClass: firstStep?.className || "",
        secondStepClass: secondStep?.className || "",
        completionVisible: Boolean(agentMessage?.querySelector(".agent-completion-panel:not([hidden])")),
        secondCompletionVisible: Boolean(secondAgentMessage?.querySelector(".agent-completion-panel:not([hidden])")),
        durationText: agentMessage?.querySelector(".agent-duration")?.textContent || "",
        copyEnabled: agentMessage?.querySelector(".msg-copy-btn")?.disabled === false,
        continueEnabled: agentMessage?.querySelector(".msg-continue-btn")?.disabled === false,
        verifyEnabled: agentMessage?.querySelector(".msg-verify-btn")?.disabled === false,
        exportEnabled: agentMessage?.querySelector(".msg-export-btn")?.disabled === false,
        inputCleared: input.value === "",
        sendEnabled: send.disabled === false,
        metaSummary: meta?.summary || "",
        metaSteps: Array.isArray(meta?.steps) ? meta.steps.length : 0,
        agentRunCalls: calls.filter((call) => call.method === "agentRun").length,
        streamReadCalls: calls.filter((call) => call.method === "agentStreamRead").length,
      };
    })();
  `);

  console.log("\nAgent stream final tail:");
  assert("agent stream completes with done event lacking trailing newline", result.waitOk === true && /Agent final tail summary/.test(result.summaryText || ""), JSON.stringify(result));
  assert("agent final summary is persisted and metadata is recorded", result.rawPersisted === "Agent final tail summary" && result.metaSummary === "Agent final tail summary" && result.metaSteps === 1, JSON.stringify(result));
  assert("agent final step and completion panel render", Number(result.stepCount || 0) === 1 && result.completionVisible === true && /1/.test(result.durationText || ""), JSON.stringify(result));
  assert("agent step updates stay scoped to the current run", result.secondWaitOk === true && /Second scoped summary/.test(result.secondSummaryText || "") && Number(result.secondStepCount || 0) === 1 && /success/.test(result.secondStepClass || "") && /success/.test(result.firstStepClass || "") && result.firstStepId && result.secondStepId && result.firstStepId !== result.secondStepId && result.secondCompletionVisible === true, JSON.stringify(result));
  assert("agent controls recover after final tail", !result.busy && result.copyEnabled === true && result.continueEnabled === true && result.verifyEnabled === true && result.exportEnabled === true && result.inputCleared === true && result.sendEnabled === true, JSON.stringify(result));
  assert("mocked bridge stream path was used", result.agentRunCalls === 2 && Number(result.streamReadCalls || 0) >= 6, JSON.stringify(result));
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
