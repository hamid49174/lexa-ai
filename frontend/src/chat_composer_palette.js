/* Chat composer palette and starter-card UI helpers. Classic script loaded before chat.js. */

let _composerCommandOpen = false;
let _composerCommandIdx = 0;
let _composerCommandLastQuery = "";

function composerCommandQuery() {
  const value = String(chatInput?.value || "");
  if (!value.startsWith("/")) return "";
  return value.slice(1).split(/\s+/)[0].toLowerCase();
}

function updateComposerCommandActiveDescendant() {
  const palette = document.getElementById("composer-command-palette");
  const rows = _composerCommandRows();
  const activeRow = _composerCommandOpen ? rows[_composerCommandIdx] : null;
  if (palette) palette.setAttribute("aria-hidden", _composerCommandOpen ? "false" : "true");
  if (!chatInput) return;
  chatInput.setAttribute("aria-controls", "composer-command-palette");
  chatInput.setAttribute("aria-expanded", _composerCommandOpen ? "true" : "false");
  chatInput.setAttribute("aria-autocomplete", "list");
  if (activeRow?.id) chatInput.setAttribute("aria-activedescendant", activeRow.id);
  else chatInput.removeAttribute("aria-activedescendant");
}

function createComposerCommandEmptyState() {
  const empty = document.createElement("div");
  empty.className = "composer-command-empty";
  empty.setAttribute("role", "option");
  empty.setAttribute("aria-disabled", "true");
  empty.textContent = t("composer.empty");
  return empty;
}

function createComposerCommandRow(command, index) {
  const label = composerCommandLabel(command);
  const desc = composerCommandDesc(command);
  const prefixHint = composerCommandHintText(command);
  const row = document.createElement("button");
  row.type = "button";
  row.id = `composer-command-option-${command.id}`;
  row.className = "composer-command-item" + (index === _composerCommandIdx ? " selected" : "");
  row.setAttribute("role", "option");
  row.setAttribute("aria-selected", index === _composerCommandIdx ? "true" : "false");
  row.setAttribute("aria-label", composerCommandAssistiveText(label, desc, prefixHint));
  row.title = composerCommandTitleText(label, desc, prefixHint);
  row.dataset.commandId = command.id;

  const icon = document.createElement("span");
  icon.className = "composer-command-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.appendChild(createComposerCommandIconElement(command.icon));

  const main = document.createElement("span");
  main.className = "composer-command-main";
  const labelEl = document.createElement("span");
  labelEl.className = "composer-command-label";
  labelEl.textContent = label;
  const descEl = document.createElement("span");
  descEl.className = "composer-command-desc";
  descEl.textContent = desc;
  main.append(labelEl, descEl);

  const prefix = document.createElement("span");
  prefix.className = "composer-command-prefix";
  prefix.textContent = prefixHint;
  row.append(icon, main, prefix);
  row.addEventListener("mousedown", (e) => {
    e.preventDefault();
    selectComposerCommand(command.id);
  });
  return row;
}

function renderComposerCommandPalette(query = composerCommandQuery()) {
  const palette = document.getElementById("composer-command-palette");
  if (!palette) return;
  const normalizedQuery = composerCommandAliasKey(query);
  if (normalizedQuery !== _composerCommandLastQuery) {
    _composerCommandIdx = 0;
    _composerCommandLastQuery = normalizedQuery;
  }
  const items = composerCommandSearchItems(query);
  if (_composerCommandIdx >= items.length) _composerCommandIdx = 0;
  palette.replaceChildren();
  if (!items.length) {
    palette.replaceChildren(createComposerCommandEmptyState());
    updateComposerCommandActiveDescendant();
    return;
  }
  items.forEach((command, index) => {
    palette.appendChild(createComposerCommandRow(command, index));
  });
  updateComposerCommandActiveDescendant();
}

function setComposerCommandPaletteOpen(open, options = {}) {
  const palette = document.getElementById("composer-command-palette");
  const button = document.getElementById("composer-command-btn");
  if (!palette) return;
  _composerCommandOpen = Boolean(open);
  if (button) {
    button.classList.toggle("active", _composerCommandOpen);
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", _composerCommandOpen ? "true" : "false");
    button.setAttribute("aria-controls", "composer-command-palette");
  }
  palette.classList.toggle("hidden", !_composerCommandOpen);
  palette.setAttribute("aria-hidden", _composerCommandOpen ? "false" : "true");
  if (_composerCommandOpen) {
    renderComposerCommandPalette(options.query || composerCommandQuery());
    if (options.focusInput !== false && chatInput) {
      setTimeout(() => {
        if (_composerCommandOpen && typeof chatInput.focus === "function") chatInput.focus();
      }, 0);
    }
  } else {
    updateComposerCommandActiveDescendant();
  }
}

function toggleComposerCommandPalette() {
  if (!_composerCommandOpen) {
    _composerCommandIdx = 0;
    setComposerCommandPaletteOpen(true, { query: composerCommandQuery(), focusInput: true });
  } else {
    setComposerCommandPaletteOpen(false);
  }
}

