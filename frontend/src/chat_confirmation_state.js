/*
 * Confirmation state helpers for classic renderer scripts.
 * Real approval/denial execution stays in chat.js.
 */

function confirmationActionSummaryText(action, prepared) {
  const summary = prepared.summary || {};
  const paramKeys = Array.isArray(summary.param_keys) ? summary.param_keys.join(", ") : "";
  return [
    `Command: ${summary.command || action.action}`,
    `Scope: ${summary.action_scope || prepared.action_scope || ""}`,
    paramKeys ? `Params: ${paramKeys}` : "",
    `Expires: ${prepared.expires_at || ""}`,
  ].filter(Boolean).join("\n");
}
