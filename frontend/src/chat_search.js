/*
 * Global chat search overlay and conversation export flow.
 */

let searchDebounce = null;
let searchRestoreFocusEl = null;
let searchRequestSeq = 0;
function restoreSearchFocus() {
  const el = searchRestoreFocusEl;
  searchRestoreFocusEl = null;
  if (!el || !el.isConnected || typeof el.focus !== "function") return;
  try { el.focus({ preventScroll: true }); }
  catch (_) { try { el.focus(); } catch (_) {} }
}
function searchFocusableElements(root) {
  return [...root.querySelectorAll(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )].filter(el => !el.disabled && !el.hidden && el.getClientRects().length > 0);
}
function trapSearchFocus(root, event) {
  const items = searchFocusableElements(root);
  if (!items.length) {
    event.preventDefault();
    return;
  }
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function createSearchIcon() {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "18");
  svg.setAttribute("height", "18");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "var(--accent)");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("aria-hidden", "true");
  const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  circle.setAttribute("cx", "11");
  circle.setAttribute("cy", "11");
  circle.setAttribute("r", "8");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.setAttribute("x1", "21");
  line.setAttribute("y1", "21");
  line.setAttribute("x2", "16.65");
  line.setAttribute("y2", "16.65");
  svg.append(circle, line);
  return svg;
}

function createSearchOverlayPanel() {
  const panel = document.createElement("div");
  panel.className = "search-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", t("nav.searchTooltip"));

  const header = document.createElement("div");
  header.className = "search-header";
  const input = document.createElement("input");
  input.type = "text";
  input.id = "search-input";
  input.className = "search-input";
  input.placeholder = t("chat.searchPlaceholder");
  input.setAttribute("aria-label", t("chat.searchPlaceholder"));
  input.setAttribute("autocomplete", "off");
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "search-close-btn";
  closeBtn.id = "search-close-btn";
  closeBtn.setAttribute("aria-label", t("common.close"));
  closeBtn.textContent = "\u00d7";
  header.append(createSearchIcon(), input, closeBtn);

  const results = document.createElement("div");
  results.id = "search-results";
  results.className = "search-results";
  renderSearchEmpty(results, t("chat.searchHint"));
  panel.append(header, results);
  return panel;
}