function closeComposerCommandPalette() {
  setComposerCommandPaletteOpen(false);
}

function updateComposerCommandPaletteFromInput() {
  if (!chatInput) return;
  const value = String(chatInput.value || "");
  if (value.startsWith("/") && !value.includes(" ")) {
    setComposerCommandPaletteOpen(true, { query: composerCommandQuery(), focusInput: false });
  } else if (_composerCommandOpen && value.trim() !== "") {
    closeComposerCommandPalette();
  }
}

function selectComposerCommand(commandId) {
  const command = LEXA_COMPOSER_COMMANDS.find((item) => item.id === commandId);
  if (!command || !chatInput) return false;
  const label = composerCommandLabel(command);
  chatInput.value = composerCommandPrefix(command);
  syncChatInputSize();
  closeComposerCommandPalette();
  chatInput.focus();
  setChatDraft(chatInput.value);
  showToast(t("composer.readyToast", { label }), "info", 1600);
  return true;
}

function _composerCommandRows() {
  return [...document.querySelectorAll("#composer-command-palette .composer-command-item")];
}

function handleComposerCommandKeydown(e) {
  if (!_composerCommandOpen) return false;
  const rows = _composerCommandRows();
  if (e.key === "Escape") {
    e.preventDefault();
    closeComposerCommandPalette();
    return true;
  }
  if (!rows.length) return false;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const dir = e.key === "ArrowDown" ? 1 : -1;
    rows[_composerCommandIdx]?.classList.remove("selected");
    rows[_composerCommandIdx]?.setAttribute("aria-selected", "false");
    _composerCommandIdx = (_composerCommandIdx + dir + rows.length) % rows.length;
    rows[_composerCommandIdx]?.classList.add("selected");
    rows[_composerCommandIdx]?.setAttribute("aria-selected", "true");
    rows[_composerCommandIdx]?.scrollIntoView({ block: "nearest" });
    updateComposerCommandActiveDescendant();
    return true;
  }
  if (e.key === "Enter" || e.key === "Tab") {
    e.preventDefault();
    const id = rows[_composerCommandIdx]?.dataset.commandId;
    return selectComposerCommand(id);
  }
  return false;
}

function setupComposerCommandPalette() {
  const button = document.getElementById("composer-command-btn");
  const palette = document.getElementById("composer-command-palette");
  if (!button || !palette) return;
  updateComposerCommandActiveDescendant();
  button.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowDown") return;
    e.preventDefault();
    _composerCommandIdx = 0;
    setComposerCommandPaletteOpen(true, { query: composerCommandQuery(), focusInput: true });
  });
  document.addEventListener("mousedown", (e) => {
    if (!_composerCommandOpen) return;
    if (palette.contains(e.target) || button.contains(e.target)) return;
    closeComposerCommandPalette();
  });
}

// ══════════════════════════════════════════════════════
// Voice capture, streaming, and TTS live in chat_voice.js.

// ── SMART SUGGESTIONS ───────────────────────────

// ── CONVERSATION STARTERS ───────────────────────
function _getConversationStarters() {
  return {
    morning: [
      { icon: "sun", title: t("chat.starterDayPlan"), text: t("chat.starterDayPlanDesc"), msg: t("chat.starterMsgDayPlan") },
      { icon: "mail", title: t("chat.starterEmails"), text: t("chat.starterEmailsDesc"), msg: t("chat.starterMsgEmails") },
      { icon: "checklist", title: t("chat.starterTodos"), text: t("chat.starterTodosDescMorning"), msg: t("chat.starterMsgTodos") },
      { icon: "system", title: t("chat.starterSystem"), text: t("chat.starterSystemDesc"), msg: t("chat.starterMsgSysteminfo") },
    ],
    afternoon: [
      { icon: "timer", title: t("chat.starterPomodoro"), text: t("chat.starterPomodoroDesc"), msg: t("chat.starterMsgPomodoro") },
      { icon: "checklist", title: t("chat.starterTodos"), text: t("chat.starterTodosDescAfternoon"), msg: t("chat.starterMsgTodos") },
      { icon: "music", title: t("chat.starterMusic"), text: t("chat.starterMusicDescWork"), msg: t("chat.starterMsgFocusMusic") },
      { icon: "system", title: t("chat.starterSystem"), text: t("chat.starterSystemDescPerf"), msg: t("chat.starterMsgSysteminfo") },
    ],
    evening: [
      { icon: "chart", title: t("chat.starterReview"), text: t("chat.starterReviewDesc"), msg: t("chat.starterMsgWhatDone") },
      { icon: "music", title: t("chat.starterMusic"), text: t("chat.starterMusicDescChill"), msg: t("chat.starterMsgChillMusic") },
      { icon: "spark", title: t("chat.starterCleanup"), text: t("chat.starterCleanupDesc"), msg: t("chat.starterMsgCleanDownloads") },
      { icon: "note", title: t("chat.starterNotes"), text: t("chat.starterNotesDesc"), msg: t("chat.starterMsgShowNotes") },
    ],
    night: [
      { icon: "moon", title: t("chat.starterNightMode"), text: t("chat.starterNightModeDesc"), msg: t("chat.starterMsgQuieter") },
      { icon: "note", title: t("chat.starterNotes"), text: t("chat.starterNotesDescNight"), msg: t("chat.starterMsgShowNotes") },
      { icon: "timer", title: t("chat.starterTimer"), text: t("chat.starterTimerDesc"), msg: t("chat.starterMsgTimer30") },
      { icon: "message", title: t("chat.starterSmalltalk"), text: t("chat.starterSmalltalkDesc"), msg: t("chat.starterMsgHowAreYou") },
    ],
    general: [
      { icon: "bolt", title: t("chat.starterQuickStart"), text: t("chat.starterQuickStartDesc"), msg: t("chat.starterMsgWhatCanYouDo") },
      { icon: "checklist", title: t("chat.starterTodos"), text: t("chat.starterTodosDescGeneral"), msg: t("chat.starterMsgTodos") },
      { icon: "music", title: t("chat.starterMusic"), text: t("chat.starterMusicDescGeneral"), msg: t("chat.starterMsgGoodMusic") },
      { icon: "system", title: t("chat.starterSystem"), text: t("chat.starterSystemDescGeneral"), msg: t("chat.starterMsgSysteminfo") },
    ],
  };
}

