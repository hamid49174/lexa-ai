/**
 * Smoke tests for sendMessage() guard ordering.
 * Run with: node tests/test_chat_send_guards.js
 */

const fs = require("fs");
const path = require("path");

const chatCoreSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat.js"),
  "utf8"
);
const chatVoiceSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_voice.js"),
  "utf8"
);
const chatConversationsSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_conversations.js"),
  "utf8"
);
const chatAgentRunsSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_agent_runs.js"),
  "utf8"
);
const chatStateSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_state.js"),
  "utf8"
);
const chatFileUploadSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_file_upload.js"),
  "utf8"
);
const src = [chatCoreSrc, chatVoiceSrc, chatAgentRunsSrc, chatConversationsSrc].join("\n");
const chatBundleSrc = [src, chatStateSrc, chatFileUploadSrc].join("\n");
const chatConstantsSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_constants.js"),
  "utf8"
);
const chatExportSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_export.js"),
  "utf8"
);
const chatComposerSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_composer_helpers.js"),
  "utf8"
);
const chatMessageActionsSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_message_actions.js"),
  "utf8"
);
const chatMessageActionsControllerSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_message_actions_controller.js"),
  "utf8"
);
const chatInputHelpersSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_input_helpers.js"),
  "utf8"
);
const chatHistoryUiSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat_history_ui.js"),
  "utf8"
);
const deI18n = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "i18n", "de.json"), "utf8");
const enI18n = fs.readFileSync(path.join(__dirname, "..", "frontend", "src", "i18n", "en.json"), "utf8");

function extractFn(source, name) {
  const needles = [`async function ${name}(`, `function ${name}(`];
  const start = Math.min(
    ...needles.map((needle) => source.indexOf(needle)).filter((index) => index >= 0)
  );
  if (start === -1) throw new Error(`'${name}' not found`);
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`No closing brace for '${name}'`);
}

function extractConstArray(source, name) {
  const start = source.indexOf(`const ${name} = [`);
  if (start === -1) throw new Error(`'${name}' not found`);
  const end = source.indexOf("];", start);
  if (end === -1) throw new Error(`No closing array for '${name}'`);
  return source.slice(start, end + 2);
}

const sandbox = new Function(`
  "use strict";
  let inputValue = "";
  let backendOnline = true;
  let loading = false;
  const events = [];
  const chatInput = { get value() { return inputValue; }, set value(value) { inputValue = String(value); } };
  const LexaConfig = { MAX_CHAT_INPUT_LENGTH: 10 };
  const LexaState = {
    get(key) {
      if (key === "isLoading") return loading;
      if (key === "backendOnline") return backendOnline;
      return null;
    },
    set(key, value) {
      if (key === "isLoading") loading = Boolean(value);
      events.push(["set", key, value]);
    },
  };
  function showToast(message, type) { events.push(["toast", message, type]); }
  function t(key, values = {}) {
    if (String(key).startsWith("composer.")) return key;
    return key + ":" + (values.max || "");
  }
  async function sendAgentMessage(text) { events.push(["agent", text]); }
  ${extractFn(chatInputHelpersSrc, "chatInputMetrics")}
  ${extractFn(src, "getMessagePersistText")}
  ${extractFn(src, "setMessagePersistText")}
  ${extractConstArray(chatComposerSrc, "LEXA_COMPOSER_COMMANDS")}
  ${extractFn(chatComposerSrc, "composerCommandText")}
  ${extractFn(chatComposerSrc, "composerCommandLabel")}
  ${extractFn(chatComposerSrc, "composerCommandDesc")}
  ${extractFn(chatComposerSrc, "composerCommandPrefix")}
  ${extractFn(chatComposerSrc, "composerCommandAliases")}
  ${extractFn(chatComposerSrc, "composerCommandAliasKey")}
  ${extractFn(chatComposerSrc, "composerCommandHintText")}
  ${extractFn(chatComposerSrc, "composerCommandAliasValues")}
  ${extractFn(chatComposerSrc, "composerCommandIconSvg")}
  ${extractFn(chatComposerSrc, "composerCommandMatches")}
  ${extractFn(chatComposerSrc, "composerCommandScore")}
  ${extractFn(chatComposerSrc, "composerCommandSearchItems")}
  ${extractFn(chatComposerSrc, "composerCommandForAlias")}
  ${extractFn(chatComposerSrc, "expandComposerSlashAlias")}
  ${extractFn(chatMessageActionsSrc, "messageActionPromptLimit")}
  ${extractFn(chatMessageActionsSrc, "messageActionBoundedSource")}
  ${extractFn(chatMessageActionsSrc, "messageActionPromptWithSource")}
  ${extractFn(chatMessageActionsSrc, "workspaceDraftPromptFromText")}
  ${extractFn(chatMessageActionsSrc, "continuePromptFromText")}
  ${extractFn(chatMessageActionsSrc, "verifyAnswerPromptFromText")}
  ${extractFn(chatExportSrc, "messageExportMarkdownFromText")}
  ${extractFn(chatExportSrc, "messageExportFilename")}
  ${extractConstArray(chatConstantsSrc, "_AGENT_PATTERNS")}
  ${extractFn(src, "_normalizeGermanSearchText")}
  ${extractFn(src, "_needsAgentMode")}
  ${extractFn(src, "_normalizeAgentCommandText")}
  ${extractFn(src, "_isHermesWorkerCommand")}
  ${extractFn(src, "_stripHermesWorkerPrefix")}
  ${extractFn(src, "_isHermesSystemStatusRequest")}
  ${extractFn(src, "sendMessage")}
  return {
    chatInputMetrics,
    getMessagePersistText,
    setMessagePersistText,
    composerCommandAliasKey,
    composerCommandSearchItems,
    composerCommandForAlias,
    composerCommandHintText,
    composerCommandIconSvg,
    composerCommandText,
    composerCommands: LEXA_COMPOSER_COMMANDS,
    expandComposerSlashAlias,
    workspaceDraftPromptFromText,
    continuePromptFromText,
    verifyAnswerPromptFromText,
    messageExportMarkdownFromText,
    messageExportFilename,
    _needsAgentMode,
    _isHermesWorkerCommand,
    _stripHermesWorkerPrefix,
    _isHermesSystemStatusRequest,
    sendMessage,
    setInput(value) { inputValue = value; },
    setMaxLength(value) { LexaConfig.MAX_CHAT_INPUT_LENGTH = Number(value); },
    setBackendOnline(value) { backendOnline = Boolean(value); },
    state() { return { loading, events: events.slice() }; },
    reset() { events.length = 0; loading = false; backendOnline = true; inputValue = ""; LexaConfig.MAX_CHAT_INPUT_LENGTH = 10; },
  };
`)();

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

