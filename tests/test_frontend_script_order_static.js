/**
 * Static checks for classic renderer script loading order.
 * Run with: node tests/test_frontend_script_order_static.js
 */

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend", "src", "index.html"), "utf8");
const chatSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat.js"), "utf8");
const chatConstantsSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_constants.js"), "utf8");
const chatFormattingSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_formatting.js"), "utf8");
const chatMarkdownSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_markdown.js"), "utf8");
const chatMessageFormattingSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_message_formatting.js"), "utf8");
const chatExportSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_export.js"), "utf8");
const chatComposerSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_composer_helpers.js"), "utf8");
const chatMessageActionsSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_message_actions.js"), "utf8");
const chatInputHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_input_helpers.js"), "utf8");
const chatToolConfirmationSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_tool_confirmation_ui.js"), "utf8");
const chatToolDisplaySrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_tool_display_ui.js"), "utf8");
const chatConfirmationStateSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_confirmation_state.js"), "utf8");
const chatHistoryUiSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_history_ui.js"), "utf8");
const chatStreamingHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_streaming_helpers.js"), "utf8");
const settingsHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "settings_helpers.js"), "utf8");
const settingsSrc = fs.readFileSync(path.join(root, "frontend", "src", "settings.js"), "utf8");

let passed = 0;
let failed = 0;

function assert(desc, ok, detail = "") {
  if (ok) {
    console.log(`  ok: ${desc}`);
    passed += 1;
  } else {
    console.error(`  FAIL: ${desc}${detail ? " - " + detail : ""}`);
    failed += 1;
  }
}

function scriptSources(source) {
  return Array.from(source.matchAll(/<script\b[^>]*\bsrc="([^"]+)"[^>]*>/g)).map((match) => match[1]);
}

console.log("\nFrontend script order:");

const scripts = scriptSources(html);
const expectedTail = [
  "./config.js",
  "./state.js",
  "./orb3d.js",
  "./modals.js",
  "./chat_constants.js",
  "./chat_formatting.js",
  "./chat_markdown.js",
  "./chat_message_formatting.js",
  "./chat_export.js",
  "./chat_composer_helpers.js",
  "./chat_message_actions.js",
  "./chat_input_helpers.js",
  "./chat_tool_confirmation_ui.js",
  "./chat_tool_display_ui.js",
  "./chat_confirmation_state.js",
  "./chat_history_ui.js",
  "./chat_streaming_helpers.js",
  "./chat.js",
  "./productivity.js",
  "./dashboard.js",
  "./system.js",
  "./commands.js",
  "./memory.js",
  "./personal_os.js",
  "./settings_helpers.js",
  "./settings.js",
  "./devtools.js",
];
const tail = scripts.slice(-expectedTail.length);

