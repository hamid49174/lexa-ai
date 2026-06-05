/**
 * Static checks for classic renderer script loading order.
 * Run with: node tests/test_frontend_script_order_static.js
 */

const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend", "src", "index.html"), "utf8");
const storageSrc = fs.readFileSync(path.join(root, "frontend", "src", "storage.js"), "utf8");
const appSrc = fs.readFileSync(path.join(root, "frontend", "src", "app.js"), "utf8");
const appAmbientSrc = fs.readFileSync(path.join(root, "frontend", "src", "app_ambient.js"), "utf8");
const appActionsSrc = fs.readFileSync(path.join(root, "frontend", "src", "app_actions.js"), "utf8");
const appDesktopShortcutsSrc = fs.readFileSync(path.join(root, "frontend", "src", "app_desktop_shortcuts.js"), "utf8");
const appHealthSrc = fs.readFileSync(path.join(root, "frontend", "src", "app_health.js"), "utf8");
const chatSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat.js"), "utf8");
const chatConstantsSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_constants.js"), "utf8");
const chatFormattingSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_formatting.js"), "utf8");
const chatMarkdownSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_markdown.js"), "utf8");
const chatMessageFormattingSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_message_formatting.js"), "utf8");
const chatExportSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_export.js"), "utf8");
const chatComposerSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_composer_helpers.js"), "utf8");
const chatComposerPaletteSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_composer_palette.js"), "utf8");
const chatMessageActionsSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_message_actions.js"), "utf8");
const chatMessageActionsControllerSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_message_actions_controller.js"), "utf8");
const chatInputHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_input_helpers.js"), "utf8");
const chatToolConfirmationSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_tool_confirmation_ui.js"), "utf8");
const chatToolDisplaySrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_tool_display_ui.js"), "utf8");
const chatConfirmationStateSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_confirmation_state.js"), "utf8");
const chatHistoryUiSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_history_ui.js"), "utf8");
const chatStreamingHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_streaming_helpers.js"), "utf8");
const chatFileDisplaySrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_file_display_ui.js"), "utf8");
const chatStateSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_state.js"), "utf8");
const chatAgentRunsSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_agent_runs.js"), "utf8");
const chatConversationsSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_conversations.js"), "utf8");
const chatFileUploadSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_file_upload.js"), "utf8");
const chatSearchSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_search.js"), "utf8");
const chatVoiceSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_voice.js"), "utf8");
const personalOsDisplayHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "personal_os_display_helpers.js"), "utf8");
const personalOsPromptHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "personal_os_prompt_helpers.js"), "utf8");
const personalOsDomHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "personal_os_dom_helpers.js"), "utf8");
const personalOsStateHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "personal_os_state_helpers.js"), "utf8");
const personalOsGraphHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "personal_os_graph_helpers.js"), "utf8");
const personalOsReviewHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "personal_os_review_helpers.js"), "utf8");
const personalOsRenderersSrc = fs.readFileSync(path.join(root, "frontend", "src", "personal_os_renderers.js"), "utf8");
const personalOsSrc = fs.readFileSync(path.join(root, "frontend", "src", "personal_os.js"), "utf8");
const settingsHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "settings_helpers.js"), "utf8");
const settingsProviderHelpersSrc = fs.readFileSync(path.join(root, "frontend", "src", "settings_provider_helpers.js"), "utf8");
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
  "./chat_composer_palette.js",
  "./chat_message_actions.js",
  "./chat_message_actions_controller.js",
  "./chat_input_helpers.js",
  "./chat_tool_confirmation_ui.js",
  "./chat_tool_display_ui.js",
  "./chat_confirmation_state.js",
  "./chat_history_ui.js",
  "./chat_streaming_helpers.js",
  "./chat_file_display_ui.js",
  "./chat_state.js",
  "./chat_agent_runs.js",
  "./chat_conversations.js",
  "./chat_file_upload.js",
  "./chat_search.js",
  "./chat_voice.js",
  "./chat.js",
  "./productivity.js",
  "./dashboard.js",
  "./system.js",
  "./commands.js",
  "./memory.js",
  "./personal_os_display_helpers.js",
  "./personal_os_prompt_helpers.js",
  "./personal_os_dom_helpers.js",
  "./personal_os_state_helpers.js",
  "./personal_os_graph_helpers.js",
  "./personal_os_review_helpers.js",
  "./personal_os_renderers.js",
  "./personal_os.js",
  "./settings_helpers.js",
  "./settings_provider_helpers.js",
  "./settings.js",
  "./devtools.js",
];
const tail = scripts.slice(-expectedTail.length);

