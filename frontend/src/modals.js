/* ════════════════════════════════════════════════
   LEXA AI — Modals & UI Helpers
   Extracted from app.js for modularity.
   Contains: showInputModal, showToast, notification center,
   shortcuts overlay, command palette, onboarding, help.
   ════════════════════════════════════════════════ */

// ── UI STATE HELPERS ─────────────────────────────
function createLoadingState(text = t("common.loading")) {
  const div = document.createElement("div");
  div.className = "loading-state";
  div.innerHTML = `<div class="loading-spinner"></div><div class="loading-text">${escapeHtml(text)}</div>`;
  return div;
}

function createErrorState(message, retryFn) {
  const div = document.createElement("div");
  div.className = "error-state";
  const icon = document.createElement("div");
  icon.className = "error-icon";
  icon.textContent = "!";
  div.appendChild(icon);
  const msg = document.createElement("div");
  msg.className = "error-message";
  msg.textContent = message;
  div.appendChild(msg);
  if (retryFn) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "error-retry-btn";
    btn.textContent = t("common.retry");
    btn.addEventListener("click", retryFn);
    div.appendChild(btn);
  }
  return div;
}

function createEmptyState(icon, title, description, actionLabel, actionFn) {
  const div = document.createElement("div");
  div.className = "empty-state";
  const ic = document.createElement("div");
  ic.className = "empty-icon";
  ic.textContent = icon;
  div.appendChild(ic);
  const t = document.createElement("div");
  t.className = "empty-title";
  t.textContent = title;
  div.appendChild(t);
  if (description) {
    const d = document.createElement("div");
    d.className = "empty-desc";
    d.textContent = description;
    div.appendChild(d);
  }
  if (actionLabel && actionFn) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "empty-action-btn";
    btn.textContent = actionLabel;
    btn.addEventListener("click", actionFn);
    div.appendChild(btn);
  }
  return div;
}

function createSkeletonCards(count = 3) {
  const wrap = document.createElement("div");
  for (let i = 0; i < count; i++) {
    const card = document.createElement("div");
    card.className = "skeleton skeleton-card";
    wrap.appendChild(card);
  }
  return wrap;
}

// ── NOTIFICATION CENTER ───────────────────────────
const _notifHistory = [];
let _notifCenterOpen = false;
let _unreadNotifs = 0;
let _notifCenterRestoreFocusEl = null;
let _notifCenterPositionBound = false;

function positionNotifCenter(panel, anchor) {
  if (!panel) return;
  const viewportWidth = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
  const viewportHeight = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
  const compact = viewportWidth <= 560;
  const shortViewport = viewportHeight <= 420;
  const hasAnchor = Boolean(anchor && typeof anchor.getBoundingClientRect === "function");
  panel.classList.toggle("notif-center-compact", compact);
  panel.classList.toggle("notif-center-short", shortViewport);
  panel.classList.toggle("notif-center-anchored", hasAnchor);
}

function bindNotifCenterPositioning() {
  if (_notifCenterPositionBound) return;
  _notifCenterPositionBound = true;
  window.addEventListener("resize", () => {
    if (!_notifCenterOpen) return;
    positionNotifCenter(
      document.getElementById("notif-center"),
      document.getElementById("notif-bell-btn")
    );
  });
}

function ensureNotifCenterA11y(panel) {
  if (!panel || panel.dataset.a11yBound === "true") return;
  panel.dataset.a11yBound = "true";
  panel.setAttribute("tabindex", "-1");
  bindNotifCenterPositioning();
  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setNotifCenterOpen(false);
    }
    if (event.key === "Tab") trapFocusIn(panel, event);
  });
}

