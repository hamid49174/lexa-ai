const { contextBridge, ipcRenderer } = require("electron");

const API = "http://127.0.0.1:8000";
const LOCAL_AUTH_HEADER = "X-Lexa-Local-Token";
let localAuthTokenPromise = null;

function isLocalLexaBackendUrl(url) {
  try {
    const parsed = new URL(String(url), API);
    const api = new URL(API);
    return parsed.protocol === api.protocol
      && parsed.port === api.port
      && ["127.0.0.1", "localhost"].includes(parsed.hostname);
  } catch (_error) {
    return false;
  }
}

function getLocalAuthToken() {
  if (!localAuthTokenPromise) {
    localAuthTokenPromise = ipcRenderer.invoke("local-auth-token").catch(() => "");
  }
  return localAuthTokenPromise;
}

async function withLocalAuthHeader(url, options = {}) {
  const requestOptions = { ...options };
  if (!isLocalLexaBackendUrl(url)) return requestOptions;
  const token = await getLocalAuthToken();
  if (!token) return requestOptions;
  const headers = new Headers(requestOptions.headers || {});
  headers.set(LOCAL_AUTH_HEADER, token);
  requestOptions.headers = headers;
  return requestOptions;
}

function bridgePolicy(name, risk, action_type, target, options = {}) {
  const requiresGate = risk === "high" || risk === "critical";
  return Object.freeze({
    name,
    risk,
    action_type,
    target,
    requires_user_presence: options.requires_user_presence ?? requiresGate,
    requires_main_confirmation: options.requires_main_confirmation ?? requiresGate,
    batch_allowed: Boolean(options.batch_allowed),
    audit: options.audit ?? requiresGate,
  });
}

function buildBridgeMethodPolicy(entries) {
  const policy = {};
  for (const entry of entries) {
    policy[entry.name] = entry;
  }
  return Object.freeze(policy);
}

const BRIDGE_METHOD_POLICY = buildBridgeMethodPolicy([
  bridgePolicy("API_BASE", "low", "read", "constant"),
  bridgePolicy("loadI18n", "low", "read", "ipc:i18n-load", { batch_allowed: true }),
  bridgePolicy("minimize", "low", "write", "ipc:window-minimize"),
  bridgePolicy("maximize", "low", "write", "ipc:window-maximize"),
  bridgePolicy("close", "low", "write", "ipc:window-close"),
  bridgePolicy("notify", "medium", "write", "ipc:show-notification", { audit: true }),
  bridgePolicy("getAutostart", "low", "read", "ipc:get-autostart", { batch_allowed: true }),
  bridgePolicy("setAutostart", "high", "admin", "ipc:set-autostart"),
  bridgePolicy("onSwitchView", "low", "read", "ipc:switch-view", { batch_allowed: true }),
  bridgePolicy("onUpdateAvailable", "low", "read", "ipc:update-available", { batch_allowed: true }),
  bridgePolicy("licenseGet", "medium", "secret", "ipc:license-get"),
  bridgePolicy("licenseActivate", "high", "secret", "ipc:license-activate"),
  bridgePolicy("licenseSet", "high", "secret", "ipc:license-set"),
  bridgePolicy("licenseValidate", "high", "secret", "/license/validate"),

  bridgePolicy("chat", "medium", "write", "/chat"),
  bridgePolicy("chatFile", "medium", "write", "/chat/file"),
  bridgePolicy("generateTitle", "medium", "write", "/ai/title"),
  bridgePolicy("execute", "critical", "execute", "/companion/execute"),
  bridgePolicy("prepareCompanionExecute", "medium", "write", "/companion/execute/prepare", { audit: true }),
  bridgePolicy("executeWithConfirmation", "critical", "execute", "/companion/execute"),
  bridgePolicy("executeBatch", "critical", "execute", "/companion/execute/batch"),
  bridgePolicy("companionAuditRecent", "low", "read", "/companion/audit/recent", { batch_allowed: true }),
  bridgePolicy("commands", "low", "read", "/companion/commands", { batch_allowed: true }),
  bridgePolicy("timers", "low", "read", "/companion/timers", { batch_allowed: true }),
  bridgePolicy("timersAcknowledge", "medium", "write", "/companion/timers/acknowledge", { audit: true }),

  bridgePolicy("tts", "medium", "write", "/voice/tts"),
  bridgePolicy("stt", "medium", "secret", "/voice/stt"),
  bridgePolicy("voiceStatus", "low", "read", "/voice/diagnostics", { batch_allowed: true }),
  bridgePolicy("voiceDiagnostics", "low", "read", "/voice/diagnostics", { batch_allowed: true }),
  bridgePolicy("voiceArchitecture", "low", "read", "/voice/architecture", { batch_allowed: true }),
  bridgePolicy("voiceRealtimePreflight", "low", "read", "/voice/realtime/preflight", { batch_allowed: true }),
  bridgePolicy("voiceRealtimeStart", "high", "secret", "/voice/realtime/start"),
  bridgePolicy("voiceRealtimeStop", "medium", "write", "/voice/realtime/stop", { audit: true }),
  bridgePolicy("voiceWebSocket", "medium", "secret", "ws:/voice/ws", { audit: true }),
  bridgePolicy("ttsVoices", "low", "read", "/voice/tts/voices", { batch_allowed: true }),
  bridgePolicy("elevenlabsSetKey", "critical", "secret", "/voice/tts/elevenlabs/key"),
  bridgePolicy("elevenlabsDeleteKey", "critical", "secret", "/voice/tts/elevenlabs/key"),
  bridgePolicy("elevenlabsVoices", "low", "read", "/voice/tts/elevenlabs/voices", { batch_allowed: true }),
  bridgePolicy("elevenlabsSetVoice", "medium", "write", "/voice/tts/elevenlabs/voice", { audit: true }),
  bridgePolicy("elevenlabsSetModel", "medium", "write", "/voice/tts/elevenlabs/model", { audit: true }),
  bridgePolicy("elevenlabsSetSettings", "medium", "write", "/voice/tts/elevenlabs/settings", { audit: true }),
  bridgePolicy("elevenlabsToggle", "medium", "write", "/voice/tts/elevenlabs/toggle", { audit: true }),
  bridgePolicy("sttModels", "low", "read", "/voice/stt/models", { batch_allowed: true }),
  bridgePolicy("sttSetModel", "medium", "write", "/voice/stt/model", { audit: true }),
  bridgePolicy("sttSetLanguage", "medium", "write", "/voice/stt/language", { audit: true }),
  bridgePolicy("sttSetEngine", "medium", "write", "/voice/stt/engine", { audit: true }),
  bridgePolicy("deepgramSetKey", "critical", "secret", "/voice/stt/deepgram/key"),
  bridgePolicy("deepgramDeleteKey", "critical", "secret", "/voice/stt/deepgram/key"),
  bridgePolicy("cartesiaSetKey", "critical", "secret", "/voice/tts/cartesia/key"),
  bridgePolicy("cartesiaDeleteKey", "critical", "secret", "/voice/tts/cartesia/key"),
  bridgePolicy("wakewordStart", "high", "secret", "/voice/wakeword/start"),
  bridgePolicy("wakewordStop", "medium", "write", "/voice/wakeword/stop", { audit: true }),
  bridgePolicy("wakewordStatus", "low", "read", "/voice/wakeword/status", { batch_allowed: true }),
  bridgePolicy("wakewordEvents", "low", "read", "/voice/wakeword/events", { batch_allowed: true }),
  bridgePolicy("conversationStart", "high", "secret", "/voice/conversation/start"),
  bridgePolicy("conversationStop", "medium", "write", "/voice/conversation/stop", { audit: true }),

  bridgePolicy("health", "low", "read", "/health", { batch_allowed: true }),
  bridgePolicy("startupHealth", "low", "read", "/health/startup", { batch_allowed: true }),
  bridgePolicy("aiStatus", "low", "read", "/ai/status", { batch_allowed: true }),
  bridgePolicy("aiModels", "low", "read", "/ai/models", { batch_allowed: true }),
  bridgePolicy("setAiModel", "medium", "write", "/ai/models", { audit: true }),
  bridgePolicy("diagnostics", "low", "read", "/diagnostics", { batch_allowed: true }),
  bridgePolicy("healthTools", "low", "read", "/health/tools", { batch_allowed: true }),

  bridgePolicy("memoryStats", "low", "read", "/memory/stats", { batch_allowed: true }),
  bridgePolicy("memoryGraph", "low", "read", "/memory/graph", { batch_allowed: true }),
  bridgePolicy("memoryAdd", "medium", "write", "/memory/add", { audit: true }),
  bridgePolicy("memoryCleanup", "high", "admin", "/memory/cleanup"),
  bridgePolicy("notes", "low", "read", "/memory/notes", { batch_allowed: true }),
  bridgePolicy("noteGet", "low", "read", "/memory/notes/{id}", { batch_allowed: true }),
  bridgePolicy("noteUpdate", "medium", "write", "/memory/notes/{id}", { audit: true }),
  bridgePolicy("routines", "low", "read", "/memory/routines", { batch_allowed: true }),
  bridgePolicy("setProfile", "high", "write", "/memory/profile"),
  bridgePolicy("ftsSearch", "low", "read", "/search/fts", { batch_allowed: true }),
  bridgePolicy("rebuildFts", "medium", "admin", "/memory/rebuild-fts", { audit: true }),
  bridgePolicy("historyClear", "high", "admin", "/history"),
  bridgePolicy("search", "low", "read", "/search", { batch_allowed: true }),
  bridgePolicy("conversations", "low", "read", "/conversations", { batch_allowed: true }),
  bridgePolicy("conversationCreate", "medium", "write", "/conversations", { audit: true }),
  bridgePolicy("conversationGet", "low", "read", "/conversations/{id}", { batch_allowed: true }),
  bridgePolicy("conversationUpdate", "high", "write", "/conversations/{id}"),
  bridgePolicy("conversationDelete", "high", "admin", "/conversations/{id}"),
  bridgePolicy("conversationLoad", "medium", "write", "/conversations/{id}/load", { audit: true }),
  bridgePolicy("conversationExport", "medium", "read", "/conversations/{id}/export"),

  bridgePolicy("calendarStatus", "low", "read", "/calendar/status", { batch_allowed: true }),
  bridgePolicy("calendarToday", "low", "read", "/calendar/today", { batch_allowed: true }),
  bridgePolicy("calendarWeek", "low", "read", "/calendar/week", { batch_allowed: true }),
  bridgePolicy("calendarConnect", "high", "admin", "/calendar/connect"),
  bridgePolicy("clipboardHistory", "high", "secret", "/clipboard/history"),
  bridgePolicy("clipboardAdd", "medium", "write", "/clipboard/add", { audit: true }),
  bridgePolicy("clipboardClear", "high", "admin", "/clipboard/history"),
  bridgePolicy("snippets", "low", "read", "/snippets", { batch_allowed: true }),
  bridgePolicy("snippetCreate", "medium", "write", "/snippets", { audit: true }),
  bridgePolicy("snippetDelete", "medium", "admin", "/snippets/{name}", { audit: true }),

  bridgePolicy("todos", "low", "read", "/productivity/todos", { batch_allowed: true }),
  bridgePolicy("todoCreate", "medium", "write", "/productivity/todos", { audit: true }),
  bridgePolicy("todoUpdate", "medium", "write", "/productivity/todos/{id}", { audit: true }),
  bridgePolicy("todoDelete", "medium", "admin", "/productivity/todos/{id}", { audit: true }),
  bridgePolicy("todoComplete", "medium", "write", "/productivity/todos/{id}/complete", { audit: true }),
  bridgePolicy("pomodoroStatus", "low", "read", "/productivity/pomodoro", { batch_allowed: true }),
  bridgePolicy("pomodoroStart", "medium", "write", "/productivity/pomodoro/start", { audit: true }),
  bridgePolicy("pomodoroStop", "medium", "write", "/productivity/pomodoro/stop", { audit: true }),
  bridgePolicy("pomodoroAcknowledge", "medium", "write", "/productivity/pomodoro/acknowledge", { audit: true }),
  bridgePolicy("habits", "low", "read", "/productivity/habits", { batch_allowed: true }),
  bridgePolicy("habitCreate", "medium", "write", "/productivity/habits", { audit: true }),
  bridgePolicy("habitLog", "medium", "write", "/productivity/habits/{name}/log", { audit: true }),
  bridgePolicy("habitDelete", "medium", "admin", "/productivity/habits/{name}", { audit: true }),
  bridgePolicy("timeTracking", "low", "read", "/productivity/time-tracking", { batch_allowed: true }),
  bridgePolicy("timeTrackingStart", "medium", "write", "/productivity/time-tracking/start", { audit: true }),
  bridgePolicy("timeTrackingStop", "medium", "write", "/productivity/time-tracking/stop", { audit: true }),
  bridgePolicy("timeTrackingReport", "low", "read", "/productivity/time-tracking/report", { batch_allowed: true }),
  bridgePolicy("focusStatus", "low", "read", "/productivity/focus", { batch_allowed: true }),
  bridgePolicy("focusOn", "medium", "write", "/productivity/focus/on", { audit: true }),
  bridgePolicy("focusOff", "medium", "write", "/productivity/focus/off", { audit: true }),
  bridgePolicy("productivityStats", "low", "read", "/productivity/stats", { batch_allowed: true }),
  bridgePolicy("weeklyStats", "low", "read", "/productivity/weekly", { batch_allowed: true }),

  bridgePolicy("hermesGatewayAutostartStatus", "low", "read", "/hermes/gateway/autostart", { batch_allowed: true }),
  bridgePolicy("hermesGatewayAutostartSet", "high", "admin", "/hermes/gateway/autostart"),
  bridgePolicy("hermesCapabilities", "low", "read", "/hermes/capabilities", { batch_allowed: true }),
  bridgePolicy("hermesProviders", "low", "read", "/hermes/providers", { batch_allowed: true }),
  bridgePolicy("hermesOverview", "low", "read", "/hermes/overview", { batch_allowed: true }),
  bridgePolicy("backupCreate", "high", "secret", "/backup"),
  bridgePolicy("backupRestore", "critical", "admin", "/backup/restore"),
  bridgePolicy("backupCreateDb", "medium", "admin", "/backup/create", { audit: true }),
  bridgePolicy("backupListDb", "low", "read", "/backup/list", { batch_allowed: true }),
  bridgePolicy("backupRestoreDb", "critical", "admin", "/backup/restore-db"),
  bridgePolicy("weatherCurrent", "medium", "read", "/companion/execute:weather_current"),
  bridgePolicy("weatherForecast", "medium", "read", "/companion/execute:weather_forecast"),
  bridgePolicy("visionAnalyze", "critical", "secret", "/vision/analyze"),
  bridgePolicy("visionOcr", "high", "secret", "/companion/execute:screen_read_text"),
  bridgePolicy("visionStatus", "low", "read", "/vision/status", { batch_allowed: true }),
  bridgePolicy("agentRun", "critical", "execute", "/agent/run"),
  bridgePolicy("agentStreamRead", "low", "read", "agent-stream:read"),
  bridgePolicy("agentStreamCancel", "low", "write", "agent-stream:cancel"),
  bridgePolicy("agentChat", "critical", "execute", "/agent/chat"),
  bridgePolicy("agentStatus", "low", "read", "/agent/status", { batch_allowed: true }),
  bridgePolicy("mcpServers", "low", "read", "/mcp/servers", { batch_allowed: true }),
  bridgePolicy("mcpConnect", "critical", "execute", "/mcp/servers/{name}/connect"),
  bridgePolicy("mcpDisconnect", "critical", "execute", "/mcp/servers/{name}/disconnect"),
  bridgePolicy("mcpServerTools", "low", "read", "/mcp/servers/{name}/tools", { batch_allowed: true }),
  bridgePolicy("mcpCallTool", "critical", "execute", "/mcp/servers/{server}/call"),

  bridgePolicy("personalOsStatus", "low", "read", "/personal-os/status", { batch_allowed: true }),
  bridgePolicy("personalOsDiagnostics", "low", "read", "/personal-os/diagnostics", { batch_allowed: true }),
  bridgePolicy("personalOsDrafts", "low", "read", "/personal-os/drafts", { batch_allowed: true }),
  bridgePolicy("personalOsDraftView", "low", "read", "/personal-os/drafts/view", { batch_allowed: true }),
  bridgePolicy("personalOsDraftReview", "low", "read", "/personal-os/drafts/review", { batch_allowed: true }),
  bridgePolicy("personalOsDraftDecision", "high", "write", "/personal-os/drafts/decision"),
  bridgePolicy("personalOsDraftApply", "critical", "admin", "/personal-os/drafts/apply"),
  bridgePolicy("personalOsQuery", "low", "read", "/personal-os/query", { batch_allowed: true }),
  bridgePolicy("personalOsReadFile", "medium", "read", "/personal-os/files/read"),
  bridgePolicy("personalOsGraph", "low", "read", "/personal-os/graph", { batch_allowed: true }),
  bridgePolicy("personalOsContextPack", "low", "read", "/personal-os/context-pack", { batch_allowed: true }),
  bridgePolicy("personalOsObsidianContext", "low", "read", "/personal-os/obsidian-context", { batch_allowed: true }),
  bridgePolicy("personalOsSharedContext", "low", "read", "/personal-os/shared-context", { batch_allowed: true }),
  bridgePolicy("personalOsCodeLoop", "medium", "read", "/personal-os/lexa-code-loop"),
  bridgePolicy("personalOsRawSubmit", "high", "write", "/personal-os/raw-inbox/submit"),
  bridgePolicy("personalOsRawStatus", "low", "read", "/personal-os/raw-inbox/status", { batch_allowed: true }),
]);

