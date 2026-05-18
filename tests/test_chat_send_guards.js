/**
 * Smoke tests for sendMessage() guard ordering.
 * Run with: node tests/test_chat_send_guards.js
 */

const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat.js"),
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
  function t(key, values = {}) { return key + ":" + (values.max || ""); }
  async function sendAgentMessage(text) { events.push(["agent", text]); }
  ${extractFn(src, "chatInputMetrics")}
  ${extractFn(src, "sendMessage")}
  return {
    chatInputMetrics,
    sendMessage,
    setInput(value) { inputValue = value; },
    setBackendOnline(value) { backendOnline = Boolean(value); },
    state() { return { loading, events: events.slice() }; },
    reset() { events.length = 0; loading = false; backendOnline = true; inputValue = ""; },
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
  assert("agent stream read has timeout guard", agentSource.includes("AGENT_STREAM_TIMEOUT_MS") && agentSource.includes("Promise.race") && agentSource.includes("agentReader.cancel"));
  assert("agent timeout uses translated UI message", agentSource.includes('t("chat.agentTimeout")') && deI18n.includes('"chat.agentTimeout"') && enI18n.includes('"chat.agentTimeout"'));
  assert("agent mode has user stop control", agentSource.includes("agent-stop-btn") && agentSource.includes("agentStoppedByUser") && agentSource.includes("agent_stream_stopped"));
  assert("agent stop cancels stream reader", agentSource.includes("await agentReader.cancel()") && agentSource.includes('t("chat.agentStopped")'));
  assert("agent stop uses translated tooltip", agentSource.includes('t("chat.agentStopTooltip")') && deI18n.includes('"chat.agentStopTooltip"') && enI18n.includes('"chat.agentStopTooltip"'));

  const showTypingSource = extractFn(src, "showTyping");
  const sendSource = extractFn(src, "sendMessage");
  assert("normal chat stop marks a user abort", showTypingSource.includes('_lexaStreamAbortReason = "user"') && showTypingSource.includes('t("chat.stopResponseTooltip")'));
  assert("normal chat stream distinguishes stop from timeout", sendSource.includes("streamStoppedByUser") && sendSource.includes('t("chat.responseStopped")') && sendSource.includes('_lexaStreamAbortReason = "timeout"'));
  assert("normal chat stop labels are translated", deI18n.includes('"chat.stopResponseButton"') && enI18n.includes('"chat.stopResponseButton"') && deI18n.includes('"chat.responseStopped"') && enI18n.includes('"chat.responseStopped"'));
  assert("normal chat HTTP error clears stream timeout", sendSource.includes("clearTimeout(_streamTimeout);") && sendSource.includes("window._lexaStreamAbort = null"));

  const voiceStartStatusSource = extractFn(src, "voiceStart");
  const voiceProcessStatusSource = extractFn(src, "voiceProcess");
  const voiceStreamChatStatusSource = extractFn(src, "voiceStreamChat");
  const voiceTTSNextStatusSource = extractFn(src, "voiceTTSNext");
  const voiceStatusUpdateSource = extractFn(src, "voiceStatusBarUpdate");
  const voiceStatusResetSource = extractFn(src, "voiceStatusBarReset");
  const voiceSpeechPendingSource = extractFn(src, "voiceSpeechPending");
  const voiceResetIfNoSpeechSource = extractFn(src, "voiceStatusBarResetIfNoSpeechPending");
  const voiceTtsFindSplitSource = extractFn(src, "voiceTTSFindSplit");
  const voiceTtsChunkSource = extractFn(src, "voiceTTSChunkText");
  const voiceTtsFlushSource = extractFn(src, "voiceTTSFlushBuffer");
  assert("voice status bar helper updates shared UI", src.includes("function voiceStatusBarUpdate") && src.includes("VoiceStatusBar.show()"));
  assert("voice status bar reset clears stale transcript chrome", voiceStatusResetSource.includes('setTranscript("")') && voiceStatusResetSource.includes('setProvider("")') && voiceStatusResetSource.includes("setLatency(0)"));
  assert("voice status reset waits for pending speech", voiceSpeechPendingSource.includes('LexaState.get("ttsEnabled")') && voiceSpeechPendingSource.includes("Voice.ttsPlaying") && voiceSpeechPendingSource.includes("Voice.ttsQueue.length") && voiceResetIfNoSpeechSource.includes("if (!voiceSpeechPending()) voiceStatusBarReset()"));
  assert("voice recording sets localized listening provider", voiceStartStatusSource.includes('state: "listening"') && voiceStartStatusSource.includes('voiceUiText("chat.voiceProviderRecording"') && deI18n.includes('"chat.voiceProviderRecording"') && enI18n.includes('"chat.voiceProviderRecording"'));
  assert("voice processing exposes localized STT status", voiceProcessStatusSource.includes('provider: "STT"') && voiceProcessStatusSource.includes('voiceUiText("chat.voiceTranscribing"'));
  assert("voice stream exposes AI status and resets when no TTS will speak", voiceStreamChatStatusSource.includes('provider: "AI"') && voiceStreamChatStatusSource.includes("voiceStatusBarResetIfNoSpeechPending()"));
  assert("voice stream uses configured API base and cleans up timeout/reader", src.includes("function voiceApiBase()") && voiceStreamChatStatusSource.includes("const API = voiceApiBase()") && voiceStreamChatStatusSource.includes("let timeout = null") && voiceStreamChatStatusSource.includes("let reader = null") && voiceStreamChatStatusSource.includes("finally") && voiceStreamChatStatusSource.includes("await reader.cancel()"));
  assert("voice stream flushes TTS through bounded chunker", src.includes("VOICE_TTS_MAX_CHUNK_CHARS") && voiceStreamChatStatusSource.includes("voiceTTSFlushBuffer(ttsBuf)") && voiceStreamChatStatusSource.includes("voiceTTSFlushBuffer(ttsBuf, true)") && voiceTtsFlushSource.includes("voiceTTSEnqueue(speakable.trim())"));
  assert("voice stream flushes final TTS buffer after reader close", voiceStreamChatStatusSource.includes("ttsBuf = voiceTTSFlushBuffer(ttsBuf, true);\n    if (timeout)"));
  const ttsChunkSandbox = new Function(`${voiceTtsFindSplitSource}\n${voiceTtsChunkSource}\nreturn { voiceTTSChunkText };`)();
  const longTtsChunks = ttsChunkSandbox.voiceTTSChunkText("Alpha ".repeat(80), 80);
  assert("voice TTS chunker bounds long speech segments", longTtsChunks.length > 1 && longTtsChunks.every((chunk) => chunk.length <= 80 && chunk === chunk.trim()));
  assert("voice TTS exposes speaking status without visible status chrome", voiceTTSNextStatusSource.includes('state: "speaking"') && voiceTTSNextStatusSource.includes('voiceUiText("chat.voiceProviderSpeech"') && voiceTTSNextStatusSource.includes('voiceUiText("chat.voiceSpeakingResponse"') && src.includes('state === "speaking"') && src.includes("voiceStatusBarReset({ hide: true })") && src.includes("VOICE_TTS_PLAYBACK_RATE"));
  assert("voice TTS drives the main orb speaking state", src.includes("function voiceSetOrbConversationState") && voiceTTSNextStatusSource.includes('voiceSetOrbConversationState("speaking")') && voiceTTSNextStatusSource.includes("voiceSetOrbConversationState(null)"));

  const persistTextSource = extractFn(src, "getMessagePersistText");
  const persistableSource = extractFn(src, "isPersistableChatMessage");
  const saveChatSource = extractFn(src, "saveChatHistory");
  const autoSaveSource = extractFn(src, "autoSaveConversation");
  const saveCurrentSource = extractFn(src, "saveCurrentConversation");
  const clearChatSource = extractFn(src, "clearChat");
  const trimChatSource = extractFn(src, "trimChatMessages");
  const newConversationSource = extractFn(src, "newConversation");
  const switchSource = extractFn(src, "switchConversation");
  const refreshSidebarSource = extractFn(src, "refreshConversationSidebar");
  const loadConversationsSource = extractFn(src, "loadConversations");
  assert("chat persistence reads agent summaries", persistTextSource.includes('querySelector(".agent-summary")'));
  assert("chat persistence skips only transient typing messages", persistableSource.includes("typing-message"));
  assert("local chat cache uses shared persisted text helper", saveChatSource.includes("getMessagePersistText(msg)"));
  assert("conversation autosave uses shared persisted text helper", autoSaveSource.includes("getMessagePersistText(msg)") && saveCurrentSource.includes("getMessagePersistText(msg)"));
  assert("chat persistence no longer skips first real message", !saveChatSource.includes("i === 0") && !autoSaveSource.includes("i === 0") && !saveCurrentSource.includes("i === 0"));
  assert("clear and switch remove all existing chat messages", clearChatSource.includes("msgs.forEach((m) => m.remove())") && switchSource.includes("msgs.forEach((m) => m.remove())"));
  assert("new chat removes all existing chat messages", newConversationSource.includes("msgs.forEach((m) => m.remove())"));
  assert("chat DOM trimming no longer preserves stale first message", trimChatSource.includes("MAX_DOM_MESSAGES") && trimChatSource.includes("for (let i = 0; i < toRemove; i++)"));
  assert("first-message edit removes the edited message too", !src.includes("Keep greeting (index 0)") && !src.includes("if (i > 0) allMsgs[i].remove()"));
  assert("conversation sidebar refresh is shared", refreshSidebarSource.includes("window.lexa.conversations()") && refreshSidebarSource.includes("renderConversationList()"));
  assert("saved conversations refresh sidebar counts", saveCurrentSource.includes("await refreshConversationSidebar()"));
  assert("cleared conversations refresh sidebar counts", clearChatSource.includes(".then(() => refreshConversationSidebar())"));
  assert("initial conversation loading uses shared sidebar refresh", loadConversationsSource.includes("await refreshConversationSidebar()"));

  const uploadSource = extractFn(src, "handleFileUpload");
  const uploadMessageSource = extractFn(src, "addFileUploadMessage");
  const uploadCardSource = extractFn(src, "buildFileUploadCard");
  const uploadResponseSource = extractFn(src, "addFileUploadResponse");
  const uploadBadgeSource = extractFn(src, "buildFileInfoBadge");
  assert("file upload blocks while chat is loading", uploadSource.includes('LexaState.get("isLoading")') && uploadSource.includes('t("chat.uploadBusy")'));
  assert("file upload conversation create failure stops upload", uploadSource.includes('showToast(t("toast.createError"), "error")') && uploadSource.includes("return;"));
  assert("file upload renders card through DOM helper", uploadSource.includes("addFileUploadMessage(file, userMsg)") && !uploadSource.includes("fileCardHtml"));
  assert("file upload card avoids raw HTML string rendering", uploadCardSource.includes("document.createElement") && uploadCardSource.includes("textContent = file.name") && !uploadCardSource.includes("innerHTML"));
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