function setNotifCenterOpen(open, options = {}) {
  const panel = document.getElementById("notif-center");
  if (!panel) return;
  const btn = document.getElementById("notif-bell-btn");
  ensureNotifCenterA11y(panel);
  _notifCenterOpen = Boolean(open);
  if (_notifCenterOpen) {
    const active = document.activeElement;
    if (active && active !== document.body && !panel.contains(active)) {
      _notifCenterRestoreFocusEl = active;
    }
    positionNotifCenter(panel, btn);
    panel.classList.remove("hidden");
    panel.setAttribute("aria-hidden", "false");
    _unreadNotifs = 0;
    const badge = document.getElementById("notif-badge");
    if (badge) badge.classList.add("hidden");
    if (btn) {
      btn.classList.add("notif-bell-active");
      btn.setAttribute("aria-expanded", "true");
      btn.setAttribute("aria-controls", "notif-center");
    }
    setTimeout(() => {
      if (!_notifCenterOpen || panel.classList.contains("hidden")) return;
      const firstControl = panel.querySelector(".notif-center-close, .notif-center-clear");
      if (firstControl && typeof firstControl.focus === "function") firstControl.focus();
      else panel.focus();
    }, 0);
  } else {
    panel.classList.add("hidden");
    panel.setAttribute("aria-hidden", "true");
    if (btn) {
      btn.classList.remove("notif-bell-active");
      btn.setAttribute("aria-expanded", "false");
      btn.setAttribute("aria-controls", "notif-center");
    }
    if (options.restoreFocus !== false) restoreFocus(_notifCenterRestoreFocusEl);
    _notifCenterRestoreFocusEl = null;
  }
}

function toggleNotifCenter() {
  setNotifCenterOpen(!_notifCenterOpen);
}

function clearNotifCenter() {
  _notifHistory.length = 0;
  _unreadNotifs = 0;
  const list = document.getElementById("notif-center-list");
  if (list) {
    list.innerHTML = '<div class="notif-center-empty">' + escapeHtml(t("notifications.empty")) + '</div>';
  }
  const badge = document.getElementById("notif-badge");
  if (badge) badge.classList.add("hidden");
}

function _addToNotifCenter(message, type) {
  const now = new Date();
  const _locale = LexaI18n.getCurrentLanguage() === "en" ? "en-US" : "de-DE";
  const timeStr = now.toLocaleTimeString(_locale, { hour: "2-digit", minute: "2-digit" });
  _notifHistory.unshift({ message, type, time: timeStr });
  if (_notifHistory.length > 50) _notifHistory.pop();

  const list = document.getElementById("notif-center-list");
  if (list) {
    const emptyEl = list.querySelector(".notif-center-empty");
    if (emptyEl) emptyEl.remove();

    const item = document.createElement("div");
    item.className = `notif-item notif-item-${type}`;
    const icons = { success: "\u2713", error: "\u2717", warning: "\u26A0", info: "\u2139" };
    const icon = document.createElement("span");
    icon.className = "notif-item-icon";
    icon.textContent = icons[type] || icons.info;
    const text = document.createElement("span");
    text.className = "notif-item-text";
    text.textContent = message;
    const time = document.createElement("span");
    time.className = "notif-item-time";
    time.textContent = timeStr;
    item.appendChild(icon);
    item.appendChild(text);
    item.appendChild(time);
    list.insertBefore(item, list.firstChild);
  }

  if (!_notifCenterOpen) {
    _unreadNotifs++;
    const badge = document.getElementById("notif-badge");
    if (badge) {
      badge.textContent = _unreadNotifs > 9 ? "9+" : _unreadNotifs;
      badge.classList.remove("hidden");
    }
  }
}

