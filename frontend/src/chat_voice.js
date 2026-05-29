/*
 * Chat voice capture, streaming response, and TTS queue.
 */

//  Flow: Mic Button → Record → STT → Show Text → AI → TTS
// ══════════════════════════════════════════════════════

// ── STATE ──
const Voice = {
  recording: false,
  mediaRecorder: null,
  audioChunks: [],
  stream: null,
  ttsQueue: [],
  ttsPlaying: false,
  ttsAudio: null,
  ttsAudioUrl: null,
  ttsRunId: 0,
  recordMimeType: "audio/webm",
  silenceTimer: null,
  recordTimeout: null,
  audioCtx: null,
};

const VOICE_TTS_MIN_CHUNK_CHARS = 10;
const VOICE_TTS_MAX_CHUNK_CHARS = 420;
const VOICE_TTS_PLAYBACK_RATE = 1.08;

function voiceUiText(key, fallback, params) {
  try {
    const text = typeof t === "function" ? t(key, params) : "";
    return text && text !== key ? text : fallback;
  } catch (_) {
    return fallback;
  }
}

function setVoiceToggleA11y(button, active, labelKey, titleKey, fallbackLabel, fallbackTitle) {
  if (!button) return;
  button.dataset.i18nAriaLabel = labelKey;
  button.dataset.i18nTitle = titleKey;
  button.setAttribute("aria-label", voiceUiText(labelKey, fallbackLabel));
  button.setAttribute("aria-pressed", active ? "true" : "false");
  button.title = voiceUiText(titleKey, fallbackTitle);
}

function updateMicToggleA11y(active = false) {
  const mic = document.getElementById("mic-btn");
  setVoiceToggleA11y(
    mic,
    active,
    "chat.micToggleLabel",
    active ? "chat.micStopTitle" : "chat.micStartTitle",
    "Voice recording",
    active ? "Stop voice recording (Ctrl+M)" : "Start voice recording (Ctrl+M)"
  );
}

function updateMicProcessingA11y(processing = false) {
  const mic = document.getElementById("mic-btn");
  if (!mic) return;
  const isProcessing = Boolean(processing);
  mic.classList.toggle("processing", isProcessing);
  mic.setAttribute("aria-busy", isProcessing ? "true" : "false");
}

function updateTtsToggleA11y(active = false) {
  const ttsToggle = document.getElementById("tts-toggle");
  setVoiceToggleA11y(
    ttsToggle,
    active,
    "chat.ttsToggleLabel",
    active ? "chat.ttsToggleOnTitle" : "chat.ttsToggleOffTitle",
    "Text-to-speech",
    active ? "Text-to-speech is on. Click to turn off." : "Text-to-speech is off. Click to turn on."
  );
}

// ── SETUP (called once from app.js init) ──
function voiceDebugLog(message, meta = undefined) {
  if (typeof window === "undefined" || window.LEXA_DEBUG_VOICE !== true) return;
  if (meta === undefined) console.debug(message);
  else console.debug(message, meta);
}

function setupVoice() {
  const mic = document.getElementById("mic-btn");
  const tts = document.getElementById("tts-toggle");

  if (mic) {
    updateMicToggleA11y(Voice.recording);
    updateMicProcessingA11y(false);
    mic.addEventListener("click", voiceToggle);
    voiceDebugLog("[Voice] Mic button ready");
  } else {
    console.warn("[Voice] mic-btn not found in DOM");
  }

  if (tts) {
    const initialTtsEnabled = Boolean(LexaState.get("ttsEnabled"));
    tts.classList.toggle("active", initialTtsEnabled);
    updateTtsToggleA11y(initialTtsEnabled);
    tts.addEventListener("click", () => {
      const on = !LexaState.get("ttsEnabled");
      LexaState.set("ttsEnabled", on);
      tts.classList.toggle("active", on);
      updateTtsToggleA11y(on);
      if (!on) voiceTTSClear();
      showToast(on ? t("chat.ttsEnabled") : t("chat.ttsDisabled"), "info", 1500);
    });
  }
}