assert("renderer uses expected classic script order", JSON.stringify(tail) === JSON.stringify(expectedTail), JSON.stringify(tail));
assert("safe storage helper loads before i18n and app bootstrap", scripts.indexOf("./storage.js") >= 0 && scripts.indexOf("./storage.js") < scripts.indexOf("./i18n/i18n.js") && scripts.indexOf("./storage.js") < scripts.indexOf("./app.js"));
assert("safe storage helper is a classic script", storageSrc.includes("function lexaStorageGet(") && storageSrc.includes("function lexaStorageSet(") && storageSrc.includes("function lexaStorageJson(") && storageSrc.includes("LEXA_STORAGE_MEMORY") && !/(^|\n)\s*(import|export)\b/.test(storageSrc));
assert("app helpers load after i18n and before app.js", scripts.indexOf("./i18n/i18n.js") < scripts.indexOf("./app_ambient.js") && scripts.indexOf("./app_ambient.js") < scripts.indexOf("./app_actions.js") && scripts.indexOf("./app_actions.js") < scripts.indexOf("./app_desktop_shortcuts.js") && scripts.indexOf("./app_desktop_shortcuts.js") < scripts.indexOf("./app_health.js") && scripts.indexOf("./app_health.js") < scripts.indexOf("./app.js"));
assert("chat constants load before chat.js", scripts.indexOf("./chat_constants.js") >= 0 && scripts.indexOf("./chat_constants.js") < scripts.indexOf("./chat.js"));
assert("chat formatting loads after constants and before chat.js", scripts.indexOf("./chat_formatting.js") > scripts.indexOf("./chat_constants.js") && scripts.indexOf("./chat_formatting.js") < scripts.indexOf("./chat.js"));
assert("chat markdown loads after formatting and before chat.js", scripts.indexOf("./chat_markdown.js") > scripts.indexOf("./chat_formatting.js") && scripts.indexOf("./chat_markdown.js") < scripts.indexOf("./chat.js"));
assert("chat message formatting loads after markdown and before chat.js", scripts.indexOf("./chat_message_formatting.js") > scripts.indexOf("./chat_markdown.js") && scripts.indexOf("./chat_message_formatting.js") < scripts.indexOf("./chat.js"));
assert("chat export loads after message formatting and before chat.js", scripts.indexOf("./chat_export.js") > scripts.indexOf("./chat_message_formatting.js") && scripts.indexOf("./chat_export.js") < scripts.indexOf("./chat.js"));
assert("chat composer helpers load after export and before chat.js", scripts.indexOf("./chat_composer_helpers.js") > scripts.indexOf("./chat_export.js") && scripts.indexOf("./chat_composer_helpers.js") < scripts.indexOf("./chat.js"));
assert("chat composer palette loads after composer helpers and before chat.js", scripts.indexOf("./chat_composer_palette.js") > scripts.indexOf("./chat_composer_helpers.js") && scripts.indexOf("./chat_composer_palette.js") < scripts.indexOf("./chat.js"));
assert("chat message actions load after composer palette and before chat.js", scripts.indexOf("./chat_message_actions.js") > scripts.indexOf("./chat_composer_palette.js") && scripts.indexOf("./chat_message_actions.js") < scripts.indexOf("./chat.js"));
assert("chat message actions controller loads after prompt helpers and before chat.js", scripts.indexOf("./chat_message_actions_controller.js") > scripts.indexOf("./chat_message_actions.js") && scripts.indexOf("./chat_message_actions_controller.js") < scripts.indexOf("./chat.js"));
assert("chat input helpers load after message actions controller and before chat.js", scripts.indexOf("./chat_input_helpers.js") > scripts.indexOf("./chat_message_actions_controller.js") && scripts.indexOf("./chat_input_helpers.js") < scripts.indexOf("./chat.js"));
assert("chat tool confirmation UI loads after input helpers and before chat.js", scripts.indexOf("./chat_tool_confirmation_ui.js") > scripts.indexOf("./chat_input_helpers.js") && scripts.indexOf("./chat_tool_confirmation_ui.js") < scripts.indexOf("./chat.js"));
assert("chat tool display UI loads after tool confirmation UI and before chat.js", scripts.indexOf("./chat_tool_display_ui.js") > scripts.indexOf("./chat_tool_confirmation_ui.js") && scripts.indexOf("./chat_tool_display_ui.js") < scripts.indexOf("./chat.js"));
assert("chat confirmation state loads after tool display UI and before chat.js", scripts.indexOf("./chat_confirmation_state.js") > scripts.indexOf("./chat_tool_display_ui.js") && scripts.indexOf("./chat_confirmation_state.js") < scripts.indexOf("./chat.js"));
assert("chat history UI loads after confirmation state and before chat.js", scripts.indexOf("./chat_history_ui.js") > scripts.indexOf("./chat_confirmation_state.js") && scripts.indexOf("./chat_history_ui.js") < scripts.indexOf("./chat.js"));
assert("chat streaming helpers load after history UI and before chat.js", scripts.indexOf("./chat_streaming_helpers.js") > scripts.indexOf("./chat_history_ui.js") && scripts.indexOf("./chat_streaming_helpers.js") < scripts.indexOf("./chat.js"));
assert("chat file display helpers load after streaming helpers and before chat.js", scripts.indexOf("./chat_file_display_ui.js") > scripts.indexOf("./chat_streaming_helpers.js") && scripts.indexOf("./chat_file_display_ui.js") < scripts.indexOf("./chat.js"));
assert("chat state helpers load after file display helpers and before chat.js", scripts.indexOf("./chat_state.js") > scripts.indexOf("./chat_file_display_ui.js") && scripts.indexOf("./chat_state.js") < scripts.indexOf("./chat.js"));
assert("chat agent-run flow loads after state helpers and before chat.js", scripts.indexOf("./chat_agent_runs.js") > scripts.indexOf("./chat_state.js") && scripts.indexOf("./chat_agent_runs.js") < scripts.indexOf("./chat.js"));
assert("chat conversation flow loads after agent-run flow and before chat.js", scripts.indexOf("./chat_conversations.js") > scripts.indexOf("./chat_agent_runs.js") && scripts.indexOf("./chat_conversations.js") < scripts.indexOf("./chat.js"));
assert("chat file upload flow loads after conversation flow and before chat.js", scripts.indexOf("./chat_file_upload.js") > scripts.indexOf("./chat_conversations.js") && scripts.indexOf("./chat_file_upload.js") < scripts.indexOf("./chat.js"));
assert("chat search flow loads after upload flow and before chat.js", scripts.indexOf("./chat_search.js") > scripts.indexOf("./chat_file_upload.js") && scripts.indexOf("./chat_search.js") < scripts.indexOf("./chat.js"));
assert("chat voice flow loads after search flow and before chat.js", scripts.indexOf("./chat_voice.js") > scripts.indexOf("./chat_search.js") && scripts.indexOf("./chat_voice.js") < scripts.indexOf("./chat.js"));
assert("Personal OS display helpers load after memory and before personal_os.js", scripts.indexOf("./personal_os_display_helpers.js") > scripts.indexOf("./memory.js") && scripts.indexOf("./personal_os_display_helpers.js") < scripts.indexOf("./personal_os.js"));
assert("Personal OS prompt helpers load after display helpers and before personal_os.js", scripts.indexOf("./personal_os_prompt_helpers.js") > scripts.indexOf("./personal_os_display_helpers.js") && scripts.indexOf("./personal_os_prompt_helpers.js") < scripts.indexOf("./personal_os.js"));
assert("Personal OS DOM helpers load after prompt helpers and before personal_os.js", scripts.indexOf("./personal_os_dom_helpers.js") > scripts.indexOf("./personal_os_prompt_helpers.js") && scripts.indexOf("./personal_os_dom_helpers.js") < scripts.indexOf("./personal_os.js"));
assert("Personal OS state helpers load after DOM helpers and before personal_os.js", scripts.indexOf("./personal_os_state_helpers.js") > scripts.indexOf("./personal_os_dom_helpers.js") && scripts.indexOf("./personal_os_state_helpers.js") < scripts.indexOf("./personal_os.js"));
assert("Personal OS graph helpers load after state helpers and before personal_os.js", scripts.indexOf("./personal_os_graph_helpers.js") > scripts.indexOf("./personal_os_state_helpers.js") && scripts.indexOf("./personal_os_graph_helpers.js") < scripts.indexOf("./personal_os.js"));
assert("Personal OS review helpers load after graph helpers and before personal_os.js", scripts.indexOf("./personal_os_review_helpers.js") > scripts.indexOf("./personal_os_graph_helpers.js") && scripts.indexOf("./personal_os_review_helpers.js") < scripts.indexOf("./personal_os.js"));
assert("Personal OS renderers load after review helpers and before personal_os.js", scripts.indexOf("./personal_os_renderers.js") > scripts.indexOf("./personal_os_review_helpers.js") && scripts.indexOf("./personal_os_renderers.js") < scripts.indexOf("./personal_os.js"));
assert("settings helpers load after personal OS and before settings.js", scripts.indexOf("./settings_helpers.js") > scripts.indexOf("./personal_os.js") && scripts.indexOf("./settings_helpers.js") < scripts.indexOf("./settings.js"));
assert("settings provider helpers load after settings helpers and before settings.js", scripts.indexOf("./settings_provider_helpers.js") > scripts.indexOf("./settings_helpers.js") && scripts.indexOf("./settings_provider_helpers.js") < scripts.indexOf("./settings.js"));
assert("renderer scripts do not opt into module mode", !/<script\b[^>]*type=["']module["']/i.test(html));
assert("app ambient helper is a classic script", appAmbientSrc.includes("function initLexaAmbientCanvas(") && appAmbientSrc.includes("window.__lexaAmbientDebug") && !/(^|\n)\s*(import|export)\b/.test(appAmbientSrc));
assert("app action delegation helper is a classic script", appActionsSrc.includes("function _initDelegation(") && appActionsSrc.includes("function _dispatch(") && appActionsSrc.includes("runTool(cmd, params") && !/(^|\n)\s*(import|export)\b/.test(appActionsSrc));
assert("app desktop shortcut helper is a classic script", appDesktopShortcutsSrc.includes("function setupDesktopIntegration(") && appDesktopShortcutsSrc.includes("function setupKeyboardShortcuts(") && appDesktopShortcutsSrc.includes("async function triggerScreenshotAnalysis(") && !/(^|\n)\s*(import|export)\b/.test(appDesktopShortcutsSrc));
assert("app health helper is a classic script", appHealthSrc.includes("async function checkHealth(") && appHealthSrc.includes("async function requestSystemInfoCached(") && appHealthSrc.includes("window.requestSystemInfoCached = requestSystemInfoCached") && !/(^|\n)\s*(import|export)\b/.test(appHealthSrc));
assert("chat constants file is classic script data", chatConstantsSrc.includes("const _AGENT_PATTERNS = [") && !/\b(import|export)\b/.test(chatConstantsSrc));
assert("chat formatting file is classic helper script", chatFormattingSrc.includes("function stripModelFunctionTags(") && chatFormattingSrc.includes("function normalizeChatUrl(") && !/\b(import|export)\b/.test(chatFormattingSrc));
assert("chat markdown file is classic helper script", chatMarkdownSrc.includes("function appendInlineMarkdown(") && chatMarkdownSrc.includes("function appendCodeBlock(") && !/\b(import|export)\b/.test(chatMarkdownSrc));
assert("chat message formatting file is classic helper script", chatMessageFormattingSrc.includes("function appendMarkdownSegment(") && chatMessageFormattingSrc.includes("function formatMessage(") && !/\b(import|export)\b/.test(chatMessageFormattingSrc));
assert("chat export file is classic helper script", chatExportSrc.includes("function messageExportMarkdownFromText(") && chatExportSrc.includes("function messageExportFilename(") && !/\b(import|export)\b/.test(chatExportSrc));
assert("chat composer helpers file is classic helper script", chatComposerSrc.includes("const LEXA_COMPOSER_COMMANDS = [") && chatComposerSrc.includes("function composerCommandSearchItems(") && chatComposerSrc.includes("function expandComposerSlashAlias(") && !/\b(import|export)\b/.test(chatComposerSrc));
assert("chat composer palette file is classic helper script", chatComposerPaletteSrc.includes("function setupComposerCommandPalette(") && chatComposerPaletteSrc.includes("function renderConversationStarters(") && chatComposerPaletteSrc.includes("function handleComposerCommandKeydown(") && !/(^|\n)\s*(import|export)\b/.test(chatComposerPaletteSrc));
assert("chat message actions file is classic helper script", chatMessageActionsSrc.includes("function workspaceDraftPromptFromText(") && chatMessageActionsSrc.includes("function continuePromptFromText(") && chatMessageActionsSrc.includes("function verifyAnswerPromptFromText(") && !/\b(import|export)\b/.test(chatMessageActionsSrc));
assert("chat message action controller file is classic helper script", chatMessageActionsControllerSrc.includes("function createMessageActionOverflowMenu(") && chatMessageActionsControllerSrc.includes("async function startWorkspaceDraftFromMessage(") && chatMessageActionsControllerSrc.includes("function copyMessage(") && chatMessageActionsControllerSrc.includes("function createMessageExportButton(") && !/(^|\n)\s*(import|export)\b/.test(chatMessageActionsControllerSrc));
assert("chat input helpers file is classic helper script", chatInputHelpersSrc.includes("function chatInputMetrics(") && !/\b(import|export)\b/.test(chatInputHelpersSrc));
assert("chat tool confirmation UI file is classic helper script", chatToolConfirmationSrc.includes("function appendToolConfirmationUi(") && chatToolConfirmationSrc.includes("chat.localActionBlockedTitle") && chatToolConfirmationSrc.includes("chatToolActionParamKeys(action)") && !chatToolConfirmationSrc.includes("confirmAction(confirmBtn") && !chatToolConfirmationSrc.includes("denyAction(denyBtn)") && !/\b(import|export)\b/.test(chatToolConfirmationSrc));
assert("chat tool display UI file is classic helper script", chatToolDisplaySrc.includes("function toolResultDisplayText(") && !/\b(import|export)\b/.test(chatToolDisplaySrc));
assert("chat confirmation state file is classic helper script", chatConfirmationStateSrc.includes("function confirmationActionSummaryText(") && !/\b(import|export)\b/.test(chatConfirmationStateSrc));
assert("chat history UI file is classic helper script", chatHistoryUiSrc.includes("function conversationListRawTitle(") && chatHistoryUiSrc.includes("function createConversationListItem(") && chatHistoryUiSrc.includes("function renderConversationEmptyState(") && chatHistoryUiSrc.includes("bindKeyboardAction(item") && !/(^|\n)\s*(import|export)\b/.test(chatHistoryUiSrc));
assert("chat streaming helpers file is classic helper script", chatStreamingHelpersSrc.includes("function chatStreamBufferedLines(") && chatStreamingHelpersSrc.includes("function chatStreamFinalLines(") && chatStreamingHelpersSrc.includes("function parseChatStreamDataLine(") && !/\b(import|export)\b/.test(chatStreamingHelpersSrc));
assert("chat file display helpers file is classic helper script", chatFileDisplaySrc.includes("function fileUploadSizeLabel(") && chatFileDisplaySrc.includes("function fileInfoBadgeText(") && !/(^|\n)\s*(import|export)\b/.test(chatFileDisplaySrc));
assert("chat state file is classic helper script", chatStateSrc.includes("function chatTransientSetItem(") && chatStateSrc.includes("function chatCachedHistorySnapshot(") && chatStateSrc.includes("let _conversationSwitchSeq = 0") && !/(^|\n)\s*(import|export)\b/.test(chatStateSrc));
assert("chat agent-run flow file is classic helper script", chatAgentRunsSrc.includes("function normalizeAgentRunMeta(") && chatAgentRunsSrc.includes("function renderAgentAttentionPanel(") && chatAgentRunsSrc.includes("function renderPersistedAgentRunMeta(") && chatAgentRunsSrc.includes("function startAgentCompletionResolve(") && !/(^|\n)\s*(import|export)\b/.test(chatAgentRunsSrc));
assert("chat conversation flow file is classic helper script", chatConversationsSrc.includes("async function newConversation(") && chatConversationsSrc.includes("async function switchConversation(") && chatConversationsSrc.includes("function renderConversationList(") && chatConversationsSrc.includes("function updateConversationTitleLocally(") && !/(^|\n)\s*(import|export)\b/.test(chatConversationsSrc));
assert("chat file upload flow file is classic helper script", chatFileUploadSrc.includes("async function handleFileUpload(") && chatFileUploadSrc.includes("function buildFileUploadCard(") && chatFileUploadSrc.includes("fileUploadSizeLabel(file)") && !/(^|\n)\s*(import|export)\b/.test(chatFileUploadSrc));
assert("chat search flow file is classic helper script", chatSearchSrc.includes("function openSearchOverlay(") && chatSearchSrc.includes("function trapSearchFocus(") && chatSearchSrc.includes("async function exportConversation(") && !/(^|\n)\s*(import|export)\b/.test(chatSearchSrc));
assert("chat voice flow file is classic helper script", chatVoiceSrc.includes("const Voice = {") && chatVoiceSrc.includes("function setupVoice(") && chatVoiceSrc.includes("async function voiceStreamChat(") && chatVoiceSrc.includes("function playTTS(") && !/(^|\n)\s*(import|export)\b/.test(chatVoiceSrc));
assert("Personal OS display helpers file is classic helper script", personalOsDisplayHelpersSrc.includes("function posText(") && personalOsDisplayHelpersSrc.includes("function posErrorMessage(") && personalOsDisplayHelpersSrc.includes("function posStateLabel(") && personalOsDisplayHelpersSrc.includes("function posDraftStatusText(") && !/(^|\n)\s*(import|export)\b/.test(personalOsDisplayHelpersSrc));
assert("Personal OS prompt helpers file is classic helper script", personalOsPromptHelpersSrc.includes("function posChatPromptLimit(") && personalOsPromptHelpersSrc.includes("function personalOsReviewPrompt(") && personalOsPromptHelpersSrc.includes("function personalOsSendReviewToChat(") && !/(^|\n)\s*(import|export)\b/.test(personalOsPromptHelpersSrc));
assert("Personal OS DOM helpers file is classic helper script", personalOsDomHelpersSrc.includes("function createPersonalOsDraftRow(") && personalOsDomHelpersSrc.includes("function createPersonalOsCodeLoopView(") && personalOsDomHelpersSrc.includes("function createPersonalOsHomeAction(") && !/(^|\n)\s*(import|export)\b/.test(personalOsDomHelpersSrc));
assert("Personal OS state helpers file is classic helper script", personalOsStateHelpersSrc.includes("function posQueueCounts(") && personalOsStateHelpersSrc.includes("function posRefreshOptions(") && personalOsStateHelpersSrc.includes("function loadPersonalOsQueueFilter(") && !/(^|\n)\s*(import|export)\b/.test(personalOsStateHelpersSrc));
assert("Personal OS graph helpers file is classic helper script", personalOsGraphHelpersSrc.includes("function createPersonalOsSvgElement(") && personalOsGraphHelpersSrc.includes("function renderPersonalOsGraphPayload(") && personalOsGraphHelpersSrc.includes("function setupPersonalOsGraphFocus(") && !/(^|\n)\s*(import|export)\b/.test(personalOsGraphHelpersSrc));
assert("Personal OS review helpers file is classic helper script", personalOsReviewHelpersSrc.includes("function createPosApplyHint(") && personalOsReviewHelpersSrc.includes("function createPosPromptHint(") && personalOsReviewHelpersSrc.includes("function renderPosApplyHint(") && personalOsReviewHelpersSrc.includes("function renderPosPromptHint(") && !/(^|\n)\s*(import|export)\b/.test(personalOsReviewHelpersSrc));
assert("Personal OS renderers file is classic helper script", personalOsRenderersSrc.includes("function renderPersonalOsStatus(") && personalOsRenderersSrc.includes("function renderPersonalOsDetail(") && personalOsRenderersSrc.includes("function renderPersonalOsCodeLoop(") && !/(^|\n)\s*(import|export)\b/.test(personalOsRenderersSrc));
assert("settings helpers file is classic helper script", settingsHelpersSrc.includes("function settingsSafeTheme(") && settingsHelpersSrc.includes("function settingsSafeAccent(") && settingsHelpersSrc.includes("function settingsSafeFontSize(") && settingsHelpersSrc.includes("function settingsSafeLanguage(") && !/(^|\n)\s*(import|export)\b/.test(settingsHelpersSrc));
assert("settings provider helpers file is classic helper script", settingsProviderHelpersSrc.includes("function settingsRenderAiModelSelection(") && settingsProviderHelpersSrc.includes("function settingsAiModelGroupedOptions(") && !/(^|\n)\s*(import|export)\b/.test(settingsProviderHelpersSrc));
assert("app.js delegates extracted app flows", !appSrc.includes("function initLexaAmbientCanvas(") && !appSrc.includes("function _dispatch(") && !appSrc.includes("function setupDesktopIntegration(") && !appSrc.includes("function setupKeyboardShortcuts(") && !appSrc.includes("async function checkHealth(") && appSrc.includes("initLexaAmbientCanvas();") && appSrc.includes("_initDelegation();") && appSrc.includes("setupDesktopIntegration();") && appSrc.includes("setupKeyboardShortcuts();") && appSrc.includes("checkHealth();"));
assert("chat.js consumes extracted agent patterns", !chatSrc.includes("const _AGENT_PATTERNS = [") && chatSrc.includes("_AGENT_PATTERNS.some"));
assert("extracted formatting helpers remain consumed", !chatSrc.includes("function stripModelFunctionTags(") && !chatSrc.includes("function normalizeChatUrl(") && chatMessageFormattingSrc.includes("stripModelFunctionTags(text)") && chatMarkdownSrc.includes("normalizeChatUrl(match["));
assert("extracted markdown helpers remain consumed", !chatSrc.includes("function appendInlineMarkdown(") && !chatSrc.includes("function appendCodeBlock(") && chatMessageFormattingSrc.includes("appendMarkdownSegment(parent") && chatMessageFormattingSrc.includes("appendCodeBlock(parent"));
assert("chat.js consumes extracted message formatting helpers", !chatSrc.includes("function appendMarkdownSegment(") && !chatSrc.includes("function appendFormattedMessage(") && !chatSrc.includes("function formatMessage(") && chatSrc.includes("appendFormattedMessage(target"));
assert("message action controller consumes extracted export helpers", !chatSrc.includes("function messageExportMarkdownFromText(") && !chatSrc.includes("function messageExportFilename(") && chatMessageActionsControllerSrc.includes("messageExportMarkdownFromText(text)") && chatMessageActionsControllerSrc.includes("messageExportFilename()"));
assert("chat.js consumes extracted composer helpers", !chatSrc.includes("const LEXA_COMPOSER_COMMANDS = [") && !chatSrc.includes("function composerCommandSearchItems(") && !chatSrc.includes("function expandComposerSlashAlias(") && (chatSrc.includes("expandComposerSlashAlias(rawText)") || chatComposerPaletteSrc.includes("composerCommandSearchItems(query)")));
assert("chat.js consumes extracted composer palette", !chatSrc.includes("function setupComposerCommandPalette(") && !chatSrc.includes("function renderConversationStarters(") && chatComposerPaletteSrc.includes("function setupComposerCommandPalette(") && chatComposerPaletteSrc.includes("function renderConversationStarters("));
assert("chat message action controller consumes extracted prompt helpers", !chatSrc.includes("function workspaceDraftPromptFromText(") && !chatSrc.includes("function continuePromptFromText(") && !chatSrc.includes("function verifyAnswerPromptFromText(") && chatMessageActionsControllerSrc.includes("workspaceDraftPromptFromText(getMessagePersistText") && chatMessageActionsControllerSrc.includes("continuePromptFromText(getMessagePersistText") && chatMessageActionsControllerSrc.includes("verifyAnswerPromptFromText(getMessagePersistText"));
assert("chat.js consumes extracted message action controller", !chatSrc.includes("function createMessageActionOverflowMenu(") && !chatSrc.includes("function copyTextToClipboard(") && !chatSrc.includes("function exportMessageMarkdown(") && !chatSrc.includes("async function startWorkspaceDraftFromMessage(") && chatSrc.includes("createMessageActionOverflowMenu(moreActions)") && chatSrc.includes("createMessageExportButton(true)") && chatSrc.includes("copyMessage(copyBtn)") && chatMessageActionsControllerSrc.includes("function previousUserPromptForMessage("));
assert("chat.js consumes extracted input metrics helper", !chatSrc.includes("function chatInputMetrics(") && chatSrc.includes("chatInputMetrics(chatInput.value)"));
assert("chat local-action UI helper is no longer used by normal chat", !chatSrc.includes("function appendToolConfirmationUi(") && chatSrc.includes("options?.showLocalActionCard") && !chatSrc.includes("appendToolConfirmationUi(body, actionData)"));
assert("chat tool result formatter stays isolated from chat auto-execution", !chatSrc.includes("const skip = new Set([\"icon\", \"icon_code\", \"will_rain\", \"success\"]);") && !chatSrc.includes("toolResultDisplayText(execResult.data)") && !chatSrc.includes("execResult"));
assert("chat does not auto-execute or visibly block local tools from normal chat responses", !chatSrc.includes("window.lexa.execute(") && !chatSrc.includes("window.lexa.executeWithConfirmation(") && !chatSrc.includes("window.lexa.prepareCompanionExecute(") && !chatSrc.includes("window.confirm(") && chatSrc.includes("handleChatToolActionBlocked(actionData)") && chatFileUploadSrc.includes("handleChatToolActionBlocked(res.action, { source: \"file-upload\" })") && chatSrc.includes("options.toast === true"));
assert("chat.js consumes extracted agent-run flow", !chatSrc.includes("function normalizeAgentRunMeta(") && !chatSrc.includes("function renderAgentAttentionPanel(") && !chatSrc.includes("function renderPersistedAgentRunMeta(") && chatAgentRunsSrc.includes("renderAgentOutcomeSummary(summaryEl, counts)") && chatAgentRunsSrc.includes("saveAgentRunMetaForConversation(convId)"));
assert("chat conversation flow consumes extracted history UI", !chatSrc.includes("function createConversationListItem(") && chatConversationsSrc.includes("renderConversationEmptyState(container, t(\"chat.noConversations\"))") && chatConversationsSrc.includes("createConversationListItem(c, { attention, isActive })"));
assert("chat.js consumes extracted streaming helpers", !chatSrc.includes("const lines = buffer.split(\"\\\\n\");") && chatSrc.includes("chatStreamBufferedLines(buffer)") && chatSrc.includes("chatStreamFinalLines(buffer)") && chatSrc.includes("parseChatStreamDataLine(line)"));
assert("chat voice consumes shared streaming parser helpers", !chatVoiceSrc.includes("const lines = buffer.split(\"\\\\n\");") && chatVoiceSrc.includes("chatStreamBufferedLines(buffer)") && chatVoiceSrc.includes("chatStreamFinalLines(buffer)") && chatVoiceSrc.includes("parseChatStreamDataLine(line)"));
assert("chat.js consumes extracted state helpers", !chatSrc.includes("function chatTransientSetItem(") && !chatSrc.includes("let _conversationSwitchSeq = 0") && chatSrc.includes("chatTransientSetItem(CHAT_HISTORY_CACHE_KEY") && chatSrc.includes("chatGetActiveConversationId()"));
assert("chat.js consumes extracted conversation flow", !chatSrc.includes("async function newConversation(") && !chatSrc.includes("function renderConversationList(") && !chatSrc.includes("function updateConversationTitleLocally(") && chatConversationsSrc.includes("renderAgentAttentionPanel(container, convList)") && chatConversationsSrc.includes("await saveCurrentConversation({ notifyFailure: notify })"));
assert("chat.js consumes extracted file upload flow", !chatSrc.includes("async function handleFileUpload(") && !chatSrc.includes("function buildFileUploadCard(") && chatFileUploadSrc.includes("fileUploadSizeLabel(file)") && chatFileUploadSrc.includes("fileInfoBadgeText(fileInfo)"));
assert("chat.js consumes extracted search/export flow", !chatSrc.includes("function openSearchOverlay(") && !chatSrc.includes("function appendHighlightedText(") && chatSearchSrc.includes("function openSearchOverlay(") && chatSearchSrc.includes("async function exportConversation("));
assert("chat.js consumes extracted voice flow", !chatSrc.includes("const Voice = {") && !chatSrc.includes("function setupVoice(") && chatVoiceSrc.includes("function voiceStatusBarUpdate(") && chatVoiceSrc.includes("function renderTalkButton("));
assert("Personal OS keeps display helpers extracted", !personalOsSrc.includes("function posErrorMessage(") && !personalOsSrc.includes("function posStateLabel(") && !personalOsSrc.includes("function posDraftStatusText(") && personalOsRenderersSrc.includes("posStateLabel(\"live\")") && personalOsDomHelpersSrc.includes("posDraftStatusText(draft.approval)"));
assert("Personal OS keeps review helpers extracted", !personalOsSrc.includes("function createPosApplyHint(") && !personalOsSrc.includes("function createPosPromptHint(") && personalOsRenderersSrc.includes("createPosPromptHint(payload, review)") && personalOsRenderersSrc.includes("createPosApplyHint(review)"));
assert("personal_os.js delegates extracted Personal OS flows", !personalOsSrc.includes("function renderPersonalOsStatus(") && !personalOsSrc.includes("function createPersonalOsDraftRow(") && !personalOsSrc.includes("function renderPersonalOsGraphPayload(") && personalOsSrc.includes("renderPersonalOsStatus(") && personalOsSrc.includes("renderPersonalOsGraphPayload("));
assert("settings.js consumes extracted preference helpers", !settingsSrc.includes("[\"13\", \"14\", \"15\", \"16\"].includes(String(size))") && settingsSrc.includes("settingsSafeTheme(") && settingsSrc.includes("settingsSafeAccent(") && settingsSrc.includes("settingsSafeFontSize(") && settingsSrc.includes("settingsSafeLanguage("));
assert("settings.js uses safe preference storage", settingsSrc.includes('lexaStorageGet("lexa-theme", "dark")') && settingsSrc.includes('lexaStorageSet("lexa-theme"') && settingsSrc.includes('lexaStorageGet("lexa-fontsize", "")') && !settingsSrc.includes("localStorage.getItem(") && !settingsSrc.includes("localStorage.setItem("));
assert("settings.js owns provider/model handlers", settingsSrc.includes("function loadModelSelection(") && settingsSrc.includes("function changeAiModel(") && !chatSrc.includes("function loadModelSelection(") && !chatSrc.includes("function changeAiModel("));
assert("settings.js consumes extracted provider/model display helpers", settingsSrc.includes("settingsRenderAiModelSelection(data, select, desc)") && settingsSrc.includes("settingsAiModelDescriptionText(result.current)"));
assert("Beta/Internal readiness labels remain in the shell", html.includes('data-readiness="beta"') && html.includes('data-readiness="internal"'));

const ids = Array.from(html.matchAll(/\bid="([^"]+)"/g)).map((match) => match[1]);
const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
assert("index.html has no duplicate DOM ids", duplicates.length === 0, duplicates.join(", "));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