// ── TOAST SYSTEM ─────────────────────────────────
function showToast(message, type = "info", duration = 3500) {
  const container = document.getElementById("toast-container");
  const icons = { success: "\u2713", error: "\u2717", warning: "\u26A0", info: "\u2139" };
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || icons.info}</span>
    <span class="toast-text">${escapeHtml(message)}</span>
  `;
  if (!container) return;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("toast-out");
    toast.addEventListener("animationend", () => toast.remove());
  }, duration);
  // Also log to notification center
  _addToNotifCenter(message, type);
}

// ── GENERIC INPUT MODAL ──────────────────────────
/**
 * Zeigt einen modalen Dialog mit beliebig vielen Eingabefeldern.
 * @param {string} title - Titel des Modals
 * @param {Array} fields - Felddefinitionen: [{id, label, type, placeholder, default, required, options, rows}]
 * @param {string} submitLabel - Text des Bestaetigungs-Buttons
 * @returns {Promise<Object|null>} - Werte oder null bei Abbruch
 */
function showInputModal(title, fields, submitLabel = "OK") {
  return new Promise((resolve) => {
    const restoreFocusEl = document.activeElement;
    const overlay = document.createElement("div");
    overlay.className = "note-modal-overlay";
    const closeInputModal = (value) => {
      overlay.remove();
      restoreFocus(restoreFocusEl);
      resolve(value);
    };

    const panel = document.createElement("div");
    panel.className = "input-modal-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-label", title);

    const header = document.createElement("div");
    header.className = "note-modal-header";
    const h3 = document.createElement("h3");
    h3.textContent = title;
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "note-modal-close";
    closeBtn.setAttribute("aria-label", t("common.close"));
    closeBtn.textContent = "\u2715";
    closeBtn.addEventListener("click", () => closeInputModal(null));
    header.appendChild(h3);
    header.appendChild(closeBtn);

    const body = document.createElement("div");
    body.className = "input-modal-body";

    const inputs = {};
    fields.forEach(field => {
      const row = document.createElement("div");
      row.className = "input-modal-row";

      const label = document.createElement("label");
      label.textContent = field.label;
      const fieldKey = field.id || field.name;
      label.htmlFor = "im-" + fieldKey;
      row.appendChild(label);

      let el;
      if (field.type === "select") {
        el = document.createElement("select");
        el.className = "input-modal-select";
        (field.options || []).forEach(opt => {
          const o = document.createElement("option");
          o.value = opt.value !== undefined ? opt.value : opt;
          o.textContent = opt.label || opt;
          if (o.value === (field.default || "")) o.selected = true;
          el.appendChild(o);
        });
      } else if (field.type === "textarea") {
        el = document.createElement("textarea");
        el.value = field.default || "";
        el.placeholder = field.placeholder || "";
        el.rows = field.rows || 4;
        el.className = "note-modal-textarea";
      } else {
        el = document.createElement("input");
        el.type = field.type || "text";
        el.value = field.default !== undefined ? String(field.default) : "";
        el.placeholder = field.placeholder || "";
        if (field.type === "number") {
          if (field.min !== undefined) el.min = field.min;
          if (field.max !== undefined) el.max = field.max;
        }
        el.className = "input-modal-input";
      }
      el.id = "im-" + fieldKey;
      inputs[fieldKey] = el;
      row.appendChild(el);
      body.appendChild(row);
    });

    const footer = document.createElement("div");
    footer.className = "note-modal-footer";

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "note-modal-cancel";
    cancelBtn.textContent = t("common.cancel");
    cancelBtn.addEventListener("click", () => closeInputModal(null));

    const submitBtn = document.createElement("button");
    submitBtn.type = "button";
    submitBtn.className = "note-modal-save";
    submitBtn.textContent = submitLabel;

    const doSubmit = () => {
      const values = {};
      let valid = true;
      fields.forEach(field => {
        const fieldKey = field.id || field.name;
        const el = inputs[fieldKey];
        let val;
        if (field.type === "number") {
          val = parseFloat(el.value);
          if (isNaN(val)) val = field.default || 0;
        } else {
          val = el.value.trim();
        }
        if (field.required && !val && val !== 0) {
          el.classList.add("input-invalid");
          valid = false;
        } else {
          el.classList.remove("input-invalid");
          values[fieldKey] = val;
        }
      });
      if (!valid) return;
      closeInputModal(values);
    };

    submitBtn.addEventListener("click", doSubmit);
    body.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && e.target.tagName !== "TEXTAREA") {
        e.preventDefault();
        doSubmit();
      }
      if (e.key === "Escape") closeInputModal(null);
    });

    footer.appendChild(cancelBtn);
    footer.appendChild(submitBtn);
    panel.appendChild(header);
    panel.appendChild(body);
    panel.appendChild(footer);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeInputModal(null);
    });
    overlay.addEventListener("keydown", (e) => {
      if (e.key === "Tab") trapFocusIn(panel, e);
    });

    setTimeout(() => {
      const first = body.querySelector("input, textarea, select");
      if (first) first.focus();
    }, 50);
  });
}

// ── KEYBOARD SHORTCUTS OVERLAY ───────────────────
function showShortcutsOverlay() {
  if (document.getElementById("shortcuts-overlay")) {
    document.getElementById("shortcuts-overlay").remove();
    return;
  }

  const restoreFocusEl = document.activeElement;
  const overlay = document.createElement("div");
  overlay.id = "shortcuts-overlay";
  overlay.className = "shortcuts-overlay";
  const closeShortcuts = () => {
    overlay.remove();
    restoreFocus(restoreFocusEl);
  };

  const shortcuts = [
    { group: t("shortcuts.groupNavigation"), items: [
      { key: "Ctrl + 1\u20139", desc: t("shortcuts.switchViews") },
      { key: "Escape",     desc: t("shortcuts.backToChat") },
      { key: "Ctrl + B",   desc: t("shortcuts.toggleSidebar") },
    ]},
    { group: t("shortcuts.groupChat"), items: [
      { key: "Ctrl + N",   desc: t("shortcuts.newConversation") },
      { key: "Ctrl + L",   desc: t("shortcuts.clearChat") },
      { key: "Ctrl + M",   desc: t("shortcuts.toggleMic") },
      { key: "Ctrl + T",         desc: t("shortcuts.quickTodo") },
      { key: "Ctrl + Shift + N", desc: t("shortcuts.quickNote") },
      { key: "Enter",            desc: t("shortcuts.sendMessage") },
      { key: "\u2191 / \u2193", desc: t("shortcuts.inputHistory") },
    ]},
    { group: t("shortcuts.groupSearchTools"), items: [
      { key: "Ctrl + F",   desc: t("shortcuts.globalSearch") },
      { key: "Ctrl + K",   desc: t("shortcuts.openCommandSearch") },
      { key: "Ctrl + P",   desc: t("shortcuts.openPalette") },
      { key: "Ctrl + /",   desc: t("shortcuts.showHideHelp") },
    ]},
  ];

  const groupsHTML = shortcuts.map(g => `
    <div class="sc-group">
      <div class="sc-group-title">${g.group}</div>
      ${g.items.map(s => `
        <div class="sc-row">
          <kbd class="sc-key">${s.key}</kbd>
          <span class="sc-desc">${s.desc}</span>
        </div>
      `).join("")}
    </div>
  `).join("");

  overlay.innerHTML = `
    <div class="shortcuts-panel" role="dialog" aria-modal="true" aria-label="${escapeHtml(t("shortcuts.title"))}">
      <div class="shortcuts-header">
        <span>${escapeHtml(t("shortcuts.title"))}</span>
        <button type="button" class="shortcuts-close" id="shortcuts-close-btn" aria-label="${escapeHtml(t("common.close"))}">&times;</button>
      </div>
      <div class="shortcuts-body">${groupsHTML}</div>
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeShortcuts(); });
  overlay.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeShortcuts();
    if (e.key === "Tab") trapFocusIn(overlay, e);
  });
  document.getElementById("shortcuts-close-btn").addEventListener("click", closeShortcuts);
  setTimeout(() => document.getElementById("shortcuts-close-btn")?.focus(), 0);
}

