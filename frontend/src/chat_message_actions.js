/* Pure answer action prompt builders loaded before chat.js. Keep this file free of module syntax. */

function workspaceDraftPromptFromText(sourceText) {
  const source = String(sourceText || "").trim();
  if (!source) return "";
  const workspaceCommand = LEXA_COMPOSER_COMMANDS.find((command) => command.id === "workspace");
  const prefix = composerCommandPrefix(workspaceCommand);
  const limit = 8000;
  const boundedSource = source.length > limit
    ? `${source.slice(0, limit)}\n\n[Source clipped for chat handoff.]`
    : source;
  return `${prefix}Turn the following Lexa answer into a clean reusable workspace artifact. Preserve useful nuance, mark claims that need verification, and keep facts, assumptions, ideas, decisions, evidence, risks, open questions, and tasks separate.\n\nSource answer:\n${boundedSource}`.trim();
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
  const marker = source.length > sourceBudget && clipMarker.length < sourceBudget ? clipMarker : "";
  const sourceLimit = Math.max(0, sourceBudget - marker.length);
  const boundedSource = source.length > sourceLimit
    ? `${source.slice(0, sourceLimit)}${marker}`
    : source;
  const text = `${prefix}${sourceLabel}${boundedSource}`.slice(0, targetMax);
  return { text, cursorStart: Math.min(prefix.length, text.length) };
}

function verifyAnswerPromptFromText(sourceText) {
  const source = String(sourceText || "").trim();
  if (!source) return "";
  const researchCommand = LEXA_COMPOSER_COMMANDS.find((command) => command.id === "research");
  const prefix = composerCommandPrefix(researchCommand);
  const limit = 8000;
  const boundedSource = source.length > limit
    ? `${source.slice(0, limit)}\n\n${t("chat.verifyAnswerClipMarker")}`
    : source;
  return `${prefix}Verify the following Lexa answer with source-backed research. Extract checkable claims, separate facts, assumptions, ideas, decisions, evidence, risks, unsupported claims, and follow-up tasks. Cite sources where available and mark anything not verified clearly.\n\nSource answer:\n${boundedSource}`.trim();
}