const READ_ONLY_COMPANION_BATCH_COMMANDS = new Set([
  "system_info",
  "weather_current",
  "weather_forecast",
]);

const BRIDGE_RISK_RANK = Object.freeze({ low: 0, medium: 1, high: 2, critical: 3 });
const BRIDGE_AUDIT_RISK = 1;
const SIMPLE_PROFILE_KEYS = new Set(["name", "language", "theme", "accent", "locale"]);
const SENSITIVE_PROFILE_KEY_PATTERN = /(?:api|auth|credential|email|identity|key|license|password|payment|secret|security|token)/i;
const SENSITIVE_OS_PATH_PATTERN = /(?:^|[\\/])(?:00_System|03_Profile|05_Memory[\\/]Core|05_Memory[\\/]Stable)(?:[\\/]|$)|(?:\.env|secret|token|credential|password|private|identity|key)/i;
const PARAM_SENSITIVE_BRIDGE_METHODS = new Set([
  "conversationUpdate",
  "conversationGet",
  "conversationExport",
  "setProfile",
  "memoryAdd",
  "noteUpdate",
  "clipboardHistory",
  "personalOsReadFile",
  "personalOsQuery",
  "personalOsContextPack",
  "personalOsObsidianContext",
  "notes",
  "search",
  "ftsSearch",
  "mcpServers",
  "mcpServerTools",
]);

function riskAtLeast(risk, minimum) {
  return (BRIDGE_RISK_RANK[risk] ?? 0) >= (BRIDGE_RISK_RANK[minimum] ?? 0);
}

function effectiveBridgePolicy(basePolicy, overrides = {}) {
  const risk = overrides.risk || basePolicy.risk;
  const requiresGate = riskAtLeast(risk, "high");
  const audit = overrides.audit ?? (basePolicy.audit || (BRIDGE_RISK_RANK[risk] ?? 0) >= BRIDGE_AUDIT_RISK);
  return Object.freeze({
    ...basePolicy,
    ...overrides,
    base_risk: basePolicy.risk,
    risk,
    effective_risk: risk,
    requires_user_presence: overrides.requires_user_presence ?? requiresGate,
    requires_main_confirmation: overrides.requires_main_confirmation ?? requiresGate,
    audit,
    classification_reason: overrides.classification_reason || "base_policy",
    rate_limited: Boolean(overrides.rate_limited),
  });
}

