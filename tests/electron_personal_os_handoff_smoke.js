/**
 * Electron Personal OS chat-handoff and draft-review display smoke.
 * Uses mocked renderer state only; never approves, rejects, applies, raw-submits, or touches OS files.
 * Run with: node tests\electron_personal_os_handoff_smoke.js
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

const smokeUserData = fs.mkdtempSync(path.join(os.tmpdir(), "lexa-personal-os-handoff-"));
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
ipcMain.handle("local-auth-token", () => "personal-os-handoff-smoke-token");
ipcMain.handle("bridge:audit", (_event, payload = {}) => {
  bridgeAudits.push(payload);
  return { ok: true };
});
ipcMain.handle("bridge:presence:request", (_event, payload = {}) => {
  presenceRequests.push(payload);
  return { ok: false, reason: "personal_os_handoff_smoke_denied" };
});
ipcMain.handle("bridge:presence:consume", () => ({ ok: false, reason: "challenge_missing_or_expired" }));
ipcMain.on("get-autostart", (event) => { event.returnValue = false; });
ipcMain.on("set-autostart", () => {});

async function main() {
  await app.whenReady();

  const rendererErrors = [];
  const win = new BrowserWindow({
    width: 1160,
    height: 820,
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
        && typeof switchView === "function"
        && typeof renderPersonalOsQueryPayload === "function"
        && typeof renderPersonalOsDraftList === "function"
        && typeof renderPersonalOsDetail === "function"
        && typeof personalOsSendContextToChat === "function"
        && typeof personalOsSendReviewToChat === "function"
        && typeof personalOsReviewPrompt === "function"
        && typeof renderPosPromptHint === "function"
        && typeof renderPosApplyHint === "function"
        && document.getElementById("chat-input")
        && document.getElementById("personal-os-view")
      );

      const fetchCalls = [];
      const originalFetch = window.fetch;
      window.fetch = async (url, options = {}) => {
        fetchCalls.push({ url: String(url || ""), method: options?.method || "GET" });
        return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "content-type": "application/json" } });
      };

      const originalSendMessage = window.sendMessage;
      let sendCalls = 0;
      window.sendMessage = function(...args) {
        sendCalls += 1;
        return originalSendMessage.apply(this, args);
      };

      if (typeof clearRenderedChatMessages === "function") clearRenderedChatMessages();
      try {
        localStorage.removeItem("lexa-chat-history");
        localStorage.removeItem("lexa-active-conversation");
        localStorage.removeItem("lexa-chat-draft");
      } catch (_) {}
      if (typeof LexaState !== "undefined") {
        LexaState.set("backendOnline", true);
        LexaState.set("isLoading", false);
        LexaState.set("currentConversationId", null);
        LexaState.set("ttsEnabled", false);
        LexaState.clearInterval("personal-os");
      }

      const unsafe = "<img src=x onerror=alert(1)>";
      switchView("personal-os");
      await new Promise((resolve) => setTimeout(resolve, 250));
      if (typeof LexaState !== "undefined") LexaState.clearInterval("personal-os");

      renderPersonalOsQueryPayload({
        ok: true,
        path: "00_System/INDEX.md",
        frontmatter: {
          title: "Context handoff " + unsafe,
          type: "index",
          memory_level: "system",
          tags: ["lexa", unsafe],
        },
        body: "Context body " + unsafe + "\\nUse this only as source material.",
      });
      const contextButton = document.querySelector('[data-action="personalOsSendContextToChat"]');
      contextButton?.click();
      await new Promise((resolve) => setTimeout(resolve, 160));
      const contextPrompt = document.getElementById("chat-input")?.value || "";
      const contextState = {
        buttonExists: Boolean(contextButton),
        currentView: LexaState.get("currentView"),
        inputValue: contextPrompt,
        inputDraft: localStorage.getItem("lexa-chat-draft") || "",
        messages: document.querySelectorAll("#chat-messages .message").length,
        unsafeNodes: document.querySelectorAll("#chat-messages script,#chat-messages img[onerror],#personal-os-view script,#personal-os-view img[onerror]").length,
      };

      switchView("personal-os");
      await new Promise((resolve) => setTimeout(resolve, 160));
      if (typeof LexaState !== "undefined") LexaState.clearInterval("personal-os");
      renderPersonalOsDraftList({
        ok: true,
        counts: { total: 1, pending: 1, approved: 0, rejected: 0, invalid: 0 },
        drafts: [{
          title: "Review draft " + unsafe,
          path: "06_Inbox/Drafts/review-smoke.md",
          approval: "pending",
          memory_level: "working",
          source: "smoke",
          tags: ["review", unsafe],
        }],
      });
      const draft = {
        ok: true,
        path: "06_Inbox/Drafts/review-smoke.md",
        approval: "pending",
        frontmatter: {
          title: "Review draft " + unsafe,
          type: "draft",
          memory_level: "working",
          source: "smoke",
          confidence: "test",
          tags: ["review", unsafe],
          related: ["05_Memory/Rollups/review.md", unsafe],
        },
        body: "Draft proposal body " + unsafe,
      };
      const review = {
        assist: {
          status: "attention",
          summary: "Review assist summary " + unsafe,
          nextAction: "Human review only " + unsafe,
          checks: [
            { state: "warn", label: "Evidence " + unsafe, detail: "Needs source check " + unsafe },
          ],
        },
        checklist: { hasApproved: true, hasRejected: true, approvedChecked: false, rejectedChecked: false },
        applyHint: { enabled: false, target: "05_Memory/Rollups/target.md", reason: "Apply disabled until explicit human approval " + unsafe },
        history: { events: [{ type: "DraftCreated", timestamp: "2026-05-21T10:00:00Z", agent: "Smoke", reason: "Display only " + unsafe }] },
        related: [{ title: "Related context " + unsafe, path: "05_Memory/Rollups/review.md", type: "memory-summary", bodyPreview: "Related preview " + unsafe }],
        targetCandidate: "05_Memory/Rollups/target.md",
        targetSource: "frontmatter",
        target: { path: "05_Memory/Rollups/target.md" },
        diff: { changed: true, lines: ["--- target", "+++ draft", "+ Add proposed line " + unsafe] },
      };
      renderPersonalOsDetail(draft, review);
      const draftListSnapshot = {
        text: document.getElementById("pos-draft-list")?.textContent || "",
        html: document.getElementById("pos-draft-list")?.innerHTML || "",
        rowCount: document.querySelectorAll("#pos-draft-list .pos-draft-row").length,
      };
      const detailBefore = {
        title: document.getElementById("pos-detail-title")?.textContent || "",
        text: document.getElementById("pos-draft-detail")?.textContent || "",
        html: document.getElementById("pos-draft-detail")?.innerHTML || "",
        approveDisabled: document.getElementById("pos-approve-btn")?.disabled === true,
        rejectDisabled: document.getElementById("pos-reject-btn")?.disabled === true,
        applyDisabled: document.getElementById("pos-apply-btn")?.disabled === true,
        chatReviewDisabled: document.getElementById("pos-chat-review-btn")?.disabled === true,
        promptHint: Boolean(document.querySelector("#pos-draft-detail .pos-prompt-hint")),
        applyHint: Boolean(document.querySelector("#pos-draft-detail .pos-apply-hint")),
        statusText: document.querySelector("#pos-draft-detail .pos-detail-meta .pos-pill")?.textContent || "",
      };
      document.getElementById("pos-chat-review-btn")?.click();
      await new Promise((resolve) => setTimeout(resolve, 160));
      const reviewPrompt = document.getElementById("chat-input")?.value || "";
      const reviewState = {
        currentView: LexaState.get("currentView"),
        inputValue: reviewPrompt,
        inputDraft: localStorage.getItem("lexa-chat-draft") || "",
        messages: document.querySelectorAll("#chat-messages .message").length,
        unsafeNodes: document.querySelectorAll("#chat-messages script,#chat-messages img[onerror],#personal-os-view script,#personal-os-view img[onerror]").length,
      };

      window.fetch = originalFetch;
      window.sendMessage = originalSendMessage;
      return {
        contextState,
        draftListSnapshot,
        detailBefore,
        reviewState,
        sendCalls,
        fetchCalls,
      };
    })();
  `);

  await new Promise((resolve) => setTimeout(resolve, 120));

  console.log("\nPersonal OS chat handoff smoke:");
  const contextState = result.contextState || {};
  assert("Personal OS context handoff button is available", contextState.buttonExists === true, JSON.stringify(contextState));
  assert("context handoff places prompt in chat composer", contextState.currentView === "chat" && /Personal-OS-Kontext|Personal OS context|Kontext/i.test(contextState.inputValue || "") && contextState.inputValue.includes("00_System/INDEX.md") && contextState.inputValue.includes("<img src=x onerror=alert(1)>"), JSON.stringify(contextState));
  assert("context handoff persists composer draft without auto-send", contextState.inputDraft === contextState.inputValue && Number(contextState.messages || 0) === 0, JSON.stringify(contextState));

  console.log("\nPersonal OS draft-review display smoke:");
  const draftList = result.draftListSnapshot || {};
  assert("mocked draft queue renders review candidate safely", Number(draftList.rowCount || 0) === 1 && draftList.text.includes("Review draft") && /&lt;img src=x onerror=alert\(1\)&gt;/.test(draftList.html || ""), JSON.stringify(draftList));

  const detail = result.detailBefore || {};
  assert("mocked draft detail renders review surfaces safely", detail.title.includes("Review draft") && detail.text.includes("Draft proposal body") && detail.text.includes("Review assist summary") && detail.promptHint === true && detail.applyHint === true && /&lt;img src=x onerror=alert\(1\)&gt;/.test(detail.html || ""), JSON.stringify(detail));
  assert("draft status label and current write controls reflect existing review UI state", /Needs review|Pruefung|Prüfung|Muss geprüft|Offen|review/i.test(detail.statusText || "") && detail.chatReviewDisabled === false && detail.applyDisabled === true, JSON.stringify(detail));

  const reviewState = result.reviewState || {};
  assert("draft review handoff places review prompt in chat composer", reviewState.currentView === "chat" && /Draft|Entwurf|Review Assist/i.test(reviewState.inputValue || "") && reviewState.inputValue.includes("06_Inbox/Drafts/review-smoke.md") && reviewState.inputValue.includes("<img src=x onerror=alert(1)>"), JSON.stringify(reviewState));
  assert("draft review handoff includes no-auto-decision guidance", /Triff keine|keine Approval|no auto/i.test(reviewState.inputValue || ""), JSON.stringify(reviewState.inputValue || ""));
  assert("draft review handoff persists composer draft without auto-send", reviewState.inputDraft === reviewState.inputValue && Number(reviewState.messages || 0) === 0, JSON.stringify(reviewState));
  assert("unsafe handoff/review content does not create executable nodes", Number(contextState.unsafeNodes || 0) === 0 && Number(reviewState.unsafeNodes || 0) === 0, JSON.stringify({ context: contextState.unsafeNodes, review: reviewState.unsafeNodes }));
  assert("handoff smoke did not call send/fetch", Number(result.sendCalls || 0) === 0 && Array.isArray(result.fetchCalls) && result.fetchCalls.length === 0, JSON.stringify({ sendCalls: result.sendCalls, fetchCalls: result.fetchCalls }));

  const forbiddenBridgeMethods = new Set([
    "personalOsDraftDecision",
    "personalOsDraftApply",
    "personalOsRawSubmit",
    "execute",
    "executeWithConfirmation",
    "prepareCompanionExecute",
    "chatFile",
    "setAiModel",
    "elevenlabsSetKey",
    "deepgramSetKey",
    "cartesiaSetKey",
  ]);
  assert("handoff smoke did not call write/tool/provider/secret bridge methods", bridgeAudits.every((entry) => !forbiddenBridgeMethods.has(entry?.method)) && presenceRequests.length === 0, JSON.stringify({ bridgeAudits, presenceRequests }));
  assert("renderer stayed free of fatal errors", rendererErrors.length === 0, JSON.stringify(rendererErrors));

  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  await win.close();
  app.exit(failed > 0 ? 1 : 0);
}

main().catch(async (error) => {
  console.error(error);
  app.exit(1);
});
