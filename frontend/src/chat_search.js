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