function firstPayloadObject(args, index = 0) {
  const value = Array.isArray(args) ? args[index] : undefined;
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}

function objectKeys(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? Object.keys(value).sort() : [];
}

function hasOnlyKeys(value, allowedKeys) {
  const keys = objectKeys(value);
  return keys.length > 0 && keys.every((key) => allowedKeys.includes(key));
}

function normalizeBridgePathSegments(value) {
  const parts = String(value || "").replace(/\//g, "\\").split(/\\+/);
  const normalized = [];
  for (const part of parts) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (normalized.length > 0 && normalized[normalized.length - 1] !== "..") {
        normalized.pop();
      } else {
        normalized.push(part);
      }
      continue;
    }
    normalized.push(part);
  }
  return normalized.join("\\");
}

function bridgePathInfo(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return { normalized: "", insideRoot: false, hasParentSegment: false, suspicious: false };
  }
  const slashNormalized = raw.replace(/\//g, "\\");
  const rawSegments = slashNormalized.split(/\\+/).filter(Boolean);
  const hasParentSegment = rawSegments.includes("..");
  const dotOnlySegment = rawSegments.some((part) => /^\.\.+$/.test(part) && part !== "..");
  const absoluteOrDevicePath = slashNormalized.startsWith("\\")
    || /^[a-zA-Z]:/.test(slashNormalized)
    || /^\\\\[.?]\\/.test(slashNormalized)
    || /^\\\\/.test(slashNormalized);
  const normalized = normalizeBridgePathSegments(slashNormalized);
  return {
    normalized: normalized.replace(/\\/g, "/"),
    insideRoot: !absoluteOrDevicePath && !hasParentSegment,
    hasParentSegment,
    suspicious: dotOnlySegment || absoluteOrDevicePath,
  };
}

function normalizedBridgePath(value) {
  return bridgePathInfo(value).normalized;
}

function isPathTraversal(value) {
  const info = bridgePathInfo(value);
  if (!info.normalized) return false;
  return info.hasParentSegment || info.suspicious || !info.insideRoot;
}

function isSensitivePersonalOsPath(value) {
  const normalized = normalizedBridgePath(value);
  if (!normalized || isPathTraversal(normalized)) return true;
  return SENSITIVE_OS_PATH_PATTERN.test(normalized);
}

function clampPositiveInteger(value, fallback, min, max) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function classifyConversationUpdate(basePolicy, args) {
  const payload = firstPayloadObject(args, 1);
  if (!payload) {
    return effectiveBridgePolicy(basePolicy, {
      risk: "high",
      classification_reason: "conversation_update_missing_payload",
    });
  }
  if (hasOnlyKeys(payload, ["title"])) {
    return effectiveBridgePolicy(basePolicy, {
      risk: "medium",
      requires_user_presence: false,
      requires_main_confirmation: false,
      audit: true,
      classification_reason: "conversation_title_update",
    });
  }
  if (hasOnlyKeys(payload, ["messages"]) && Array.isArray(payload.messages)) {
    if (payload.messages.length > 0) {
      return effectiveBridgePolicy(basePolicy, {
        risk: "medium",
        requires_user_presence: false,
        requires_main_confirmation: false,
        audit: true,
        rate_limited: true,
        classification_reason: "conversation_autosave_messages",
      });
    }
    return effectiveBridgePolicy(basePolicy, {
      risk: "high",
      classification_reason: "conversation_clear_messages",
    });
  }
  return effectiveBridgePolicy(basePolicy, {
    risk: "high",
    classification_reason: "conversation_update_unusual_payload",
  });
}

function classifyProfileSet(basePolicy, args) {
  const key = String(args?.[0] || "").trim().toLowerCase();
  if (SIMPLE_PROFILE_KEYS.has(key)) {
    return effectiveBridgePolicy(basePolicy, {
      risk: "medium",
      requires_user_presence: false,
      requires_main_confirmation: false,
      audit: true,
      classification_reason: "profile_simple_key",
    });
  }
  return effectiveBridgePolicy(basePolicy, {
    risk: SENSITIVE_PROFILE_KEY_PATTERN.test(key) ? "high" : "medium",
    requires_user_presence: SENSITIVE_PROFILE_KEY_PATTERN.test(key),
    requires_main_confirmation: SENSITIVE_PROFILE_KEY_PATTERN.test(key),
    audit: true,
    classification_reason: SENSITIVE_PROFILE_KEY_PATTERN.test(key) ? "profile_sensitive_key" : "profile_unknown_key",
  });
}

function classifyPersonalOsReadFile(basePolicy, args) {
  const pathValue = args?.[0] || "";
  if (isPathTraversal(pathValue)) {
    return effectiveBridgePolicy(basePolicy, {
      risk: "high",
      blocked: true,
      classification_reason: "personal_os_path_traversal",
    });
  }
  const sensitivePath = isSensitivePersonalOsPath(pathValue);
  return effectiveBridgePolicy(basePolicy, {
    risk: sensitivePath ? "high" : "medium",
    requires_user_presence: sensitivePath,
    requires_main_confirmation: sensitivePath,
    audit: true,
    classification_reason: sensitivePath ? "personal_os_sensitive_path" : "personal_os_scope_limited_read",
  });
}

function classifyBridgeCall(method, args = []) {
  const basePolicy = BRIDGE_METHOD_POLICY[method];
  if (!basePolicy) return null;
  if (method === "conversationUpdate") return classifyConversationUpdate(basePolicy, args);
  if (method === "setProfile") return classifyProfileSet(basePolicy, args);
  if (method === "personalOsReadFile") return classifyPersonalOsReadFile(basePolicy, args);
  if (method === "conversationExport") {
    return effectiveBridgePolicy(basePolicy, { risk: "high", classification_reason: "conversation_full_export" });
  }
  if (method === "conversationGet") {
    return effectiveBridgePolicy(basePolicy, {
      risk: "medium",
      requires_user_presence: false,
      requires_main_confirmation: false,
      audit: true,
      classification_reason: "conversation_single_read",
    });
  }
  if (["notes", "search", "ftsSearch", "personalOsQuery", "personalOsContextPack", "personalOsObsidianContext"].includes(method)) {
    return effectiveBridgePolicy(basePolicy, {
      risk: "medium",
      requires_user_presence: false,
      requires_main_confirmation: false,
      audit: true,
      rate_limited: true,
      classification_reason: `${method}_privacy_limited_read`,
    });
  }
  if (["mcpServers", "mcpServerTools"].includes(method)) {
    return effectiveBridgePolicy(basePolicy, {
      risk: "medium",
      requires_user_presence: false,
      requires_main_confirmation: false,
      audit: true,
      classification_reason: "mcp_metadata_read",
    });
  }
  return effectiveBridgePolicy(basePolicy);
}

function stableBridgeValue(value, seen = new WeakSet(), depth = 0) {
  const MAX_DEPTH = 8;
  const MAX_ARRAY_ITEMS = 50;
  const MAX_OBJECT_KEYS = 50;
  const MAX_STRING_CHARS = 512;

  if (value === null || value === undefined) return value;
  const valueType = typeof value;
  if (valueType === "string") {
    return value.length > MAX_STRING_CHARS
      ? { __type: "String", length: value.length, prefix: value.slice(0, MAX_STRING_CHARS) }
      : value;
  }
  if (valueType === "number" || valueType === "boolean") return value;
  if (valueType === "bigint") return value.toString();
  if (valueType === "function") return "[Function]";
  if (valueType !== "object") return String(value);
  if (depth >= MAX_DEPTH) return "[MaxDepth]";
  if (seen.has(value)) return "[Circular]";
  seen.add(value);

  if (typeof Blob !== "undefined" && value instanceof Blob) {
    return {
      __type: value.constructor?.name || "Blob",
      size: value.size,
      type: value.type || "",
      name: value.name || "",
      lastModified: value.lastModified || 0,
    };
  }

  if (value instanceof ArrayBuffer) {
    return { __type: "ArrayBuffer", byteLength: value.byteLength };
  }

  if (ArrayBuffer.isView(value)) {
    return { __type: value.constructor?.name || "TypedArray", byteLength: value.byteLength };
  }

  if (Array.isArray(value)) {
    const normalizedItems = value
      .slice(0, MAX_ARRAY_ITEMS)
      .map((item) => stableBridgeValue(item, seen, depth + 1));
    if (value.length > MAX_ARRAY_ITEMS) {
      normalizedItems.push({ __truncated_items: value.length - MAX_ARRAY_ITEMS });
    }
    return normalizedItems;
  }

  const normalized = {};
  const keys = Object.keys(value).sort();
  for (const key of keys.slice(0, MAX_OBJECT_KEYS)) {
    normalized[key] = stableBridgeValue(value[key], seen, depth + 1);
  }
  if (keys.length > MAX_OBJECT_KEYS) {
    normalized.__truncated_keys = keys.length - MAX_OBJECT_KEYS;
  }
  return normalized;
}

