/*
 * Tool confirmation UI helpers for classic renderer scripts.
 * Render-only helpers live here; approval/execution stays in chat.js.
 */

function appendToolConfirmationUi(body, action) {
  if (!body || !action) return null;

  const actionDiv = document.createElement("div");
  actionDiv.className = "msg-action";

  const actionLabel = document.createElement("div");
  actionLabel.className = "action-label";
  actionLabel.textContent = t("chat.confirmationRequired");

  const actionCmd = document.createElement("div");
  actionCmd.className = "action-cmd";
  actionCmd.textContent = `${String(action.action)}(${JSON.stringify(action.params || {})})`;

  actionDiv.appendChild(actionLabel);
  actionDiv.appendChild(actionCmd);
  body.appendChild(actionDiv);

  const confirmBtn = document.createElement("button");
  confirmBtn.type = "button";
  confirmBtn.className = "confirm-btn";
  confirmBtn.textContent = t("chat.confirmBtn");
  confirmBtn.addEventListener("click", () => confirmAction(confirmBtn, encodeURIComponent(JSON.stringify(action))));

  const denyBtn = document.createElement("button");
  denyBtn.type = "button";
  denyBtn.className = "deny-btn";
  denyBtn.textContent = t("common.cancel");
  denyBtn.addEventListener("click", () => denyAction(denyBtn));

  body.appendChild(confirmBtn);
  body.appendChild(denyBtn);

  return { actionDiv, confirmBtn, denyBtn };
}
