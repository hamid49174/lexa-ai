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