function openSearchOverlay() {
  // Etwaige In-Konversation-Such-Markierungen (Ctrl+F) entfernen, damit sie nicht neben der
  // globalen Suche stehen bleiben.
  if (typeof clearChatFindHighlights === "function") clearChatFindHighlights();
  let overlay = document.getElementById("search-overlay");
  if (!overlay) {
    overlay = document.createElement("div"); overlay.id = "search-overlay"; overlay.className = "search-overlay";
    overlay.replaceChildren(createSearchOverlayPanel());
    document.body.appendChild(overlay);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) closeSearchOverlay(); });
    const closeBtn = overlay.querySelector("#search-close-btn");
    const inputEl = overlay.querySelector("#search-input");
    closeBtn?.addEventListener("click", closeSearchOverlay);
    inputEl?.addEventListener("input", (e) => {
      const requestSeq = ++searchRequestSeq;
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => performSearch(e.target.value.trim(), requestSeq), 300);
    });
    inputEl?.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSearchOverlay(); });
    overlay.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeSearchOverlay();
      if (e.key === "Tab") trapSearchFocus(overlay, e);
    });
  }
  const active = document.activeElement;
  if (active && active !== document.body && !overlay.contains(active)) {
    searchRestoreFocusEl = active;
  }
  overlay.classList.add("visible");
  // Hintergrund (App-Root) fuer Screenreader inert schalten, solange das Such-Modal
  // offen ist (WAI-ARIA: aria-modal allein versteckt den Hintergrund nicht). Das
  // Overlay ist Body-Kind ausserhalb von #app und bleibt erreichbar.
  document.getElementById("app")?.setAttribute("aria-hidden", "true");
  searchRequestSeq += 1;
  if (searchDebounce) clearTimeout(searchDebounce);
  searchDebounce = null;
  const input = overlay.querySelector("#search-input");
  if (input) {
    input.value = "";
    input.focus();
  }
  renderSearchEmpty(overlay.querySelector("#search-results"), t("chat.searchHint"));
}
function closeSearchOverlay(options = {}) {
  document.getElementById("search-overlay")?.classList.remove("visible");
  document.getElementById("app")?.removeAttribute("aria-hidden");
  if (searchDebounce) clearTimeout(searchDebounce);
  searchDebounce = null;
  searchRequestSeq += 1;
  if (options.restoreFocus !== false) restoreSearchFocus();
  else searchRestoreFocusEl = null;
}
async function performSearch(query, requestSeq = ++searchRequestSeq) {
  const container = document.getElementById("search-results");
  if (!container) return;
  if (requestSeq !== searchRequestSeq) return;
  if (!query) { renderSearchEmpty(container, t("chat.searchHint")); return; }
  if (query.length < 2) { renderSearchEmpty(container, t("chat.searchMinChars")); return; }
  try {
    const data = await window.lexa.search(query);
    if (requestSeq !== searchRequestSeq) return;
    container.replaceChildren();
    const buildSearchItem = (icon, title, meta, action) => {
      const item = document.createElement("div");
      item.className = "search-item";
      item.setAttribute("role", "button");
      item.setAttribute("tabindex", "0");
      item.setAttribute("aria-label", `${title}. ${meta || ""}`.trim());
      const iconEl = document.createElement("span");
      iconEl.className = "search-item-icon";
      iconEl.textContent = icon;
      const info = document.createElement("div");
      info.className = "search-item-info";
      const titleEl = document.createElement("div");
      titleEl.className = "search-item-title";
      appendHighlightedText(titleEl, String(title || ""), query);
      const metaEl = document.createElement("div");
      metaEl.className = "search-item-meta";
      metaEl.textContent = meta || "";
      info.appendChild(titleEl);
      info.appendChild(metaEl);
      item.appendChild(iconEl);
      item.appendChild(info);
      const runAction = () => { closeSearchOverlay({ restoreFocus: false }); action(); };
      item.addEventListener("click", runAction);
      item.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          runAction();
        }
      });
      return item;
    };
    if (data.conversations?.length > 0) { const catEl = document.createElement("div"); catEl.className = "search-category"; catEl.textContent = t("chat.categoryChats"); container.appendChild(catEl); for (const c of data.conversations) container.appendChild(buildSearchItem("\u{1F4AC}", c.title, `${t("chat.messageCount", {count: c.message_count || 0})} \u00b7 ${String(c.updated_at || "").substring(0, 16)}`, () => switchConversation(c.id))); }
    if (data.notes?.length > 0) { const catEl = document.createElement("div"); catEl.className = "search-category"; catEl.textContent = t("chat.categoryNotes"); container.appendChild(catEl); for (const n of data.notes) container.appendChild(buildSearchItem("\u{1F4DD}", n.title, `${n.category || ""} \u00b7 ${String(n.created_at || "").substring(0, 10)}`, () => switchView("memory"))); }
    if (data.memories?.length > 0) { const catEl = document.createElement("div"); catEl.className = "search-category"; catEl.textContent = t("chat.categoryMemories"); container.appendChild(catEl); for (const m of data.memories) { const preview = String(m.content || "").substring(0, 80) + (String(m.content || "").length > 80 ? "\u2026" : ""); container.appendChild(buildSearchItem("\u{1F9E0}", preview, `${m.category || ""} \u00b7 ${t("chat.importance", {value: parseInt(m.importance) || 0})}`, () => switchView("memory"))); } }
    let total = (data.conversations?.length || 0) + (data.notes?.length || 0) + (data.memories?.length || 0);

    // FTS deep search — adds additional results from full-text index
    try {
      const fts = await window.lexa.ftsSearch(query);
      if (requestSeq !== searchRequestSeq) return;
      if (fts && fts.total > 0) {
        // Collect existing note/memory IDs to avoid duplicates
        const existingNoteIds = new Set((data.notes || []).map(n => n.id));
        const existingMemoryIds = new Set((data.memories || []).map(m => m.id));

        const ftsNotes = (fts.notes || []).filter(n => !existingNoteIds.has(n.id));
        const ftsMemories = (fts.memories || []).filter(m => !existingMemoryIds.has(m.id));

        if (ftsNotes.length > 0) {
          const catEl = document.createElement("div"); catEl.className = "search-category"; catEl.textContent = t("chat.categoryFtsNotes"); container.appendChild(catEl);
          for (const n of ftsNotes) {
            const snippet = String(n.snippet || n.title || "").substring(0, 100);
            container.appendChild(buildSearchItem("\u{1F50D}", snippet, `FTS \u00b7 ${n.category || ""} \u00b7 ${String(n.created_at || "").substring(0, 10)}`, () => switchView("memory")));
          }
          total += ftsNotes.length;
        }

        if (ftsMemories.length > 0) {
          const catEl = document.createElement("div"); catEl.className = "search-category"; catEl.textContent = t("chat.categoryFtsMemories"); container.appendChild(catEl);
          for (const m of ftsMemories) {
            const snippet = String(m.snippet || m.content || "").substring(0, 100);
            container.appendChild(buildSearchItem("\u{1F50E}", snippet, `FTS \u00b7 ${m.category || ""} \u00b7 ${t("chat.importance", {value: parseInt(m.importance) || 0})}`, () => switchView("memory")));
          }
          total += ftsMemories.length;
        }
      }
    } catch (e) {
      if (requestSeq !== searchRequestSeq) return;
      console.warn("[Chat] FTS search not available:", e.message || e);
    }

    if (total === 0) renderSearchEmpty(container, t("chat.searchNoResults"));
    else { const countEl = document.createElement("div"); countEl.className = "search-count"; countEl.textContent = t("chat.searchResults", {count: total}); container.prepend(countEl); }
  } catch (e) {
    if (requestSeq !== searchRequestSeq) return;
    console.error("[Chat] Search failed:", e.message || e);
    renderSearchEmpty(container, t("chat.searchError"));
  }
}

