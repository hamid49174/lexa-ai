/* App action delegation helpers. Classic script loaded before app.js. */


function _isKeyboardActionTarget(el) {
  if (!el?.dataset?.action) return false;
  const tag = String(el.tagName || "").toUpperCase();
  if (["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA", "OPTION"].includes(tag)) return false;
  return el.getAttribute("role") === "button" || el.tabIndex >= 0;
}

function _keyboardActionShouldActivate(e) {
  return e.key === "Enter" || e.key === " ";
}

function _isNativeInteractiveAction(el) {
  const tag = String(el?.tagName || "").toUpperCase();
  return ["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA", "OPTION", "LABEL"].includes(tag);
}

function _prepareActionElement(el) {
  if (!el?.dataset?.action || _isNativeInteractiveAction(el)) return;
  if (!el.hasAttribute("role")) el.setAttribute("role", "button");
  if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
}

function _setupActionAccessibility(root = document) {
  root.querySelectorAll?.("[data-action]").forEach(_prepareActionElement);
}

function _safeDispatch(el, ds, value) {
  try {
    _dispatch(el, ds, value);
  } catch (e) {
    const action = ds?.action || "unknown";
    console.warn("[Action] Handler failed:", action, e.message || e);
    if (typeof showToast === "function") {
      showToast(t("toast.executionError"), "error", 3000);
    }
  }
}

function _initDelegation() {
  _setupActionAccessibility();
  const actionObserver = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => {
        if (!(node instanceof Element)) return;
        _prepareActionElement(node);
        _setupActionAccessibility(node);
      });
    }
  });
  actionObserver.observe(document.body, { childList: true, subtree: true });

  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const tag = String(el.tagName || "").toUpperCase();
    if (["INPUT", "SELECT", "TEXTAREA", "OPTION"].includes(tag)) return;
    _safeDispatch(el, el.dataset, null);
  });
  document.addEventListener("keydown", (e) => {
    if (!_keyboardActionShouldActivate(e)) return;
    const el = e.target.closest("[data-action]");
    if (!_isKeyboardActionTarget(el)) return;
    e.preventDefault();
    _safeDispatch(el, el.dataset, null);
  });
  document.addEventListener("change", (e) => {
    const el = e.target;
    if (!el.dataset || !el.dataset.action) return;
    _safeDispatch(el, el.dataset, el.type === "checkbox" ? el.checked : el.value);
  });
  document.addEventListener("input", (e) => {
    const el = e.target;
    if (!el.dataset || !el.dataset.action) return;
    _safeDispatch(el, el.dataset, el.value);
  });

  window.addEventListener("beforeunload", () => actionObserver.disconnect(), { once: true });
}

function _dispatch(el, ds, value) {
  const a = ds.action;
  const arg = ds.arg;
  const cmd = ds.cmd;
  switch (a) {
    // Window controls (through preload bridge)
    case "lexa-minimize": window.lexa.minimize(); break;
    case "lexa-maximize": window.lexa.maximize(); break;
    case "lexa-close": window.lexa.close(); break;
    // Parameterized tool/action calls
    case "runTool": {
      let params = {};
      if (ds.params) {
        try {
          params = JSON.parse(ds.params);
        } catch (e) {
          console.warn("[Action] Invalid data-params for runTool:", e.message || e);
          showToast(t("toast.executionError"), "error", 3000);
          return;
        }
      }
      runTool(cmd, params, ds.confirm === "true");
      break;
    }
    case "quickAction": quickAction(cmd, ds.prompt, ds.param); break;
    case "switchView": switchView(arg || ds.view); break;
    case "toggleNavMenu": toggleNavMenu(); break;
    case "toggleChatView": toggleChatView(); break;
    case "windowLayoutAction": windowLayoutAction(arg); break;
    case "gitPullPushAction": gitPullPushAction(arg); break;
    case "dockerStartStopAction": dockerStartStopAction(arg); break;
    case "setAccentColor": setAccentColor(arg); break;
    case "toggleWakeWord": toggleWakeWord(); break;
    // Value-passing handlers (from change / input events)
    case "changeAiModel": changeAiModel(value); break;
    case "changeSttModel": changeSttModel(value); break;
    case "changeSttEngine": changeSttEngine(value); break;
    case "setDeepgramKey": setDeepgramKeyAction(); break;
    case "deleteDeepgramKey": deleteDeepgramKeyAction(); break;
    case "setCartesiaKey": setCartesiaKeyAction(); break;
    case "deleteCartesiaKey": deleteCartesiaKeyAction(); break;
    case "setCartesiaVoice": setCartesiaVoiceAction(); break;
    case "elevenlabsKeyAction": elevenlabsKeyAction(); break;
    case "elevenlabsToggleAction": elevenlabsToggleAction(value); break;
    case "elevenlabsVoiceChange": elevenlabsVoiceChange(value); break;
    case "elevenlabsModelChange": elevenlabsModelChange(value); break;
    case "elevenlabsSettingsChange": elevenlabsSettingsChange(); break;
    case "setFontSize": setFontSize(value); break;
    case "toggleTheme": toggleTheme(value); break;
    case "changeLanguage": changeLanguage(value); break;
    case "applySendModeToggle": applySendModeToggle(value); break;
    case "toggleAutostart": toggleAutostart(value); break;
    case "toggleNotifications": toggleNotifications(value); break;
    case "filterTodosLocal": filterTodosLocal(value); break;
    case "filterNotes": filterNotes(value); break;
    case "filterCommands": filterCommands(value); break;
    case "visionScreenshot": triggerScreenshotAnalysis(); break;
    // Chat inline-handler replacements (CSP-safe)
    case "copy-code": copyCode(el); break;
    case "copy-message": copyMessage(el); break;
    case "confirm-action": confirmAction(el, el.dataset.payload); break;
    case "deny-action": denyAction(el); break;
    // Zero-arg functions — dispatch by name via window global
    default: {
      const fn = window[a];
      if (typeof fn === "function") fn();
    }
  }
}
