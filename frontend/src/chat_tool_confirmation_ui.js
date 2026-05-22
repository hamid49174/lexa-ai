/*
 * Tool confirmation UI helpers for classic renderer scripts.
 * Normal chat is render-only for local tool actions.
 */

function chatToolActionName(action) {
  return String(action?.action || action?.name || "tool");
}

function chatToolActionParamKeys(action) {
  const params = action?.params;
  if (!params || typeof params !== "object" || Array.isArray(params)) return [];
  return Object.keys(params).sort();
}

function chatActionReplyLooksLikeToolExecution(reply, action) {
  const text = String(reply || "").trim();
  if (!text) return true;

  const actionName = chatToolActionName(action).toLowerCase();
  const normalized = text.toLowerCase();
  const mentionsAction = actionName && normalized.includes(actionName);
  const executionPhrase = /\b(fuehre|führe|execute|run|running|starte|start)\b/i.test(text) || /\baus\b/i.test(text);
  return Boolean(mentionsAction && executionPhrase);
}

function chatActionFallbackText() {
  const docLang = typeof document !== "undefined" ? document.documentElement?.lang : "";
  const navLang = typeof navigator !== "undefined" ? navigator.language : "";
  const lang = String(docLang || navLang || "de").toLowerCase();
  if (lang.startsWith("en")) {
    return "I am here. Tell me what you want to do next.";
  }
  return "Ich bin da. Sag mir kurz, was ich als Naechstes machen soll.";
}

function chatActionDisplayReply(response) {
  const reply = String(response?.reply || "").trim();
  if (!response?.action) return reply;
  if (chatActionReplyLooksLikeToolExecution(reply, response.action)) return chatActionFallbackText();
  return reply;
}

function appendToolConfirmationUi(body, action) {
  if (!body || !action) return null;

  const actionDiv = document.createElement("div");
  actionDiv.className = "msg-action msg-action-blocked";

  const actionLabel = document.createElement("div");
  actionLabel.className = "action-label";
  actionLabel.textContent = t("chat.localActionBlockedTitle");

  const actionCmd = document.createElement("div");
  actionCmd.className = "action-cmd";
  const paramKeys = chatToolActionParamKeys(action);
  actionCmd.textContent = paramKeys.length
    ? `${chatToolActionName(action)}(${paramKeys.join(", ")})`
    : `${chatToolActionName(action)}()`;

  const actionDetail = document.createElement("div");
  actionDetail.className = "action-detail";
  actionDetail.textContent = t("chat.localActionBlockedDetail", { action: chatToolActionName(action) });

  actionDiv.appendChild(actionLabel);
  actionDiv.appendChild(actionCmd);
  actionDiv.appendChild(actionDetail);
  body.appendChild(actionDiv);

  return { actionDiv };
}
