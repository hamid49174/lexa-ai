/**
 * Smoke tests for app.js chat input wiring.
 * Run with: node tests/test_app_chat_input_wiring.js
 */

const fs = require("fs");
const path = require("path");

function collectJsFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...collectJsFiles(full));
    else if (entry.isFile() && entry.name.endsWith(".js")) out.push(full);
  }
  return out;
}

const src = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "app.js"),
  "utf8"
);
const html = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "index.html"),
  "utf8"
);
const chatSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "chat.js"),
  "utf8"
);
const memorySrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "memory.js"),
  "utf8"
);
const modalsSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "modals.js"),
  "utf8"
);
const commandsSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "commands.js"),
  "utf8"
);
const productivitySrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "productivity.js"),
  "utf8"
);
const settingsSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "settings.js"),
  "utf8"
);
const voiceCss = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "css", "voice.css"),
  "utf8"
);
const overridesCss = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "css", "overrides.css"),
  "utf8"
);
const orb3dSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "orb3d.js"),
  "utf8"
);
const i18nDe = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "i18n", "de.json"),
  "utf8"
);
const i18nEn = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "i18n", "en.json"),
  "utf8"
);
const i18nDeJson = JSON.parse(i18nDe);
const i18nEnJson = JSON.parse(i18nEn);
const i18nSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "i18n", "i18n.js"),
  "utf8"
);
const frontendSrcDir = path.join(__dirname, "..", "frontend", "src");
const frontendJsFiles = collectJsFiles(frontendSrcDir);
const frontendMarkupFiles = [
  path.join(frontendSrcDir, "index.html"),
  ...frontendJsFiles,
];

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

console.log("\napp.js chat input wiring:");