function bytesToHex(bytes) {
  return Array.from(bytes).map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function sha256Hex(text) {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new Error("bridge_crypto_unavailable");
  const encoded = new TextEncoder().encode(String(text));
  const digest = await subtle.digest("SHA-256", encoded);
  return bytesToHex(new Uint8Array(digest));
}

async function bridgeArgsHash(args = []) {
  const normalized = stableBridgeValue(Array.from(args));
  return sha256Hex(JSON.stringify(normalized));
}

function bridgeArgKeys(args = []) {
  const keys = [];
  Array.from(args).forEach((arg, index) => {
    if (arg && typeof arg === "object" && !(typeof Blob !== "undefined" && arg instanceof Blob) && !Array.isArray(arg)) {
      const objectKeys = Object.keys(arg).sort();
      if (objectKeys.length) {
        objectKeys.slice(0, 20).forEach((key) => keys.push(`arg${index}.${key}`));
        if (objectKeys.length > 20) keys.push(`arg${index}.[truncated]`);
        return;
      }
    }
    keys.push(`arg${index}`);
  });
  return keys.slice(0, 40);
}

function bridgeChallengePrefix(challengeId) {
  return String(challengeId || "").slice(0, 10);
}

function auditBridgeDecision(policy, allowed, reason, argsHash, argKeys, challengeId = "") {
  if (!policy?.audit && allowed) return;
  const event = {
    timestamp: new Date().toISOString(),
    method: policy?.name || "unknown",
    risk: policy?.risk || "unknown",
    base_risk: policy?.base_risk || policy?.risk || "unknown",
    effective_risk: policy?.effective_risk || policy?.risk || "unknown",
    action_type: policy?.action_type || "unknown",
    allowed: Boolean(allowed),
    reason: String(reason || ""),
    args_hash: String(argsHash || "").slice(0, 16),
    arg_keys: Array.isArray(argKeys) ? argKeys.slice(0, 40) : [],
    classification_reason: String(policy?.classification_reason || ""),
    challenge_id_prefix: bridgeChallengePrefix(challengeId),
  };
  const line = `[BridgeAudit] ${JSON.stringify(event)}`;
  if (allowed) console.info(line);
  else console.warn(line);
  try {
    ipcRenderer.invoke("bridge:audit", event).catch(() => {});
  } catch (_error) {}
}

const BRIDGE_SECURITY_MESSAGES = {
  de: {
    bridge_policy_missing: "Diese lokale Aktion ist in Lexa nicht freigegeben.",
    bridge_privacy_denied: "Diese lokale Aktion ist durch Lexas Sicherheitsregeln gesperrt.",
    bridge_batch_denied: "Diese lokale Aktion wurde nicht gestartet. Stapelaktionen duerfen hier nur sichere Leseaktionen enthalten.",
    bridge_presence_denied: "Diese lokale Aktion wurde nicht gestartet. Lexa konnte die Sicherheitsfreigabe nicht bestaetigen.",
    bridge_presence_invalid: "Diese lokale Aktion wurde nicht gestartet. Die Sicherheitsfreigabe ist abgelaufen.",
    bridge_security_denied: "Diese lokale Aktion wurde nicht gestartet.",
  },
  en: {
    bridge_policy_missing: "This local action is not enabled in Lexa.",
    bridge_privacy_denied: "This local action is blocked by Lexa safety rules.",
    bridge_batch_denied: "This local action was not started. Batch actions here may only contain safe read-only actions.",
    bridge_presence_denied: "This local action was not started. Lexa could not verify the safety gate.",
    bridge_presence_invalid: "This local action was not started. The safety gate expired.",
    bridge_security_denied: "This local action was not started.",
  },
};

function bridgeSecurityLocale() {
  try {
    const lang = String(navigator?.language || "").toLowerCase();
    if (lang.startsWith("de")) return "de";
  } catch (_error) {}
  return "en";
}

function bridgeSecurityDisplayMessage(code = "bridge_security_denied") {
  const locale = bridgeSecurityLocale();
  return BRIDGE_SECURITY_MESSAGES[locale]?.[code]
    || BRIDGE_SECURITY_MESSAGES.en[code]
    || BRIDGE_SECURITY_MESSAGES[locale]?.bridge_security_denied
    || BRIDGE_SECURITY_MESSAGES.en.bridge_security_denied;
}

function bridgeSecurityError(_message, code = "bridge_security_denied") {
  const error = new Error(bridgeSecurityDisplayMessage(code));
  error.name = "BridgeSecurityError";
  error.code = code;
  return error;
}

async function invokeMainBridge(channel, payload) {
  try {
    const result = await ipcRenderer.invoke(channel, payload);
    if (result && result.code === "main_ipc_handler_failed") {
      return { ok: false, reason: result.reason || "main_ipc_handler_failed", code: result.code };
    }
    return result;
  } catch (_error) {
    return { ok: false, reason: "main_ipc_invoke_failed", code: "main_ipc_invoke_failed" };
  }
}

function companionBatchCommandName(entry) {
  if (typeof entry === "string") return entry;
  if (!entry || typeof entry !== "object") return "";
  return String(entry.command || entry.action || entry.name || "").trim();
}

function validateExecuteBatchCommands(commands) {
  if (!Array.isArray(commands) || commands.length === 0) {
    return { ok: false, reason: "batch_empty_or_invalid" };
  }
  for (const entry of commands) {
    const command = companionBatchCommandName(entry);
    if (!command || !READ_ONLY_COMPANION_BATCH_COMMANDS.has(command)) {
      return { ok: false, reason: `batch_command_not_read_only:${command || "unknown"}` };
    }
  }
  return { ok: true, reason: "batch_read_only_allowlist" };
}

async function guardedBridgeCall(method, args, executor, options = {}) {
  const policy = classifyBridgeCall(method, args);
  if (!policy) throw bridgeSecurityError("", "bridge_policy_missing");

  const argsHash = await bridgeArgsHash(args);
  const argKeys = bridgeArgKeys(args);
  if (policy.blocked) {
    auditBridgeDecision(policy, false, policy.classification_reason || "blocked_by_policy", argsHash, argKeys);
    throw bridgeSecurityError("", "bridge_privacy_denied");
  }

  if (method === "executeBatch") {
    const batchCheck = validateExecuteBatchCommands(args[0]);
    if (!batchCheck.ok) {
      auditBridgeDecision(policy, false, batchCheck.reason, argsHash, argKeys);
      throw bridgeSecurityError("", "bridge_batch_denied");
    }
  }

  let challengeId = "";
  const needsPresence = policy.requires_user_presence || policy.requires_main_confirmation;
  if (needsPresence && !options.disablePresenceChallenge) {
    const challenge = await invokeMainBridge("bridge:presence:request", {
      method,
      risk: policy.risk,
      base_risk: policy.base_risk || policy.risk,
      effective_risk: policy.effective_risk || policy.risk,
      action_type: policy.action_type,
      target: policy.target,
      args_hash: argsHash,
      arg_keys: argKeys,
      classification_reason: policy.classification_reason || "",
    });
    if (!challenge?.ok || !challenge.challenge_id) {
      auditBridgeDecision(policy, false, challenge?.reason || "presence_denied", argsHash, argKeys);
      throw bridgeSecurityError("", "bridge_presence_denied");
    }
    challengeId = challenge.challenge_id;
    const consumed = await invokeMainBridge("bridge:presence:consume", {
      challenge_id: challengeId,
      method,
      args_hash: argsHash,
    });
    if (!consumed?.ok) {
      auditBridgeDecision(policy, false, consumed?.reason || "presence_consume_failed", argsHash, argKeys, challengeId);
      throw bridgeSecurityError("", "bridge_presence_invalid");
    }
  }

  auditBridgeDecision(policy, true, needsPresence ? "presence_confirmed" : "policy_allowed", argsHash, argKeys, challengeId);
  return executor();
}

function assertBridgePolicyComplete(bridge) {
  const missing = Object.keys(bridge).filter((name) => !BRIDGE_METHOD_POLICY[name]);
  if (missing.length) {
    throw new Error(`Missing bridge method policy: ${missing.join(", ")}`);
  }
}

function createGuardedBridge(bridge, options = {}) {
  assertBridgePolicyComplete(bridge);
  const guarded = {};
  for (const [name, value] of Object.entries(bridge)) {
    const policy = BRIDGE_METHOD_POLICY[name];
    const requiresGuard = policy.requires_user_presence
      || policy.requires_main_confirmation
      || policy.audit
      || riskAtLeast(policy.risk, "medium")
      || name === "executeBatch"
      || PARAM_SENSITIVE_BRIDGE_METHODS.has(name);
    if (typeof value !== "function" || !requiresGuard) {
      guarded[name] = value;
      continue;
    }
    guarded[name] = (...args) => guardedBridgeCall(name, args, () => value(...args), options);
  }
  return Object.freeze(guarded);
}

function isLexaSmokeMockAllowed() {
  const argv = Array.isArray(process.argv) ? process.argv.join(" ") : "";
  const explicitSmokeTest = process.env.LEXA_ELECTRON_SMOKE_TEST === "1";
  const smokeRunner = /electron_(?:ui_visual|presence_challenge)_smoke\.js/i.test(argv);
  return process.env.LEXA_ELECTRON_SMOKE_MOCK === "1"
    && process.env.NODE_ENV !== "production"
    && (explicitSmokeTest || smokeRunner);
}

if (isLexaSmokeMockAllowed()) {
  let nextConversationId = 1000;
  const conversations = [
    { id: 1, title: "Smoke Test Chat", message_count: 2, last_message: "Mocked local data" },
  ];
  const conversationMessages = new Map([
    [1, [
      { role: "user", content: "Hallo Lexa" },
      { role: "assistant", content: "Bereit." },
    ]],
  ]);
  const systemInfo = {
    cpu_percent: 12,
    cpu_cores: 8,
    cpu_freq_mhz: 3200,
    ram_percent: 42,
    ram_used_gb: 6.2,
    ram_total_gb: 16,
    disk_percent: 58,
    disk_used_gb: 180,
    disk_total_gb: 512,
    battery_percent: 88,
    battery_plugged: true,
  };
  const ok = (extra = {}) => ({ success: true, ok: true, ...extra });
  const smokeMockBehaviors = Object.create(null);
  const smokeMockCalls = [];
  const cloneSmokePayload = (value) => {
    if (value === undefined) return undefined;
    try {
      return JSON.parse(JSON.stringify(value));
    } catch (_e) {
      return value;
    }
  };
  const normalizeSmokeBehavior = (behavior) => {
    if (Array.isArray(behavior)) return behavior.map((item) => ({ ...(item || {}) }));
    return { ...(behavior || {}) };
  };
  const runSmokeMock = async (method, args, fallback) => {
    smokeMockCalls.push({ method, args: cloneSmokePayload(args || []) });
    let behavior = smokeMockBehaviors[method];
    if (Array.isArray(behavior)) {
      behavior = behavior.shift();
      if (!smokeMockBehaviors[method]?.length) delete smokeMockBehaviors[method];
    }
    if (behavior) {
      const delayMs = Math.max(0, Number.parseInt(behavior.delay_ms || behavior.delayMs || 0, 10) || 0);
      if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
      if (behavior.throw || behavior.error) {
        throw new Error(String(behavior.message || behavior.error || "smoke mock error"));
      }
      if (Object.prototype.hasOwnProperty.call(behavior, "response")) return cloneSmokePayload(behavior.response);
      if (Object.prototype.hasOwnProperty.call(behavior, "value")) return cloneSmokePayload(behavior.value);
    }
    return fallback();
  };
  const smokeControlBridge = Object.freeze({
    set(method, behavior) {
      if (!method) return false;
      smokeMockBehaviors[String(method)] = normalizeSmokeBehavior(behavior);
      return true;
    },
    clear(method) {
      if (method) delete smokeMockBehaviors[String(method)];
      return true;
    },
    reset() {
      Object.keys(smokeMockBehaviors).forEach((key) => delete smokeMockBehaviors[key]);
      smokeMockCalls.length = 0;
      return true;
    },
    calls(method = "") {
      const key = String(method || "");
      return cloneSmokePayload(key ? smokeMockCalls.filter((entry) => entry.method === key) : smokeMockCalls);
    },
  });
  const emptyPersonalOs = () => ({
    ok: true,
    status: "ready",
    summary: "Mocked Personal OS",
    counts: {},
    drafts: [],
    files: [],
    tools: [],
    checks: [],
  });
  const findConversation = (id) => conversations.find((c) => String(c.id) === String(id));

  const smokeBridge = {
    API_BASE: "mock://lexa-smoke",
    loadI18n: (lang) => ipcRenderer.invoke("i18n-load", lang),
    minimize: () => {},
    maximize: () => {},
    close: () => {},
    notify: () => {},
    onSwitchView: () => {},
    onUpdateAvailable: () => {},
    health: async () => ({
      status: "ok",
      version: "smoke",
      hermes: {
        state: "ready",
        available: true,
        can_run_tasks: true,
        telegram_configured: true,
        summary: "Hermes mock ready.",
      },
    }),
    startupHealth: async () => ({
      ok: true,
      status: "ok",
      state: "ready",
      summary: "Startup und Runtime-Basis sind bereit.",
      counts: { ok: 11, warn: 0, blocked: 0 },
      safeForCockpit: true,
    }),
    commands: async () => ({ commands: {}, total: 0 }),
    execute: async (command) => command === "system_info"
      ? ok({ data: systemInfo })
      : ok({ data: {}, message: "mocked" }),
    prepareCompanionExecute: async (command, params = {}) => ok({
      requires_confirmation: true,
      confirmation_id: "smoke-confirmation",
      command_hash: "smoke-hash",
      action_scope: "confirmation_required",
      summary: { command, action_scope: "confirmation_required", param_keys: Object.keys(params || {}) },
    }),
    executeWithConfirmation: async () => ok({ data: {}, message: "mocked confirmed" }),
    executeBatch: async (commands = []) => ({ results: commands.map((command) => ok({ command })) }),
    companionAuditRecent: async () => ({ ok: true, entries: [], count: 0, skipped_noise: 0 }),
    timers: async () => ({ timers: [] }),
    timersAcknowledge: async () => ok(),
    pomodoroAcknowledge: async () => ok(),
    chat: async (message) => ({ response: `Mock: ${message || ""}`.trim() }),
    chatFile: async () => ({ response: "Mock file response" }),
    generateTitle: async (message = "") => runSmokeMock("generateTitle", [message], async () => ({ title: String(message || "Smoke Test").slice(0, 40) })),
    aiStatus: async () => ({
      active_provider: "groq",
      groq: { available: true },
      openai: { available: true },
      gemini: { available: true },
      anthropic: { available: true },
      fallback_enabled: true,
      fallback_available: ["openai:gpt-4o"],
    }),
    aiModels: async () => ({ current: "smoke-model", current_name: "Smoke Model", available: {} }),
    setAiModel: async () => ok(),
    memoryStats: async () => ({ notes: 0, memories: 0, interactions: 0, routines: 0 }),
    memoryGraph: async () => ({
      status: "ok",
      nodes: [
        { id: "hub:memory", label: "Lexa Gedächtnis", type: "hub", group: "hub", weight: 10, preview: "Smoke graph" },
        { id: "group:notes", label: "Notizen", type: "group", group: "notes", weight: 5, preview: "" },
        { id: "note:smoke", label: "Smoke Note", type: "note", group: "notes", weight: 3, preview: "Mock note" },
        { id: "note:unsafe-smoke", label: "Smoke <img src=x onerror=alert(1)>", type: "note", group: "notes", weight: 2.5, preview: "<script>alert(1)</script>" },
      ],
      links: [
        { source: "hub:memory", target: "group:notes", kind: "contains", weight: 2 },
        { source: "group:notes", target: "note:smoke", kind: "contains", weight: 1 },
        { source: "note:smoke", target: "note:unsafe-smoke", kind: "related", weight: 1 },
      ],
      counts: { nodes: 4, links: 3 },
      source: "smoke_mock",
    }),
    memoryAdd: async () => ok(),
    memoryCleanup: async () => ok(),
    notes: async () => ({ notes: [] }),
    noteGet: async () => null,
    noteUpdate: async () => ok(),
    snippets: async () => ({ snippets: [] }),
    snippetCreate: async () => ok(),
    snippetDelete: async () => ok(),
    routines: async () => ({ routines: [] }),
    todos: async () => ({ todos: [] }),
    todoCreate: async () => ok(),
    todoUpdate: async () => ok(),
    todoComplete: async () => ok(),
    todoDelete: async () => ok(),
    pomodoroStatus: async () => ({ running: false }),
    pomodoroStart: async () => ok({ running: true }),
    pomodoroStop: async () => ok({ running: false }),
    focusStatus: async () => ({ active: false }),
    focusOn: async () => ok({ active: true }),
    focusOff: async () => ok({ active: false }),
    weeklyStats: async () => ({ days: [] }),
    productivityStats: async () => ({}),
    habits: async () => ({ habits: [] }),
    habitCreate: async () => ok(),
    habitLog: async () => ok(),
    habitDelete: async () => ok(),
    timeTracking: async () => ({ entries: [] }),
    timeTrackingStart: async () => ok(),
    timeTrackingStop: async () => ok(),
    timeTrackingReport: async () => ({ entries: [], total_seconds: 0 }),
    clipboardHistory: async () => ({ items: [] }),
    clipboardAdd: async () => ok(),
    clipboardClear: async () => ok(),
    conversations: async () => runSmokeMock("conversations", [], async () => ({ conversations: conversations.slice() })),
    conversationCreate: async (title = "Neuer Chat") => runSmokeMock("conversationCreate", [title], async () => {
      const id = ++nextConversationId;
      const conversation = { id, title, message_count: 0, last_message: "" };
      conversations.unshift(conversation);
      conversationMessages.set(id, []);
      return { id, title, conversation };
    }),
    conversationGet: async (id) => runSmokeMock("conversationGet", [id], async () => {
      const conversation = findConversation(id);
      if (!conversation) return { detail: "not found" };
      return { ...conversation, messages: conversationMessages.get(conversation.id) || [] };
    }),
    conversationUpdate: async (id, data = {}) => runSmokeMock("conversationUpdate", [id, data], async () => {
      let conversation = findConversation(id);
      if (!conversation) {
        conversation = { id, title: data.title || "Smoke Test Chat", message_count: 0, last_message: "" };
        conversations.unshift(conversation);
      }
      if (data.title) conversation.title = data.title;
      if (Array.isArray(data.messages)) {
        conversationMessages.set(conversation.id, data.messages);
        conversation.message_count = data.messages.length;
        conversation.last_message = data.messages.at(-1)?.content || "";
      }
      return ok({ conversation });
    }),
    conversationDelete: async (id) => runSmokeMock("conversationDelete", [id], async () => {
      const index = conversations.findIndex((c) => String(c.id) === String(id));
      if (index >= 0) conversations.splice(index, 1);
      conversationMessages.delete(Number(id));
      return ok();
    }),
    conversationLoad: async (id) => runSmokeMock("conversationLoad", [id], async () => ok()),
    conversationExport: async (id) => ({ text: `# Conversation ${id}\n\nMock export.` }),
    historyClear: async () => runSmokeMock("historyClear", [], async () => ok()),
    search: async (query) => runSmokeMock("search", [query], async () => ({ conversations: [], notes: [], memories: [] })),
    ftsSearch: async (query) => runSmokeMock("ftsSearch", [query], async () => ({ results: [], total: 0, notes: [], memories: [] })),
    rebuildFts: async () => ok(),
    diagnostics: async () => ({
      ok: true,
      hermes: {
        health_state: "ready",
        summary: "Hermes mock ready.",
        can_run_tasks: true,
        gateway: { configured: true, can_start: true },
      },
    }),
    hermesGatewayAutostartStatus: async () => ({
      status: "ok",
      supported: true,
      enabled: false,
      can_enable: true,
      telegram_configured: true,
      missing: [],
      nextAction: "",
    }),
    hermesGatewayAutostartSet: async (enabled) => ok({
      status: enabled ? "enabled" : "disabled",
      autostart: {
        status: "ok",
        supported: true,
        enabled: Boolean(enabled),
        can_enable: true,
        telegram_configured: true,
        missing: [],
        nextAction: "",
      },
    }),
    hermesCapabilities: async () => ({
      ok: true,
      healthState: "attention",
      summary: "Hermes capability map: 6/11 groups ready, 5 need attention, 0 blocked. Lexa surfaces: 2 strong, 4 partial, 3 weak, 2 missing.",
      nextAction: "Expose safe toolset presets in Lexa instead of one generic Hermes run box.",
      counts: {
        total: 11,
        ready: 6,
        attention: 5,
        blocked: 0,
        strongLexaSurface: 2,
        partialLexaSurface: 4,
        weakLexaSurface: 3,
        missingLexaSurface: 2,
        defaultToolsets: 25,
        enabledDefaultToolsets: 18,
        configuredProviders: 1,
        primaryProviders: 1,
        mediaProviders: 0,
      },
      groups: [
        { id: "desktop-control", label: "Desktop Control", state: "ready", lexaSurface: "strong" },
        { id: "tool-platform", label: "Tool Platform", state: "attention", lexaSurface: "weak" },
      ],
      gaps: [
        { id: "tool-platform", label: "Tool Platform", state: "attention", lexaSurface: "weak", nextAction: "Expose safe toolset presets in Lexa instead of one generic Hermes run box." },
        { id: "automation-board", label: "Automation, Cron & Kanban", state: "attention", lexaSurface: "missing", nextAction: "Expose read-only job/board status first." },
      ],
      safeMode: true,
    }),
    hermesProviders: async () => ({
      ok: true,
      healthState: "attention",
      summary: "Hermes provider setup: primary ready, 0/0 fallback(s) credential-ready, 1 provider credential group(s) detected.",
      nextAction: "Add at least one fallback with `hermes fallback add`.",
      primary: { provider: "auto", providerId: "auto", model: "", effectiveProviderHint: "openai" },
      fallbacks: [],
      counts: { configuredProviders: 1, fallbacks: 0, fallbacksReady: 0, fallbacksNotReady: 0 },
      setup: { primaryCommand: "hermes model", fallbackAddCommand: "hermes fallback add", secretsRedacted: true },
      safeMode: true,
    }),
    hermesOverview: async () => ({
      ok: true,
      healthState: "ready",
      summary: "Lexa/Hermes/OS ist arbeitsfaehig: Hermes ready, Telegram bereit, Autostart an, Drafts 0 pending, 11 approved, 3 rejected, Logs ok.",
      nextAction: "Build visible OS/Hermes cockpit",
      checks: [
        { id: "backend", label: "Lexa backend", state: "ok", detail: "Backend route is live." },
        { id: "hermes", label: "Hermes", state: "ok", detail: "Hermes mock ready." },
        { id: "telegram", label: "Telegram", state: "ok", detail: "configured" },
      ],
      counts: {
        drafts: { pending: 0, approved: 11, rejected: 3 },
        contextFiles: 5,
        capabilities: { ready: 6, total: 11, weakLexaSurface: 3, missingLexaSurface: 2 },
      },
      capabilities: {
        healthState: "attention",
        summary: "Hermes capability map: 6/11 groups ready, 5 need attention, 0 blocked.",
        counts: { ready: 6, total: 11, weakLexaSurface: 3, missingLexaSurface: 2 },
        gaps: [
          { id: "tool-platform", label: "Tool Platform", state: "attention", lexaSurface: "weak", nextAction: "Expose safe toolset presets in Lexa." },
        ],
      },
      providerStatus: {
        healthState: "attention",
        summary: "Hermes provider setup: primary ready, 0/0 fallback(s) credential-ready, 1 provider credential group(s) detected.",
        nextAction: "Add at least one fallback with `hermes fallback add`.",
        primary: { provider: "auto", providerId: "auto", model: "", effectiveProviderHint: "openai" },
        fallbacks: [],
        counts: { configuredProviders: 1, fallbacks: 0, fallbacksReady: 0, fallbacksNotReady: 0 },
      },
      contextFiles: [
        { title: "Current AI Brief", path: "05_Memory/Rollups/Current_AI_Brief.md" },
        { title: "Hermes Capabilities", path: "08_Lexa/Architecture/Hermes_Capabilities.md" },
      ],
      nextTasks: ["Build visible OS/Hermes cockpit"],
      safeMode: true,
    }),
    healthTools: async () => ({ ok: true, available: [], missing: [] }),
    mcpServers: async () => ({ servers: [] }),
    getAutostart: () => false,
    setAutostart: () => {},
    setProfile: async () => ok(),
    licenseGet: async () => ({ valid: true }),
    licenseActivate: async () => ok({ valid: true, success: true }),
    licenseSet: async () => ok(),
    licenseValidate: async () => ok({ valid: true }),
    backupListDb: async () => ({ backups: [] }),
    backupCreateDb: async () => ok(),
    backupRestoreDb: async () => ok(),
    voiceStatus: async () => ({ ok: true, state: "ready", wakeword: { active: false, ready: true } }),
    voiceDiagnostics: async () => ({ ok: true, state: "ready" }),
    voiceRealtimeStart: async () => ({ ok: false, can_start: false, session_state: "blocked", blockers: ["smoke mock"] }),
    voiceRealtimeStop: async () => ({ ok: true, session_state: "stopped" }),
    wakewordStart: async () => ({ status: "started", active: true, ready: true }),
    wakewordStop: async () => ({ status: "stopped", active: false, ready: true }),
    wakewordStatus: async () => ({ active: false, ready: true }),
    wakewordEvents: async () => ({ events: [] }),
    tts: async () => null,
    stt: async () => ({ text: "" }),
    sttModels: async () => ({ models: [] }),
    sttSetEngine: async () => ok(),
    sttSetModel: async () => ok(),
    elevenlabsVoices: async () => ({ voices: [] }),
    elevenlabsToggle: async () => ok(),
    elevenlabsSetKey: async () => ok(),
    elevenlabsSetVoice: async () => ok(),
    elevenlabsSetModel: async () => ok(),
    elevenlabsSetSettings: async () => ok(),
    deepgramSetKey: async () => ok(),
    deepgramDeleteKey: async () => ok(),
    cartesiaSetKey: async () => ok(),
    cartesiaDeleteKey: async () => ok(),
    visionStatus: async () => ({ success: true, data: { available: false, providers: [], screenshot: true, details: "smoke mock" } }),
    visionAnalyze: async () => ({ text: "" }),
    personalOsDiagnostics: async () => emptyPersonalOs(),
    personalOsDrafts: async () => emptyPersonalOs(),
    personalOsDraftView: async () => emptyPersonalOs(),
    personalOsDraftReview: async () => emptyPersonalOs(),
    personalOsDraftDecision: async () => emptyPersonalOs(),
    personalOsDraftApply: async () => emptyPersonalOs(),
    personalOsGraph: async () => emptyPersonalOs(),
    personalOsQuery: async () => emptyPersonalOs(),
    personalOsContextPack: async () => emptyPersonalOs(),
    personalOsObsidianContext: async () => emptyPersonalOs(),
    personalOsSharedContext: async () => ({ fresh: false, topic: "", recentIntents: [], entities: {} }),
    personalOsReadFile: async () => emptyPersonalOs(),
    personalOsRawStatus: async () => emptyPersonalOs(),
    personalOsRawSubmit: async () => emptyPersonalOs(),
    personalOsCodeLoop: async () => emptyPersonalOs(),
    agentRun: async (message = "", options = {}) => runSmokeMock("agentRun", [message, options], async () => ({
      ok: true,
      summary: "Smoke mock completed",
      steps: [],
      counts: { found: 0, changed: 0, done: 1, blocked: 0, failed: 0 },
    })),
    agentStreamRead: async (streamId) => runSmokeMock("agentStreamRead", [streamId], async () => ({ done: true, value: [] })),
    agentStreamCancel: async (streamId) => runSmokeMock("agentStreamCancel", [streamId], async () => ({ ok: true, cancelled: false })),
  };
  contextBridge.exposeInMainWorld("lexa", createGuardedBridge(smokeBridge, { disablePresenceChallenge: true }));
  contextBridge.exposeInMainWorld("lexaSmoke", smokeControlBridge);
  return;
}

// Fetch wrapper with AbortController timeout (default 30s)
async function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const requestOptions = await withLocalAuthHeader(url, options);
    const res = await fetch(url, { ...requestOptions, signal: controller.signal });
    return res;
  } finally {
    clearTimeout(id);
  }
}