// ── COMMAND PALETTE (Ctrl+P) ────────────────────
let _paletteRestoreFocusEl = null;

function restoreFocus(el) {
  if (!el || !el.isConnected || typeof el.focus !== "function") return;
  try { el.focus({ preventScroll: true }); }
  catch (_) { try { el.focus(); } catch (_) {} }
}

function getFocusableElements(root) {
  return [...root.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )].filter(el => !el.disabled && !el.hidden && el.getClientRects().length > 0);
}

function trapFocusIn(root, e) {
  const items = getFocusableElements(root);
  if (!items.length) {
    e.preventDefault();
    return;
  }
  const first = items[0];
  const last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

function setupCommandPalette() {
  let paletteEl = document.getElementById("command-palette");
  if (!paletteEl) {
    paletteEl = document.createElement("div");
    paletteEl.id = "command-palette";
    paletteEl.className = "cmd-palette-overlay";
    paletteEl.innerHTML = `
      <div class="cmd-palette" role="dialog" aria-modal="true" aria-label="${escapeHtml(t("palette.title"))}">
        <input type="text" id="palette-input" class="palette-input" placeholder="${escapeHtml(t("palette.placeholder"))}" aria-label="${escapeHtml(t("palette.placeholder"))}" aria-controls="palette-results" aria-autocomplete="list" autocomplete="off">
        <div id="palette-results" class="palette-results" role="listbox" aria-label="${escapeHtml(t("palette.title"))}"></div>
      </div>
    `;
    document.body.appendChild(paletteEl);

    paletteEl.addEventListener("click", (e) => {
      if (e.target === paletteEl) closePalette();
    });
    paletteEl.addEventListener("keydown", (e) => {
      if (e.key === "Tab") trapFocusIn(paletteEl, e);
    });

    document.getElementById("palette-input").addEventListener("input", (e) => {
      renderPaletteResults(e.target.value.toLowerCase().trim());
    });

    document.getElementById("palette-input").addEventListener("keydown", (e) => {
      if (e.key === "Escape") closePalette();
      if (e.key === "Enter") {
        const first = document.querySelector(".palette-item.selected") || document.querySelector(".palette-item");
        if (first) first.click();
      }
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        navigatePalette(e.key === "ArrowDown" ? 1 : -1);
      }
    });
  }
}