function renderSearchEmpty(container, message) {
  if (!container) return;
  container.replaceChildren();
  const empty = document.createElement("div");
  empty.className = "search-empty";
  empty.textContent = message || "";
  container.appendChild(empty);
}

function appendHighlightedText(target, text, query) {
  const source = String(text || "");
  const needle = String(query || "");
  if (!needle) {
    target.textContent = source;
    return;
  }
  const lowerSource = source.toLowerCase();
  const lowerNeedle = needle.toLowerCase();
  let index = 0;
  let matchAt = lowerSource.indexOf(lowerNeedle, index);
  while (matchAt !== -1) {
    if (matchAt > index) target.appendChild(document.createTextNode(source.slice(index, matchAt)));
    const mark = document.createElement("mark");
    mark.textContent = source.slice(matchAt, matchAt + needle.length);
    target.appendChild(mark);
    index = matchAt + needle.length;
    matchAt = lowerSource.indexOf(lowerNeedle, index);
  }
  if (index < source.length) target.appendChild(document.createTextNode(source.slice(index)));
}

// ── In-Konversation-Suche (Ctrl+F) — Treffer im aktuellen Chat hervorheben + n/m ──
// Top-Tier-Verhalten (Claude/ChatGPT/Gemini): Ctrl+F sucht IM Chat, mit Highlight,
// Vor/Zurueck und Treffer-Zaehler. Die globale Suche (openSearchOverlay) bleibt separat.
let _chatFindMarks = [];
let _chatFindCurrent = -1;