function apiErrorText(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value.map((entry) => {
      if (!entry || typeof entry !== "object") return entry ? String(entry) : "";
      const loc = Array.isArray(entry.loc) ? entry.loc.join(".") : (entry.loc || "");
      const msg = entry.msg || entry.message || entry.error || "";
      if (loc && msg) return `${loc}: ${msg}`;
      return msg || JSON.stringify(entry);
    }).filter(Boolean).join("; ");
  }
  if (typeof value === "object") {
    return value.message || value.error || JSON.stringify(value);
  }
  return String(value);
}

function personalOsErrorText(value) {
  return apiErrorText(value);
}

function apiRequestId(res) {
  return typeof res?.headers?.get === "function"
    ? (res.headers.get("x-request-id") || res.headers.get("X-Request-ID") || "")
    : "";
}

async function apiJson(res, fallback = "Lexa request failed") {
  let data = null;
  let jsonError = null;
  const requestId = apiRequestId(res);
  try {
    data = await res.json();
  } catch (e) {
    jsonError = e;
    data = null;
  }

  if (res.ok) {
    if (jsonError) {
      return {
        ok: false,
        httpStatus: res.status,
        requestId,
        errorCode: "invalid_json",
        error: `${fallback}: invalid JSON response`,
        message: `${fallback}: invalid JSON response`,
      };
    }
    return data || {};
  }

  const objectData = data && typeof data === "object" && !Array.isArray(data) ? data : {};
  const message = apiErrorText(objectData.error)
    || apiErrorText(objectData.message)
    || apiErrorText(objectData.detail)
    || `${fallback} (HTTP ${res.status})`;

  return {
    ...objectData,
    ok: false,
    httpStatus: res.status,
    requestId: objectData.requestId || objectData.request_id || requestId,
    errorCode: objectData.errorCode || objectData.error_code || `http_${res.status}`,
    error: message,
    message,
  };
}