function openPalette() {
  setupCommandPalette();
  const overlay = document.getElementById("command-palette");
  const active = document.activeElement;
  if (active && active !== document.body && !overlay.contains(active)) {
    _paletteRestoreFocusEl = active;
  }
  overlay.classList.add("visible");
  const input = document.getElementById("palette-input");
  input.value = "";
  input.focus();
  renderPaletteResults("");
}

function closePalette(options = {}) {
  document.getElementById("command-palette")?.classList.remove("visible");
  document.getElementById("palette-input")?.removeAttribute("aria-activedescendant");
  if (options.restoreFocus !== false) restoreFocus(_paletteRestoreFocusEl);
  _paletteRestoreFocusEl = null;
}

function navigatePalette(dir) {
  const items = [...document.querySelectorAll(".palette-item")];
  const current = items.findIndex(i => i.classList.contains("selected"));
  items.forEach(i => {
    i.classList.remove("selected");
    i.setAttribute("aria-selected", "false");
  });
  const next = Math.max(0, Math.min(items.length - 1, current + dir));
  const selected = items[next];
  if (selected) {
    selected.classList.add("selected");
    selected.setAttribute("aria-selected", "true");
    document.getElementById("palette-input")?.setAttribute("aria-activedescendant", selected.id);
    selected.scrollIntoView({ block: "nearest" });
  }
}