// Pure + testbar: alle [start,end]-Treffer von query in text (case-insensitive, ohne Overlap).
function chatFindRanges(text, query) {
  const ranges = [];
  const src = String(text || "");
  const q = String(query || "");
  if (!src || !q) return ranges;
  const lower = src.toLowerCase();
  const needle = q.toLowerCase();
  let at = lower.indexOf(needle);
  while (at !== -1) {
    ranges.push([at, at + needle.length]);
    at = lower.indexOf(needle, at + needle.length);
  }
  return ranges;
}

// Sichtbare Text-Knoten unter root sammeln (ohne MARK/BUTTON/SCRIPT/STYLE -> keine
// Doppel-Markierung, keine Stoerung von hljs-Markup oder Buttons).
function _chatFindCollect(node, out) {
  const kids = node && node.childNodes ? Array.from(node.childNodes) : [];
  for (const child of kids) {
    if (child.nodeType === 3) {
      if (child.nodeValue && child.nodeValue.trim()) out.push(child);
    } else if (child.nodeType === 1) {
      const tag = String(child.tagName || "").toUpperCase();
      // PRE/CODE auslassen: highlight.js erzeugt tief verschachteltes Span-Markup; ein <mark>
      // darin liesse sich nicht sauber wieder entfernen (fragmentierte Textknoten). Suche
      // bleibt auf Prosa beschraenkt — robust und vorhersagbar.
      if (tag === "MARK" || tag === "BUTTON" || tag === "SCRIPT" || tag === "STYLE"
          || tag === "PRE" || tag === "CODE") continue;
      _chatFindCollect(child, out);
    }
  }
  return out;
}

function _chatFindWrap(textNode, query) {
  const text = textNode.nodeValue;
  const ranges = chatFindRanges(text, query);
  if (!ranges.length) return [];
  const frag = document.createDocumentFragment();
  const marks = [];
  let last = 0;
  for (const r of ranges) {
    const s = r[0], e = r[1];
    if (s > last) frag.appendChild(document.createTextNode(text.slice(last, s)));
    const mark = document.createElement("mark");
    mark.className = "chat-find-mark";
    mark.textContent = text.slice(s, e);
    frag.appendChild(mark);
    marks.push(mark);
    last = e;
  }
  if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
  if (textNode.parentNode) textNode.parentNode.replaceChild(frag, textNode);
  return marks;
}

function clearChatFindHighlights() {
  for (const mark of _chatFindMarks) {
    const parent = mark.parentNode;
    if (!parent) continue;
    parent.replaceChild(document.createTextNode(mark.textContent || ""), mark);
    if (typeof parent.normalize === "function") parent.normalize();
  }
  _chatFindMarks = [];
  _chatFindCurrent = -1;
}

function runChatFind(query) {
  clearChatFindHighlights();
  const root = document.getElementById("chat-messages");
  const q = String(query || "").trim();
  if (root && q) {
    for (const tn of _chatFindCollect(root, [])) {
      const marks = _chatFindWrap(tn, q);
      if (marks.length) _chatFindMarks.push(...marks);
    }
    if (_chatFindMarks.length) { _chatFindCurrent = 0; _focusChatFindMark(); }
  }
  _updateChatFindCount();
  return _chatFindMarks.length;
}