async function personalOsJson(res, fallback = "Personal OS request failed") {
  return apiJson(res, fallback);
}

function personalOsRetryDelayMs(res, fallbackMs = 1200) {
  const rawHeader = typeof res?.headers?.get === "function" ? (res.headers.get("retry-after") || "") : "";
  const numericSeconds = Number(rawHeader);
  if (Number.isFinite(numericSeconds) && numericSeconds > 0) {
    return Math.max(250, Math.min(5000, Math.round(numericSeconds * 1000)));
  }
  const retryDate = Date.parse(rawHeader);
  if (Number.isFinite(retryDate)) {
    return Math.max(250, Math.min(5000, retryDate - Date.now()));
  }
  return fallbackMs;
}

function personalOsDelay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const agentStreamReaders = new Map();
let agentStreamSeq = 0;

function nextAgentStreamId() {
  agentStreamSeq = (agentStreamSeq + 1) % Number.MAX_SAFE_INTEGER;
  return `agent-${Date.now().toString(36)}-${agentStreamSeq.toString(36)}`;
}

function bridgeStreamChunk(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  if (value instanceof ArrayBuffer) return Array.from(new Uint8Array(value));
  if (ArrayBuffer.isView(value)) {
    return Array.from(new Uint8Array(value.buffer, value.byteOffset, value.byteLength));
  }
  return [];
}