assert("renderer uses expected classic script order", JSON.stringify(tail) === JSON.stringify(expectedTail), JSON.stringify(tail));
assert("chat constants load before chat.js", scripts.indexOf("./chat_constants.js") >= 0 && scripts.indexOf("./chat_constants.js") < scripts.indexOf("./chat.js"));
assert("chat formatting loads after constants and before chat.js", scripts.indexOf("./chat_formatting.js") > scripts.indexOf("./chat_constants.js") && scripts.indexOf("./chat_formatting.js") < scripts.indexOf("./chat.js"));
assert("chat markdown loads after formatting and before chat.js", scripts.indexOf("./chat_markdown.js") > scripts.indexOf("./chat_formatting.js") && scripts.indexOf("./chat_markdown.js") < scripts.indexOf("./chat.js"));
assert("chat message formatting loads after markdown and before chat.js", scripts.indexOf("./chat_message_formatting.js") > scripts.indexOf("./chat_markdown.js") && scripts.indexOf("./chat_message_formatting.js") < scripts.indexOf("./chat.js"));
assert("chat export loads after message formatting and before chat.js", scripts.indexOf("./chat_export.js") > scripts.indexOf("./chat_message_formatting.js") && scripts.indexOf("./chat_export.js") < scripts.indexOf("./chat.js"));
assert("chat composer helpers load after export and before chat.js", scripts.indexOf("./chat_composer_helpers.js") > scripts.indexOf("./chat_export.js") && scripts.indexOf("./chat_composer_helpers.js") < scripts.indexOf("./chat.js"));
assert("chat message actions load after composer helpers and before chat.js", scripts.indexOf("./chat_message_actions.js") > scripts.indexOf("./chat_composer_helpers.js") && scripts.indexOf("./chat_message_actions.js") < scripts.indexOf("./chat.js"));
assert("chat input helpers load after message actions and before chat.js", scripts.indexOf("./chat_input_helpers.js") > scripts.indexOf("./chat_message_actions.js") && scripts.indexOf("./chat_input_helpers.js") < scripts.indexOf("./chat.js"));
assert("chat tool confirmation UI loads after input helpers and before chat.js", scripts.indexOf("./chat_tool_confirmation_ui.js") > scripts.indexOf("./chat_input_helpers.js") && scripts.indexOf("./chat_tool_confirmation_ui.js") < scripts.indexOf("./chat.js"));
assert("chat tool display UI loads after tool confirmation UI and before chat.js", scripts.indexOf("./chat_tool_display_ui.js") > scripts.indexOf("./chat_tool_confirmation_ui.js") && scripts.indexOf("./chat_tool_display_ui.js") < scripts.indexOf("./chat.js"));
assert("chat confirmation state loads after tool display UI and before chat.js", scripts.indexOf("./chat_confirmation_state.js") > scripts.indexOf("./chat_tool_display_ui.js") && scripts.indexOf("./chat_confirmation_state.js") < scripts.indexOf("./chat.js"));
assert("chat history UI loads after confirmation state and before chat.js", scripts.indexOf("./chat_history_ui.js") > scripts.indexOf("./chat_confirmation_state.js") && scripts.indexOf("./chat_history_ui.js") < scripts.indexOf("./chat.js"));
assert("chat streaming helpers load after history UI and before chat.js", scripts.indexOf("./chat_streaming_helpers.js") > scripts.indexOf("./chat_history_ui.js") && scripts.indexOf("./chat_streaming_helpers.js") < scripts.indexOf("./chat.js"));
assert("settings helpers load after personal OS and before settings.js", scripts.indexOf("./settings_helpers.js") > scripts.indexOf("./personal_os.js") && scripts.indexOf("./settings_helpers.js") < scripts.indexOf("./settings.js"));
assert("renderer scripts do not opt into module mode", !/<script\b[^>]*type=["']module["']/i.test(html));
assert("chat constants file is classic script data", chatConstantsSrc.includes("const _AGENT_PATTERNS = [") && !/\b(import|export)\b/.test(chatConstantsSrc));
assert("chat formatting file is classic helper script", chatFormattingSrc.includes("function stripModelFunctionTags(") && chatFormattingSrc.includes("function normalizeChatUrl(") && !/\b(import|export)\b/.test(chatFormattingSrc));
assert("chat markdown file is classic helper script", chatMarkdownSrc.includes("function appendInlineMarkdown(") && chatMarkdownSrc.includes("function appendCodeBlock(") && !/\b(import|export)\b/.test(chatMarkdownSrc));
assert("chat message formatting file is classic helper script", chatMessageFormattingSrc.includes("function appendMarkdownSegment(") && chatMessageFormattingSrc.includes("function formatMessage(") && !/\b(import|export)\b/.test(chatMessageFormattingSrc));
assert("chat export file is classic helper script", chatExportSrc.includes("function messageExportMarkdownFromText(") && chatExportSrc.includes("function messageExportFilename(") && !/\b(import|export)\b/.test(chatExportSrc));
assert("chat composer helpers file is classic helper script", chatComposerSrc.includes("const LEXA_COMPOSER_COMMANDS = [") && chatComposerSrc.includes("function composerCommandSearchItems(") && chatComposerSrc.includes("function expandComposerSlashAlias(") && !/\b(import|export)\b/.test(chatComposerSrc));
assert("chat message actions file is classic helper script", chatMessageActionsSrc.includes("function workspaceDraftPromptFromText(") && chatMessageActionsSrc.includes("function continuePromptFromText(") && chatMessageActionsSrc.includes("function verifyAnswerPromptFromText(") && !/\b(import|export)\b/.test(chatMessageActionsSrc));
assert("chat input helpers file is classic helper script", chatInputHelpersSrc.includes("function chatInputMetrics(") && !/\b(import|export)\b/.test(chatInputHelpersSrc));
assert("chat tool confirmation UI file is classic helper script", chatToolConfirmationSrc.includes("function appendToolConfirmationUi(") && chatToolConfirmationSrc.includes("confirmAction(confirmBtn") && chatToolConfirmationSrc.includes("denyAction(denyBtn)") && !/\b(import|export)\b/.test(chatToolConfirmationSrc));
assert("chat tool display UI file is classic helper script", chatToolDisplaySrc.includes("function toolResultDisplayText(") && !/\b(import|export)\b/.test(chatToolDisplaySrc));
assert("chat confirmation state file is classic helper script", chatConfirmationStateSrc.includes("function confirmationActionSummaryText(") && !/\b(import|export)\b/.test(chatConfirmationStateSrc));
assert("chat history UI file is classic helper script", chatHistoryUiSrc.includes("function conversationListRawTitle(") && chatHistoryUiSrc.includes("function createConversationListItem(") && chatHistoryUiSrc.includes("function renderConversationEmptyState(") && chatHistoryUiSrc.includes("bindKeyboardAction(item") && !/(^|\n)\s*(import|export)\b/.test(chatHistoryUiSrc));
assert("chat streaming helpers file is classic helper script", chatStreamingHelpersSrc.includes("function chatStreamBufferedLines(") && chatStreamingHelpersSrc.includes("function parseChatStreamDataLine(") && !/\b(import|export)\b/.test(chatStreamingHelpersSrc));
assert("settings helpers file is classic helper script", settingsHelpersSrc.includes("function settingsSafeTheme(") && settingsHelpersSrc.includes("function settingsSafeAccent(") && settingsHelpersSrc.includes("function settingsSafeFontSize(") && settingsHelpersSrc.includes("function settingsSafeLanguage(") && !/(^|\n)\s*(import|export)\b/.test(settingsHelpersSrc));
assert("chat.js consumes extracted agent patterns", !chatSrc.includes("const _AGENT_PATTERNS = [") && chatSrc.includes("_AGENT_PATTERNS.some"));
assert("extracted formatting helpers remain consumed", !chatSrc.includes("function stripModelFunctionTags(") && !chatSrc.includes("function normalizeChatUrl(") && chatMessageFormattingSrc.includes("stripModelFunctionTags(text)") && chatMarkdownSrc.includes("normalizeChatUrl(match["));
assert("extracted markdown helpers remain consumed", !chatSrc.includes("function appendInlineMarkdown(") && !chatSrc.includes("function appendCodeBlock(") && chatMessageFormattingSrc.includes("appendMarkdownSegment(parent") && chatMessageFormattingSrc.includes("appendCodeBlock(parent"));
assert("chat.js consumes extracted message formatting helpers", !chatSrc.includes("function appendMarkdownSegment(") && !chatSrc.includes("function appendFormattedMessage(") && !chatSrc.includes("function formatMessage(") && chatSrc.includes("appendFormattedMessage(target"));
assert("chat.js consumes extracted export helpers", !chatSrc.includes("function messageExportMarkdownFromText(") && !chatSrc.includes("function messageExportFilename(") && chatSrc.includes("messageExportMarkdownFromText(text)") && chatSrc.includes("messageExportFilename()"));
assert("chat.js consumes extracted composer helpers", !chatSrc.includes("const LEXA_COMPOSER_COMMANDS = [") && !chatSrc.includes("function composerCommandSearchItems(") && !chatSrc.includes("function expandComposerSlashAlias(") && chatSrc.includes("composerCommandSearchItems(query)") && chatSrc.includes("expandComposerSlashAlias(rawText)"));
assert("chat.js consumes extracted message action prompt helpers", !chatSrc.includes("function workspaceDraftPromptFromText(") && !chatSrc.includes("function continuePromptFromText(") && !chatSrc.includes("function verifyAnswerPromptFromText(") && chatSrc.includes("workspaceDraftPromptFromText(getMessagePersistText") && chatSrc.includes("continuePromptFromText(getMessagePersistText") && chatSrc.includes("verifyAnswerPromptFromText(getMessagePersistText"));
assert("chat.js consumes extracted input metrics helper", !chatSrc.includes("function chatInputMetrics(") && chatSrc.includes("chatInputMetrics(chatInput.value)"));
assert("chat.js consumes extracted tool confirmation UI", !chatSrc.includes("function appendToolConfirmationUi(") && chatSrc.includes("appendToolConfirmationUi(body, action)") && chatSrc.includes("appendToolConfirmationUi(body, actionData)"));
assert("chat.js consumes extracted tool display helper", !chatSrc.includes("const skip = new Set([\"icon\", \"icon_code\", \"will_rain\", \"success\"]);") && chatSrc.includes("toolResultDisplayText(execResult.data)"));
assert("chat.js consumes extracted confirmation state helper", !chatSrc.includes("const summary = prepared.summary || {};") && chatSrc.includes("confirmationActionSummaryText(action, prepared)"));
assert("chat.js consumes extracted history UI", !chatSrc.includes("function createConversationListItem(") && chatSrc.includes("renderConversationEmptyState(container, t(\"chat.noConversations\"))") && chatSrc.includes("createConversationListItem(c, { attention, isActive })"));
assert("chat.js consumes extracted streaming helpers", !chatSrc.includes("const lines = buffer.split(\"\\\\n\");") && chatSrc.includes("chatStreamBufferedLines(buffer)") && chatSrc.includes("parseChatStreamDataLine(line)"));
assert("settings.js consumes extracted preference helpers", !settingsSrc.includes("[\"13\", \"14\", \"15\", \"16\"].includes(String(size))") && settingsSrc.includes("settingsSafeTheme(") && settingsSrc.includes("settingsSafeAccent(") && settingsSrc.includes("settingsSafeFontSize(") && settingsSrc.includes("settingsSafeLanguage("));
assert("Beta/Internal readiness labels remain in the shell", html.includes('data-readiness="beta"') && html.includes('data-readiness="internal"'));

const ids = Array.from(html.matchAll(/\bid="([^"]+)"/g)).map((match) => match[1]);
const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
assert("index.html has no duplicate DOM ids", duplicates.length === 0, duplicates.join(", "));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