function renderPaletteResults(query) {
  const container = document.getElementById("palette-results");
  if (!container) return;

  // Combine views + commands
  const viewItems = VIEW_KEYS.map(v => ({
    type: "view", name: v, desc: t("modals.switchToView", { view: v }), icon: "\u{1F4CB}"
  }));
  viewItems.push(
    { type: "action", name: "help", desc: t("modals.showHelp"), icon: "\u2753", action: "showHelp()" },
    { type: "action", name: "onboarding", desc: t("modals.startOnboarding"), icon: "\u{1F44B}", action: "showOnboarding()" },
    { type: "action", name: "shortcuts", desc: t("modals.showShortcuts"), icon: "\u2328", action: "showShortcutsOverlay()" },
  );
  const cmdItems = getAllCommands().map(c => ({
    type: "cmd", name: c.name, desc: c.desc, icon: c.status === "confirm" ? "\u26A0" : "\u26A1", cat: c.cat
  }));
  const allItems = [...viewItems, ...cmdItems];

  const filtered = query
    ? allItems.filter(i => i.name.includes(query) || i.desc.toLowerCase().includes(query) || (i.cat || "").toLowerCase().includes(query))
    : allItems.slice(0, 15);

  container.innerHTML = "";

  if (filtered.length === 0) {
    document.getElementById("palette-input")?.removeAttribute("aria-activedescendant");
    container.innerHTML = '<div class="palette-empty" role="status">' + escapeHtml(t("modals.nothingFound")) + '</div>';
    return;
  }

  filtered.slice(0, 20).forEach((item, i) => {
    const el = document.createElement("div");
    el.id = `palette-item-${i}`;
    el.className = "palette-item" + (i === 0 ? " selected" : "");
    el.setAttribute("role", "option");
    el.setAttribute("aria-selected", i === 0 ? "true" : "false");
    el.setAttribute("aria-label", `${item.name}: ${item.desc}`);
    el.tabIndex = -1;
    el.innerHTML = `
      <span class="palette-icon" aria-hidden="true">${item.icon}</span>
      <div class="palette-item-info">
        <span class="palette-name">${escapeHtml(item.name)}</span>
        <span class="palette-desc">${escapeHtml(item.desc)}</span>
      </div>
      <span class="palette-type">${item.type === "view" ? "VIEW" : escapeHtml(item.cat || "CMD")}</span>
    `;
    el.addEventListener("click", () => {
      if (item.type === "view") { switchView(item.name); closePalette({ restoreFocus: false }); }
      else if (item.type === "action") { 
        const fnName = item.action.replace("()", "");
        if (typeof window[fnName] === "function") window[fnName]();
        closePalette({ restoreFocus: false });
      }
      else { insertCommand(item.name); closePalette({ restoreFocus: false }); }
    });
    container.appendChild(el);
  });
  document.getElementById("palette-input")?.setAttribute("aria-activedescendant", "palette-item-0");
}