(async () => {
  console.log("\nsendMessage() guards:");

  const calm = sandbox.chatInputMetrics("x".repeat(20), { MAX_CHAT_INPUT_LENGTH: 100, CHAR_COUNTER_WARN: 75, CHAR_COUNTER_DANGER: 95 });
  assert("keeps counter hidden before warn threshold", calm.visible === false);
  const warn = sandbox.chatInputMetrics("x".repeat(80), { MAX_CHAT_INPUT_LENGTH: 100, CHAR_COUNTER_WARN: 75, CHAR_COUNTER_DANGER: 95 });
  assert("marks warning range", warn.visible === true && warn.warn === true && warn.danger === false);
  const over = sandbox.chatInputMetrics("x".repeat(101), { MAX_CHAT_INPUT_LENGTH: 100, CHAR_COUNTER_WARN: 75, CHAR_COUNTER_DANGER: 95 });
  assert("marks over-limit range", over.visible === true && over.over === true && over.label === "101/100");
  const defaultMetrics = sandbox.chatInputMetrics(null, {});
  assert("chat input metrics handles empty input with fallback config", defaultMetrics.length === 0 && defaultMetrics.max === 4000 && defaultMetrics.visible === false && defaultMetrics.label === "0/4000");
  const dangerEdge = sandbox.chatInputMetrics("x".repeat(95), { MAX_CHAT_INPUT_LENGTH: 100, CHAR_COUNTER_WARN: 75, CHAR_COUNTER_DANGER: 95 });
  assert("chat input metrics marks the danger threshold without over-limit state", dangerEdge.danger === true && dangerEdge.over === false && dangerEdge.visible === true);

  sandbox.setInput("x".repeat(11));
  await sandbox.sendMessage();
  let state = sandbox.state();
  assert("does not enter loading state for too-long input", state.loading === false);
  assert("shows too-long warning", state.events.some((event) => event[0] === "toast" && event[2] === "warning"));
  assert("does not set isLoading before too-long return", !state.events.some((event) => event[0] === "set" && event[1] === "isLoading"));

  sandbox.reset();
  sandbox.setInput("hello");
  sandbox.setBackendOnline(false);
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("does not enter loading state when backend is offline", state.loading === false);
  assert("shows backend offline error", state.events.some((event) => event[0] === "toast" && event[2] === "error"));
  assert("does not set isLoading before offline return", !state.events.some((event) => event[0] === "set" && event[1] === "isLoading"));

  sandbox.reset();
  sandbox.setInput("/agent x");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("routes manual agent command without pre-loading", state.loading === false);
  assert("strips /agent prefix before agent route", state.events.some((event) => event[0] === "agent" && event[1] === "x"));
  assert("does not set isLoading before agent route", !state.events.some((event) => event[0] === "set" && event[1] === "isLoading"));

  const agentSource = extractFn(src, "sendAgentMessage");
  const agentErrorSource = extractFn(src, "agentUserFacingError");
  const agentDoneStart = agentSource.indexOf('if (event.type === "done")');
  const agentDoneEnd = agentSource.indexOf('if (event.type === "error")', agentDoneStart);
  const agentDoneSource = agentDoneStart >= 0 && agentDoneEnd > agentDoneStart
    ? agentSource.slice(agentDoneStart, agentDoneEnd)
    : "";
  assert("agent stream read has timeout guard", agentSource.includes("AGENT_STREAM_TIMEOUT_MS") && agentSource.includes("Promise.race") && agentSource.includes("agentReader.cancel"));
  assert("agent stream supports Electron bridge stream ids", src.includes("function createAgentStreamReader") && src.includes("window.lexa.agentStreamRead(streamId)") && src.includes("window.lexa.agentStreamCancel(streamId)") && src.includes("function normalizeAgentStreamChunk") && agentSource.includes("createAgentStreamReader(response)"));
  assert("agent stream shares safe SSE parser and consumes final tail", agentSource.includes("chatStreamBufferedLines(buffer)") && agentSource.includes("chatStreamFinalLines(buffer)") && agentSource.includes("parseChatStreamDataLine(line)") && !agentSource.includes("JSON.parse(raw)") && !agentSource.includes("line.slice(6)"));
  assert("agent user-facing errors hide common technical statuses", agentErrorSource.includes("unknown|undefined|null") && agentErrorSource.includes("unauthorized|forbidden|not found|internal server error") && agentErrorSource.includes("failed to fetch|networkerror|econn|socket|timeout|ipc|handler failed") && agentErrorSource.includes("clipAgentStepText(text, 120)"));
  assert("agent timeout uses translated UI message", agentSource.includes('t("chat.agentTimeout")') && deI18n.includes('"chat.agentTimeout"') && enI18n.includes('"chat.agentTimeout"'));
  assert("agent mode has user stop control", agentSource.includes("agent-stop-btn") && agentSource.includes("agentStoppedByUser") && agentSource.includes("agent_stream_stopped"));
  assert("agent stop cancels stream reader", agentSource.includes("await agentReader.cancel()") && agentSource.includes('t("chat.agentStopped")'));
  assert("agent stop uses translated tooltip", agentSource.includes('t("chat.agentStopTooltip")') && deI18n.includes('"chat.agentStopTooltip"') && enI18n.includes('"chat.agentStopTooltip"'));
  assert("agent handoff can use compact visible user text", agentSource.includes("const agentText = String(text || \"\").trim()") && agentSource.includes("const displayText = String(options?.displayText || agentText).trim()") && agentSource.includes("addMessage(displayText, \"user\")") && agentSource.includes("window.lexa.agentRun(agentText, { worker: options?.worker || \"lexa\" })"));
  assert("hermes worker detector routes direct Hermes commands", sandbox._isHermesWorkerCommand("Hermes oeffne VS Code"));
  assert("hermes worker slash strips visible prefix", sandbox._stripHermesWorkerPrefix("/hermes erstelle app.py") === "erstelle app.py");
  assert("hermes system status detector catches status metrics", sandbox._isHermesSystemStatusRequest("pruefe Systemstatus CPU RAM Speicherplatz"));
  assert("hermes system status guard rejects zero-step completions", agentSource.includes("const hermesSystemStatusGuard") && agentSource.includes('t("chat.hermesSystemStatusNoTool")') && agentSource.includes('action: "system_info"') && agentSource.includes("finalSteps.length === 0") && deI18n.includes('"chat.hermesSystemStatusNoTool"') && enI18n.includes('"chat.hermesSystemStatusNoTool"'));
  assert("agent run exposes busy live status", agentSource.includes('msgEl.setAttribute("aria-busy", "true")') && agentSource.includes('summaryEl.setAttribute("role", "status")') && agentSource.includes('summaryEl.setAttribute("aria-live", "polite")') && agentSource.includes('t("chat.agentStarting")') && agentSource.includes('t("chat.agentWorking")') && agentSource.includes('t("chat.agentCompleted")') && agentSource.includes('msgEl.removeAttribute("aria-busy")') && deI18n.includes('"chat.agentStarting"') && enI18n.includes('"chat.agentStarting"'));
  assert("agent steps expose list semantics", agentSource.includes('stepsContainer.setAttribute("role", "list")') && agentSource.includes('stepsContainer.setAttribute("aria-label", t("chat.agentStepsLabel"))') && agentSource.includes('stepEl.setAttribute("role", "listitem")') && agentSource.includes('stepEl.setAttribute("aria-label", readableLabel)') && deI18n.includes('"chat.agentStepsLabel"') && enI18n.includes('"chat.agentStepsLabel"'));
  assert("agent step updates stay scoped to the current agent message", agentSource.includes('stepsContainer.querySelectorAll(".agent-step")') && agentSource.includes("dataset.agentStepIndex") && agentSource.includes("agentRunDomId") && !agentSource.includes("document.getElementById(`agent-step-${"));
  assert("agent steps keep readable labels separate from hidden technical detail", src.includes("function agentStepDisplayLabel") && src.includes("function agentStepTechnicalLabel") && src.includes("function agentStepActionLabel") && src.includes('label.textContent = readableLabel') && src.includes("stepEl.dataset.technicalLabel = technicalLabel") && src.includes("stepEl.title = readableLabel") && src.includes('"chat.agentStepWithDetail"') && deI18n.includes('"chat.agentStepPersonalOs"') && enI18n.includes('"chat.agentStepPersonalOs"'));
  assert("desktop engine steps do not show boolean params as labels", src.includes("function agentStepText") && src.includes('"window", "window_title", "text", "target"') && src.includes('name === "desktop_engine_observe"') && src.includes('"Desktop beobachten"') && src.includes('["string", "number"].includes(typeof value)') && deI18n.includes('"chat.agentStepDesktopObserve"') && enI18n.includes('"chat.agentStepDesktopStatus"'));
  assert("hermes desktop steps have specific readable labels", src.includes('name === "screen_read_text" || name === "screen_ocr"') && src.includes('name === "ui_tree"') && src.includes('name === "ui_find"') && src.includes('name === "hermes_desktop_task"') && src.includes('action === "ui_tree"') && src.includes('action === "ui_find"') && deI18n.includes('"chat.agentStepScreenRead"') && deI18n.includes('"chat.agentStepUiTree"') && deI18n.includes('"chat.agentStepUiFind"') && deI18n.includes('"chat.agentStepHermesDesktop"') && enI18n.includes('"chat.agentStepScreenRead"') && enI18n.includes('"chat.agentStepHermesDesktop"'));
  assert("hermes desktop step detail compacts pasted approval chains", src.includes("function compactHermesDesktopMessage") && src.includes('String(action || "") === "hermes_desktop_task"') && src.includes('agentStepParamSummary(step?.params, step?.action)') && src.includes('(?:ja|yes|ok|okay)'));
  assert("agent steps add outcome badges", src.includes("function agentStepOutcomeKind") && src.includes("function renderAgentStepOutcome") && agentSource.includes("renderAgentStepOutcome(stepEl, normalizedStep)") && src.includes("chat.agentOutcome${suffix}") && deI18n.includes('"chat.agentOutcomeFound"') && enI18n.includes('"chat.agentOutcomeFound"') && deI18n.includes('"chat.agentOutcomeBlocked"') && enI18n.includes('"chat.agentOutcomeFailed"'));
  assert("agent runs add aggregate outcome summary", src.includes("function agentRunOutcomeCounts") && src.includes("function renderAgentOutcomeSummary") && agentSource.includes('outcomeSummaryEl.className = "agent-outcome-summary"') && agentSource.includes("recordAgentStepOutcome(step, agentOutcomeCounts, agentStepOutcomes)") && agentSource.includes("renderAgentOutcomeSummary(outcomeSummaryEl, agentOutcomeCounts)") && agentSource.includes("let finalSteps = Array.isArray(run.steps) ? run.steps : []") && agentSource.includes("const finalOutcomeCounts = finalSteps.length") && agentSource.includes("renderAgentOutcomeSummary(outcomeSummaryEl, finalOutcomeCounts)") && deI18n.includes('"chat.agentOutcomeSummaryLabel"') && enI18n.includes('"chat.agentOutcomeSummaryLabel"'));
  assert("agent runs add structured completion panel", src.includes("function renderAgentCompletionPanel") && src.includes("function agentOutcomeTotal") && agentSource.includes('completionEl.setAttribute("role", "group")') && agentSource.includes("renderAgentCompletionPanel(completionEl, finalOutcomeCounts") && deI18n.includes('"chat.agentCompletionReached"') && enI18n.includes('"chat.agentCompletionNext"'));
  assert("agent runs can draft continuation prompts", src.includes("function agentCompletionContinuePrompt") && src.includes("function startAgentCompletionContinue") && agentSource.includes("agentCompletionContinuePrompt({ ...run, steps: finalSteps, summary: finalSummary }, finalOutcomeCounts") && src.includes('continueButton.className = "agent-completion-continue-btn"') && src.includes("continueButton._lexaAgentContinuePrompt = options.continuePrompt.text") && src.includes("chatInput.setSelectionRange(cursorStart, cursorStart)") && src.includes('flashIconButton(btn, "\\u2713", "\\u21AA", 1500, t("chat.agentCompletionContinueStarted"))') && deI18n.includes('"chat.agentCompletionContinueButton"') && enI18n.includes('"chat.agentCompletionContinueBoundary"'));
  assert("agent-mode detector routes research briefs", sandbox._needsAgentMode("erstelle einen quellenbasierten research brief zu Lexa"));
  assert("agent-mode detector routes source-backed analyses", sandbox._needsAgentMode("erstelle eine analyse mit quellen und belegen zu Lexa"));
  assert("agent-mode detector routes workspace drafts", sandbox._needsAgentMode("baue einen workspace draft als markdown kontext"));
  assert("agent-mode detector routes reversed workspace drafts", sandbox._needsAgentMode("erstelle einen markdown entwurf als workspace fuer Lexa"));
  assert("agent-mode detector routes context packs", sandbox._needsAgentMode("erstelle ein Personal OS Context Pack fuer Lexa"));
  assert("agent-mode detector routes draft reviews", sandbox._needsAgentMode("pruefe die pending drafts zur freigabe"));
  assert("agent-mode detector routes draft reviews with umlauts", sandbox._needsAgentMode("pr\u00fcfe die pending drafts zur freigabe"));
  assert("agent-mode detector routes sequential umlaut wording", sandbox._needsAgentMode("\u00f6ffne Notepad und anschlie\u00dfend Chrome"));
  assert("agent-mode detector routes skill drafts", sandbox._needsAgentMode("entwirf einen Lexa Skill als Markdown Vorlage"));
  assert("agent-mode detector routes deep think decisions", sandbox._needsAgentMode("erstelle einen entscheidungsbrief mit optionen und risiken"));
  assert("agent-mode detector routes deep think with umlauts", sandbox._needsAgentMode("abw\u00e4g optionen und risiken fuer Lexa sauber ab"));
  assert("agent-mode detector routes ship checks", sandbox._needsAgentMode("release check fuer Lexa vor dem publish"));
  assert("composer slash alias expands research workflow", sandbox.expandComposerSlashAlias("/research Lexa").includes("source-backed research brief") && sandbox.expandComposerSlashAlias("/research Lexa").includes("Lexa"));
  assert("composer short alias expands research workflow", sandbox.expandComposerSlashAlias("/rb Lexa").includes("source-backed research brief") && sandbox.expandComposerSlashAlias("/rb Lexa").includes("Lexa"));
  assert("composer dashed alias expands research workflow", sandbox.expandComposerSlashAlias("/deep-research Lexa").includes("source-backed research brief") && sandbox.expandComposerSlashAlias("/deep_research Lexa").includes("Lexa"));
  assert("composer unique prefix alias expands research workflow", sandbox.expandComposerSlashAlias("/deep-res Lexa").includes("source-backed research brief") && sandbox.expandComposerSlashAlias("/deep_res Lexa").includes("Lexa"));
  assert("composer slash alias expands workspace workflow", sandbox.expandComposerSlashAlias("/workspace Lexa roadmap").includes("workspace draft") && sandbox.expandComposerSlashAlias("/workspace Lexa roadmap").includes("Lexa roadmap"));
  assert("composer short alias expands workspace workflow", sandbox.expandComposerSlashAlias("/ws Lexa roadmap").includes("workspace draft") && sandbox.expandComposerSlashAlias("/ws Lexa roadmap").includes("Lexa roadmap"));
  assert("composer unique prefix alias expands workspace workflow", sandbox.expandComposerSlashAlias("/work Lexa roadmap").includes("workspace draft") && sandbox.expandComposerSlashAlias("/work Lexa roadmap").includes("Lexa roadmap"));
  sandbox.setMaxLength(4000);
  assert("workspace handoff prompt wraps answers as artifacts", sandbox.workspaceDraftPromptFromText("Alpha answer").includes("workspace draft") && sandbox.workspaceDraftPromptFromText("Alpha answer").includes("Source answer:\nAlpha answer"));
  const longWorkspaceSource = `WORKSPACE-HEAD ${"x".repeat(5000)} WORKSPACE-TAIL`;
  const clippedWorkspacePrompt = sandbox.workspaceDraftPromptFromText(longWorkspaceSource);
  assert("workspace handoff prompt clips long answers within chat limit", clippedWorkspacePrompt.includes("[Source clipped for chat handoff.]") && clippedWorkspacePrompt.length <= 4000);
  assert("workspace handoff clipped source preserves answer head and tail", clippedWorkspacePrompt.includes("WORKSPACE-HEAD") && clippedWorkspacePrompt.includes("WORKSPACE-TAIL"));
  assert("workspace handoff prompt skips empty source", sandbox.workspaceDraftPromptFromText(null) === "");
  assert("workspace handoff prompt preserves multiline special text", sandbox.workspaceDraftPromptFromText("Line <one>\nLine & two").includes("Source answer:\nLine <one>\nLine & two"));
  sandbox.setMaxLength(4000);
  const continuePrompt = sandbox.continuePromptFromText("Alpha answer");
  assert("continue-from-answer prompt preserves source and cursor", continuePrompt.text.includes("chat.continueFromAnswerPrefix") && continuePrompt.text.includes("chat.continueFromAnswerNextRequest") && continuePrompt.text.includes("chat.continueFromAnswerSourceLabel:\nAlpha answer") && continuePrompt.cursorStart > 0);
  sandbox.setMaxLength(1200);
  const longContinueSource = `CONTINUE-HEAD ${"x".repeat(5000)} CONTINUE-TAIL`;
  const clippedContinuePrompt = sandbox.continuePromptFromText(longContinueSource);
  assert("continue-from-answer prompt clips long source context", clippedContinuePrompt.text.includes("chat.continueFromAnswerClipMarker") && clippedContinuePrompt.text.length <= 984);
  assert("continue-from-answer clipped source preserves answer head and tail", clippedContinuePrompt.text.includes("CONTINUE-HEAD") && clippedContinuePrompt.text.includes("CONTINUE-TAIL"));
  const emptyContinuePrompt = sandbox.continuePromptFromText(undefined);
  assert("continue-from-answer prompt skips empty source", emptyContinuePrompt.text === "" && emptyContinuePrompt.cursorStart === 0);
  assert("continue-from-answer prompt preserves multiline special text", sandbox.continuePromptFromText("Line <one>\nLine & two").text.includes("Line <one>\nLine & two"));
  sandbox.setMaxLength(4000);
  const verifyPrompt = sandbox.verifyAnswerPromptFromText("Alpha answer");
  assert("verify-answer prompt wraps answers as source-backed research", verifyPrompt.includes("source-backed research") && verifyPrompt.includes("checkable claims") && verifyPrompt.includes("Source answer:") && verifyPrompt.includes("Alpha answer"));
  sandbox.setMaxLength(1200);
  const longVerifySource = `VERIFY-HEAD ${"x".repeat(5000)} VERIFY-TAIL`;
  const clippedVerifyPrompt = sandbox.verifyAnswerPromptFromText(longVerifySource);
  assert("verify-answer prompt clips long answers within chat limit", clippedVerifyPrompt.includes("chat.verifyAnswerClipMarker") && clippedVerifyPrompt.length <= 1200);
  assert("verify-answer clipped source preserves answer head and tail", clippedVerifyPrompt.includes("VERIFY-HEAD") && clippedVerifyPrompt.includes("VERIFY-TAIL"));
  assert("verify-answer prompt skips empty source", sandbox.verifyAnswerPromptFromText(" ") === "");
  assert("verify-answer prompt preserves multiline special text", sandbox.verifyAnswerPromptFromText("Line <one>\nLine & two").includes("Source answer:\nLine <one>\nLine & two"));
  const exportedMarkdown = sandbox.messageExportMarkdownFromText("Alpha answer", { title: "Lexa Note", exportedAt: "2026-05-18T04:58:14.627Z" });
  assert("message markdown export keeps source and metadata", exportedMarkdown.includes("# Lexa Note") && exportedMarkdown.includes("Exported: 2026-05-18T04:58:14.627Z") && exportedMarkdown.includes("Source: Lexa chat") && exportedMarkdown.endsWith("Alpha answer\n"));
  assert("message markdown export skips empty source", sandbox.messageExportMarkdownFromText("   ") === "");
  const defaultExportedMarkdown = sandbox.messageExportMarkdownFromText("Body", { title: "   ", exportedAt: "2026-05-18T04:58:14.627Z" });
  assert("message markdown export falls back to default title", defaultExportedMarkdown.startsWith("# Lexa Answer\n\n- Exported: 2026-05-18T04:58:14.627Z"));
  assert("message markdown export preserves multiline source", sandbox.messageExportMarkdownFromText("Line 1\n\nLine 2", { exportedAt: "2026-05-18T04:58:14.627Z" }).endsWith("Line 1\n\nLine 2\n"));
  assert("message markdown export uses stable filename", sandbox.messageExportFilename(new Date("2026-05-18T04:58:14.627Z")) === "lexa-answer-2026-05-18T04-58-14-627Z.md");
  const persistedMessage = { dataset: { persistText: "**Bold**\\n\\n```js\\nconst x = 1;\\n```" }, querySelector() { return { textContent: "rendered fallback" }; } };
  assert("message text helper prefers raw persisted markdown", sandbox.getMessagePersistText(persistedMessage).includes("```js") && !sandbox.getMessagePersistText(persistedMessage).includes("rendered fallback"));
  const messageToStore = { dataset: {}, querySelector() { return null; } };
  sandbox.setMessagePersistText(messageToStore, "  ## Stored markdown  ");
  assert("message text helper stores trimmed raw markdown", messageToStore.dataset.persistText === "## Stored markdown" && sandbox.getMessagePersistText(messageToStore) === "## Stored markdown");
  assert("composer slash alias expands context workflow", sandbox.expandComposerSlashAlias("/context Lexa roadmap").includes("context pack") && sandbox.expandComposerSlashAlias("/context Lexa roadmap").includes("Lexa roadmap"));
  assert("composer short alias expands context workflow", sandbox.expandComposerSlashAlias("/ctx Lexa roadmap").includes("context pack") && sandbox.expandComposerSlashAlias("/ctx Lexa roadmap").includes("Lexa roadmap"));
  assert("composer slash alias expands draft review workflow", sandbox.expandComposerSlashAlias("/review Lexa drafts").includes("pending drafts") && sandbox.expandComposerSlashAlias("/review Lexa drafts").includes("Lexa drafts"));
  assert("composer short alias expands draft review workflow", sandbox.expandComposerSlashAlias("/rv Lexa drafts").includes("pending drafts") && sandbox.expandComposerSlashAlias("/rv Lexa drafts").includes("Lexa drafts"));
  assert("composer slash alias expands skill workflow", sandbox.expandComposerSlashAlias("/skill research").includes("Lexa Skill") && sandbox.expandComposerSlashAlias("/skill research").includes("research"));
  assert("composer short alias expands skill workflow", sandbox.expandComposerSlashAlias("/sk research").includes("Lexa Skill") && sandbox.expandComposerSlashAlias("/sk research").includes("research"));
  assert("composer slash alias expands deep think workflow", sandbox.expandComposerSlashAlias("/think roadmap").includes("Deep Think") && sandbox.expandComposerSlashAlias("/think roadmap").includes("roadmap"));
  assert("composer short alias expands deep think workflow", sandbox.expandComposerSlashAlias("/dt roadmap").includes("Deep Think") && sandbox.expandComposerSlashAlias("/dt roadmap").includes("roadmap"));
  assert("composer slash alias expands ship check workflow", sandbox.expandComposerSlashAlias("/ship Lexa").includes("Ship Check") && sandbox.expandComposerSlashAlias("/ship Lexa").includes("Lexa"));
  assert("composer short alias expands ship check workflow", sandbox.expandComposerSlashAlias("/rl Lexa").includes("Ship Check") && sandbox.expandComposerSlashAlias("/rl Lexa").includes("Lexa"));
  assert("composer ambiguous prefix alias stays unexpanded", sandbox.composerCommandForAlias("re", { allowPrefix: true }) === null);
  assert("composer alias key normalizes separators and umlauts", sandbox.composerCommandAliasKey("Mehr-Schritt") === "mehrschritt" && sandbox.composerCommandAliasKey("deep_research") === "deepresearch");
  assert("composer command text uses fallback when no i18n key is configured", sandbox.composerCommandText({ fallbackLabel: "Fallback Label" }, "label") === "Fallback Label");
  assert("composer command text handles empty command", sandbox.composerCommandText(null, "label") === "");
  assert("composer command icon svg falls back to command icon", sandbox.composerCommandIconSvg("missing").includes("<svg") && sandbox.composerCommandIconSvg("missing").includes('M18 6 6 18'));
  const researchCommand = sandbox.composerCommands.find((command) => command.id === "research");
  const workspaceCommand = sandbox.composerCommands.find((command) => command.id === "workspace");
  const contextCommand = sandbox.composerCommands.find((command) => command.id === "context");
  const reviewCommand = sandbox.composerCommands.find((command) => command.id === "review");
  const skillCommand = sandbox.composerCommands.find((command) => command.id === "skill");
  const thinkCommand = sandbox.composerCommands.find((command) => command.id === "think");
  const shipCommand = sandbox.composerCommands.find((command) => command.id === "ship");
  assert("composer hint shows research short alias", sandbox.composerCommandHintText(researchCommand) === "/research /rb");
  assert("composer hint shows workspace short alias", sandbox.composerCommandHintText(workspaceCommand) === "/workspace /ws");
  assert("composer hint shows context short alias", sandbox.composerCommandHintText(contextCommand) === "/context /ctx");
  assert("composer hint shows draft review short alias", sandbox.composerCommandHintText(reviewCommand) === "/review /rv");
  assert("composer hint shows skill short alias", sandbox.composerCommandHintText(skillCommand) === "/skill /sk");
  assert("composer hint shows deep think short alias", sandbox.composerCommandHintText(thinkCommand) === "/think /dt");
  assert("composer hint shows ship check short alias", sandbox.composerCommandHintText(shipCommand) === "/ship /rl");
  assert("composer search ranks research alias first", sandbox.composerCommandSearchItems("r")[0]?.id === "research");
  assert("composer search ranks workspace alias first", sandbox.composerCommandSearchItems("w")[0]?.id === "workspace");
  assert("composer search ranks context alias first", sandbox.composerCommandSearchItems("c")[0]?.id === "context");
  assert("composer search ranks draft review alias first", sandbox.composerCommandSearchItems("rv")[0]?.id === "review");
  assert("composer search ranks skill alias first", sandbox.composerCommandSearchItems("sk")[0]?.id === "skill");
  assert("composer search ranks deep think alias first", sandbox.composerCommandSearchItems("dt")[0]?.id === "think");
  assert("composer search ranks ship alias first", sandbox.composerCommandSearchItems("rl")[0]?.id === "ship");
  assert("composer search ranks screen alias first", sandbox.composerCommandSearchItems("s")[0]?.id === "screen");
  assert("composer search ranks voice alias first", sandbox.composerCommandSearchItems("v")[0]?.id === "voice");

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("erstelle einen quellenbasierten research brief zu Lexa");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("natural research prompt routes to agent before loading", state.loading === false && state.events.some((event) => event[0] === "agent"));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("erstelle eine analyse mit quellen und belegen zu Lexa");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("natural source analysis prompt routes to agent before loading", state.loading === false && state.events.some((event) => event[0] === "agent"));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("/research Lexa");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("slash research alias routes expanded workflow to agent", state.loading === false && state.events.some((event) => event[0] === "agent" && event[1].includes("source-backed research brief") && event[1].includes("Lexa")));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("/rb Lexa");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("short research alias routes expanded workflow to agent", state.loading === false && state.events.some((event) => event[0] === "agent" && event[1].includes("source-backed research brief") && event[1].includes("Lexa")));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("baue einen workspace draft als markdown kontext");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("natural workspace prompt routes to agent before loading", state.loading === false && state.events.some((event) => event[0] === "agent"));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("erstelle einen markdown entwurf als workspace fuer Lexa");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("natural reversed workspace prompt routes to agent before loading", state.loading === false && state.events.some((event) => event[0] === "agent"));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("/workspace Lexa roadmap");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("slash workspace alias routes expanded workflow to agent", state.loading === false && state.events.some((event) => event[0] === "agent" && event[1].includes("workspace draft") && event[1].includes("Lexa roadmap")));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("/ws Lexa roadmap");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("short workspace alias routes expanded workflow to agent", state.loading === false && state.events.some((event) => event[0] === "agent" && event[1].includes("workspace draft") && event[1].includes("Lexa roadmap")));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("erstelle ein Personal OS Context Pack fuer Lexa");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("natural context pack prompt routes to agent before loading", state.loading === false && state.events.some((event) => event[0] === "agent"));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("/ctx Lexa roadmap");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("short context alias routes expanded workflow to agent", state.loading === false && state.events.some((event) => event[0] === "agent" && event[1].includes("context pack") && event[1].includes("Lexa roadmap")));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("pruefe die pending drafts zur freigabe");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("natural draft review prompt routes to agent before loading", state.loading === false && state.events.some((event) => event[0] === "agent"));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("/rv Lexa drafts");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("short draft review alias routes expanded workflow to agent", state.loading === false && state.events.some((event) => event[0] === "agent" && event[1].includes("pending drafts") && event[1].includes("Lexa drafts")));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("entwirf einen Lexa Skill als Markdown Vorlage");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("natural skill draft prompt routes to agent before loading", state.loading === false && state.events.some((event) => event[0] === "agent"));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("/sk research");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("short skill alias routes expanded workflow to agent", state.loading === false && state.events.some((event) => event[0] === "agent" && event[1].includes("Lexa Skill") && event[1].includes("research")));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("erstelle einen entscheidungsbrief mit optionen und risiken");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("natural deep think prompt routes to agent before loading", state.loading === false && state.events.some((event) => event[0] === "agent"));
  assert("natural deep think prompt recognizes abwaegung with umlaut", sandbox._needsAgentMode("abwägung der optionen und risiken fuer Lexa") === true);
  assert("natural deep think prompt recognizes ascii abwaegung", sandbox._needsAgentMode("abwaegung der optionen und risiken fuer Lexa") === true);

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("/dt roadmap");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("short deep think alias routes expanded workflow to agent", state.loading === false && state.events.some((event) => event[0] === "agent" && event[1].includes("Deep Think") && event[1].includes("roadmap")));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("release check fuer Lexa vor dem publish");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("natural ship check prompt routes to agent before loading", state.loading === false && state.events.some((event) => event[0] === "agent"));

  sandbox.reset();
  sandbox.setMaxLength(500);
  sandbox.setInput("/rl Lexa");
  await sandbox.sendMessage();
  state = sandbox.state();
  assert("short ship alias routes expanded workflow to agent", state.loading === false && state.events.some((event) => event[0] === "agent" && event[1].includes("Ship Check") && event[1].includes("Lexa")));

  const showTypingSource = extractFn(src, "showTyping");
  const sendSource = extractFn(src, "sendMessage");
  assert("normal chat stop marks a user abort", showTypingSource.includes('_lexaStreamAbortReason = "user"') && showTypingSource.includes('t("chat.stopResponseTooltip")'));
  assert("normal chat stream distinguishes stop from timeout", sendSource.includes("streamStoppedByUser") && sendSource.includes('t("chat.responseStopped")') && sendSource.includes('_lexaStreamAbortReason = "timeout"'));
  assert("normal chat stop labels are translated", deI18n.includes('"chat.stopResponseButton"') && enI18n.includes('"chat.stopResponseButton"') && deI18n.includes('"chat.responseStopped"') && enI18n.includes('"chat.responseStopped"'));
  assert("normal chat HTTP error clears stream timeout", sendSource.includes("clearTimeout(_streamTimeout);") && sendSource.includes("window._lexaStreamAbort = null"));
  assert("normal chat HTTP errors persist and re-enable answer actions", sendSource.includes("setMessagePersistText(msgEl, errMsg);") && sendSource.includes("copyBtn.disabled = false;\n      memoryBtn.disabled = false;\n      workspaceBtn.disabled = false;\n      continueBtn.disabled = false;\n      verifyBtn.disabled = false;\n      exportBtn.disabled = false;\n      regenBtn.disabled = false;") && sendSource.includes("saveChatHistory();\n      saveCurrentConversation();\n      return;"));
  assert("normal chat stream includes local auth cookie credentials", sendSource.includes('fetch(`${window.lexa.API_BASE}/chat/stream`, {') && sendSource.includes('credentials: "include"'));
  assert("normal chat stream consumes final unterminated SSE line", sendSource.includes("const handleStreamData =") && sendSource.includes("buffer += decoder.decode();") && sendSource.includes("chatStreamFinalLines(buffer)") && sendSource.includes("handleStreamData(data)"));

  const voiceStartStatusSource = extractFn(src, "voiceStart");
  const voiceProcessStatusSource = extractFn(src, "voiceProcess");
  const voiceStreamChatStatusSource = extractFn(src, "voiceStreamChat");
  const voiceTTSNextStatusSource = extractFn(src, "voiceTTSNext");
  const voiceStatusUpdateSource = extractFn(src, "voiceStatusBarUpdate");
  const voiceStatusResetSource = extractFn(src, "voiceStatusBarReset");
  assert("voice chat stream includes local auth cookie credentials", voiceStreamChatStatusSource.includes('fetch(`${API}/chat/stream`, {') && voiceStreamChatStatusSource.includes('credentials: "include"'));
  const voiceSpeechPendingSource = extractFn(src, "voiceSpeechPending");
  const voiceResetIfNoSpeechSource = extractFn(src, "voiceStatusBarResetIfNoSpeechPending");
  const voiceTtsFindSplitSource = extractFn(src, "voiceTTSFindSplit");
  const voiceTtsChunkSource = extractFn(src, "voiceTTSChunkText");
  const voiceTtsFlushSource = extractFn(src, "voiceTTSFlushBuffer");
  assert("voice status bar helper updates shared UI", src.includes("function voiceStatusBarUpdate") && src.includes("VoiceStatusBar.show()"));
  assert("orb voice surface hides status chrome and drives the orb", src.includes("function voiceUsesOrbSurface") && src.includes("function voiceEndOrbSurface") && src.includes("window.__lexaOrbVoiceActive") && src.includes("voiceSetOrbConversationState(safeState") && src.includes("voiceHideStatusBar()"));
  assert("voice status reset ends the orb-only surface", voiceStatusResetSource.includes("window.__lexaOrbVoiceActive") && voiceStatusResetSource.includes("voiceEndOrbSurface()"));
  assert("voice status bar reset clears stale transcript chrome", voiceStatusResetSource.includes('setTranscript("")') && voiceStatusResetSource.includes('setProvider("")') && voiceStatusResetSource.includes("setLatency(0)"));
  assert("voice status reset waits for pending speech", voiceSpeechPendingSource.includes('LexaState.get("ttsEnabled")') && voiceSpeechPendingSource.includes("Voice.ttsPlaying") && voiceSpeechPendingSource.includes("Voice.ttsQueue.length") && voiceResetIfNoSpeechSource.includes("if (!voiceSpeechPending()) voiceStatusBarReset()"));
  assert("voice recording sets localized listening provider", voiceStartStatusSource.includes('state: "listening"') && voiceStartStatusSource.includes('voiceUiText("chat.voiceProviderRecording"') && deI18n.includes('"chat.voiceProviderRecording"') && enI18n.includes('"chat.voiceProviderRecording"'));
  assert("voice processing exposes localized processing status", voiceProcessStatusSource.includes('voiceUiText("chat.voiceProviderProcessing"') && voiceProcessStatusSource.includes('voiceUiText("chat.voiceTranscribing"'));
  assert("voice stream exposes response status and resets when no TTS will speak", voiceStreamChatStatusSource.includes('voiceUiText("chat.voiceProviderResponse"') && voiceStreamChatStatusSource.includes("voiceStatusBarResetIfNoSpeechPending()"));
  assert("voice stream uses configured API base and cleans up timeout/reader", src.includes("function voiceApiBase()") && voiceStreamChatStatusSource.includes("const API = voiceApiBase()") && voiceStreamChatStatusSource.includes("let timeout = null") && voiceStreamChatStatusSource.includes("let reader = null") && voiceStreamChatStatusSource.includes("finally") && voiceStreamChatStatusSource.includes("await reader.cancel()"));
  assert("voice stream shares safe SSE parser and consumes final tail", voiceStreamChatStatusSource.includes("const handleVoiceStreamData =") && voiceStreamChatStatusSource.includes("chatStreamBufferedLines(buffer)") && voiceStreamChatStatusSource.includes("chatStreamFinalLines(buffer)") && voiceStreamChatStatusSource.includes("parseChatStreamDataLine(line)") && voiceStreamChatStatusSource.includes("if (d.reply && !fullText) fullText = d.reply"));
  assert("voice stream flushes TTS through bounded chunker", src.includes("VOICE_TTS_MAX_CHUNK_CHARS") && voiceStreamChatStatusSource.includes("voiceTTSFlushBuffer(ttsBuf)") && voiceStreamChatStatusSource.includes("voiceTTSFlushBuffer(ttsBuf, true)") && voiceTtsFlushSource.includes("voiceTTSEnqueue(speakable.trim())"));
  assert("voice stream flushes final TTS buffer after reader close", voiceStreamChatStatusSource.includes("ttsBuf = voiceTTSFlushBuffer(ttsBuf, true);\n    if (timeout)"));
  const ttsChunkSandbox = new Function(`${voiceTtsFindSplitSource}\n${voiceTtsChunkSource}\nreturn { voiceTTSChunkText };`)();
  const longTtsChunks = ttsChunkSandbox.voiceTTSChunkText("Alpha ".repeat(80), 80);
  assert("voice TTS chunker bounds long speech segments", longTtsChunks.length > 1 && longTtsChunks.every((chunk) => chunk.length <= 80 && chunk === chunk.trim()));
  assert("voice TTS exposes speaking status without visible status chrome", voiceTTSNextStatusSource.includes('state: "speaking"') && voiceTTSNextStatusSource.includes('voiceUiText("chat.voiceProviderSpeech"') && voiceTTSNextStatusSource.includes('voiceUiText("chat.voiceSpeakingResponse"') && src.includes('safeState === "speaking"') && src.includes("voiceStatusBarReset({ hide: true })") && src.includes("VOICE_TTS_PLAYBACK_RATE"));
  assert("voice TTS drives the main orb speaking state", src.includes("function voiceSetOrbConversationState") && voiceTTSNextStatusSource.includes('voiceSetOrbConversationState("speaking")') && voiceTTSNextStatusSource.includes("voiceSetOrbConversationState(null)"));

  const persistTextSource = extractFn(src, "getMessagePersistText");
  const persistableSource = extractFn(src, "isPersistableChatMessage");
  const saveChatSource = extractFn(src, "saveChatHistory");
  const autoSaveSource = extractFn(src, "autoSaveConversation");
  const saveCurrentSource = extractFn(src, "saveCurrentConversation");
  const loadHistorySource = extractFn(src, "loadChatHistory");
  const clearChatSource = extractFn(src, "clearChat");
  const trimChatSource = extractFn(src, "trimChatMessages");
  const newConversationSource = extractFn(src, "newConversation");
  const switchSource = extractFn(src, "switchConversation");
  const renderConversationSource = extractFn(src, "renderConversationList");
  const refreshSidebarSource = extractFn(src, "refreshConversationSidebar");
  const loadConversationsSource = extractFn(src, "loadConversations");
  const deleteConversationSource = extractFn(src, "deleteConversation");
  const autoTitleSource = extractFn(src, "autoTitleConversation");
  assert("chat persistence prefers raw markdown before rendered text", persistTextSource.includes("dataset?.persistText") && persistTextSource.includes('querySelector(".agent-summary")'));
  assert("chat messages store raw markdown for reuse", src.includes("setMessagePersistText(msg, text)") && src.includes("setMessagePersistText(msgEl, fullText || textEl.textContent)") && src.includes("setMessagePersistText(msgEl, finalSummary)"));
  assert("agent run metadata survives reload without entering backend messages", src.includes("function normalizeAgentRunMeta") && src.includes("function setMessageAgentRunMeta") && src.includes("function saveAgentRunMetaForConversation") && src.includes("function createAgentRunMetaResolver") && src.includes("function renderPersistedConversationMessages") && src.includes("renderPersistedAgentRunMeta(body, agentRunMeta, text)") && saveChatSource.includes("getMessageAgentRunMeta(msg)") && saveChatSource.includes("messages.push(meta ? { text, type, meta } : { text, type })") && saveCurrentSource.includes("const convId = LexaState.get(\"currentConversationId\")") && saveCurrentSource.includes("saveAgentRunMetaForConversation(convId)") && autoSaveSource.includes("const convId = LexaState.get(\"currentConversationId\")") && autoSaveSource.includes("saveAgentRunMetaForConversation(convId)") && saveCurrentSource.includes("messages.push({ role, content: text })") && !saveCurrentSource.includes("meta }"));
  assert("chat persistence skips only transient typing messages", persistableSource.includes("typing-message"));
  assert("local chat cache uses shared persisted text helper", saveChatSource.includes("getMessagePersistText(msg)"));
  assert("conversation autosave uses shared persisted text helper and stable conversation id", autoSaveSource.includes("const convId = LexaState.get(\"currentConversationId\")") && autoSaveSource.includes("getMessagePersistText(msg)") && autoSaveSource.includes("await window.lexa.conversationUpdate(convId, { messages })") && saveCurrentSource.includes("getMessagePersistText(msg)"));
  assert("conversation autosave pauses during conversation switching", chatBundleSrc.includes("let _conversationSwitchInFlight = 0") && autoSaveSource.includes("if (_conversationSwitchInFlight > 0) return") && switchSource.includes("_conversationSwitchInFlight += 1") && switchSource.includes("_conversationSwitchInFlight = Math.max(0, _conversationSwitchInFlight - 1)"));
  assert("auto title updates local sidebar title by stable string id", src.includes("function updateConversationTitleLocally") && src.includes("String(conv?.id) !== String(convId)") && src.includes("LexaState.set(\"conversationsList\", next)") && autoTitleSource.includes("String(userMessage || \"\").trim()") && autoTitleSource.includes("const generatedTitle = String(result?.title || \"\").trim()") && autoTitleSource.includes("updateConversationTitleLocally(convId, title)"));
  assert("manual conversation changes warn when pre-change save fails", saveCurrentSource.includes("options = null") && saveCurrentSource.includes("const opts = options || {}") && saveCurrentSource.includes("return true") && saveCurrentSource.includes('if (opts.notifyFailure) showToast(t("toast.conversationSaveFailed"), "warning"') && saveCurrentSource.includes("return false") && switchSource.includes("await saveCurrentConversation({ notifyFailure: notify })") && newConversationSource.includes("await saveCurrentConversation({ notifyFailure: true })") && deI18n.includes('"toast.conversationSaveFailed"') && enI18n.includes('"toast.conversationSaveFailed"'));
  assert("conversation save separates update success from sidebar refresh failure", saveCurrentSource.includes("await window.lexa.conversationUpdate(convId, { messages })") && saveCurrentSource.includes("console.warn(\"[Chat] Saved conversation but failed to refresh sidebar:\"") && saveCurrentSource.includes('showToast(t("toast.conversationRefreshFailed"), "warning"') && saveCurrentSource.includes("return true") && deI18n.includes('"toast.conversationRefreshFailed"') && enI18n.includes('"toast.conversationRefreshFailed"'));
  assert("persisted conversation reloads use shared renderer", src.includes("function renderPersistedConversationMessages") && src.includes("const text = msg?.content ?? msg?.text ?? \"\"") && src.includes("msg?.meta || (agentMetaForMessage ? agentMetaForMessage(msg?.role || \"assistant\", text) : null)") && src.includes("const activeConvId = conv.id || convId") && src.includes("renderPersistedConversationMessages(conv.messages, activeConvId)") && src.includes("saveAgentRunMetaForConversation(activeConvId)") && src.includes("renderPersistedConversationMessages(messages, convId)") && src.includes("if (convId) saveAgentRunMetaForConversation(convId)") && switchSource.includes("renderPersistedConversationMessages(messages, convId)") && switchSource.includes("saveAgentRunMetaForConversation(convId)"));
  assert("conversation reload clears old rendered messages before hydrating", src.includes("function clearRenderedChatMessages") && src.includes("querySelectorAll(\".message\").forEach((msg) => msg.remove())") && loadHistorySource.includes("if (conv && !conv.detail && Array.isArray(conv.messages))") && loadHistorySource.includes("clearRenderedChatMessages();\n        LexaState.set(\"currentConversationId\", activeConvId)") && loadHistorySource.includes("if (!Array.isArray(messages)) return;") && loadHistorySource.includes("clearRenderedChatMessages();\n    renderPersistedConversationMessages(messages, convId)") && !loadHistorySource.includes("messages.length === 0"));
  assert("failed conversation switch restores previous active selection", src.includes("function restoreActiveConversationSelection") && chatBundleSrc.includes("function chatSetActiveConversationId") && chatBundleSrc.includes("function clearChatActiveConversationId") && switchSource.includes('const previousConvId = LexaState.get("currentConversationId")') && switchSource.includes("const previousActiveConversation = chatGetActiveConversationId()") && switchSource.includes("restoreActiveConversationSelection(previousConvId, previousActiveConversation)") && switchSource.includes('showToast(t("toast.convNotFound")') && switchSource.includes('console.warn("[Chat] Failed to switch conversation:'));
  assert("chat transcript and active conversation avoid localStorage business state", chatBundleSrc.includes("function chatTransientSetItem") && chatBundleSrc.includes("function chatCachedHistorySnapshot") && saveChatSource.includes("chatTransientSetItem(CHAT_HISTORY_CACHE_KEY") && loadHistorySource.includes("chatGetActiveConversationId()") && !chatBundleSrc.includes('localStorage.setItem("lexa-chat-history"') && !chatBundleSrc.includes('localStorage.getItem("lexa-chat-history"') && !chatBundleSrc.includes('localStorage.setItem("lexa-active-conversation"') && !chatBundleSrc.includes('localStorage.getItem("lexa-active-conversation"'));
  assert("conversation switch ignores stale async loads", chatBundleSrc.includes("let _conversationSwitchSeq = 0") && switchSource.includes("const switchSeq = ++_conversationSwitchSeq") && switchSource.includes("await saveCurrentConversation({ notifyFailure: notify })") && switchSource.includes("if (switchSeq !== _conversationSwitchSeq) return false") && switchSource.includes("const conv = await window.lexa.conversationGet(convId)") && switchSource.includes("await window.lexa.conversationLoad(convId)") && switchSource.includes("restoreActiveConversationSelection(previousConvId, previousActiveConversation)"));
  assert("chat persistence no longer skips first real message", !saveChatSource.includes("i === 0") && !autoSaveSource.includes("i === 0") && !saveCurrentSource.includes("i === 0"));
  assert("clear and switch remove all existing chat messages", clearChatSource.includes("msgs.forEach((m) => m.remove())") && switchSource.includes("msgs.forEach((m) => m.remove())"));
  assert("clear and delete remove transient agent attention state", src.includes("function clearAgentRunLocalStateForConversation") && src.includes("function agentRunStateRemoveItem") && src.includes("agentRunStateRemoveItem(agentRunMetaCacheKey(convId))") && src.includes("agentRunStateRemoveItem(agentRunAttentionResolvedCacheKey(convId))") && src.includes("String(item.convId) !== String(convId)") && clearChatSource.includes("clearAgentRunLocalStateForConversation(convId);\n    markConversationClearedLocally(convId);\n    renderConversationList();") && deleteConversationSource.includes("await window.lexa.conversationDelete(convId)") && deleteConversationSource.includes("clearAgentRunLocalStateForConversation(convId)"));
  assert("new chat removes all existing chat messages", newConversationSource.includes("msgs.forEach((m) => m.remove())"));
  assert("new chat blocks duplicate creates while busy", chatBundleSrc.includes("let _newConversationInFlight = false") && src.includes("function setNewConversationControlsBusy") && newConversationSource.includes("if (_newConversationInFlight) return false") && newConversationSource.includes("setNewConversationControlsBusy(true)") && newConversationSource.includes("} finally {") && newConversationSource.includes("setNewConversationControlsBusy(false)") && newConversationSource.includes("return true"));
  assert("new chat separates create success from setup and refresh failures", newConversationSource.includes("result = await window.lexa.conversationCreate(title)") && newConversationSource.includes("upsertConversationLocally({ id: result.id") && newConversationSource.includes('showToast(t("toast.createError"), "error")') && newConversationSource.includes("await window.lexa.historyClear()") && newConversationSource.includes('showToast(t("toast.newChatHistoryClearFailed"), "warning"') && newConversationSource.includes("await refreshConversationSidebar()") && newConversationSource.includes('showToast(t("toast.newChatRefreshFailed"), "warning"') && src.includes("function upsertConversationLocally") && src.includes("updateConversationCount(next.length)") && deI18n.includes('"toast.newChatHistoryClearFailed"') && enI18n.includes('"toast.newChatRefreshFailed"'));
  assert("conversation list surfaces blocked or failed agent runs with product copy", src.includes("function agentRunAttentionForConversation") && src.includes("function renderAgentAttentionPanel") && src.includes("function agentAttentionDisplayTitle") && src.includes("function agentAttentionStatusSummary") && src.includes('panel.className = "agent-attention-panel"') && renderConversationSource.includes("renderAgentAttentionPanel(container, convList)") && src.includes("btn.addEventListener(\"click\", () => switchConversation(item.convId))") && deI18n.includes('"chat.agentAttentionFallbackTitle"') && enI18n.includes('"chat.agentAttentionStatusBoth"'));
  assert("conversation list can filter blocked or failed agent runs", src.includes("function agentRunAttentionListForConversations") && src.includes("function updateAgentAttentionFilterButton") && src.includes("function toggleAgentAttentionFilter") && src.includes('document.getElementById("agent-attention-filter-btn")') && src.includes('btn.setAttribute("aria-pressed"') && src.includes('LexaState.set("conversationAttentionOnly", next)') && renderConversationSource.includes("const attentionById = new Map") && renderConversationSource.includes("if (attentionOnly && attentionList.length === 0)") && renderConversationSource.includes('LexaState.set("conversationAttentionOnly", false)') && renderConversationSource.includes("const visibleConversations = attentionOnly ? convList.filter") && renderConversationSource.includes('renderAgentAttentionFilterNote(container, attentionList.length)') && chatHistoryUiSrc.includes('badge.className = "conv-agent-attention-badge"') && chatHistoryUiSrc.includes("function conversationListSafePreviewText") && deI18n.includes('"chat.agentAttentionFilterClear"') && enI18n.includes('"chat.agentAttentionPreviewNeedsReview"'));
  assert("conversation list can resolve attention without deleting agent metadata", src.includes("function agentRunAttentionResolvedCacheKey") && src.includes("function agentRunAttentionRecordKey") && src.includes("function agentRunAttentionResolvedKeys") && src.includes("function saveAgentRunAttentionResolvedKeys") && src.includes("if (resolved.has(key)) return") && src.includes("function resolveAgentAttentionForConversation") && src.includes("attention.keys.forEach((key) => resolved.add(key))") && src.includes("saveAgentRunAttentionResolvedKeys(convId, resolved)") && src.includes('resolveBtn.className = "agent-attention-resolve-btn"') && chatHistoryUiSrc.includes('resolveBtn.className = "conv-action-btn conv-agent-resolve-btn"') && deI18n.includes('"chat.agentAttentionResolved"') && enI18n.includes('"chat.agentAttentionResolveLabel"'));
  assert("conversation list can restore recently resolved attention", src.includes("function agentRunAttentionResolvedHistoryCacheKey") && src.includes("function saveAgentRunAttentionResolvedHistory") && src.includes("function agentRunAttentionResolvedHistoryForConversations") && src.includes("function recordAgentAttentionResolution") && src.includes("function removeAgentAttentionResolution") && src.includes("function restoreAgentAttentionHistoryItem") && src.includes("recordAgentAttentionResolution(attention)") && src.includes("removeAgentAttentionResolution(convId, [key])") && renderConversationSource.includes("renderAgentResolvedHistoryPanel(container, convList)") && src.includes('restoreBtn.className = "agent-resolved-restore-btn"') && deI18n.includes('"chat.agentResolvedCounts"') && enI18n.includes('"chat.agentResolvedOpenLabel"'));
  assert("conversation list attention icons avoid raw HTML sinks", src.includes("function createChatAttentionIcon") && src.includes('document.createElementNS(CHAT_ATTENTION_ICON_NS, "svg")') && src.includes("resolveBtn.appendChild(createAgentAttentionResolveIcon())") && src.includes("restoreBtn.appendChild(createAgentAttentionRestoreIcon())") && !src.includes("resolveBtn.innerHTML") && !src.includes("restoreBtn.innerHTML"));
  assert("conversation list prunes old or orphaned resolved attention history", src.includes("function agentRunAttentionResolvedHistoryMaxAgeMs") && src.includes("function agentRunAttentionResolvedHistoryItemHasEvidence") && src.includes("const resolved = agentRunAttentionResolvedKeys(item.convId)") && src.includes("const recordKeys = new Set(records.map((record, index) => agentRunAttentionRecordKey(record, index)))") && src.includes("function pruneAgentRunAttentionResolvedHistoryItems") && src.includes("now - item.resolved_at > maxAgeMs") && src.includes("slice(0, agentRunAttentionResolvedHistoryLimit())") && src.includes("saveAgentRunAttentionResolvedHistory(pruned)"));
  assert("conversation list filters resolved attention history to visible conversations", src.includes("function agentRunAttentionResolvedHistoryForConversations") && src.includes("const ids = new Set((Array.isArray(convList) ? convList : [])") && src.includes("const visible = history.filter((item) => ids.has(String(item.convId)))") && src.includes("if (visible.length !== history.length) saveAgentRunAttentionResolvedHistory(visible)") && src.includes("renderAgentResolvedHistoryPanel(container, convList)"));
  assert("conversation list updates compact agent attention header summary", src.includes("function updateAgentAttentionHeaderSummary") && src.includes('document.getElementById("agent-attention-summary")') && src.includes("const openCount = Array.isArray(attentionList) ? attentionList.length : 0") && src.includes("const resolvedCount = agentRunAttentionResolvedHistoryForConversations(convList).length") && src.includes("const hasConversations = Array.isArray(convList) && convList.length > 0") && src.includes('clear.className = "agent-attention-summary-chip clear"') && src.includes('summary.classList.add("hidden")') && renderConversationSource.includes("updateAgentAttentionHeaderSummary(attentionList, convList)") && deI18n.includes('"chat.agentAttentionHeaderClearLabel"') && enI18n.includes('"chat.agentAttentionHeaderLabel"'));
  assert("chat DOM trimming no longer preserves stale first message", trimChatSource.includes("MAX_DOM_MESSAGES") && trimChatSource.includes("for (let i = 0; i < toRemove; i++)"));
  assert("first-message edit removes the edited message too", !src.includes("Keep greeting (index 0)") && !src.includes("if (i > 0) allMsgs[i].remove()"));
  assert("edit and delete persist only after transcript DOM mutation", src.includes("function persistChatAfterDomMutation") && src.includes("persistChatAfterDomMutation();\n      }\n      showToast(t(\"chat.editLoaded\")") && src.includes("msg.remove();\n        persistChatAfterDomMutation();") && !src.includes("setTimeout(() => msg.remove(), 200);\n      saveChatHistory();"));
  assert("regenerate has guarded prompt recovery and user feedback", chatMessageActionsControllerSrc.includes("function previousUserPromptForMessage") && chatMessageActionsControllerSrc.includes("async function startRegenerateMessage") && chatMessageActionsControllerSrc.includes('showToast(t("chat.uploadBusy"), "warning")') && chatMessageActionsControllerSrc.includes('showToast(t("chat.regenerateMissingPrompt"), "warning", 2200)') && src.includes('regenBtn.addEventListener("click", () => startRegenerateMessage(regenBtn, msg))') && src.includes('regenBtn.addEventListener("click", () => startRegenerateMessage(regenBtn, msgEl, text))') && deI18n.includes('"chat.regenerateMissingPrompt"') && enI18n.includes('"chat.regenerateMissingPrompt"'));
  assert("loaded chat messages put copy before assistant actions", src.includes("header.appendChild(timeSpan);\n  header.appendChild(copyBtn);\n\n  if (!isUser)") && src.includes("header.appendChild(createContinueFromMessageButton())") && src.includes("header.appendChild(createVerifyAnswerButton())") && src.includes("header.appendChild(createMessageActionOverflowMenu(moreActions))"));
  assert("streaming assistant answers enable full action set after completion", src.includes("copyBtn.disabled = true") && src.includes("memoryBtn.disabled = true") && src.includes("const workspaceBtn = createWorkspaceHandoffButton();\n  workspaceBtn.disabled = true") && src.includes("const continueBtn = createContinueFromMessageButton(true)") && src.includes("const verifyBtn = createVerifyAnswerButton(true)") && src.includes("const exportBtn = createMessageExportButton(true)") && src.includes("header.appendChild(createMessageActionOverflowMenu([memoryBtn, workspaceBtn, regenBtn]))") && src.includes("if (getMessagePersistText(msgEl))") && src.includes("verifyBtn.disabled = false;\n      exportBtn.disabled = false;\n      regenBtn.disabled = false;"));
  assert("agent summaries enable copy, memory, continue, and verify actions after completion", src.includes('memoryBtn.addEventListener("click", () => saveMessageAsMemory(memoryBtn, msgEl))') && src.includes("const continueBtn = createContinueFromMessageButton(true)") && src.includes("const verifyBtn = createVerifyAnswerButton(true)") && src.includes("header.appendChild(createMessageActionOverflowMenu([memoryBtn, workspaceBtn]))") && agentDoneSource.includes("copyBtn.disabled = false;") && agentDoneSource.includes("memoryBtn.disabled = false;") && agentDoneSource.includes("continueBtn.disabled = false;") && agentDoneSource.includes("verifyBtn.disabled = false;") && agentSource.includes("copyBtn.disabled = false;") && agentSource.includes("memoryBtn.disabled = false;") && agentSource.includes("workspaceBtn.disabled = false;") && agentSource.includes("exportBtn.disabled = false;") && agentSource.includes("setMessagePersistText(msgEl, summaryEl.textContent)"));
  assert("agent completion resolve uses local attention keys", src.includes("function startAgentCompletionResolve") && src.includes("agentCompletionAttentionKeyFromText(text)") && src.includes("getMessageAgentRunMeta(msg)") && src.includes("const hasAttention = Number(counts?.failed || 0) > 0 || Number(counts?.blocked || 0) > 0") && src.includes("saveAgentRunMetaForConversation(convId)") && src.includes("resolved.add(key)") && src.includes("markAgentCompletionResolveButtonDone(btn)") && src.includes('resolveButton.className = "agent-completion-resolve-btn"') && src.includes("attentionResolved: isAgentCompletionAttentionResolved") && deI18n.includes('"chat.agentCompletionResolveDone"') && enI18n.includes('"chat.agentCompletionResolveTooltip"'));
  assert("agent completion resolve can be undone locally", src.includes("function undoAgentCompletionResolve") && src.includes("resolved.delete(key)") && src.includes("markAgentCompletionResolveButtonOpen(btn)") && src.includes('if (btn?.dataset?.resolved === "true") return undoAgentCompletionResolve(btn)') && src.includes('btn.dataset.resolved = "true"') && src.includes('btn.dataset.resolved = "false"') && src.includes('showToast(t("chat.agentAttentionRestored")') && deI18n.includes('"chat.agentCompletionResolveUndoTooltip"') && enI18n.includes('"chat.agentCompletionResolveUndoButton"'));
  assert("conversation sidebar refresh is shared", refreshSidebarSource.includes("window.lexa.conversations()") && refreshSidebarSource.includes("renderConversationList()"));
  assert("saved conversations refresh sidebar counts", saveCurrentSource.includes("await refreshConversationSidebar()"));
  assert("cleared conversations refresh sidebar counts", src.includes("function markConversationClearedLocally") && src.includes("return { ...conv, message_count: 0, last_message: \"\", messages: [] }") && clearChatSource.includes("markConversationClearedLocally(convId);\n    renderConversationList();") && clearChatSource.includes(".then(() => refreshConversationSidebar())") && clearChatSource.includes('showToast(t("toast.chatClearSyncFailed"), "warning"') && deI18n.includes('"toast.chatClearSyncFailed"') && enI18n.includes('"toast.chatClearSyncFailed"'));
  assert("initial conversation loading uses shared sidebar refresh", loadConversationsSource.includes("await refreshConversationSidebar()"));
  assert("conversation delete blocks duplicate clicks and restores on failure", chatHistoryUiSrc.includes("deleteConversation(conversation.id, delBtn)") && deleteConversationSource.includes('triggerBtn?.getAttribute("aria-busy") === "true"') && deleteConversationSource.includes('triggerBtn.setAttribute("aria-busy", "true")') && deleteConversationSource.includes("finally") && deleteConversationSource.includes("triggerBtn.removeAttribute(\"aria-busy\")"));
  assert("conversation delete separates backend delete from sidebar refresh failure", src.includes("function removeConversationLocally") && src.includes("updateConversationCount(next.length)") && deleteConversationSource.includes("let convList = removeConversationLocally(convId)") && deleteConversationSource.includes("await refreshConversationSidebar()") && deleteConversationSource.includes('showToast(t("toast.deleteRefreshFailed"), "warning"') && deleteConversationSource.includes('showToast(t("toast.deleteError"), "error")') && deI18n.includes('"toast.deleteRefreshFailed"') && enI18n.includes('"toast.deleteRefreshFailed"'));

  const uploadSource = extractFn(chatFileUploadSrc, "handleFileUpload");
  const uploadMessageSource = extractFn(chatFileUploadSrc, "addFileUploadMessage");
  const uploadCardSource = extractFn(chatFileUploadSrc, "buildFileUploadCard");
  const uploadPreviewSource = extractFn(chatFileUploadSrc, "buildFileUploadPreview");
  const uploadResponseSource = extractFn(chatFileUploadSrc, "addFileUploadResponse");
  const uploadBadgeSource = extractFn(chatFileUploadSrc, "buildFileInfoBadge");
  assert("file upload blocks while chat is loading", uploadSource.includes('LexaState.get("isLoading")') && uploadSource.includes('t("chat.uploadBusy")'));
  assert("file upload conversation create failure stops upload", uploadSource.includes('showToast(t("toast.createError"), "error")') && uploadSource.includes("return;"));
  assert("file upload tolerates sidebar refresh failure after conversation create", uploadSource.includes("result = await window.lexa.conversationCreate") && uploadSource.includes("if (!result?.id)") && uploadSource.includes("await refreshConversationSidebar()") && uploadSource.includes('showToast(t("toast.conversationRefreshFailed"), "warning"') && uploadSource.includes("chatSetActiveConversationId(result.id)"));
  assert("file upload resets busy state through finally", chatFileUploadSrc.includes("function setFileUploadBusy") && chatFileUploadSrc.includes("function saveFileUploadConversationSnapshot") && uploadSource.includes("setFileUploadBusy(true)") && uploadSource.includes("} finally {") && uploadSource.includes("hideTyping();") && uploadSource.includes("saveFileUploadConversationSnapshot();") && uploadSource.includes("setFileUploadBusy(false)"));
  assert("file upload opens the chat transcript before rendering attachment", uploadSource.includes('if (!window._chatViewOpen && typeof toggleChatView === "function") toggleChatView()') && uploadSource.indexOf('if (!window._chatViewOpen && typeof toggleChatView === "function") toggleChatView()') < uploadSource.indexOf("addFileUploadMessage(file, userMsg)"));
  assert("file upload renders card through DOM helper", uploadSource.includes("addFileUploadMessage(file, userMsg)") && !uploadSource.includes("fileCardHtml"));
  assert("file upload card avoids raw HTML string rendering", uploadCardSource.includes("document.createElement") && uploadCardSource.includes("textContent = file.name") && !uploadCardSource.includes("innerHTML"));
  assert("file upload image card renders local preview safely", chatFileUploadSrc.includes("function buildFileUploadIcon") && uploadCardSource.includes("buildFileUploadPreview(file, ext)") && uploadCardSource.includes('card.classList.add("file-card-with-preview")') && uploadPreviewSource.includes("fileUploadCanPreview(file)") && uploadPreviewSource.includes('img.className = "file-card-preview"') && uploadPreviewSource.includes("URL.createObjectURL(file)") && uploadPreviewSource.includes("URL.revokeObjectURL(previewUrl)") && uploadPreviewSource.includes("img.replaceWith(buildFileUploadIcon(ext))"));
  assert("file upload message inserts card into user bubble", uploadMessageSource.includes('querySelectorAll(".message.user-message")') && uploadMessageSource.includes("buildFileUploadCard(file)"));
  assert("file upload busy label is translated", deI18n.includes('"chat.uploadBusy"') && enI18n.includes('"chat.uploadBusy"'));
  assert("file upload response uses DOM badge helper", uploadSource.includes("addFileUploadResponse(res)") && uploadResponseSource.includes("buildFileInfoBadge(res.file_info)"));
  assert("file upload info badge avoids raw HTML string rendering", uploadBadgeSource.includes("document.createElement") && uploadBadgeSource.includes("badge.textContent") && !uploadBadgeSource.includes("innerHTML"));
  assert("file upload response no longer double-formats reply HTML", !uploadSource.includes("infoHtml + formatMessage(res.reply)"));

  const setupVoiceSource = extractFn(src, "setupVoice");
  const voiceStartSource = extractFn(src, "voiceStart");
  const voiceStopSource = extractFn(src, "voiceStop");
  const voiceProcessSource = extractFn(src, "voiceProcess");
  const voiceMimeSource = extractFn(src, "voicePreferredMimeType");
  const voiceRecorderWillProcessSource = extractFn(src, "voiceRecorderWillProcessOnStop");
  const voiceNextSource = extractFn(src, "voiceTTSNext");
  const voiceEnqueueSource = extractFn(src, "voiceTTSEnqueue");
  const voiceResetPlaybackSource = extractFn(src, "voiceTTSResetPlayback");
  const voiceClearSource = extractFn(src, "voiceTTSClear");
  assert("voice composer toggle a11y helpers localize pressed state", src.includes("function setVoiceToggleA11y") && src.includes('button.setAttribute("aria-pressed"') && src.includes("function updateMicToggleA11y") && src.includes("function updateTtsToggleA11y"));
  assert("mic processing state exposes aria busy", src.includes("function updateMicProcessingA11y") && src.includes('mic.classList.toggle("processing", isProcessing)') && src.includes('mic.setAttribute("aria-busy", isProcessing ? "true" : "false")'));
  assert("voice composer toggle labels are translated", deI18n.includes('"chat.micToggleLabel"') && enI18n.includes('"chat.micToggleLabel"') && deI18n.includes('"chat.ttsToggleOnTitle"') && enI18n.includes('"chat.ttsToggleOnTitle"'));
  assert("voice setup initializes mic and tts toggle accessibility", setupVoiceSource.includes("updateMicToggleA11y(Voice.recording)") && setupVoiceSource.includes("updateMicProcessingA11y(false)") && setupVoiceSource.includes("updateTtsToggleA11y(initialTtsEnabled)") && setupVoiceSource.includes("updateTtsToggleA11y(on)"));
  assert("voice pipeline UI errors are localized", voiceStartSource.includes('voiceUiText("chat.micAccessDeniedMsg"') && voiceProcessSource.includes('voiceUiText("chat.voiceNoRecording"') && voiceProcessSource.includes('voiceUiText("chat.voiceNotUnderstood"') && voiceProcessSource.includes('voiceUiText("chat.voiceErrorPrefix"') && src.includes('voiceUiText("chat.voiceBackendUnreachable"'));
  assert("voice pipeline localization keys exist", deI18n.includes('"chat.voiceTranscribing"') && enI18n.includes('"chat.voiceTranscribing"') && deI18n.includes('"chat.voiceBackendUnreachable"') && enI18n.includes('"chat.voiceBackendUnreachable"'));
  assert("voice recording checks MediaRecorder support", voiceStartSource.includes("typeof MediaRecorder") && voiceStartSource.includes('t("chat.sttUnavailableMsg")'));
  assert("voice recording chooses a supported mime type", voiceMimeSource.includes("MediaRecorder.isTypeSupported") && voiceStartSource.includes("voicePreferredMimeType()"));
  assert("voice stop only marks busy when recorder will process", voiceRecorderWillProcessSource.includes("Voice.mediaRecorder") && voiceRecorderWillProcessSource.includes('Voice.mediaRecorder.state !== "inactive"') && voiceStopSource.includes("const shouldProcessRecording = voiceRecorderWillProcessOnStop()") && voiceStopSource.includes("updateMicProcessingA11y(shouldProcessRecording)") && voiceStopSource.includes("voiceStatusBarResetIfNoSpeechPending()"));
  assert("voice processing posts the recorded mime type", voiceProcessSource.includes("Voice.recordMimeType") && !voiceProcessSource.includes('{ type: "audio/webm" }'));
  assert("mic pressed state follows recording lifecycle", voiceStartSource.includes("updateMicToggleA11y(true)") && voiceStartSource.includes("updateMicToggleA11y(false)") && voiceStopSource.includes("updateMicToggleA11y(false)"));
  assert("mic busy state follows STT processing lifecycle", voiceStopSource.includes("updateMicProcessingA11y(shouldProcessRecording)") && voiceProcessSource.includes("updateMicProcessingA11y(true)") && voiceProcessSource.includes("updateMicProcessingA11y(false)"));
  assert("tts toggle off clears queued/current speech", setupVoiceSource.includes("voiceTTSClear()") && setupVoiceSource.includes('t("chat.ttsDisabled")'));
  assert("tts enqueue stores bounded chunks before playback", voiceEnqueueSource.includes("voiceTTSChunkText(text)") && voiceEnqueueSource.includes("chunks.forEach((chunk) => Voice.ttsQueue.push(chunk))") && voiceEnqueueSource.includes("Voice.ttsQueue.length > 0"));
  assert("tts playback tracks current audio url for cleanup", voiceNextSource.includes("Voice.ttsAudio = audio") && voiceNextSource.includes("Voice.ttsAudioUrl = url"));
  assert("tts queue ignores stale async audio after clear", voiceNextSource.includes("ttsRunId") && voiceNextSource.includes("runId !== Voice.ttsRunId") && voiceNextSource.includes("voiceTTSResetPlayback({ hide: !LexaState.get(\"ttsEnabled\") })"));
  assert("tts reset helper clears queue, playback flag, stale status, and orb state", voiceResetPlaybackSource.includes("Voice.ttsQueue.length = 0") && voiceResetPlaybackSource.includes("Voice.ttsPlaying = false") && voiceResetPlaybackSource.includes("voiceStatusBarReset({ hide })") && voiceResetPlaybackSource.includes("voiceSetOrbConversationState(null)"));
  assert("tts idle and clear reset stale status transcript", voiceNextSource.includes("if (wasPlaying)") && voiceNextSource.includes("voiceStatusBarReset();") && voiceNextSource.includes("voiceSetOrbConversationState(null)") && voiceClearSource.includes("voiceTTSResetPlayback({ hide: true })"));
  assert("tts clear stops current audio and revokes url", voiceClearSource.includes("audio.pause()") && voiceClearSource.includes("URL.revokeObjectURL(url)"));

  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
  if (failed > 0) process.exit(1);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