// ── MIC TOGGLE ──
function voiceToggle() {
  if (Voice.recording) voiceStop(); else voiceStart();
}

function voicePreferredMimeType() {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") return "";
  return [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
  ].find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function voiceUsesOrbSurface(state) {
  const safeState = String(state || "").toLowerCase();
  return Boolean(window.__lexaOrbVoiceActive)
    && ["listening", "processing", "speaking", "bargein", "error"].includes(safeState);
}

function voiceHideStatusBar() {
  if (typeof VoiceStatusBar === "undefined") return;
  if (!VoiceStatusBar._bar && typeof VoiceStatusBar.init === "function") VoiceStatusBar.init();
  VoiceStatusBar.hide();
}

function voiceEndOrbSurface() {
  if (typeof window !== "undefined") window.__lexaOrbVoiceActive = false;
  showOrbListening(false);
  voiceSetOrbConversationState(null);
  voiceHideStatusBar();
}

function voiceStatusBarUpdate({ state, transcript, provider, latency } = {}) {
  if (typeof VoiceStatusBar === "undefined") return;
  const safeState = state ? String(state).toLowerCase() : "";
  if (voiceUsesOrbSurface(safeState)) {
    if (safeState === "error") {
      voiceEndOrbSurface();
    } else {
      showOrbListening(false);
      voiceSetOrbConversationState(safeState === "bargein" ? "listening" : safeState);
      voiceHideStatusBar();
    }
    return;
  }
  if (safeState === "speaking") {
    voiceStatusBarReset({ hide: true });
    return;
  }
  VoiceStatusBar.show();
  if (state) VoiceStatusBar.setState(state);
  if (transcript !== undefined) VoiceStatusBar.setTranscript(transcript);
  if (provider !== undefined) VoiceStatusBar.setProvider(provider);
  if (latency !== undefined) VoiceStatusBar.setLatency(latency);
}

function voiceStatusBarReset(options) {
  const hide = Boolean(options?.hide);
  if (typeof window !== "undefined" && window.__lexaOrbVoiceActive) {
    voiceEndOrbSurface();
    return;
  }
  if (typeof VoiceStatusBar === "undefined") return;
  if (!VoiceStatusBar._bar && typeof VoiceStatusBar.init === "function") VoiceStatusBar.init();
  VoiceStatusBar.setState("idle");
  VoiceStatusBar.setTranscript("");
  VoiceStatusBar.setProvider("");
  VoiceStatusBar.setLatency(0);
  if (hide || !options?.showIdle) VoiceStatusBar.hide();
}

function voiceSpeechPending() {
  return Boolean(LexaState.get("ttsEnabled") && (Voice.ttsPlaying || Voice.ttsQueue.length > 0));
}

function voiceStatusBarResetIfNoSpeechPending() {
  if (!voiceSpeechPending()) voiceStatusBarReset();
}

function voiceSetOrbConversationState(state) {
  const safeState = state || null;
  if (typeof window !== "undefined" && typeof window.setOrbConversationState === "function") {
    window.setOrbConversationState(safeState);
    return;
  }
  if (typeof _setOrbConversationState === "function") {
    _setOrbConversationState(safeState);
    return;
  }

  const orbCanvas = document.getElementById("voice-orb-canvas");
  const orbContainer = document.getElementById("voice-orb-container");
  if (orbCanvas) {
    orbCanvas.classList.remove("conv-listening", "conv-processing", "conv-speaking", "conv-bargein");
    if (safeState) orbCanvas.classList.add("conv-" + safeState);
  }
  if (orbContainer) {
    orbContainer.classList.toggle("conversation-active", Boolean(safeState));
    if (safeState) orbContainer.dataset.convState = safeState;
    else delete orbContainer.dataset.convState;
  }
  if (window.dashboardOrb && typeof window.dashboardOrb.setConversationState === "function") {
    window.dashboardOrb.setConversationState(safeState);
  }
}

function voiceRecorderWillProcessOnStop() {
  return Boolean(Voice.mediaRecorder && Voice.mediaRecorder.state !== "inactive");
}

function voiceApiBase() {
  return window.lexa?.API_BASE || "http://127.0.0.1:8000";
}

function voiceTTSFindSplit(text, maxLength = VOICE_TTS_MAX_CHUNK_CHARS) {
  const value = String(text || "");
  if (value.length <= maxLength) return value.length;
  const windowText = value.slice(0, maxLength);
  const minSplit = Math.floor(maxLength * 0.45);
  for (const boundary of [". ", "! ", "? ", "\n", "; ", ": ", ", "]) {
    const index = windowText.lastIndexOf(boundary);
    if (index >= minSplit) return index + (boundary === "\n" ? 1 : boundary.length - 1);
  }
  const spaceIndex = windowText.lastIndexOf(" ");
  if (spaceIndex >= minSplit) return spaceIndex;
  return maxLength;
}

function voiceTTSChunkText(text, maxLength = VOICE_TTS_MAX_CHUNK_CHARS) {
  let remaining = String(text || "").replace(/\s+/g, " ").trim();
  const chunks = [];
  while (remaining.length > maxLength) {
    const splitAt = voiceTTSFindSplit(remaining, maxLength);
    const chunk = remaining.slice(0, splitAt).trim();
    if (chunk) chunks.push(chunk);
    remaining = remaining.slice(splitAt).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

function voiceTTSFlushBuffer(buffer, force = false) {
  const value = String(buffer || "");
  const complete = value.match(/^(.*[.!?\n])\s*/s);
  let speakable = "";
  let remaining = value;
  if (complete && complete[1].trim().length >= VOICE_TTS_MIN_CHUNK_CHARS) {
    speakable = complete[1];
    remaining = value.slice(complete[0].length);
  } else if (force) {
    speakable = value;
    remaining = "";
  } else if (value.length >= VOICE_TTS_MAX_CHUNK_CHARS) {
    const splitAt = voiceTTSFindSplit(value);
    speakable = value.slice(0, splitAt);
    remaining = value.slice(splitAt);
  }
  if (speakable.trim()) voiceTTSEnqueue(speakable.trim());
  return remaining.trimStart();
}

// ── START RECORDING ──
async function voiceStart() {
  const mic = document.getElementById("mic-btn");
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(false);
    updateMicToggleA11y(false);
    updateMicProcessingA11y(false);
    voiceStatusBarUpdate({ state: "error", transcript: t("chat.sttUnavailableMsg"), provider: "" });
    showToast(t("chat.sttUnavailableMsg"), "error");
    return;
  }

  try {
    Voice.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(false);
    updateMicToggleA11y(false);
    updateMicProcessingA11y(false);
    const message = voiceUiText("chat.micAccessDeniedMsg", "Microphone access denied. Please allow access.");
    voiceStatusBarUpdate({ state: "error", transcript: message, provider: "" });
    showToast(message, "error");
    return;
  }

  Voice.audioChunks = [];
  const mimeType = voicePreferredMimeType();
  try {
    Voice.mediaRecorder = new MediaRecorder(Voice.stream, mimeType ? { mimeType } : undefined);
    Voice.recordMimeType = Voice.mediaRecorder.mimeType || mimeType || "audio/webm";
  } catch (e) {
    if (Voice.stream) { Voice.stream.getTracks().forEach(t => t.stop()); Voice.stream = null; }
    if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(false);
    updateMicToggleA11y(false);
    updateMicProcessingA11y(false);
    voiceStatusBarUpdate({ state: "error", transcript: t("chat.sttUnavailableMsg"), provider: "" });
    showToast(t("chat.sttUnavailableMsg"), "error");
    return;
  }
  Voice.mediaRecorder.ondataavailable = e => { if (e.data.size > 0) Voice.audioChunks.push(e.data); };
  Voice.mediaRecorder.onstop = () => voiceProcess();
  Voice.mediaRecorder.start();
  Voice.recording = true;
  LexaState.set("isRecording", true);
  if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(true);
  updateMicToggleA11y(true);

  if (mic) mic.classList.add("recording");
  voiceStatusBarUpdate({ state: "listening", transcript: "", provider: voiceUiText("chat.voiceProviderRecording", "Recording") });

  // Silence detection
  voiceStartSilenceDetect(Voice.stream);

  // Safety: max 30s
  Voice.recordTimeout = setTimeout(() => { if (Voice.recording) voiceStop(); }, 30000);

  voiceDebugLog("[Voice] Recording started");
}

// ── STOP RECORDING ──
function voiceStop() {
  const mic = document.getElementById("mic-btn");
  const shouldProcessRecording = voiceRecorderWillProcessOnStop();
  if (Voice.silenceTimer) { clearInterval(Voice.silenceTimer); Voice.silenceTimer = null; }
  if (Voice.recordTimeout) { clearTimeout(Voice.recordTimeout); Voice.recordTimeout = null; }
  if (shouldProcessRecording) Voice.mediaRecorder.stop();
  if (Voice.stream) { Voice.stream.getTracks().forEach(t => t.stop()); Voice.stream = null; }
  Voice.recording = false;
  LexaState.set("isRecording", false);
  if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(false);
  updateMicToggleA11y(false);
  if (mic) mic.classList.remove("recording");
  updateMicProcessingA11y(shouldProcessRecording);
  if (shouldProcessRecording) {
    voiceStatusBarUpdate({ state: "processing", provider: voiceUiText("chat.voiceProviderProcessing", "Verarbeitung") });
  } else {
    voiceStatusBarResetIfNoSpeechPending();
  }
  voiceDebugLog("[Voice] Recording stopped");
}

// ── SILENCE DETECTION ──
function voiceStartSilenceDetect(stream) {
  try {
    if (!Voice.audioCtx) Voice.audioCtx = new AudioContext();
    const src = Voice.audioCtx.createMediaStreamSource(stream);
    const analyser = Voice.audioCtx.createAnalyser();
    analyser.fftSize = 512;
    src.connect(analyser);
    const data = new Float32Array(analyser.fftSize);
    let silenceStart = null;
    let hasSpeech = false;

    Voice.silenceTimer = setInterval(() => {
      if (!Voice.recording) { clearInterval(Voice.silenceTimer); return; }
      analyser.getFloatTimeDomainData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
      const rms = Math.sqrt(sum / data.length);

      if (rms > 0.012) { hasSpeech = true; silenceStart = null; }
      else if (hasSpeech) {
        if (!silenceStart) silenceStart = Date.now();
        else if (Date.now() - silenceStart > 2000) {
          voiceDebugLog("[Voice] Silence detected, auto-stop");
          clearInterval(Voice.silenceTimer);
          voiceStop();
        }
      }
    }, 100);
  } catch (e) {
    console.warn("[Voice] Silence detection failed:", e);
  }
}

// ── PROCESS: STT → CHAT → TTS ──
async function voiceProcess() {
  const blob = new Blob(Voice.audioChunks, { type: Voice.recordMimeType || "audio/webm" });
  if (blob.size < 100) {
    const message = voiceUiText("chat.voiceNoRecording", "No recording captured.");
    updateMicProcessingA11y(false);
    voiceStatusBarUpdate({ state: "error", transcript: message, provider: "" });
    showToast(message, "warning");
    return;
  }

  const mic = document.getElementById("mic-btn");
  updateMicProcessingA11y(true);
  voiceStatusBarUpdate({ state: "processing", transcript: voiceUiText("chat.voiceTranscribing", "Transcribing speech..."), provider: voiceUiText("chat.voiceProviderProcessing", "Verarbeitung") });

  // Auto-open chat so user sees results
  if (!window._chatViewOpen && typeof toggleChatView === "function") toggleChatView();

  try {
    // 1. STT
    voiceDebugLog("[Voice] Sending to STT", { bytes: blob.size });
    const stt = await window.lexa.stt(blob);
    voiceDebugLog("[Voice] STT result received", {
      hasText: Boolean(stt?.text),
      language: String(stt?.language || ""),
      textLength: String(stt?.text || "").length,
    });

    if (!stt.success || !stt.text || !stt.text.trim()) {
      voiceStatusBarUpdate({ state: "error", transcript: voiceUiText("chat.voiceNotUnderstood", "Could not understand."), provider: voiceUiText("chat.voiceProviderProcessing", "Verarbeitung") });
      showToast(voiceUiText("chat.voiceNotUnderstoodFull", "Could not understand. Please try again."), "warning", 2500);
      updateMicProcessingA11y(false);
      return;
    }

    voiceStatusBarUpdate({ state: "processing", transcript: stt.text, provider: voiceUiText("chat.voiceProviderProcessing", "Verarbeitung") });

    // Show user text in chat
    addMessage(stt.text, "user", null, false, true);

    // 2. AI Chat (streaming)
    voiceDebugLog("[Voice] Sending voice transcript to AI", { textLength: String(stt.text || "").length });
    updateMicProcessingA11y(false);

    await voiceStreamChat(stt.text);

  } catch (e) {
    console.error("[Voice] Pipeline error:", e);
    const errorText = e.message || String(e);
    voiceStatusBarUpdate({ state: "error", transcript: errorText, provider: "" });
    showToast(voiceUiText("chat.voiceErrorPrefix", "Voice error: {{msg}}", { msg: errorText }), "error");
    updateMicProcessingA11y(false);
  }
}

// ── STREAMING CHAT + TTS ──
async function voiceStreamChat(text) {
  const API = voiceApiBase();
  let fullText = "";
  let action = null;
  let requiresConfirmation = false;
  let timeout = null;
  let reader = null;

  try {
    voiceStatusBarUpdate({ state: "processing", provider: voiceUiText("chat.voiceProviderResponse", "Antwort"), transcript: text });
    const abort = new AbortController();
    timeout = setTimeout(() => abort.abort(), 45000);

    const resp = await fetch(`${API}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        message: text,
        conversation_id: LexaState.get("activeConversationId"),
      }),
      signal: abort.signal,
    });

    if (!resp.ok) {
      // Fallback to non-streaming
      const fallback = await window.lexa.chat(text);
      handleChatResponse(fallback, true);
      voiceStatusBarResetIfNoSpeechPending();
      if (timeout) { clearTimeout(timeout); timeout = null; }
      return;
    }

    reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let ttsBuf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const d = JSON.parse(line.slice(6));
          if (d.c) {
            fullText += d.c;
            ttsBuf += d.c;
            ttsBuf = voiceTTSFlushBuffer(ttsBuf);
          }
          if (d.done) {
            action = d.action || null;
            requiresConfirmation = d.rc || false;
            ttsBuf = voiceTTSFlushBuffer(ttsBuf, true);
          }
        } catch (_) {}
      }
    }

    ttsBuf = voiceTTSFlushBuffer(ttsBuf, true);
    if (timeout) { clearTimeout(timeout); timeout = null; }

    if (fullText) {
      const displayText = action && typeof chatActionDisplayReply === "function"
        ? chatActionDisplayReply({ reply: fullText, action })
        : fullText;
      addMessage(displayText, "system", action, requiresConfirmation, true);
      if (action) handleChatToolActionBlocked(action, { source: "voice", toast: false });
    }
    voiceStatusBarResetIfNoSpeechPending();

  } catch (e) {
    if (timeout) { clearTimeout(timeout); timeout = null; }
    if (reader) {
      try { await reader.cancel(); } catch (cancelErr) { console.warn("[Voice] Reader cancel failed:", cancelErr.message || cancelErr); }
    }
    console.warn("[Voice] Stream failed, fallback:", e);
    try {
      const fb = await window.lexa.chat(text);
      handleChatResponse(fb, true);
      voiceStatusBarResetIfNoSpeechPending();
    } catch (_) {
      const backendMessage = voiceUiText("chat.voiceBackendUnreachable", "Connection error. Backend not reachable.");
      voiceStatusBarUpdate({ state: "error", transcript: backendMessage, provider: "" });
      addMessage(backendMessage, "system");
    }
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

// ── TTS QUEUE ──
function voiceTTSEnqueue(text) {
  if (!LexaState.get("ttsEnabled") || !text) return;
  const chunks = voiceTTSChunkText(text);
  chunks.forEach((chunk) => Voice.ttsQueue.push(chunk));
  if (!Voice.ttsPlaying && Voice.ttsQueue.length > 0) voiceTTSNext();
}

function voiceTTSResetPlayback(options) {
  const hide = Boolean(options?.hide);
  Voice.ttsQueue.length = 0;
  Voice.ttsPlaying = false;
  voiceStatusBarReset({ hide });
  voiceSetOrbConversationState(null);
}

async function voiceTTSNext() {
  if (Voice.ttsQueue.length === 0) {
    const wasPlaying = Voice.ttsPlaying;
    Voice.ttsPlaying = false;
    if (wasPlaying) {
      voiceStatusBarReset();
      voiceSetOrbConversationState(null);
    }
    return;
  }
  Voice.ttsPlaying = true;
  const runId = Voice.ttsRunId;
  const text = Voice.ttsQueue.shift();
  try {
    voiceSetOrbConversationState("speaking");
    voiceStatusBarUpdate({
      state: "speaking",
      transcript: voiceUiText("chat.voiceSpeakingResponse", "Speaking response..."),
      provider: voiceUiText("chat.voiceProviderSpeech", "Voice"),
    });
    const url = await window.lexa.tts(text);
    if (url) {
      if (runId !== Voice.ttsRunId || !LexaState.get("ttsEnabled")) {
        URL.revokeObjectURL(url);
        voiceTTSResetPlayback({ hide: !LexaState.get("ttsEnabled") });
        return;
      }
      const audio = new Audio(url);
      audio.playbackRate = VOICE_TTS_PLAYBACK_RATE;
      if ("preservesPitch" in audio) audio.preservesPitch = true;
      Voice.ttsAudio = audio;
      Voice.ttsAudioUrl = url;
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        if (Voice.ttsAudio === audio) {
          Voice.ttsAudio = null;
          Voice.ttsAudioUrl = null;
        }
        URL.revokeObjectURL(url);
        if (runId === Voice.ttsRunId && Voice.ttsQueue.length === 0) {
          voiceStatusBarReset();
          voiceSetOrbConversationState(null);
        }
        if (runId === Voice.ttsRunId) voiceTTSNext();
      };
      audio.onended = finish;
      audio.onerror = finish;
      audio.play().catch(finish);
    } else {
      if (runId === Voice.ttsRunId) voiceTTSNext();
    }
  } catch (e) {
    console.warn("[TTS] Error:", e);
    if (runId === Voice.ttsRunId) voiceTTSNext();
  }
}

function voiceTTSClear() {
  Voice.ttsRunId += 1;
  const audio = Voice.ttsAudio;
  const url = Voice.ttsAudioUrl;
  Voice.ttsAudio = null;
  Voice.ttsAudioUrl = null;
  voiceTTSResetPlayback({ hide: true });
  if (audio) {
    audio.onended = null;
    audio.onerror = null;
    try { audio.pause(); } catch (_) {}
    try { audio.removeAttribute("src"); audio.load(); } catch (_) {}
  }
  if (url) URL.revokeObjectURL(url);
}

// ── COMPAT: functions referenced by other modules ──
function toggleRecording() { voiceToggle(); }
function playTTS(text) { voiceTTSEnqueue(text); }
function showOrbListening(show) {
  const el = document.getElementById("orb-listening-text");
  if (el) el.classList.toggle("hidden", !show);
}
function showOrbTranscript(userText, lexaText) {
  const container = document.getElementById("orb-transcript");
  const userEl = document.getElementById("orb-user-text");
  const lexaEl = document.getElementById("orb-lexa-text");
  if (!container) return;
  if (userText !== undefined && userEl) userEl.textContent = userText;
  if (lexaText !== undefined && lexaEl) lexaEl.textContent = lexaText;
  container.classList.remove("hidden");
}
function clearOrbTranscript() {
  const c = document.getElementById("orb-transcript");
  const u = document.getElementById("orb-user-text");
  const l = document.getElementById("orb-lexa-text");
  if (c) c.classList.add("hidden");
  if (u) u.textContent = "";
  if (l) l.textContent = "";
}
function clearVoiceTranscriptPanel() {
  const p = document.getElementById("voice-transcript-panel");
  const l = document.getElementById("voice-transcript-list");
  if (p) p.classList.add("hidden");
  if (l) l.replaceChildren();
}
function toggleChatView() {
  const msgs = document.getElementById("chat-messages");
  const arrow = document.getElementById("chat-view-arrow");
  const orb = document.getElementById("voice-orb-container");
  const greeting = document.getElementById("sleek-greeting");
  const cards = document.getElementById("floating-cards-container");
  if (!msgs) return;
  window._chatViewOpen = !window._chatViewOpen;
  if (window._chatViewOpen) {
    msgs.classList.remove("hidden");
    if (arrow) arrow.classList.add("flipped");
    if (orb) orb.classList.add("compact");
    if (greeting) greeting.classList.add("hidden");
    if (cards) cards.classList.add("hidden");
    const settle = window.requestAnimationFrame || ((fn) => setTimeout(fn, 0));
    settle(() => {
      const lastMessage = msgs.querySelector(".message:last-of-type");
      if (lastMessage && typeof scrollChatMessageIntoCleanView === "function") {
        scrollChatMessageIntoCleanView(lastMessage, { preferStartForLong: lastMessage.classList.contains("system-message") });
      } else {
        msgs.scrollTop = msgs.scrollHeight;
      }
    });
  } else {
    msgs.classList.add("hidden");
    if (arrow) arrow.classList.remove("flipped");
    if (orb) orb.classList.remove("compact");
  }
}

function createTalkButtonIcon(active) {
  const svg = document.createElementNS(CHAT_ATTENTION_ICON_NS, "svg");
  const attrs = {
    width: "18",
    height: "18",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    "stroke-width": "2",
    class: "talk-btn-icon",
  };
  Object.entries(attrs).forEach(([name, value]) => svg.setAttribute(name, value));
  const paths = active
    ? ["M12 2v20M17 5v14M7 5v14M22 8v8M2 8v8"]
    : ["M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Zm0 14a5 5 0 0 1-5-5H5a7 7 0 0 0 14 0h-2a5 5 0 0 1-5 5Zm-2 4v3h4v-3h-4Z"];
  paths.forEach((d) => {
    const path = document.createElementNS(CHAT_ATTENTION_ICON_NS, "path");
    path.setAttribute("d", d);
    svg.appendChild(path);
  });
  return svg;
}

function createTalkButtonLabel(labelKey, label) {
  const labelEl = document.createElement("span");
  labelEl.setAttribute("data-voice-entry-label", "");
  labelEl.setAttribute("data-i18n", labelKey);
  labelEl.textContent = label;
  return labelEl;
}

function renderTalkButton(listening = false) {
  const btn = document.getElementById("talk-to-lexa-btn");
  if (!btn) return;
  const active = listening || Voice.recording;
  btn.classList.toggle("listening", active);
  const labelKey = active ? "chat.endConversation" : "chat.talkToLexaBtn";
  const label = typeof t === "function" ? t(labelKey) : (active ? "End conversation" : "Talk to Lexa");
  btn.replaceChildren(createTalkButtonIcon(active), createTalkButtonLabel(labelKey, label));
  if (typeof _updateOrbActionA11y === "function") _updateOrbActionA11y(active);
}

// ══════════════════════════════════════════════════════

function handleChatResponse(res, ambient = false) {
  if (res.detail) {
      if (ambient) showOrbTranscript(undefined, res.detail);
      addMessage(res.detail, "system", null, false, ambient);
      if (res.detail.includes("Zu viele")) showToast(t("toast.rateLimitHit"), "warning");
  }
  else {
    const displayReply = typeof chatActionDisplayReply === "function" ? chatActionDisplayReply(res) : res.reply;
    if (ambient) showOrbTranscript(undefined, displayReply);
    addMessage(displayReply, "system", res.action, res.requires_confirmation, ambient);
    playTTS(displayReply);
    if (res.action) handleChatToolActionBlocked(res.action, { source: "chat-response", toast: false });
  }
}