function starterIconSvg(name) {
  const paths = {
    bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/>',
    chart: '<path d="M4 19V5"/><path d="M4 19h16"/><path d="m7 15 3-3 3 2 4-6"/>',
    checklist: '<path d="m5 7 2 2 4-4"/><path d="M13 7h6"/><path d="m5 17 2 2 4-4"/><path d="M13 17h6"/>',
    mail: '<path d="M4 6h16v12H4z"/><path d="m4 7 8 6 8-6"/>',
    message: '<path d="M5 6h14v10H8l-3 3V6Z"/><path d="M8 10h8"/><path d="M8 13h5"/>',
    moon: '<path d="M20 15.4A7.5 7.5 0 0 1 8.6 4 8 8 0 1 0 20 15.4Z"/>',
    music: '<path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>',
    note: '<path d="M6 4h9l3 3v13H6z"/><path d="M14 4v5h5"/><path d="M9 13h6"/><path d="M9 17h4"/>',
    spark: '<path d="m12 3 1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5L12 3Z"/><path d="M19 15v4"/><path d="M17 17h4"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m4.9 19.1 1.4-1.4"/><path d="m17.7 6.3 1.4-1.4"/>',
    system: '<rect x="4" y="5" width="16" height="11" rx="2"/><path d="M8 20h8"/><path d="M10 16v4"/><path d="M14 16v4"/>',
    timer: '<circle cx="12" cy="13" r="7"/><path d="M12 9v4l3 2"/><path d="M9 2h6"/>',
  };
  const path = paths[name] || paths.spark;
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}

function renderConversationStarters() {
  const grid = document.getElementById("starter-grid");
  if (!grid) return;

  const starterCommandIds = ["workspace", "research", "think", "os"];
  const starters = starterCommandIds
    .map((id) => LEXA_COMPOSER_COMMANDS.find((command) => command.id === id))
    .filter(Boolean);

  grid.replaceChildren();
  starters.forEach((command) => {
    const label = composerCommandLabel(command);
    const desc = composerCommandDesc(command);
    const hint = composerCommandHintText(command);
    const card = document.createElement("button");
    card.type = "button";
    card.className = "starter-card";
    card.setAttribute("aria-label", `${label}: ${desc}. ${hint}`);
    card.title = `${label}: ${desc}`;
    const iconEl = document.createElement("span");
    iconEl.className = "starter-icon";
    iconEl.dataset.icon = command.icon || "spark";
    iconEl.appendChild(createComposerCommandIconElement(command.icon || "spark"));
    iconEl.setAttribute("aria-hidden", "true");
    const content = document.createElement("div");
    content.className = "starter-content";
    const titleEl = document.createElement("span");
    titleEl.className = "starter-title";
    titleEl.textContent = label;
    const descEl = document.createElement("span");
    descEl.className = "starter-desc";
    descEl.textContent = desc;
    const prefixEl = document.createElement("span");
    prefixEl.className = "starter-prefix";
    prefixEl.textContent = hint;
    content.appendChild(titleEl);
    content.appendChild(descEl);
    content.appendChild(prefixEl);
    card.appendChild(iconEl);
    card.appendChild(content);
    card.addEventListener("click", () => {
      selectComposerCommand(command.id);
    });
    grid.appendChild(card);
  });
}

// ── PERFORMANCE ──────────────────────────────────
