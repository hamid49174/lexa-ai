/* Personal OS display helpers. Classic script loaded before personal_os.js. */

function posText(value, fallback = "") {
  return value === undefined || value === null ? fallback : String(value);
}

function posUiText(key, fallback = "", values = undefined) {
  try {
    if (typeof t === "function") return t(key, values);
  } catch (_) { }
  let text = posText(fallback);
  if (values && typeof values === "object") {
    Object.entries(values).forEach(([name, value]) => {
      text = text.replaceAll(`{{${name}}}`, posText(value));
    });
  }
  return text;
}

function posUiCount(key, fallback = "{{count}}", count = 0) {
  return posUiText(key, fallback, { count: Number(count) });
}

function posStatusClass(value) {
  const state = posText(value).toLowerCase();
  if (state === "connected" || state === "ok" || state === "approved") return "pos-good";
  if (state === "pending" || state === "review") return "pos-warn";
  if (state === "rejected" || state === "conflict" || state === "missing" || state === "offline") return "pos-bad";
  return "";
}

function posEventClass(value) {
  const state = posText(value).toLowerCase();
  if (state.includes("approved") || state.includes("updated") || state.includes("applied")) return "pos-good";
  if (state.includes("draftcreated") || state.includes("writerequested") || state.includes("read")) return "pos-warn";
  if (state.includes("rejected") || state.includes("failed") || state.includes("quarantined")) return "pos-bad";
  return "";
}

function posAssistClass(value) {
  const state = posText(value).toLowerCase();
  if (state === "ready" || state === "ok") return "pos-good";
  if (state === "attention" || state === "warn") return "pos-warn";
  if (state === "blocked" || state === "block" || state === "bad") return "pos-bad";
  return "";
}

function posErrorDetailText(value, fallback = "Personal OS Fehler") {
  if (Array.isArray(value)) {
    const rows = value.map((entry) => {
      if (!entry || typeof entry !== "object") return posText(entry);
      const loc = Array.isArray(entry.loc) ? entry.loc.join(".") : posText(entry.loc);
      const msg = posText(entry.msg || entry.message || entry.error);
      if (loc && msg) return `${loc}: ${msg}`;
      return msg || JSON.stringify(entry);
    }).filter(Boolean);
    return rows.join("; ") || fallback;
  }
  if (value && typeof value === "object") {
    return posText(value.message || value.error || value.msg || JSON.stringify(value), fallback);
  }
  return posText(value, fallback);
}

function posErrorMessage(payload, fallback = "Personal OS Fehler", limit = 700) {
  const detail = payload?.detail;
  const rawRequestId = posText(payload?.requestId || payload?.request_id).trim().replace(/\s+/g, " ");
  const requestId = rawRequestId.length > 140 ? `${rawRequestId.slice(0, 126)}...[truncated]` : rawRequestId;
  const message = detail === undefined || detail === null
    ? posErrorDetailText(payload?.error || payload?.message, fallback)
    : posErrorDetailText(detail, fallback);
  if (!requestId) return posClip(message, limit);
  const suffix = `\nRequest ID: ${requestId}`;
  const max = Number.isFinite(Number(limit)) ? Math.max(0, Math.floor(Number(limit))) : 700;
  const messageLimit = Math.max(0, max - suffix.length);
  if (messageLimit <= 0) return posClip(suffix.trimStart(), max);
  return `${posClip(message, messageLimit)}${suffix}`;
}

function posClip(value, limit = 1200) {
  const text = posText(value);
  const max = Number.isFinite(Number(limit)) ? Math.max(0, Math.floor(Number(limit))) : 1200;
  if (text.length <= max) return text;
  const marker = "\n\n[truncated]";
  if (max <= marker.length) return marker.slice(0, max);
  return `${text.slice(0, max - marker.length)}${marker}`;
}

function posRefreshLabel(value, nowValue = Date.now()) {
  const stamp = Number(value);
  if (!Number.isFinite(stamp) || stamp <= 0) return posUiText("pos.refreshNotChecked", "Not checked yet");
  const date = new Date(stamp);
  if (Number.isNaN(date.getTime())) return posUiText("pos.refreshNotChecked", "Not checked yet");
  const clock = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const ageSeconds = Math.max(0, Math.round((Number(nowValue) - stamp) / 1000));
  if (ageSeconds < 5) return `${clock} - ${posUiText("pos.refreshJustNow", "just now")}`;
  if (ageSeconds < 60) return `${clock} - ${posUiText("pos.refreshSecondsAgo", "{{count}}s ago", { count: ageSeconds })}`;
  const ageMinutes = Math.floor(ageSeconds / 60);
  if (ageMinutes < 60) return `${clock} - ${posUiText("pos.refreshMinutesAgo", "{{count}}m ago", { count: ageMinutes })}`;
  const ageHours = Math.floor(ageMinutes / 60);
  return `${clock} - ${posUiText("pos.refreshHoursAgo", "{{count}}h ago", { count: ageHours })}`;
}

function posStateLabel(value) {
  const state = posText(value).toLowerCase();
  if (state === "ready") return posUiText("pos.stateReady", "READY");
  if (state === "review") return posUiText("pos.stateReview", "REVIEW");
  if (state === "blocked") return posUiText("pos.stateBlocked", "BLOCKED");
  if (state === "attention") return posUiText("pos.stateAttention", "ATTENTION");
  if (state === "live") return posUiText("pos.stateLive", "LIVE");
  return posText(value).toUpperCase();
}

function posDraftStatusText(approval) {
  const state = posText(approval).toLowerCase();
  if (state === "pending" || state === "review") return posUiText("pos.draftStatusPending", "Needs review");
  if (state === "approved") return posUiText("pos.draftStatusApproved", "Approved");
  if (state === "rejected") return posUiText("pos.draftStatusRejected", "Rejected");
  if (state === "conflict") return posUiText("pos.draftStatusConflict", "Needs repair");
  if (state === "missing") return posUiText("pos.draftStatusMissing", "Incomplete");
  return posUiText("pos.draftStatusUnknown", "Unknown state");
}