function _focusChatFindMark() {
  for (let i = 0; i < _chatFindMarks.length; i += 1) {
    _chatFindMarks[i].className = i === _chatFindCurrent ? "chat-find-mark chat-find-current" : "chat-find-mark";
  }
  const cur = _chatFindMarks[_chatFindCurrent];
  // Nur scrollen, wenn der Treffer noch im DOM haengt (Marks koennen durch neues Streaming/
  // Re-Render verwaist sein) — vermeidet Fehler/Sprünge auf abgehaengte Knoten.
  if (cur && cur.isConnected !== false && typeof cur.scrollIntoView === "function") {
    cur.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

function chatFindStep(dir) {
  if (!_chatFindMarks.length) return;
  const n = _chatFindMarks.length;
  _chatFindCurrent = (_chatFindCurrent + (dir < 0 ? -1 : 1) + n) % n;
  _focusChatFindMark();
  _updateChatFindCount();
}
window.chatFindNext = function () { chatFindStep(1); };
window.chatFindPrev = function () { chatFindStep(-1); };

function _updateChatFindCount() {
  const el = document.getElementById("chat-find-count");
  if (!el) return;
  const total = _chatFindMarks.length;
  el.textContent = total ? `${_chatFindCurrent + 1}/${total}` : "0/0";
}

function _tf(key, fallback) { return typeof t === "function" ? t(key) : fallback; }

function openChatFind() {
  let bar = document.getElementById("chat-find-bar");
  if (!bar) {
    const container = document.getElementById("chat-container") || document.body;
    bar = document.createElement("div");
    bar.id = "chat-find-bar";
    bar.className = "chat-find-bar";
    const input = document.createElement("input");
    input.type = "text";
    input.id = "chat-find-input";
    input.className = "chat-find-input";
    input.setAttribute("aria-label", _tf("chat.findInConversation", "Im Chat suchen"));
    input.placeholder = _tf("chat.findPlaceholder", "Im Chat suchen…");
    input.addEventListener("input", function () { runChatFind(input.value); });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); chatFindStep(e.shiftKey ? -1 : 1); }
      else if (e.key === "Escape") { e.preventDefault(); closeChatFind(); }
    });
    const count = document.createElement("span");
    count.id = "chat-find-count";
    count.className = "chat-find-count";
    count.textContent = "0/0";
    const prev = document.createElement("button");
    prev.type = "button"; prev.className = "chat-find-btn"; prev.dataset.action = "chatFindPrev";
    prev.textContent = "↑"; prev.setAttribute("aria-label", _tf("chat.findPrev", "Vorheriger Treffer"));
    const next = document.createElement("button");
    next.type = "button"; next.className = "chat-find-btn"; next.dataset.action = "chatFindNext";
    next.textContent = "↓"; next.setAttribute("aria-label", _tf("chat.findNext", "Nächster Treffer"));
    const close = document.createElement("button");
    close.type = "button"; close.className = "chat-find-btn chat-find-close"; close.dataset.action = "closeChatFind";
    close.textContent = "✕"; close.setAttribute("aria-label", _tf("common.close", "Schließen"));
    bar.append(input, count, prev, next, close);
    container.appendChild(bar);
  }
  bar.classList.remove("hidden");
  const inputEl = document.getElementById("chat-find-input");
  if (inputEl) { inputEl.focus(); if (typeof inputEl.select === "function") inputEl.select(); }
}
window.openChatFind = openChatFind;

function closeChatFind() {
  clearChatFindHighlights();
  const bar = document.getElementById("chat-find-bar");
  if (bar) bar.classList.add("hidden");
  const inputEl = document.getElementById("chat-find-input");
  if (inputEl) inputEl.value = "";
  _updateChatFindCount();
}
window.closeChatFind = closeChatFind;
window.chatFindRanges = chatFindRanges;
window.runChatFind = runChatFind;
window.clearChatFindHighlights = clearChatFindHighlights;

async function exportConversation(convId, fmt = "markdown") {
  try {
    const cId = convId || LexaState.get("currentConversationId");
    if (!cId) { showToast(t("toast.convNotFound"), "error"); return; }
    const data = await window.lexa.conversationExport(cId, fmt);
    if (!data.text) { showToast(t("toast.exportFailed"), "error"); return; }
    const ext = fmt === "markdown" ? "md" : "txt";
    const blob = new Blob([data.text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `lexa-chat-${cId}.${ext}`; a.click();
    URL.revokeObjectURL(url);
    showToast(t("chat.exported", {format: ext.toUpperCase()}), "success");
  } catch (e) { console.warn("[Chat] Export failed:", e.message || e); showToast(t("toast.exportError"), "error"); }
}