function registerAgentStreamResponse(res) {
  const body = res && res.body;
  const reader = body && typeof body.getReader === "function" ? body.getReader() : null;
  if (!reader) {
    return {
      ok: Boolean(res?.ok),
      status: Number(res?.status || 0),
      statusText: String(res?.statusText || ""),
      streamId: "",
    };
  }
  const streamId = nextAgentStreamId();
  agentStreamReaders.set(streamId, reader);
  return {
    ok: Boolean(res.ok),
    status: Number(res.status || 0),
    statusText: String(res.statusText || ""),
    streamId,
  };
}

async function readAgentStreamChunk(streamId) {
  const id = String(streamId || "");
  const reader = agentStreamReaders.get(id);
  if (!reader) return { done: true, value: [] };
  try {
    const result = await reader.read();
    if (result.done) agentStreamReaders.delete(id);
    return {
      done: Boolean(result.done),
      value: bridgeStreamChunk(result.value),
    };
  } catch (error) {
    agentStreamReaders.delete(id);
    throw error;
  }
}

async function cancelAgentStream(streamId) {
  const id = String(streamId || "");
  const reader = agentStreamReaders.get(id);
  agentStreamReaders.delete(id);
  if (!reader) return { ok: true, cancelled: false };
  try {
    await reader.cancel();
    return { ok: true, cancelled: true };
  } catch (error) {
    return { ok: false, cancelled: false, error: String(error?.message || error || "cancel_failed") };
  }
}

async function personalOsFetchJsonWithRetry(url, fallback, options, timeoutMs = 30000, retryOptions) {
  const requestOptions = options || {};
  const retryConfig = retryOptions || {};
  const attempts = Math.max(1, Math.floor(Number(retryConfig.attempts) || 1));
  const retryStatuses = Array.isArray(retryConfig.statuses) && retryConfig.statuses.length
    ? retryConfig.statuses.map((status) => Number(status))
    : [429];

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    const res = await fetchWithTimeout(url, requestOptions, timeoutMs);
    const payload = await personalOsJson(res, fallback);
    const shouldRetry = retryStatuses.includes(Number(payload.httpStatus)) && attempt < attempts;
    if (!shouldRetry) return payload;
    await personalOsDelay(personalOsRetryDelayMs(res, retryConfig.delayMs || 1200));
  }
  return { ok: false, error: fallback };
}

// Secure Bridge — nur erlaubte APIs exposen
function voiceMimeFilename(mimeType) {
  const normalizedType = String(mimeType || "").split(";")[0].trim().toLowerCase();
  const mimeToExt = {
    "audio/webm": "recording.webm",
    "audio/ogg": "recording.ogg",
    "audio/mp4": "recording.m4a",
    "audio/mpeg": "recording.mp3",
    "audio/wav": "recording.wav",
    "audio/x-wav": "recording.wav",
    "audio/flac": "recording.flac",
  };
  return mimeToExt[normalizedType] || "recording.webm";
}