// ── ONBOARDING WIZARD (Phase 17 + enhanced Phase 38) ────────────────
function showOnboarding() {
  if (document.getElementById("onboarding-overlay")) return;

  const overlay = document.createElement("div");
  overlay.id = "onboarding-overlay";
  overlay.className = "onboarding-overlay";

  const steps = [
    {
      icon: "\u26A1",
      title: t("onboarding.step1Title"),
      text: t("onboarding.step1Text"),
    },
    {
      icon: "\u{1F4AC}",
      title: t("onboarding.step2Title"),
      text: t("onboarding.step2Text"),
    },
    {
      icon: "\u{1F3A4}",
      title: t("onboarding.step3Title"),
      text: t("onboarding.step3Text"),
      action: async () => {
        try {
          const status = await window.lexa.voiceStatus();
          if (status.tts && status.tts.ready) {
            return { msg: t("onboarding.step3TtsReady"), type: "success" };
          } else {
            return { msg: t("onboarding.step3TtsNotConfigured"), type: "warning" };
          }
        } catch (e) {
          return { msg: t("onboarding.step3VoiceCheckFailed"), type: "warning" };
        }
      },
    },
    {
      icon: "\u{1F916}",
      title: t("onboarding.step4Title"),
      text: t("onboarding.step4Text"),
      action: async () => {
        try {
          const status = await window.lexa.aiStatus();
          const providers = [
            ["groq", "Groq"],
            ["openai", "OpenAI"],
            ["gemini", "Gemini"],
          ];
          const activeCloud = providers.find(([key]) => status[key]?.available);
          if (activeCloud) {
            const [key, label] = activeCloud;
            return { msg: t("onboarding.step4ProviderConnected", { provider: label, model: status[key].model_name || status[key].model }), type: "success" };
          } else {
            return { msg: t("onboarding.step4NoProvider"), type: "error" };
          }
        } catch (e) {
          return { msg: t("onboarding.step4CheckFailed"), type: "warning" };
        }
      },
    },
    {
      icon: "\u2328\uFE0F",
      title: t("onboarding.step5Title"),
      text: t("onboarding.step5Text"),
    },
    {
      icon: "\u{1F3A8}",
      title: t("onboarding.step6Title"),
      text: t("onboarding.step6Text"),
    },
  ];

  let currentStep = 0;

  function renderStep() {
    const s = steps[currentStep];
    const isLast = currentStep === steps.length - 1;
    const isFirst = currentStep === 0;

    overlay.innerHTML = "";
    const card = document.createElement("div");
    card.className = "onboarding-card";

    // Build step content
    const iconDiv = document.createElement("div");
    iconDiv.className = "onboarding-icon";
    iconDiv.textContent = s.icon;
    card.appendChild(iconDiv);

    const titleDiv = document.createElement("div");
    titleDiv.className = "onboarding-title";
    titleDiv.textContent = s.title;
    card.appendChild(titleDiv);

    const textDiv = document.createElement("div");
    textDiv.className = "onboarding-text";
    textDiv.textContent = s.text;
    card.appendChild(textDiv);

    // Status result area (for async check steps)
    const resultDiv = document.createElement("div");
    resultDiv.className = "onboarding-result hidden";
    card.appendChild(resultDiv);

    // Dots
    const dotsDiv = document.createElement("div");
    dotsDiv.className = "onboarding-dots";
    steps.forEach((_, i) => {
      const dot = document.createElement("span");
      dot.className = "onboarding-dot" + (i === currentStep ? " active" : "");
      dotsDiv.appendChild(dot);
    });
    card.appendChild(dotsDiv);

    // Actions
    const actions = document.createElement("div");
    actions.className = "onboarding-actions";

    if (isFirst) {
      const skip = document.createElement("button");
      skip.type = "button";
      skip.className = "onboarding-skip";
      skip.textContent = t("onboarding.skip");
      skip.addEventListener("click", closeOnboarding);
      actions.appendChild(skip);
    } else {
      const back = document.createElement("button");
      back.type = "button";
      back.className = "onboarding-back";
      back.textContent = t("onboarding.back");
      back.addEventListener("click", () => { currentStep--; renderStep(); });
      actions.appendChild(back);
    }

    const next = document.createElement("button");
    next.type = "button";
    next.className = "onboarding-next";
    next.textContent = isLast ? t("onboarding.letsGo") : t("onboarding.next");
    next.addEventListener("click", () => {
      if (isLast) closeOnboarding();
      else { currentStep++; renderStep(); }
    });
    actions.appendChild(next);
    card.appendChild(actions);

    overlay.appendChild(card);

    // Run async action if step has one
    if (s.action) {
      // Show a loading indicator while checking
      resultDiv.className = "onboarding-result onboarding-result-loading";
      resultDiv.textContent = t("modals.checking");

      s.action().then((result) => {
        resultDiv.className = "onboarding-result onboarding-result-" + (result.type || "info");
        const statusIcons = { success: "\u2713", warning: "\u26A0", error: "\u2717", info: "\u2139" };
        resultDiv.innerHTML = "";
        const statusIcon = document.createElement("span");
        statusIcon.className = "onboarding-result-icon";
        statusIcon.textContent = statusIcons[result.type] || statusIcons.info;
        resultDiv.appendChild(statusIcon);
        const statusMsg = document.createElement("span");
        statusMsg.className = "onboarding-result-msg";
        statusMsg.textContent = result.msg;
        resultDiv.appendChild(statusMsg);
      });
    }
  }

  document.body.appendChild(overlay);
  renderStep();
}

function closeOnboarding() {
  document.getElementById("onboarding-overlay")?.remove();
  localStorage.setItem("lexa-onboarded", "1");
  showToast(t("toast.enjoyLexa"), "success");
}

function checkOnboarding() {
  if (!localStorage.getItem("lexa-onboarded")) {
    setTimeout(showOnboarding, 1000);
  }
}

// ── HELP COMMAND ────────────────────────────────
function showHelp() {
  const helpText = t("help.title") + "\n\n" +
    t("help.chatSection") + "\n\n" +
    t("help.commandsSection") + "\n\n" +
    t("help.voiceSection") + "\n\n" +
    t("help.shortcutsSection") + "\n\n" +
    t("help.dragDropSection") + "\n\n" +
    t("help.settingsSection");

  addMessage(helpText, "system");
  switchView("chat");
}
