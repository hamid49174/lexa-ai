/* Pure answer action prompt builders loaded before chat.js. Keep this file free of module syntax. */

function messageActionPromptLimit(fallbackLimit = 8000) {
  const fallback = Math.max(1, Number(fallbackLimit) || 8000);
  const configured = Math.max(1, Number(LexaConfig?.MAX_CHAT_INPUT_LENGTH) || fallback);
  return Math.min(fallback, configured);
}

function messageActionBoundedSource(source, sourceBudget, clipMarker) {
  const text = String(source || "");
  const budget = Math.max(0, Number(sourceBudget) || 0);
  if (text.length <= budget) return text;
  if (budget <= 0) return "";
  const marker = `\n\n${String(clipMarker || "").trim()}\n\n`;
  if (!marker.trim() || marker.length >= budget) return text.slice(0, budget);
  const contentBudget = Math.max(0, budget - marker.length);
  const headLimit = Math.ceil(contentBudget * 0.65);
  const tailLimit = Math.max(0, contentBudget - headLimit);
  if (tailLimit <= 0) return `${text.slice(0, contentBudget)}${marker}`.slice(0, budget);
  return `${text.slice(0, headLimit)}${marker}${text.slice(text.length - tailLimit)}`.slice(0, budget);
}

function messageActionPromptWithSource(lead, source, clipMarker, fallbackLimit = 8000) {
  const limit = messageActionPromptLimit(fallbackLimit);
  const sourceBudget = Math.max(0, limit - lead.length);
  const boundedSource = messageActionBoundedSource(source, sourceBudget, clipMarker);
  return `${lead}${boundedSource}`.slice(0, limit).trim();
}

function workspaceDraftPromptFromText(sourceText) {
  const source = String(sourceText || "").trim();
  if (!source) return "";
  const workspaceCommand = LEXA_COMPOSER_COMMANDS.find((command) => command.id === "workspace");
  const prefix = composerCommandPrefix(workspaceCommand);
  const lead = `${prefix}Turn the following Lexa answer into a clean reusable workspace artifact. Preserve useful nuance, mark claims that need verification, and keep facts, assumptions, ideas, decisions, evidence, risks, open questions, and tasks separate.\n\nSource answer:\n`;
  return messageActionPromptWithSource(lead, source, "\n\n[Source clipped for chat handoff.]");
}

function continuePromptFromText(sourceText) {
  const source = String(sourceText || "").trim();
  if (!source) return { text: "", cursorStart: 0 };
  const prefix = `${t("chat.continueFromAnswerPrefix")}\n\n${t("chat.continueFromAnswerNextRequest")} `;
  const sourceLabel = `\n\n${t("chat.continueFromAnswerSourceLabel")}\n`;
  const clipMarker = `\n\n${t("chat.continueFromAnswerClipMarker")}`;
  const maxInput = Math.max(1, Number(LexaConfig?.MAX_CHAT_INPUT_LENGTH) || 12000);
  const nextRequestHeadroom = Math.min(1600, Math.max(240, Math.floor(maxInput * 0.18)));
  const targetMax = Math.max(1, maxInput - nextRequestHeadroom);
  const sourceBudget = Math.max(0, targetMax - prefix.length - sourceLabel.length);
  const boundedSource = messageActionBoundedSource(source, sourceBudget, clipMarker);
  const text = `${prefix}${sourceLabel}${boundedSource}`.slice(0, targetMax);
  return { text, cursorStart: Math.min(prefix.length, text.length) };
}

function verifyAnswerPromptFromText(sourceText) {
  const source = String(sourceText || "").trim();
  if (!source) return "";
  const researchCommand = LEXA_COMPOSER_COMMANDS.find((command) => command.id === "research");
  const prefix = composerCommandPrefix(researchCommand);
  const lead = `${prefix}Verify the following Lexa answer with source-backed research. Extract checkable claims, separate facts, assumptions, ideas, decisions, evidence, risks, unsupported claims, and follow-up tasks. Cite sources where available and mark anything not verified clearly.\n\nSource answer:\n`;
  return messageActionPromptWithSource(lead, source, `\n\n${t("chat.verifyAnswerClipMarker")}`);
}
