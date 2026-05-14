const { contextBridge, ipcRenderer } = require("electron");

const API = "http://127.0.0.1:8000";

// Fetch wrapper with AbortController timeout (default 30s)
async function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...options, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(id);
  }
}

// Secure Bridge — nur erlaubte APIs exposen
contextBridge.exposeInMainWorld("lexa", {
  // API base URL (centralized — avoids hardcoding in chat.js etc.)
  API_BASE: API,
  // i18n — load translation files via IPC (bypasses file:// fetch/CSP issues)
  loadI18n: (lang) => ipcRenderer.invoke("i18n-load", lang),

  // Window Controls
  minimize: () => ipcRenderer.send("window-minimize"),
  maximize: () => ipcRenderer.send("window-maximize"),
  close: () => ipcRenderer.send("window-close"),

  // Chat API
  chat: async (message) => {
    const res = await fetchWithTimeout(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    return res.json();
  },

  // Chat with File
  chatFile: async (file, message = "") => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("message", message);
    const res = await fetchWithTimeout(`${API}/chat/file`, {
      method: "POST",
      body: formData,
    });
    return res.json();
  },

  // Companion API
  execute: async (command, params = {}, confirmed = false) => {
    const res = await fetchWithTimeout(`${API}/companion/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, params, confirmed }),
    });
    return res.json();
  },

  // Voice: Text-to-Speech
  tts: async (text) => {
    const res = await fetchWithTimeout(`${API}/voice/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (res.ok) {
      const blob = await res.blob();
      return URL.createObjectURL(blob);
    }
    return null;
  },

  // Voice: Speech-to-Text
  stt: async (audioBlob) => {
    // Determine correct filename from blob MIME type (MediaRecorder produces webm, not wav)
    const mimeToExt = {
      "audio/webm": "recording.webm",
      "audio/ogg": "recording.ogg",
      "audio/mp4": "recording.m4a",
      "audio/mpeg": "recording.mp3",
      "audio/wav": "recording.wav",
      "audio/x-wav": "recording.wav",
      "audio/flac": "recording.flac",
    };
    const filename = mimeToExt[audioBlob.type] || "recording.webm";
    const formData = new FormData();
    formData.append("audio", audioBlob, filename);
    const res = await fetchWithTimeout(`${API}/voice/stt`, {
      method: "POST",
      body: formData,
    });
    return res.json();
  },

  // Voice status
  voiceStatus: async () => {
    try {
      const [tts, stt] = await Promise.all([
        fetchWithTimeout(`${API}/voice/tts/status`).then((r) => r.json()),
        fetchWithTimeout(`${API}/voice/stt/status`).then((r) => r.json()),
      ]);
      return { tts, stt };
    } catch (e) {
      console.warn("[Preload] voiceStatus failed:", e.message || e);
      return { tts: { ready: false }, stt: { ready: false } };
    }
  },

  // TTS Voice Management (ElevenLabs)
  ttsVoices: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/voice/tts/voices`);
      return r.json();
    } catch (e) { console.warn("[Preload] ttsVoices failed:", e.message || e); return { voices: [] }; }
  },

  // ElevenLabs TTS Management
  elevenlabsSetKey: async (apiKey) => {
    const r = await fetchWithTimeout(`${API}/voice/tts/elevenlabs/key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    });
    return r.json();
  },
  elevenlabsDeleteKey: async () => {
    const r = await fetchWithTimeout(`${API}/voice/tts/elevenlabs/key`, { method: 'DELETE' });
    return r.json();
  },
  elevenlabsVoices: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/voice/tts/elevenlabs/voices`);
      return r.json();
    } catch (e) { console.warn("[Preload] elevenlabsVoices failed:", e.message || e); return { voices: [] }; }
  },
  elevenlabsSetVoice: async (voiceId) => {
    const r = await fetchWithTimeout(`${API}/voice/tts/elevenlabs/voice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ voice_id: voiceId }),
    });
    return r.json();
  },
  elevenlabsSetModel: async (model) => {
    const r = await fetchWithTimeout(`${API}/voice/tts/elevenlabs/model`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    });
    return r.json();
  },
  elevenlabsSetSettings: async (stability, similarity, style) => {
    const r = await fetchWithTimeout(`${API}/voice/tts/elevenlabs/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stability, similarity, style }),
    });
    return r.json();
  },
  elevenlabsToggle: async (enabled) => {
    const r = await fetchWithTimeout(`${API}/voice/tts/elevenlabs/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    return r.json();
  },

  // STT Model Management
  sttModels: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/voice/stt/models`);
      return r.json();
    } catch (e) { console.warn("[Preload] sttModels failed:", e.message || e); return { models: [] }; }
  },
  sttSetModel: async (model) => {
    const r = await fetchWithTimeout(`${API}/voice/stt/model`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    });
    return r.json();
  },
  sttSetLanguage: async (language) => {
    const r = await fetchWithTimeout(`${API}/voice/stt/language`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language }),
    });
    return r.json();
  },
  sttSetEngine: async (engine) => {
    const r = await fetchWithTimeout(`${API}/voice/stt/engine`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ engine }),
    });
    return r.json();
  },
  deepgramSetKey: async (apiKey) => {
    const r = await fetchWithTimeout(`${API}/voice/stt/deepgram/key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    });
    return r.json();
  },
  deepgramDeleteKey: async () => {
    const r = await fetchWithTimeout(`${API}/voice/stt/deepgram/key`, { method: 'DELETE' });
    return r.json();
  },

  // Cartesia TTS
  cartesiaSetKey: async (apiKey) => {
    const r = await fetchWithTimeout(`${API}/voice/tts/cartesia/key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    });
    return r.json();
  },
  cartesiaDeleteKey: async () => {
    const r = await fetchWithTimeout(`${API}/voice/tts/cartesia/key`, { method: 'DELETE' });
    return r.json();
  },

  // Health
  health: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/health`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] health check failed:", e.message || e);
      return { status: "offline" };
    }
  },

  // AI Status
  aiStatus: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/ai/status`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] aiStatus failed:", e.message || e);
      return { active_provider: "none" };
    }
  },

  // Memory
  memoryStats: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/memory/stats`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] memoryStats failed:", e.message || e);
      return { notes: 0, memories: 0, interactions: 0, routines: 0 };
    }
  },

  memoryAdd: async (content, category = "learned", importance = 5) => {
    try {
      const res = await fetchWithTimeout(`${API}/memory/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, category, importance }),
      });
      return res.json();
    } catch (e) {
      console.warn("[Preload] memoryAdd failed:", e.message || e);
      return { error: "Fehler" };
    }
  },

  notes: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/memory/notes`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] notes failed:", e.message || e);
      return { notes: [] };
    }
  },

  noteGet: async (id) => {
    try {
      const res = await fetchWithTimeout(`${API}/memory/notes/${id}`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] noteGet failed:", e.message || e);
      return null;
    }
  },

  noteUpdate: async (id, data) => {
    try {
      const res = await fetchWithTimeout(`${API}/memory/notes/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      return res.json();
    } catch (e) {
      console.warn("[Preload] noteUpdate failed:", e.message || e);
      return { error: "Fehler beim Aktualisieren" };
    }
  },

  routines: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/memory/routines`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] routines failed:", e.message || e);
      return { routines: [] };
    }
  },

  setProfile: async (key, value) => {
    const res = await fetchWithTimeout(`${API}/memory/profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value }),
    });
    return res.json();
  },

  // Conversations (Phase 11)
  conversations: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/conversations`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] conversations failed:", e.message || e);
      return { conversations: [] };
    }
  },

  conversationCreate: async (title = "Neuer Chat") => {
    const res = await fetchWithTimeout(`${API}/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    return res.json();
  },

  conversationGet: async (id) => {
    const res = await fetchWithTimeout(`${API}/conversations/${id}`);
    return res.json();
  },

  conversationUpdate: async (id, data) => {
    const res = await fetchWithTimeout(`${API}/conversations/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  conversationDelete: async (id) => {
    const res = await fetchWithTimeout(`${API}/conversations/${id}`, { method: "DELETE" });
    return res.json();
  },

  conversationLoad: async (id) => {
    const res = await fetchWithTimeout(`${API}/conversations/${id}/load`, { method: "POST" });
    return res.json();
  },

  // Global Search (Phase 13)
  search: async (query) => {
    try {
      const res = await fetchWithTimeout(`${API}/search?q=${encodeURIComponent(query)}`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] search failed:", e.message || e);
      return { conversations: [], notes: [], memories: [] };
    }
  },

  conversationExport: async (id, fmt = "markdown") => {
    try {
      const res = await fetchWithTimeout(`${API}/conversations/${id}/export?fmt=${fmt}`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] conversationExport failed:", e.message || e);
      return { text: null };
    }
  },

  // AI Title & Model Selection (Phase 14)
  generateTitle: async (message) => {
    try {
      const res = await fetchWithTimeout(`${API}/ai/title`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      return res.json();
    } catch (e) {
      console.warn("[Preload] generateTitle failed:", e.message || e);
      return { title: message.substring(0, 40) };
    }
  },

  aiModels: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/ai/models`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] aiModels failed:", e.message || e);
      return { current: "llama-3.3-70b-versatile", available: {} };
    }
  },

  setAiModel: async (model) => {
    const res = await fetchWithTimeout(`${API}/ai/models`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model }),
    });
    return res.json();
  },

  // Google Calendar (Phase 47)
  calendarStatus: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/calendar/status`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] calendarStatus failed:", e.message || e);
      return { connected: false, has_client_secret: false };
    }
  },

  calendarToday: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/calendar/today`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] calendarToday failed:", e.message || e);
      return { success: false, events: [], error: "Verbindungsfehler" };
    }
  },

  calendarWeek: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/calendar/week`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] calendarWeek failed:", e.message || e);
      return { success: false, events: [], error: "Verbindungsfehler" };
    }
  },

  calendarConnect: async () => {
    const res = await fetchWithTimeout(`${API}/calendar/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    return res.json();
  },

  // Clipboard History (Phase 16)
  clipboardHistory: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/clipboard/history`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] clipboardHistory failed:", e.message || e);
      return { entries: [] };
    }
  },

  clipboardAdd: async (text) => {
    const res = await fetchWithTimeout(`${API}/clipboard/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    return res.json();
  },

  clipboardClear: async () => {
    const res = await fetchWithTimeout(`${API}/clipboard/history`, { method: "DELETE" });
    return res.json();
  },

  // Quick Text Snippets (Phase 16)
  snippets: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/snippets`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] snippets failed:", e.message || e);
      return { snippets: [] };
    }
  },

  snippetCreate: async (name, text) => {
    const res = await fetchWithTimeout(`${API}/snippets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, text }),
    });
    return res.json();
  },

  snippetDelete: async (name) => {
    const res = await fetchWithTimeout(`${API}/snippets/${encodeURIComponent(name)}`, { method: "DELETE" });
    return res.json();
  },

  // Productivity (Phase 19)
  todos: async (status = "", category = "", priority = "") => {
    try {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (category) params.set("category", category);
      if (priority) params.set("priority", priority);
      const res = await fetchWithTimeout(`${API}/productivity/todos?${params}`);
      return res.json();
    } catch (e) { console.warn("[Preload] todos failed:", e.message || e); return { todos: [] }; }
  },

  todoCreate: async (data) => {
    const res = await fetchWithTimeout(`${API}/productivity/todos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  todoUpdate: async (id, data) => {
    const res = await fetchWithTimeout(`${API}/productivity/todos/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  todoDelete: async (id) => {
    const res = await fetchWithTimeout(`${API}/productivity/todos/${id}`, { method: "DELETE" });
    return res.json();
  },

  todoComplete: async (id) => {
    const res = await fetchWithTimeout(`${API}/productivity/todos/${id}/complete`, { method: "POST" });
    return res.json();
  },

  pomodoroStatus: async () => {
    try { const res = await fetchWithTimeout(`${API}/productivity/pomodoro`); return res.json(); }
    catch (e) { console.warn("[Preload] pomodoroStatus failed:", e.message || e); return { running: false }; }
  },

  pomodoroStart: async (task = "", duration = 25) => {
    const res = await fetchWithTimeout(`${API}/productivity/pomodoro/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, duration }),
    });
    return res.json();
  },

  pomodoroStop: async () => {
    const res = await fetchWithTimeout(`${API}/productivity/pomodoro/stop`, { method: "POST" });
    return res.json();
  },

  habits: async () => {
    try { const res = await fetchWithTimeout(`${API}/productivity/habits`); return res.json(); }
    catch (e) { console.warn("[Preload] habits failed:", e.message || e); return { habits: [] }; }
  },

  habitCreate: async (data) => {
    const res = await fetchWithTimeout(`${API}/productivity/habits`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  habitLog: async (name, count = 1) => {
    const res = await fetchWithTimeout(`${API}/productivity/habits/${encodeURIComponent(name)}/log`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ count }),
    });
    return res.json();
  },

  habitDelete: async (name) => {
    const res = await fetchWithTimeout(`${API}/productivity/habits/${encodeURIComponent(name)}`, { method: "DELETE" });
    return res.json();
  },

  timeTracking: async () => {
    try { const res = await fetchWithTimeout(`${API}/productivity/time-tracking`); return res.json(); }
    catch (e) { console.warn("[Preload] timeTracking failed:", e.message || e); return { running: false }; }
  },

  timeTrackingStart: async () => {
    const res = await fetchWithTimeout(`${API}/productivity/time-tracking/start`, { method: "POST" });
    return res.json();
  },

  timeTrackingStop: async () => {
    const res = await fetchWithTimeout(`${API}/productivity/time-tracking/stop`, { method: "POST" });
    return res.json();
  },

  timeTrackingReport: async (days = 1) => {
    try { const res = await fetchWithTimeout(`${API}/productivity/time-tracking/report?days=${days}`); return res.json(); }
    catch (e) { console.warn("[Preload] timeTrackingReport failed:", e.message || e); return { report: [] }; }
  },

  focusStatus: async () => {
    try { const res = await fetchWithTimeout(`${API}/productivity/focus`); return res.json(); }
    catch (e) { console.warn("[Preload] focusStatus failed:", e.message || e); return { active: false }; }
  },

  focusOn: async (sites = "") => {
    const res = await fetchWithTimeout(`${API}/productivity/focus/on`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sites }),
    });
    return res.json();
  },

  focusOff: async () => {
    const res = await fetchWithTimeout(`${API}/productivity/focus/off`, { method: "POST" });
    return res.json();
  },

  productivityStats: async () => {
    try { const res = await fetchWithTimeout(`${API}/productivity/stats`); return res.json(); }
    catch (e) { console.warn("[Preload] productivityStats failed:", e.message || e); return {}; }
  },

  weeklyStats: async (days = 7) => {
    try { const res = await fetchWithTimeout(`${API}/productivity/weekly?days=${days}`); return res.json(); }
    catch (e) { console.warn("[Preload] weeklyStats failed:", e.message || e); return { days: [] }; }
  },

  // Batch command execution (Phase 27)
  executeBatch: async (commands, stopOnError = true) => {
    const res = await fetchWithTimeout(`${API}/companion/execute/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ commands, stop_on_error: stopOnError }),
    });
    return res.json();
  },

  // Desktop Integration (Phase 8)
  notify: (title, body, silent = false) => {
    ipcRenderer.send("show-notification", { title, body, silent });
  },

  getAutostart: () => ipcRenderer.sendSync("get-autostart"),
  setAutostart: (enabled) => ipcRenderer.send("set-autostart", enabled),

  // Listen for tray view-switch events
  onSwitchView: (callback) => {
    ipcRenderer.on("switch-view", (_, view) => callback(view));
  },

  // Companion commands list
  commands: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/companion/commands`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] commands failed:", e.message || e);
      return { commands: {}, total: 0 };
    }
  },

  // Timer polling
  timers: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/companion/timers`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] timers failed:", e.message || e);
      return { timers: [] };
    }
  },

  timersAcknowledge: async () => {
    try {
      await fetchWithTimeout(`${API}/companion/timers/acknowledge`, { method: "POST" });
    } catch (e) { console.warn("[Preload] timersAcknowledge failed:", e.message || e); }
  },

  pomodoroAcknowledge: async () => {
    try {
      await fetchWithTimeout(`${API}/productivity/pomodoro/acknowledge`, { method: "POST" });
    } catch (e) { console.warn("[Preload] pomodoroAcknowledge failed:", e.message || e); }
  },

  // Diagnostics
  diagnostics: async () => {
    const res = await fetchWithTimeout(`${API}/diagnostics`);
    return res.json();
  },

  // Memory cleanup
  memoryCleanup: async (daysOld = 90, maxImportance = 3) => {
    const res = await fetchWithTimeout(`${API}/memory/cleanup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days_old: daysOld, max_importance: maxImportance }),
    });
    return res.json();
  },

  // Backup / Restore (JSON)
  backupCreate: async () => {
    const res = await fetchWithTimeout(`${API}/backup`);
    return res.json();
  },
  backupRestore: async (data) => {
    const res = await fetchWithTimeout(`${API}/backup/restore`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  // Backup / Restore (SQLite binary)
  backupCreateDb: async () => {
    const r = await fetchWithTimeout(`${API}/backup/create`, { method: 'POST' });
    return r.json();
  },
  backupListDb: async () => {
    const r = await fetchWithTimeout(`${API}/backup/list`);
    return r.json();
  },
  backupRestoreDb: async (path) => {
    const r = await fetchWithTimeout(`${API}/backup/restore-db`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path })
    });
    return r.json();
  },

  // FTS5 Full-Text Search
  ftsSearch: async (query) => {
    const r = await fetchWithTimeout(`${API}/search/fts?q=${encodeURIComponent(query)}`);
    return r.json();
  },
  rebuildFts: async () => {
    const r = await fetchWithTimeout(`${API}/memory/rebuild-fts`, { method: 'POST' });
    return r.json();
  },

  // Clear backend chat history
  historyClear: async () => {
    try {
      await fetchWithTimeout(`${API}/history`, { method: "DELETE" });
    } catch (e) { console.warn("[Preload] historyClear failed:", e.message || e); }
  },

  // License Key Management (Phase 39)
  licenseGet: () => ipcRenderer.invoke("license-get"),
  licenseSet: (data) => ipcRenderer.invoke("license-set", data),
  licenseValidate: async (key) => {
    try {
      const res = await fetchWithTimeout(`${API}/license/validate/${encodeURIComponent(key)}`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] licenseValidate failed:", e.message || e);
      return { valid: false, error: "Backend nicht erreichbar" };
    }
  },

  // Weather (OpenWeatherMap)
  weatherCurrent: async (city = "") => {
    try {
      const res = await fetchWithTimeout(`${API}/companion/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: "weather_current", params: city ? { city } : {} }),
      });
      return res.json();
    } catch (e) {
      console.warn("[Preload] weatherCurrent failed:", e.message || e);
      return { success: false, error: "Wetter nicht verfügbar" };
    }
  },
  weatherForecast: async (city = "", days = 3) => {
    try {
      const params = {};
      if (city) params.city = city;
      if (days && days !== 3) params.days = days;
      const res = await fetchWithTimeout(`${API}/companion/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: "weather_forecast", params }),
      });
      return res.json();
    } catch (e) {
      console.warn("[Preload] weatherForecast failed:", e.message || e);
      return { success: false, error: "Vorhersage nicht verfügbar" };
    }
  },

  // Auto-update check notification (from main process)
  onUpdateAvailable: (callback) => {
    ipcRenderer.on("update-available", (_event, info) => callback(info));
  },

  // Wake Word (Phase 38)
  wakewordStart: async () => {
    const r = await fetchWithTimeout(`${API}/voice/wakeword/start`, { method: 'POST' });
    return r.json();
  },
  wakewordStop: async () => {
    const r = await fetchWithTimeout(`${API}/voice/wakeword/stop`, { method: 'POST' });
    return r.json();
  },
  wakewordStatus: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/voice/wakeword/status`);
      return r.json();
    } catch (e) { console.warn("[Preload] wakewordStatus failed:", e.message || e); return { active: false }; }
  },
  wakewordEvents: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/voice/wakeword/events`);
      return r.json();
    } catch (e) { console.warn("[Preload] wakewordEvents failed:", e.message || e); return { events: [] }; }
  },

  // Direct Conversation Mode (click orb → talk naturally)
  conversationStart: async () => {
    const r = await fetchWithTimeout(`${API}/voice/conversation/start`, { method: 'POST' });
    return r.json();
  },
  conversationStop: async () => {
    const r = await fetchWithTimeout(`${API}/voice/conversation/stop`, { method: 'POST' });
    return r.json();
  },

  // ── MCP — Model Context Protocol (Phase 47) ────────────────
  mcpServers: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/mcp/servers`);
      return r.json();
    } catch (e) {
      console.warn("[Preload] mcpServers failed:", e.message || e);
      return { enabled: false, servers: [] };
    }
  },
  mcpConnect: async (name) => {
    const r = await fetchWithTimeout(`${API}/mcp/servers/${encodeURIComponent(name)}/connect`, { method: "POST" });
    return r.json();
  },
  mcpDisconnect: async (name) => {
    const r = await fetchWithTimeout(`${API}/mcp/servers/${encodeURIComponent(name)}/disconnect`, { method: "POST" });
    return r.json();
  },
  mcpServerTools: async (name) => {
    try {
      const r = await fetchWithTimeout(`${API}/mcp/servers/${encodeURIComponent(name)}/tools`);
      return r.json();
    } catch (e) {
      console.warn("[Preload] mcpServerTools failed:", e.message || e);
      return { tools: [], count: 0 };
    }
  },
  mcpCallTool: async (serverName, tool, args = {}) => {
    const r = await fetchWithTimeout(`${API}/mcp/servers/${encodeURIComponent(serverName)}/call`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool, arguments: args }),
    });
    return r.json();
  },

  // ── WebSocket Voice Events (ChatGPT-style instant delivery) ──────
  // Returns a controller object: { close(), onEvent(callback) }
  // ── Vision/OCR (Upgrade 6) ──────────────────
  visionAnalyze: async (prompt = "", window = "") => {
    try {
      const res = await fetchWithTimeout(`${API}/vision/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt || "Was ist auf dem Bildschirm zu sehen?", auto_capture: true, window: window || null }),
      });
      return res.json();
    } catch (e) {
      console.warn("[Preload] visionAnalyze failed:", e.message || e);
      return { success: false, error: "Vision nicht erreichbar" };
    }
  },

  visionOcr: async (window = "") => {
    try {
      const res = await fetchWithTimeout(`${API}/companion/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: "screen_read_text", params: window ? { window } : {} }),
      });
      return res.json();
    } catch (e) {
      console.warn("[Preload] visionOcr failed:", e.message || e);
      return { success: false, error: "OCR nicht erreichbar" };
    }
  },

  visionStatus: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/vision/status`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] visionStatus failed:", e.message || e);
      return { success: false, data: { available: false } };
    }
  },

  // ── Agent (Phase 46) ────────────────────────
  agentRun: async (message) => {
    // Returns a ReadableStream of SSE events for the agent loop.
    // The caller should use the EventSource-like pattern or fetch+reader.
    const res = await fetch(`${API}/agent/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    return res;
  },
  agentChat: async (message) => {
    const res = await fetchWithTimeout(`${API}/agent/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    }, 120000); // 2min timeout for agent tasks
    return res.json();
  },
  agentStatus: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/agent/status`);
      return r.json();
    } catch (e) { return { enabled: false }; }
  },

  voiceWebSocket: () => {
    const WS_URL = API.replace('http', 'ws') + '/voice/ws';
    let ws = null;
    let eventCallback = null;
    let reconnectTimer = null;
    let isClosedManually = false;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 30;
    const BASE_DELAY = 1000;
    const MAX_DELAY = 30000;

    function connect() {
      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.warn("[Preload] Voice WS max reconnect attempts reached — giving up");
        return;
      }
      try {
        ws = new WebSocket(WS_URL);
      } catch (e) {
        console.warn("[Preload] WebSocket connect failed:", e.message || e);
        return;
      }

      ws.onopen = () => {
        console.info("[Preload] Voice WebSocket connected");
        reconnectAttempts = 0; // Reset on successful connection
      };

      ws.onmessage = (msg) => {
        if (!eventCallback) return;
        try {
          const evt = JSON.parse(msg.data);
          eventCallback(evt);
        } catch (e) {
          console.warn("[Preload] Voice WS parse error:", e.message || e);
        }
      };

      ws.onclose = () => {
        console.info("[Preload] Voice WebSocket closed");
        if (!isClosedManually) {
          reconnectAttempts++;
          // Exponential backoff: 1s, 2s, 4s, 8s, ... up to 30s
          const delay = Math.min(BASE_DELAY * Math.pow(2, reconnectAttempts - 1), MAX_DELAY);
          reconnectTimer = setTimeout(connect, delay);
        }
      };

      ws.onerror = (e) => {
        console.warn("[Preload] Voice WS error:", e.message || e);
      };
    }

    connect();

    return {
      onEvent(callback) { eventCallback = callback; },
      close() {
        isClosedManually = true;
        if (reconnectTimer) clearTimeout(reconnectTimer);
        if (ws) { try { ws.close(); } catch (e) { /* ignore */ } }
      },
      get connected() { return ws && ws.readyState === WebSocket.OPEN; },
    };
  },
});