const dynamicButtonCreatePattern = /document\.createElement\((["'])button\1\);/g;
const productivityButtonCreates = [...productivitySrc.matchAll(dynamicButtonCreatePattern)];
const productivityButtonsWithoutType = productivityButtonCreates.filter((match) => {
  const windowText = productivitySrc.slice(match.index, match.index + 180);
  return !/\.type\s*=\s*(["'])button\1/.test(windowText);
});
const dynamicButtonsWithoutType = [];
for (const file of frontendJsFiles) {
  const source = fs.readFileSync(file, "utf8");
  for (const match of source.matchAll(dynamicButtonCreatePattern)) {
    const windowText = source.slice(match.index, match.index + 220);
    if (!/\.type\s*=\s*(["'])button\1/.test(windowText)) {
      dynamicButtonsWithoutType.push(`${path.relative(frontendSrcDir, file)}@${match.index}`);
    }
  }
}
const staticButtonsWithoutType = [];
const staticIconButtonsWithoutName = [];
const staticFormFieldsWithoutName = [];
const missingI18nRefs = [];
const i18nDeKeys = Object.keys(i18nDeJson).sort();
const i18nEnKeys = Object.keys(i18nEnJson).sort();
const i18nKeyMismatches = [
  ...i18nDeKeys.filter((key) => !Object.prototype.hasOwnProperty.call(i18nEnJson, key)).map((key) => `de-only:${key}`),
  ...i18nEnKeys.filter((key) => !Object.prototype.hasOwnProperty.call(i18nDeJson, key)).map((key) => `en-only:${key}`),
];
const emptyI18nValues = [
  ...i18nDeKeys.filter((key) => typeof i18nDeJson[key] === "string" && i18nDeJson[key].trim() === "").map((key) => `de:${key}`),
  ...i18nEnKeys.filter((key) => typeof i18nEnJson[key] === "string" && i18nEnJson[key].trim() === "").map((key) => `en:${key}`),
];
const commandNames = [...commandsSrc.matchAll(/\bname:\s*"([^"]+)"/g)].map((match) => match[1]);
const missingCommandDescRefs = commandNames
  .map((name) => `cmd.desc.${name}`)
  .filter((key) => !Object.prototype.hasOwnProperty.call(i18nDeJson, key) || !Object.prototype.hasOwnProperty.call(i18nEnJson, key));
function noteI18nRef(key, file) {
  if (!/^[a-z0-9_.-]+$/i.test(key) || key.endsWith(".")) return;
  if (!Object.prototype.hasOwnProperty.call(i18nDeJson, key) || !Object.prototype.hasOwnProperty.call(i18nEnJson, key)) {
    missingI18nRefs.push(`${key} in ${path.relative(frontendSrcDir, file)}`);
  }
}
for (const file of frontendMarkupFiles) {
  const source = fs.readFileSync(file, "utf8");
  for (const match of source.matchAll(/data-i18n(?:-[a-z-]+)?=["']([^"']+)["']/g)) {
    noteI18nRef(match[1], file);
  }
  for (const match of source.matchAll(/\bt\(\s*["']([^"']+)["']/g)) {
    noteI18nRef(match[1], file);
  }
  for (const match of source.matchAll(/<button(?![^>]*\btype=)/g)) {
    staticButtonsWithoutType.push(`${path.relative(frontendSrcDir, file)}@${match.index}`);
  }
  for (const match of source.matchAll(/<button\b[^>]*>[\s\S]*?<\/button>/g)) {
    const htmlText = match[0];
    const openTag = htmlText.match(/^<button\b[^>]*>/)?.[0] || "";
    const visibleText = htmlText
      .replace(/<svg[\s\S]*?<\/svg>/g, "")
      .replace(/<[^>]+>/g, "")
      .replace(/&[a-zA-Z0-9#]+;/g, "")
      .trim();
    const isIconish = /\b(icon|close|delete|copy|send|mic|tts|bell|swatch|dot|btn|toggle)\b/i.test(openTag);
    const hasName = /\b(aria-label|data-i18n-aria-label|aria-labelledby)=/.test(openTag);
    const hasVisibleText = /[A-Za-zÀ-ÿ0-9]/.test(visibleText);
    if (isIconish && !hasName && !hasVisibleText) {
      staticIconButtonsWithoutName.push(`${path.relative(frontendSrcDir, file)}@${match.index}`);
    }
  }
  for (const match of source.matchAll(/<(input|textarea|select)\b[^>]*>/g)) {
    const tag = match[0];
    if (/type=["'](?:hidden|checkbox|radio)["']/.test(tag)) continue;
    const id = tag.match(/\bid=["']([^"']+)/)?.[1];
    const hasName = /\b(aria-label|data-i18n-aria-label|aria-labelledby)=/.test(tag);
    const hasExplicitLabel = Boolean(id && new RegExp(`<label[^>]*for=["']${id}["']`).test(source));
    const before = source.slice(0, match.index);
    const hasWrappingLabel = before.lastIndexOf("<label") > before.lastIndexOf("</label>") && source.indexOf("</label>", match.index) !== -1;
    if (!hasName && !hasExplicitLabel && !hasWrappingLabel) {
      staticFormFieldsWithoutName.push(`${path.relative(frontendSrcDir, file)}@${match.index}`);
    }
  }
}

const inputListener = src.match(/chatInput\.addEventListener\("input", \(\) => \{[\s\S]*?\n\s*\}\);/);
assert("input listener exists", Boolean(inputListener));
assert("input listener syncs chat input size", Boolean(inputListener?.[0].includes("syncChatInputSize")));

const historyAssignments = [...src.matchAll(/_setChatInputValue\(chatInputHistory\[chatHistoryIdx\]\);[\s\S]{0,120}/g)];
assert("history recall assignment is present", historyAssignments.length >= 1);
assert("history recall syncs chat input size", src.includes("function _setChatInputValue") && src.includes("syncChatInputSize"));

const draftAssignment = src.match(/_setChatInputValue\(chatInputDraft\);[\s\S]{0,120}/);
assert("history draft restore syncs chat input size", Boolean(draftAssignment) && src.includes("function _setChatInputValue") && src.includes("syncChatInputSize"));
assert("chat input is a multiline textarea", html.includes('<textarea id="chat-input" rows="1"') && !html.includes('type="text" id="chat-input"'));
assert("enter handling supports multiline textarea escapes", src.includes("function _chatInputShouldSendOnEnter") && src.includes("e.shiftKey") && src.includes("e.isComposing") && src.includes("window.ctrlEnterMode"));
assert("arrow history respects multiline cursor boundaries", src.includes("function _chatInputAtHistoryBoundary") && src.includes("selectionStart") && src.includes("selectionEnd") && src.includes('_chatInputAtHistoryBoundary("up")') && src.includes('_chatInputAtHistoryBoundary("down")'));
assert("textarea auto grows with overflow guard", chatSrc.includes('chatInput.tagName === "TEXTAREA"') && chatSrc.includes("scrollHeight") && chatSrc.includes("maxHeight = 160") && chatSrc.includes("chatInput.rows") && chatSrc.includes('classList.toggle("is-scrollable"') && overridesCss.includes("#chat-input.is-scrollable"));

const personalOsAutoRefresh = src.match(/refreshPersonalOsView\(\{ auto: true \}\)/);
assert("personal OS interval uses non-invasive auto refresh", Boolean(personalOsAutoRefresh));

assert("wake word start validates backend active/ready status", src.includes("function _wakeWordStartOk") && src.includes("res.active !== false") && src.includes("res.ready !== false"));
assert("wake word failures mark local state inactive", src.includes("function _markWakeWordInactive") && src.includes('LexaState.set("wakeWordActive", false)'));
assert("wake word polling periodically checks backend status", src.includes("window.lexa.wakewordStatus()") && src.includes("_wakeWordNextStatusCheck"));
assert("wake word auto-init uses same start guard", src.includes("if (_wakeWordStartOk(res))"));
assert("wake word keeps persistent preference separate from runtime state", src.includes("function _wakeWordPreferenceOn") && src.includes("function _setWakeWordPreference"));
assert("wake word manual disable clears restart and preference", src.includes("_clearWakeWordRestart();") && src.includes("_setWakeWordPreference(false);"));
assert("wake word backend status loss preserves preference and restarts", src.includes("_markWakeWordInactive(_wakeWordErrorText(status), { keepPreference: true, autoRestart: true })"));
assert("wake word backend reconnect immediately adopts desired runtime", src.includes('await _ensureWakeWordRunning("Backend healthy")'));
assert("wake word event poll reconciles renderer runtime drift", src.includes('await _ensureWakeWordRunning("Wake poll adoption")') && src.includes("if (!_wakeWordPreferenceOn()) return"));
assert("voice orb is keyboard focusable and named", html.includes('id="voice-orb-canvas" data-action="startOrbConversation" role="button" tabindex="0" aria-pressed="false"') && html.includes('data-i18n-aria-label="chat.talkToLexaBtn"'));
assert("talk-to-lexa button is an accessible toggle", html.includes('id="talk-to-lexa-btn" type="button" aria-pressed="false"') && html.includes('data-i18n-title="app.orbClickSpeak"') && html.includes("data-voice-entry-label"));
assert("composer voice buttons are accessible toggles", html.includes('id="tts-toggle" type="button" aria-pressed="false"') && html.includes('data-i18n-aria-label="chat.ttsToggleLabel"') && html.includes('id="mic-btn" type="button" aria-pressed="false" aria-busy="false"') && html.includes('data-i18n-title="chat.micStartTitle"'));
assert("non-native action controls activate on keyboard", src.includes("function _isKeyboardActionTarget") && src.includes('document.addEventListener("keydown"') && src.includes('e.key === "Enter"') && src.includes('e.key === " "') && src.includes("_safeDispatch(el, el.dataset, null)"));
assert("delegated action controls are auto-accessible", src.includes("function _setupActionAccessibility") && src.includes('root.querySelectorAll?.("[data-action]")') && src.includes('el.setAttribute("role", "button")') && src.includes('el.setAttribute("tabindex", "0")') && src.includes("new MutationObserver"));
assert("delegated action failures are contained", src.includes("function _safeDispatch") && src.includes('console.warn("[Action] Handler failed:"') && src.includes("Invalid data-params for runTool") && src.includes("JSON.parse(ds.params)"));
assert("i18n translates aria labels", i18nSrc.includes("[data-i18n-aria-label]") && i18nSrc.includes('el.setAttribute("aria-label", translated)'));
assert("German and English i18n dictionaries have matching non-empty keys", i18nDeKeys.length > 1000 && i18nDeKeys.length === i18nEnKeys.length && i18nKeyMismatches.length === 0 && emptyI18nValues.length === 0, [...i18nKeyMismatches, ...emptyI18nValues].join(", "));
assert("literal i18n references exist in German and English", missingI18nRefs.length === 0, missingI18nRefs.join(", "));
assert("all command descriptors are translated in German and English", commandNames.length >= 100 && missingCommandDescRefs.length === 0, missingCommandDescRefs.join(", "));
assert("topbar icon buttons expose translated aria labels", html.includes('id="wakeword-indicator"') && html.includes('data-i18n-aria-label="nav.wakeWordTooltip"') && html.includes('id="notif-bell-btn"') && html.includes('data-i18n-aria-label="notifications.title"') && html.includes('data-i18n-aria-label="nav.memory"') && html.includes('data-i18n-aria-label="nav.settings"'));
assert("notification center dialog and close control are localized", html.includes('id="notif-center" role="dialog"') && html.includes('data-i18n-aria-label="notifications.title"') && html.includes('class="notif-center-close"') && html.includes('data-i18n-aria-label="common.close"'));
assert("notification center synchronizes expanded, hidden, and focus state", html.includes('id="notif-center" role="dialog"') && html.includes('aria-hidden="true"') && html.includes('id="notif-bell-btn"') && html.includes('aria-expanded="false"') && html.includes('aria-controls="notif-center"') && modalsSrc.includes("function ensureNotifCenterA11y") && modalsSrc.includes("function setNotifCenterOpen") && modalsSrc.includes('panel.setAttribute("aria-hidden", "false")') && modalsSrc.includes('btn.setAttribute("aria-expanded", "true")') && modalsSrc.includes('btn.setAttribute("aria-controls", "notif-center")') && modalsSrc.includes("trapFocusIn(panel, event)") && modalsSrc.includes("restoreFocus(_notifCenterRestoreFocusEl)") && modalsSrc.includes('panel.setAttribute("tabindex", "-1")'));
assert("hidden attach button is named for accessibility", html.includes('id="attach-btn"') && html.includes('data-i18n-aria-label="chat.attachFile"') && i18nDe.includes('"chat.attachFile"') && i18nEn.includes('"chat.attachFile"'));
assert("voice orb has visible keyboard focus styling", overridesCss.includes("#voice-orb-canvas:focus-visible") && overridesCss.includes("outline-offset: 6px") && overridesCss.includes(".talk-to-lexa-btn:focus-visible"));
assert("voice entry controls expose active pressed state and localized action labels", src.includes("function _updateOrbActionA11y") && src.includes('control.setAttribute("aria-pressed"') && src.includes('talkBtn.classList.toggle("listening", isActive)') && src.includes('"app.orbClickEnd"') && src.includes('"chat.endConversation"'));
assert("talk-to-lexa button render keeps structured localized label", chatSrc.includes("function renderTalkButton") && chatSrc.includes("data-voice-entry-label") && chatSrc.includes('data-i18n="') && chatSrc.includes("_updateOrbActionA11y(active)"));
assert("classic voice recording keeps orb pressed state in sync", chatSrc.includes("_updateOrbActionA11y(true)") && chatSrc.includes("_updateOrbActionA11y(false)"));
assert("orb click checks realtime boundary before starting classic voice", src.includes("async function _primeOrbRealtimeBoundary") && src.includes("window.lexa?.voiceRealtimeStart") && src.includes("Classic voice active:"));
assert("orb click does not start classic recording after realtime starts", src.includes("function _voiceRealtimeStarted") && src.includes("_orbRealtimeVoiceActive = true") && src.includes("_updateOrbActionA11y(true)") && src.includes("if (realtimeStarted) return;"));
assert("orb click can stop an active realtime voice session", src.includes("async function stopOrbConversation") && src.includes("window.lexa?.voiceRealtimeStop") && src.includes("_orbRealtimeVoiceActive = false") && src.includes("_updateOrbActionA11y(false)"));
assert("orb status labels cascaded fallback path clearly", src.includes("function _voicePathLabel") && src.includes('return "STT -> AI -> TTS"'));
assert("wake word events update shared voice status bar", src.includes("function _voiceStatusBarEventUpdate") && src.includes('provider: "Wake Word"') && src.includes('provider: "Conversation"'));
assert("wake word timeout gives visible command guidance", src.includes('case "wake_timeout"') && src.includes('"app.voiceWakeNoCommand"') && i18nDe.includes('"app.voiceWakeNoCommand"') && i18nEn.includes('"app.voiceWakeNoCommand"'));
assert("wake word status bar mirrors command response and hides speaking chrome", src.includes('provider: "STT -> AI"') && src.includes('provider: evt.tts_handled ? _voiceSpeechProviderLabel() : "AI"') && src.includes("_voiceSpeakingResponseLabel()") && src.includes('state: "speaking"') && src.includes('safeState === "speaking"') && src.includes("VoiceStatusBar.hide()"));
assert("chat TTS shares the main orb speaking state", src.includes("window.setOrbConversationState = _setOrbConversationState") && src.includes("orbContainer.dataset.convState = safeState") && chatSrc.includes('voiceSetOrbConversationState("speaking")') && chatSrc.includes("voiceSetOrbConversationState(null)"));
assert("voice status bar markup carries the styling class", html.includes('id="voice-status-bar" class="voice-status-bar hidden"') && html.includes('class="voice-status-left"') && html.includes('class="voice-status-center"') && html.includes('class="voice-status-right"'));
assert("voice status bar announces atomic live state", html.includes('role="status"') && html.includes('aria-live="polite"') && html.includes('aria-atomic="true"') && src.includes("_refreshA11yLabel()") && src.includes('setAttribute("aria-label"'));
assert("voice status bar canvas has stable dimensions", html.includes('id="voice-level-meter" width="96" height="24"') && voiceCss.includes("#voice-level-meter") && voiceCss.includes("width: 72px"));
assert("voice level meter is hidden from assistive tech", html.includes('id="voice-level-meter" width="96" height="24" aria-hidden="true"'));
assert("voice status bar uses product-style compact chrome", voiceCss.includes("rgba(10, 10, 17, 0.82)") && voiceCss.includes("border-radius: 10px") && voiceCss.includes("font-style: normal"));
assert("voice status bar is centered as an overlay", voiceCss.includes("position: fixed") && voiceCss.includes("left: 50%") && voiceCss.includes("transform: translateX(-50%)"));
assert("voice status labels avoid emoji debug copy", src.includes('listening: _voiceText("app.voiceStateListening"') && src.includes('processing: _voiceText("app.voiceStateProcessing"') && src.includes('speaking: _voiceText("app.voiceStateSpeaking"') && !src.includes('listening: "\\uD83C\\uDFA4'));
assert("voice status visible copy uses i18n keys", src.includes("function _voiceText") && src.includes('t(key, values)') && src.includes('"app.voiceRealtimeReady"') && src.includes('"app.voiceClassicFallback"') && i18nDe.includes('"app.voiceClassicFallback"') && i18nEn.includes('"app.voiceClassicFallback"'));
assert("voice status bar clips long visible text with inspectable titles", src.includes("function _voiceStatusTextClip") && src.includes("function _voiceStatusSetText") && src.includes('el.title = text') && src.includes('[truncated]'));
assert("voice status bar normalizes unknown states", src.includes("function _voiceStatusState") && src.includes('"listening", "processing", "speaking", "error", "bargein"') && src.includes("const safeState = _voiceStatusState(state)"));
assert("voice status transcript/provider use bounded setters", src.includes("_voiceStatusSetText(this._transcript, text, 140)") && src.includes("_voiceStatusSetText(this._provider, name, 48)") && src.includes("Math.round(Number(ms))"));
assert("voice level meter avoids black debug blocks", src.includes("Math.max(0, Math.min(1, Number(vol) || 0))") && src.includes("drawRoundRect(0.5, 5.5") && src.includes("clearVolume()") && src.includes("volumeOnly") && !src.includes('ctx.fillStyle = "rgba(255,255,255,0.03)"'));
assert("compact orb remains legible in active chat", overridesCss.includes("clamp(128px, 8vw, 164px)") && overridesCss.includes("drop-shadow(0 0 18px"));
assert("orb renderer uses brighter readable base material", orb3dSrc.includes("0x4c2a78") && orb3dSrc.includes("0x120326") && orb3dSrc.includes("0.42"));
assert("speaking orb has visible movement beyond glow", orb3dSrc.includes("stateSyntheticVolume") && orb3dSrc.includes('convState === "speaking"') && orb3dSrc.includes("this.group.rotation.z") && overridesCss.includes("transform: scale(1.12)"));
assert("chat input can shrink without overlapping action buttons", overridesCss.includes("#chat-input") && overridesCss.includes("min-width: 0") && overridesCss.includes(".sleek-actions-right") && overridesCss.includes("flex-shrink: 0"));
assert("mobile top nav hides low-priority text before overflow", overridesCss.includes(".top-nav-pill .nav-time") && overridesCss.includes("display: none") && overridesCss.includes("max-width: 86px"));
assert("mobile chat input keeps stable icon button dimensions", overridesCss.includes(".send-btn.sleek-icon-btn") && overridesCss.includes("width: 34px") && overridesCss.includes("height: 34px"));
assert("open chat layout reduces vertical dead space", overridesCss.includes(".chat-container:has(.voice-orb-container.compact) .chat-messages") && overridesCss.includes("padding-top: 10px") && overridesCss.includes("padding: 18px 0 8px"));
assert("chat input CSS is textarea-ready", overridesCss.includes("max-height: 160px") && overridesCss.includes("resize: none") && overridesCss.includes("overflow-y: hidden") && overridesCss.includes("align-items: flex-end"));
assert("chat composer only sticks in open transcript mode", overridesCss.includes(".chat-input-area.sleek-input-area") && overridesCss.includes("position: relative") && overridesCss.includes(".chat-container:has(.voice-orb-container.compact) .chat-input-area.sleek-input-area") && overridesCss.includes("position: sticky"));
assert("conversation starters use inline SVG icons instead of emoji text", chatSrc.includes("function starterIconSvg") && chatSrc.includes("iconEl.innerHTML = starterIconSvg(s.icon)") && !chatSrc.includes("iconEl.textContent = s.icon"));
assert("conversation starters are native named buttons", chatSrc.includes('card.type = "button"') && chatSrc.includes('card.setAttribute("aria-label", `${s.title}: ${s.text}`)'));
assert("conversation sidebar rows are keyboard accessible", chatSrc.includes("function bindKeyboardAction") && chatSrc.includes('el.setAttribute("role", "button")') && chatSrc.includes('el.setAttribute("tabindex", "0")') && chatSrc.includes('item.setAttribute("aria-current"') && chatSrc.includes("bindKeyboardAction(item, () => switchConversation(c.id)") && chatSrc.includes("chat.openConversationLabel"));
assert("conversation action buttons are named and focus-visible", chatSrc.includes('exportBtn.type = "button"') && chatSrc.includes("chat.exportConversationLabel") && chatSrc.includes('delBtn.type = "button"') && chatSrc.includes("chat.deleteConversationLabel") && overridesCss.includes(".conv-item:focus-visible") && overridesCss.includes(".conv-item:focus-within .conv-actions"));
assert("conversation starter cards have calmer product styling", overridesCss.includes(".starter-icon svg") && overridesCss.includes("min-height: 58px") && overridesCss.includes("box-shadow: none") && overridesCss.includes("letter-spacing: 0"));
assert("memory cards are keyboard accessible and named", memorySrc.includes("function bindMemoryCardAction") && memorySrc.includes('el.setAttribute("role", "button")') && memorySrc.includes('el.setAttribute("tabindex", "0")') && memorySrc.includes("memory.openNoteLabel") && memorySrc.includes("memory.useSnippetLabel") && memorySrc.includes("memory.copyClipboardLabel"));
assert("memory destructive and toggle controls expose state", memorySrc.includes('delBtn.type = "button"') && memorySrc.includes("memory.deleteNoteLabel") && memorySrc.includes('deleteBtn.type = "button"') && memorySrc.includes("memory.deleteSnippetLabel") && memorySrc.includes('toggle.setAttribute("aria-pressed"') && memorySrc.includes("memory.toggleRoutineLabel"));
assert("memory card focus reveals nested actions", overridesCss.includes('.note-card[role="button"]:focus-visible') && overridesCss.includes(".note-card:focus-within .note-delete-btn") && overridesCss.includes(".snippet-card:focus-within .snippet-delete") && overridesCss.includes(".routine-toggle:focus-visible"));
assert("command list cards are keyboard accessible", commandsSrc.includes("function bindCommandItemAction") && commandsSrc.includes('el.setAttribute("role", "button")') && commandsSrc.includes('el.setAttribute("tabindex", "0")') && commandsSrc.includes("bindCommandItemAction(item") && commandsSrc.includes("cmd.insertCommandLabel"));
assert("command copy buttons are named and focus-visible", commandsSrc.includes('copyBtn.type = "button"') && commandsSrc.includes('const copyLabel = t("cmd.copyCommandLabel"') && commandsSrc.includes("copyBtn.title = copyLabel") && overridesCss.includes(".cmd-item:focus-visible") && overridesCss.includes(".cmd-item:focus-within .cmd-copy-btn"));
assert("command search input is named", commandsSrc.includes('id="cmd-search"') && commandsSrc.includes('aria-label="${escapeHtml(t("commands.search"))}"'));
assert("todo action buttons expose stable labels", productivitySrc.includes('checkBtn.type = "button"') && productivitySrc.includes("productivity.completeTodoLabel") && productivitySrc.includes('progressBtn.type = "button"') && productivitySrc.includes("productivity.markTodoInProgressLabel") && productivitySrc.includes('delBtn.type = "button"') && productivitySrc.includes("productivity.deleteTodoLabel"));
assert("todo titles can be edited from keyboard", productivitySrc.includes('titleEl.setAttribute("role", "button")') && productivitySrc.includes('titleEl.setAttribute("tabindex", "0")') && productivitySrc.includes("productivity.editTodoLabel") && productivitySrc.includes('event.key === "Enter" || event.key === " "') && overridesCss.includes('.todo-title[role="button"]:focus-visible'));
assert("habit buttons expose stable labels after template render", productivitySrc.includes('logBtn.type = "button"') && productivitySrc.includes("productivity.logHabitLabel") && productivitySrc.includes('deleteBtn.type = "button"') && productivitySrc.includes("productivity.deleteHabitLabel"));
assert("productivity export date follows active locale", productivitySrc.includes("function productivityLocale") && productivitySrc.includes("function productivityFormatDate") && productivitySrc.includes("toLocaleDateString(productivityLocale())") && productivitySrc.includes("productivityFormatDate()") && !productivitySrc.includes('toLocaleDateString("de-DE")'));
assert("pomodoro start and stop controls are localized", productivitySrc.includes('startBtn.textContent = t("productivity.startBtn")') && productivitySrc.includes('stopBtn.textContent = t("productivity.stopBtn")') && productivitySrc.includes('startBtn.setAttribute("aria-label", t("productivity.startBtn"))') && productivitySrc.includes('stopBtn.setAttribute("aria-label", t("productivity.stopBtn"))') && i18nDe.includes('"productivity.stopBtn"') && i18nEn.includes('"productivity.stopBtn"') && !productivitySrc.includes('textContent = "Start"') && !productivitySrc.includes('textContent = "Stop"'));
assert("productivity dynamic buttons set explicit type", productivityButtonsWithoutType.length === 0, productivityButtonsWithoutType.map((m) => `offset ${m.index}`).join(", "));
assert("all dynamic frontend buttons set explicit type", dynamicButtonsWithoutType.length === 0, dynamicButtonsWithoutType.join(", "));
assert("all static/template frontend buttons set explicit type", staticButtonsWithoutType.length === 0, staticButtonsWithoutType.join(", "));
assert("all static/template icon buttons expose an accessible name", staticIconButtonsWithoutName.length === 0, staticIconButtonsWithoutName.join(", "));
assert("all static/template form fields expose an accessible name", staticFormFieldsWithoutName.length === 0, staticFormFieldsWithoutName.join(", "));
assert("core modals expose dialog semantics and named close buttons", modalsSrc.includes('panel.setAttribute("role", "dialog")') && modalsSrc.includes('panel.setAttribute("aria-modal", "true")') && modalsSrc.includes('closeBtn.setAttribute("aria-label", t("common.close"))') && modalsSrc.includes('shortcuts-panel" role="dialog"') && memorySrc.includes('panel.setAttribute("role", "dialog")') && memorySrc.includes('panel.setAttribute("aria-modal", "true")') && memorySrc.includes("notes.editNote") && productivitySrc.includes('panel.setAttribute("role", "dialog")') && productivitySrc.includes('panel.setAttribute("aria-modal", "true")') && productivitySrc.includes("productivity.newTodoTitle") && productivitySrc.includes("productivity.startPomodoroTitle") && productivitySrc.includes("productivity.newHabitTitle") && i18nDe.includes('"notes.editNote"') && i18nEn.includes('"notes.editNote"'));
assert("core modal overlays trap tab focus", modalsSrc.includes("function getFocusableElements") && modalsSrc.includes("function trapFocusIn") && modalsSrc.includes("trapFocusIn(panel, e)") && modalsSrc.includes('e.key === "Tab"') && modalsSrc.includes("getClientRects().length > 0"));
assert("hero typography avoids viewport-scaled type and negative tracking", !overridesCss.includes("font-size: clamp") && !overridesCss.includes("letter-spacing: -"));
assert("ambient start view avoids landing-page hero treatment", overridesCss.includes(".greeting-title") && overridesCss.includes("font-size: 30px") && overridesCss.includes("-webkit-text-fill-color: currentColor") && overridesCss.includes(".talk-to-lexa-btn") && overridesCss.includes("width: 180px") && overridesCss.includes("height: 180px") && overridesCss.includes("box-shadow: none"));
assert("navigation chrome uses calmer product styling", overridesCss.includes(".sidebar-btn.active") && overridesCss.includes("background: rgba(91, 124, 250, 0.12)") && overridesCss.includes(".titlebar") && overridesCss.includes("background: rgba(9, 9, 16, 0.96)"));
assert("transient notifications avoid glow-heavy demo chrome", overridesCss.includes(".toast {") && overridesCss.includes("box-shadow: 0 18px 42px rgba(0, 0, 0, 0.3)") && overridesCss.includes(".notif-center") && overridesCss.includes("box-shadow: 0 18px 46px rgba(0, 0, 0, 0.34)"));
assert("chat transcript bubbles use calmer professional surfaces", overridesCss.includes(".system-message .msg-text") && overridesCss.includes("background: rgba(255, 255, 255, 0.032)") && overridesCss.includes(".user-message .msg-text") && overridesCss.includes("background: rgba(91, 124, 250, 0.12)") && overridesCss.includes("backdrop-filter: none"));
assert("chat suggestion chips avoid glow-heavy demo styling", overridesCss.includes(".suggestion-chip") && overridesCss.includes("border-radius: 8px") && overridesCss.includes("transform: none") && overridesCss.includes("box-shadow: none"));
assert("dashboard widgets avoid hero-glow demo styling", overridesCss.includes(".dash-widget-greeting::before") && overridesCss.includes("display: none") && overridesCss.includes(".dash-clock") && overridesCss.includes("-webkit-text-fill-color: currentColor") && overridesCss.includes(".dash-chat-btn:hover") && overridesCss.includes("box-shadow: none"));
assert("system tool cards use dense professional rows", overridesCss.includes(".tool-card") && overridesCss.includes("grid-template-columns: 36px minmax(0, 1fr)") && overridesCss.includes("min-height: 72px") && overridesCss.includes(".tool-icon") && overridesCss.includes("font-size: 15px"));
assert("dashboard greeting avoids boss/demo address", !html.includes("Guten Tag, Chef") && !i18nDe.includes("Chef!") && !i18nEn.includes("Boss!"));
assert("ambient canvas is initialized as a real animated surface", html.includes('id="lexa-ambient-canvas"') && src.includes("function initLexaAmbientCanvas") && src.includes("window.__lexaAmbientDebug") && overridesCss.includes(".lexa-ambient-canvas"));
assert("global command palette exposes dialog and listbox semantics", modalsSrc.includes('class="cmd-palette" role="dialog" aria-modal="true"') && modalsSrc.includes('aria-label="${escapeHtml(t("palette.title"))}"') && modalsSrc.includes('aria-controls="palette-results"') && modalsSrc.includes('role="listbox"') && modalsSrc.includes('el.setAttribute("role", "option")') && modalsSrc.includes('el.setAttribute("aria-selected"') && modalsSrc.includes('aria-activedescendant') && i18nDe.includes('"palette.title"') && i18nEn.includes('"palette.title"'));
assert("global command palette restores and traps focus", modalsSrc.includes("let _paletteRestoreFocusEl = null") && modalsSrc.includes("function restoreFocus") && modalsSrc.includes("_paletteRestoreFocusEl = active") && modalsSrc.includes("closePalette(options = {})") && modalsSrc.includes('options.restoreFocus !== false') && modalsSrc.includes('removeAttribute("aria-activedescendant")') && modalsSrc.includes("closePalette({ restoreFocus: false })") && modalsSrc.includes("trapFocusIn(paletteEl, e)"));
assert("shortcuts overlay restores and traps focus on dismiss", modalsSrc.includes("const restoreFocusEl = document.activeElement") && modalsSrc.includes("const closeShortcuts = () =>") && modalsSrc.includes("restoreFocus(restoreFocusEl)") && modalsSrc.includes('addEventListener("click", closeShortcuts)') && modalsSrc.includes("trapFocusIn(overlay, e)") && modalsSrc.includes('document.getElementById("shortcuts-close-btn")?.focus()'));
assert("chat composer exposes a command palette", html.includes('id="composer-command-btn"') && html.includes('id="composer-command-palette"') && chatSrc.includes("LEXA_COMPOSER_COMMANDS") && chatSrc.includes("handleComposerCommandKeydown") && src.includes("setupComposerCommandPalette"));
assert("composer command palette exposes listbox active-descendant state", html.includes('id="composer-command-palette"') && html.includes('role="listbox"') && html.includes('aria-hidden="true"') && html.includes('id="composer-command-btn"') && html.includes('aria-haspopup="listbox"') && html.includes('id="chat-input"') && html.includes('aria-controls="composer-command-palette"') && html.includes('aria-expanded="false"') && html.includes('aria-autocomplete="list"') && chatSrc.includes("function updateComposerCommandActiveDescendant") && chatSrc.includes('chatInput.setAttribute("aria-activedescendant"') && chatSrc.includes("composer-command-option-${command.id}") && chatSrc.includes('row.setAttribute("aria-label", `${label}: ${desc}`)') && chatSrc.includes('aria-hidden="true">${composerCommandIconSvg') && chatSrc.includes('button.setAttribute("aria-haspopup", "listbox")') && chatSrc.includes('e.key !== "ArrowDown"') && overridesCss.includes(".composer-command-item:focus-visible"));
assert("composer command palette copy is localized", html.includes('data-i18n-aria-label="composer.paletteLabel"') && html.includes('data-i18n-aria-label="composer.buttonLabel"') && html.includes('data-i18n-title="composer.buttonTitle"') && html.includes('data-i18n-aria-label="chat.enterMessage"') && chatSrc.includes("function composerCommandText") && chatSrc.includes("composerCommandPrefix(command)") && chatSrc.includes('t("composer.empty")') && chatSrc.includes('t("composer.readyToast", { label })') && i18nDe.includes('"composer.improve.prefix"') && i18nEn.includes('"composer.improve.prefix"') && i18nDe.includes('"composer.readyToast"') && i18nEn.includes('"composer.readyToast"'));
assert("composer command palette has professional product styling", overridesCss.includes(".composer-command-palette") && overridesCss.includes(".composer-command-item") && overridesCss.includes("grid-template-columns: 34px minmax(0, 1fr) auto"));
assert("global search overlay is named as a dialog", chatSrc.includes('class="search-panel" role="dialog" aria-modal="true"') && chatSrc.includes('aria-label="${escapeHtml(t("nav.searchTooltip"))}"') && chatSrc.includes('id="search-input"') && chatSrc.includes('aria-label="${escapeHtml(t("chat.searchPlaceholder"))}"') && chatSrc.includes('id="search-close-btn"') && chatSrc.includes('aria-label="${escapeHtml(t("common.close"))}"'));
assert("global search restores focus, traps focus, and has keyboard results", chatSrc.includes("let searchRestoreFocusEl = null") && chatSrc.includes("function restoreSearchFocus") && chatSrc.includes("function trapSearchFocus") && chatSrc.includes("searchRestoreFocusEl = active") && chatSrc.includes("closeSearchOverlay(options = {})") && chatSrc.includes("trapSearchFocus(overlay, e)") && chatSrc.includes('item.setAttribute("role", "button")') && chatSrc.includes('item.setAttribute("tabindex", "0")') && chatSrc.includes('event.key === "Enter" || event.key === " "') && overridesCss.includes(".search-item:focus-visible"));
assert("notification center rows use denser message styling", overridesCss.includes(".notif-item") && overridesCss.includes("grid-template-columns: 34px minmax(0, 1fr) auto") && overridesCss.includes(".notif-item-time"));
assert("app-wide UI QA pass bounds operational views", overridesCss.includes("App-wide UI QA pass") && overridesCss.includes(".tool-view > .view-title") && overridesCss.includes("width: min(100%, 1120px)") && overridesCss.includes("#personal-os-view > .pos-shell"));
assert("section headers and action rows wrap instead of overflowing", overridesCss.includes(".section-header") && overridesCss.includes("flex-wrap: wrap") && overridesCss.includes(".flex-row-nowrap") && overridesCss.includes("justify-content: flex-end"));
assert("settings rows use responsive grid layout", overridesCss.includes(".setting-item") && overridesCss.includes("grid-template-columns: minmax(0, 1fr) max-content") && overridesCss.includes("@media (max-width: 720px)") && overridesCss.includes("grid-template-columns: 1fr"));
assert("settings controls are bounded and focus-visible", overridesCss.includes(".settings-select,") && overridesCss.includes("max-width: min(340px, 44vw)") && overridesCss.includes("box-shadow: 0 0 0 3px rgba(139, 146, 255, 0.12)"));
assert("accent swatches are named pressed-state controls", html.includes('class="accent-dot active') && html.includes('aria-pressed="true"') && html.includes('data-i18n-aria-label="settings.purple"') && html.includes('data-i18n-aria-label="settings.gold"') && settingsSrc.includes('d.setAttribute("aria-pressed"'));
assert("settings and productivity selects expose localized labels", html.includes('id="todo-filter"') && html.includes('data-i18n-aria-label="productivity.todoFilter"') && html.includes('id="model-select"') && html.includes('data-i18n-aria-label="settings.aiModel"') && html.includes('id="el-voice-select"') && html.includes('data-i18n-aria-label="settings.voice"') && html.includes('id="stt-model-select"') && html.includes('data-i18n-aria-label="settings.sttModel"') && i18nDe.includes('"productivity.todoFilter"') && i18nEn.includes('"productivity.todoFilter"'));
assert("global empty and modal states share calmer product chrome", overridesCss.includes(".empty-state,") && overridesCss.includes(".search-panel,") && overridesCss.includes("box-shadow: 0 24px 64px rgba(0, 0, 0, 0.42)"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