const lexaBridge = {
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
    void confirmed; // Legacy UI hint only; never sent as security approval.
    const res = await fetchWithTimeout(`${API}/companion/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, params }),
    });
    return res.json();
  },
  prepareCompanionExecute: async (command, params = {}) => {
    const res = await fetchWithTimeout(`${API}/companion/execute/prepare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command, params }),
    });
    return apiJson(res, "Command confirmation prepare failed");
  },
  executeWithConfirmation: async (command, params = {}, confirmation = {}) => {
    const res = await fetchWithTimeout(`${API}/companion/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        command,
        params,
        confirmation_id: confirmation.confirmation_id || "",
        command_hash: confirmation.command_hash || "",
        action_scope: confirmation.action_scope || "",
      }),
    });
    return apiJson(res, "Confirmed command execution failed");
  },
  companionAuditRecent: async (limit = 20, hideNoise = true) => {
    try {
      const safeLimit = Math.max(1, Math.min(Number(limit) || 20, 100));
      const params = new URLSearchParams();
        params.set("limit", String(safeLimit));
        params.set("hideNoise", hideNoise ? "true" : "false");
        const res = await fetchWithTimeout(`${API}/companion/audit/recent?${params.toString()}`);
        return personalOsJson(res, "Audit request failed");
      } catch (e) {
        console.warn("[Preload] companionAuditRecent failed:", e.message || e);
        return { ok: false, entries: [], count: 0, error: e.message || String(e) };
      }
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
    const filename = voiceMimeFilename(audioBlob.type);
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
      const r = await fetchWithTimeout(`${API}/voice/diagnostics`);
      return r.json();
    } catch (e) {
      console.warn("[Preload] voiceStatus failed:", e.message || e);
      return {
        ok: false,
        state: "blocked",
        tts: { ready: false },
        stt: { ready: false },
        wakeword: { active: false, ready: false },
        audio: { available: false },
      };
    }
  },
  voiceDiagnostics: async (probeAudio = false) => {
    try {
      const params = new URLSearchParams();
      if (probeAudio) params.set("probeAudio", "true");
      const r = await fetchWithTimeout(`${API}/voice/diagnostics?${params.toString()}`);
      return r.json();
    } catch (e) {
      console.warn("[Preload] voiceDiagnostics failed:", e.message || e);
      return { ok: false, state: "blocked", error: e.message || String(e) };
    }
  },
  voiceArchitecture: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/voice/architecture`);
      return r.json();
    } catch (e) {
      console.warn("[Preload] voiceArchitecture failed:", e.message || e);
      return {
        version: "unknown",
        realtime: { configured: false, runtime_active: false, active_path: "unknown" },
        wakeword: { target: "unknown" },
        error: e.message || String(e),
      };
    }
  },
  voiceRealtimePreflight: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/voice/realtime/preflight`);
      return r.json();
    } catch (e) {
      console.warn("[Preload] voiceRealtimePreflight failed:", e.message || e);
      return {
        ok: false,
        can_start: false,
        blockers: [e.message || String(e)],
        warnings: [],
        active_path: "unknown",
      };
    }
  },
  voiceRealtimeStart: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/voice/realtime/start`, { method: "POST" });
      const payload = await r.json();
      return { httpStatus: r.status, ...payload };
    } catch (e) {
      console.warn("[Preload] voiceRealtimeStart failed:", e.message || e);
      return {
        ok: false,
        can_start: false,
        session_state: "blocked",
        blockers: [e.message || String(e)],
        active_path: "unknown",
      };
    }
  },
  voiceRealtimeStop: async () => {
    try {
      const r = await fetchWithTimeout(`${API}/voice/realtime/stop`, { method: "POST" });
      const payload = await r.json();
      return { httpStatus: r.status, ...payload };
    } catch (e) {
      console.warn("[Preload] voiceRealtimeStop failed:", e.message || e);
      return {
        ok: false,
        session_state: "unknown",
        active: false,
        error: e.message || String(e),
      };
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
      return apiJson(res, "Backend health not reachable");
    } catch (e) {
      console.warn("[Preload] health check failed:", e.message || e);
      return { status: "offline" };
    }
  },
  startupHealth: async ({ probeVoice = false } = {}) => {
    try {
      const params = new URLSearchParams();
      if (probeVoice) params.set("probeVoice", "true");
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const res = await fetchWithTimeout(`${API}/health/startup${suffix}`);
      return apiJson(res, "Startup health not reachable");
    } catch (e) {
      console.warn("[Preload] startupHealth failed:", e.message || e);
      return {
        ok: false,
        status: "offline",
        state: "blocked",
        checks: [],
        counts: { ok: 0, warn: 0, blocked: 1 },
        error: "Startup Health nicht erreichbar",
      };
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

  memoryGraph: async (limit = 160) => {
    try {
      const safeLimit = Math.max(40, Math.min(220, Number.parseInt(limit, 10) || 160));
      const res = await fetchWithTimeout(`${API}/memory/graph?limit=${encodeURIComponent(String(safeLimit))}`);
      return res.json();
    } catch (e) {
      console.warn("[Preload] memoryGraph failed:", e.message || e);
      return { status: "error", nodes: [], links: [], counts: {}, source: "unavailable" };
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
    return apiJson(res, "Diagnostics not reachable");
  },
  hermesGatewayAutostartStatus: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/hermes/gateway/autostart`);
      return apiJson(res, "Hermes Gateway Autostart nicht erreichbar");
    } catch (e) {
      console.warn("[Preload] hermesGatewayAutostartStatus failed:", e.message || e);
      return {
        status: "error",
        supported: false,
        enabled: false,
        can_enable: false,
        error: "Hermes Gateway Autostart nicht erreichbar",
      };
    }
  },
  hermesGatewayAutostartSet: async (enabled) => {
    const res = await fetchWithTimeout(`${API}/hermes/gateway/autostart`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: Boolean(enabled) }),
    });
    return apiJson(res, "Hermes Gateway Autostart nicht erreichbar");
  },
  hermesCapabilities: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/hermes/capabilities`);
      return apiJson(res, "Hermes Capabilities nicht erreichbar");
    } catch (e) {
      console.warn("[Preload] hermesCapabilities failed:", e.message || e);
      return {
        ok: false,
        healthState: "offline",
        summary: "Hermes Capabilities nicht erreichbar",
        counts: {},
        groups: [],
        gaps: [],
        error: "Hermes Capabilities nicht erreichbar",
      };
    }
  },
  hermesProviders: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/hermes/providers`);
      return apiJson(res, "Hermes Providerstatus nicht erreichbar");
    } catch (e) {
      console.warn("[Preload] hermesProviders failed:", e.message || e);
      return {
        ok: false,
        healthState: "offline",
        summary: "Hermes Providerstatus nicht erreichbar",
        counts: {},
        primary: {},
        fallbacks: [],
        error: "Hermes Providerstatus nicht erreichbar",
      };
    }
  },
  hermesOverview: async ({ includeContext = true } = {}) => {
    try {
      const params = new URLSearchParams();
      params.set("includeContext", includeContext ? "true" : "false");
      const res = await fetchWithTimeout(`${API}/hermes/overview?${params.toString()}`);
      return apiJson(res, "Hermes Overview nicht erreichbar");
    } catch (e) {
      console.warn("[Preload] hermesOverview failed:", e.message || e);
      return {
        ok: false,
        healthState: "offline",
        summary: "Lexa/Hermes Overview nicht erreichbar",
        checks: [],
        counts: {},
        contextFiles: [],
        nextTasks: [],
        error: "Hermes Overview nicht erreichbar",
      };
    }
  },
  healthTools: async () => {
    try {
      const res = await fetchWithTimeout(`${API}/health/tools`);
      return apiJson(res, "Tool health not reachable");
    } catch (e) {
      console.warn("[Preload] healthTools failed:", e.message || e);
      return { tools: {}, available_count: 0, total_count: 0, health_pct: 0 };
    }
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
      headers: { "Content-Type": "application/json", "X-Lexa-Restore-Intent": "confirmed" },
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
      headers: { 'Content-Type': 'application/json', 'X-Lexa-Restore-Intent': 'confirmed' },
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
  licenseActivate: (key) => ipcRenderer.invoke("license-activate", key),
  licenseSet: (data) => ipcRenderer.invoke("license-set", data),
  licenseValidate: async (key) => {
    try {
      const res = await fetchWithTimeout(`${API}/license/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ license_key: key }),
      });
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

  // Personal OS cockpit
  personalOsStatus: async () => {
    try {
      return personalOsFetchJsonWithRetry(
        `${API}/personal-os/status`,
        "Personal OS status failed",
        {},
        30000,
        { attempts: 2, statuses: [429], delayMs: 800 },
      );
    } catch (e) {
      console.warn("[Preload] personalOsStatus failed:", e.message || e);
      return { ok: false, status: "offline", tools: [], tools_count: 0, draft_review: false, error: "Personal OS nicht erreichbar" };
    }
  },
  personalOsDiagnostics: async () => {
    try {
      return personalOsFetchJsonWithRetry(
        `${API}/personal-os/diagnostics`,
        "Personal OS diagnostics failed",
        {},
        30000,
        { attempts: 2, statuses: [429], delayMs: 1200 },
      );
    } catch (e) {
      console.warn("[Preload] personalOsDiagnostics failed:", e.message || e);
      return {
        ok: false,
        state: "blocked",
        summary: "Personal OS nicht erreichbar",
        counts: {},
        status: { status: "offline", tools: [], tools_count: 0, draft_review: false },
        checks: [],
      };
    }
  },
  personalOsDrafts: async (approval = "pending", hideSmoke = true) => {
    try {
      const params = new URLSearchParams();
      params.set("approval", approval);
      params.set("hideSmoke", hideSmoke ? "true" : "false");
      return personalOsFetchJsonWithRetry(
        `${API}/personal-os/drafts?${params.toString()}`,
        "Personal OS draft queue failed",
        {},
        30000,
        { attempts: 2, statuses: [429], delayMs: 1000 },
      );
    } catch (e) {
      console.warn("[Preload] personalOsDrafts failed:", e.message || e);
      return { ok: false, counts: {}, drafts: [], error: "Personal OS nicht erreichbar", errors: [{ error: "Personal OS nicht erreichbar" }] };
    }
  },
  personalOsDraftView: async (draftPath) => {
    const params = new URLSearchParams();
    params.set("draftPath", draftPath);
    const r = await fetchWithTimeout(`${API}/personal-os/drafts/view?${params.toString()}`);
    return personalOsJson(r, "Personal OS draft view failed");
  },
  personalOsDraftReview: async (draftPath) => {
    const params = new URLSearchParams();
    params.set("draftPath", draftPath);
    const r = await fetchWithTimeout(`${API}/personal-os/drafts/review?${params.toString()}`);
    return personalOsJson(r, "Personal OS draft review failed");
  },
  personalOsDraftDecision: async (draftPath, decision, reason = "", force = false) => {
    const r = await fetchWithTimeout(`${API}/personal-os/drafts/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draftPath,
        decision,
        reason: reason || `Reviewed in Lexa: ${decision}`,
        agentName: "LexaHumanReview",
        force: !!force,
      }),
    });
    return personalOsJson(r, "Personal OS draft decision failed");
  },
  personalOsDraftApply: async (draftPath, reason = "") => {
    const r = await fetchWithTimeout(`${API}/personal-os/drafts/apply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draftPath,
        reason: reason || "Apply approved draft in Lexa.",
        agentName: "LexaHumanReview",
      }),
    });
    return personalOsJson(r, "Personal OS draft apply failed");
  },
  personalOsQuery: async ({ areaPath = ".", tag = "", maxMatches = 50 } = {}) => {
    const params = new URLSearchParams();
    params.set("areaPath", areaPath || ".");
    if (tag) params.set("tag", tag);
    params.set("maxMatches", String(clampPositiveInteger(maxMatches, 50, 1, 50)));
    const r = await fetchWithTimeout(`${API}/personal-os/query?${params.toString()}`);
    return personalOsJson(r, "Personal OS query failed");
  },
  personalOsReadFile: async (filepath) => {
    const params = new URLSearchParams();
    params.set("filepath", filepath);
    const r = await fetchWithTimeout(`${API}/personal-os/files/read?${params.toString()}`);
    return personalOsJson(r, "Personal OS file read failed");
  },
  personalOsGraph: async ({ areaPath = ".", maxFiles = 120, includeTags = true, hideSmoke = true } = {}) => {
    const params = new URLSearchParams();
    params.set("areaPath", areaPath || ".");
    params.set("maxFiles", String(maxFiles || 120));
    params.set("includeTags", includeTags ? "true" : "false");
    params.set("hideSmoke", hideSmoke ? "true" : "false");
    const r = await fetchWithTimeout(`${API}/personal-os/graph?${params.toString()}`);
    return personalOsJson(r, "Personal OS context map failed");
  },
  personalOsContextPack: async ({ areaPath = ".", tag = "", maxFiles = 5, bodyChars = 700, includeGraph = true, hideSmoke = true } = {}) => {
    const params = new URLSearchParams();
    params.set("areaPath", areaPath || ".");
    if (tag) params.set("tag", tag);
    params.set("maxFiles", String(clampPositiveInteger(maxFiles, 5, 1, 5)));
    params.set("bodyChars", String(clampPositiveInteger(bodyChars, 700, 0, 700)));
    params.set("includeGraph", includeGraph ? "true" : "false");
    params.set("hideSmoke", hideSmoke ? "true" : "false");
    const r = await fetchWithTimeout(`${API}/personal-os/context-pack?${params.toString()}`);
    return personalOsJson(r, "Personal OS context pack failed");
  },
  personalOsObsidianContext: async ({ topic = "", maxFiles = 5, bodyChars = 600, includePreviews = true } = {}) => {
    const params = new URLSearchParams();
    if (topic) params.set("topic", topic);
    params.set("maxFiles", String(clampPositiveInteger(maxFiles, 5, 1, 5)));
    params.set("bodyChars", String(clampPositiveInteger(bodyChars, 600, 0, 600)));
    params.set("includePreviews", includePreviews ? "true" : "false");
    const r = await fetchWithTimeout(`${API}/personal-os/obsidian-context?${params.toString()}`);
    return personalOsJson(r, "Personal OS Obsidian context failed");
  },
  personalOsSharedContext: async () => {
    const r = await fetchWithTimeout(`${API}/personal-os/shared-context`);
    return personalOsJson(r, "Personal OS shared context failed");
  },
  personalOsCodeLoop: async ({ areaPath = "00_System", tag = "lexa", maxFiles = 5, bodyChars = 650, includeGraph = true, hideSmoke = true } = {}) => {
    const params = new URLSearchParams();
    params.set("areaPath", areaPath || "00_System");
    if (tag) params.set("tag", tag);
    params.set("maxFiles", String(maxFiles || 5));
    params.set("bodyChars", String(bodyChars || 650));
    params.set("includeGraph", includeGraph ? "true" : "false");
    params.set("hideSmoke", hideSmoke ? "true" : "false");
    const r = await fetchWithTimeout(`${API}/personal-os/lexa-code-loop?${params.toString()}`);
    return personalOsJson(r, "Personal OS code loop failed");
  },
  personalOsRawSubmit: async ({ title = "", body = "", processor = "deterministic" } = {}) => {
    const r = await fetchWithTimeout(`${API}/personal-os/raw-inbox/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, body, processor }),
    }, 60000);
    return personalOsJson(r, "Personal OS raw inbox submit failed");
  },
  personalOsRawStatus: async () => {
    const r = await fetchWithTimeout(`${API}/personal-os/raw-inbox/status`);
    return personalOsJson(r, "Personal OS raw inbox status failed");
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
  agentRun: async (message, options = {}) => {
    // Native Response/ReadableStream objects do not cross Electron's sandbox bridge
    // reliably. Return a serializable stream id and read chunks via agentStreamRead().
    const worker = typeof options?.worker === "string" ? options.worker : undefined;
    const res = await fetchWithTimeout(`${API}/agent/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(worker ? { message, worker } : { message }),
    }, 15000);
    return registerAgentStreamResponse(res);
  },
  agentStreamRead: async (streamId) => {
    return readAgentStreamChunk(streamId);
  },
  agentStreamCancel: async (streamId) => {
    return cancelAgentStream(streamId);
  },
  agentChat: async (message, options = {}) => {
    const worker = typeof options?.worker === "string" ? options.worker : undefined;
    const res = await fetchWithTimeout(`${API}/agent/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(worker ? { message, worker } : { message }),
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
};

contextBridge.exposeInMainWorld("lexa", createGuardedBridge(lexaBridge));
