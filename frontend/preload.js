const { contextBridge, ipcRenderer } = require("electron");

const API = "http://127.0.0.1:8000";

// Secure Bridge — nur erlaubte APIs exposen
contextBridge.exposeInMainWorld("lexa", {
  // Window Controls
  minimize: () => ipcRenderer.send("window-minimize"),
  maximize: () => ipcRenderer.send("window-maximize"),
  close: () => ipcRenderer.send("window-close"),

  // Chat API
  chat: async (message) => {
    const res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    return res.json();
  },

  // Companion API
  execute: async (command, params = {}, confirmed = false) => {
    const res = await fetch(`${API}/companion/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, params, confirmed }),
    });
    return res.json();
  },

  // Voice: Text-to-Speech
  tts: async (text) => {
    const res = await fetch(`${API}/voice/tts`, {
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
    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.wav");
    const res = await fetch(`${API}/voice/stt`, {
      method: "POST",
      body: formData,
    });
    return res.json();
  },

  // Voice status
  voiceStatus: async () => {
    try {
      const [tts, stt] = await Promise.all([
        fetch(`${API}/voice/tts/status`).then((r) => r.json()),
        fetch(`${API}/voice/stt/status`).then((r) => r.json()),
      ]);
      return { tts, stt };
    } catch {
      return { tts: { ready: false }, stt: { ready: false } };
    }
  },

  // Health
  health: async () => {
    try {
      const res = await fetch(`${API}/health`);
      return res.json();
    } catch {
      return { status: "offline" };
    }
  },

  // AI Status (Groq + Ollama)
  aiStatus: async () => {
    try {
      const res = await fetch(`${API}/ai/status`);
      return res.json();
    } catch {
      return { active_provider: "none" };
    }
  },

  // Memory
  memoryStats: async () => {
    try {
      const res = await fetch(`${API}/memory/stats`);
      return res.json();
    } catch {
      return { notes: 0, memories: 0, interactions: 0, routines: 0 };
    }
  },

  notes: async () => {
    try {
      const res = await fetch(`${API}/memory/notes`);
      return res.json();
    } catch {
      return { notes: [] };
    }
  },

  routines: async () => {
    try {
      const res = await fetch(`${API}/memory/routines`);
      return res.json();
    } catch {
      return { routines: [] };
    }
  },

  setProfile: async (key, value) => {
    const res = await fetch(`${API}/memory/profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key, value }),
    });
    return res.json();
  },

  // Conversations (Phase 11)
  conversations: async () => {
    try {
      const res = await fetch(`${API}/conversations`);
      return res.json();
    } catch {
      return { conversations: [] };
    }
  },

  conversationCreate: async (title = "Neuer Chat") => {
    const res = await fetch(`${API}/conversations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    return res.json();
  },

  conversationGet: async (id) => {
    const res = await fetch(`${API}/conversations/${id}`);
    return res.json();
  },

  conversationUpdate: async (id, data) => {
    const res = await fetch(`${API}/conversations/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  conversationDelete: async (id) => {
    const res = await fetch(`${API}/conversations/${id}`, { method: "DELETE" });
    return res.json();
  },

  conversationLoad: async (id) => {
    const res = await fetch(`${API}/conversations/${id}/load`, { method: "POST" });
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
});
