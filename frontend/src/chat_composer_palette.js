/* Chat composer palette UI helpers. Classic script loaded before chat.js. */

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
  } else if (_composerCommandOpen) {
    // Schließen, sobald die Eingabe kein Slash-Präfix mehr ist — inkl. komplett geleert
    // (vorher blieb die Palette bei leerem Feld sichtbar hängen).
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

// ── PERFORMANCE ──────────────────────────────────
