/* ════════════════════════════════════════════════
   LEXA AI — Memory Module
   Memory view, Notes, Snippets, Clipboard history,
   Routines, Diagnostics, Memory cleanup
   Extracted from tools.js
   ════════════════════════════════════════════════ */

// ── HELPER: safe overlay removal with escHandler cleanup ──
function _closeOverlay(overlay, escHandler) {
  if (overlay && overlay.parentNode) overlay.remove();
  if (escHandler) document.removeEventListener("keydown", escHandler);
}

function bindMemoryCardAction(el, handler, label) {
  if (!el || typeof handler !== "function") return;
  if (label) el.setAttribute("aria-label", label);
  if (!el.hasAttribute("role")) el.setAttribute("role", "button");
  if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "0");
  el.addEventListener("keydown", (event) => {
    if (event.target !== el) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handler(event);
    }
  });
  el.addEventListener("click", handler);
}

const MEMORY_GRAPH_NS = "http://www.w3.org/2000/svg";
const MEMORY_GRAPH_GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
let memoryGraphState = null;
let memoryGraphRefreshSeq = 0;
let _clipboardHistoryRevealRunning = false;
let _memoryCleanupRunning = false;
let _routineToggleRunning = false;
let _snippetDeleteRunning = false;
let _noteDeleteRunning = false;

function setMemoryActionBusy(button, busy) {
  if (!button) return;
  button.disabled = Boolean(busy);
  if (busy) button.setAttribute("aria-busy", "true");
  else button.removeAttribute("aria-busy");
}

function setMemoryActionButtonsBusy(actionName, busy) {
  document.querySelectorAll(`[data-action="${actionName}"]`).forEach((button) => {
    setMemoryActionBusy(button, busy);
  });
}

function memoryGraphHash(value) {
  let hash = 2166136261;
  const text = String(value || "");
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash >>> 0);
}

function memoryGraphColor(type) {
  const colors = {
    hub: "#a78bfa",
    group: "#7dd3fc",
    type: "#c084fc",
    keyword: "#34d399",
    note: "#8b9cff",
    memory: "#f0abfc",
    conversation: "#60a5fa",
    routine: "#fbbf24",
    snippet: "#2dd4bf",
  };
  return colors[type] || "#9ca3af";
}

function memoryGraphClassToken(value, fallback = "node") {
  const token = String(value || fallback)
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return token || fallback;
}

function memoryGraphSafeNodes(nodes = []) {
  return nodes
    .filter((node) => node && node.id)
    .map((node) => {
      const type = memoryGraphClassToken(node.type, "node");
      return {
        id: String(node.id),
        label: String(node.label || node.id).slice(0, 96),
        type,
        group: memoryGraphClassToken(node.group || type, type),
        weight: Math.max(0.5, Math.min(12, Number(node.weight) || 1)),
        preview: String(node.preview || "").slice(0, 220),
        meta: node.meta && typeof node.meta === "object" ? node.meta : {},
      };
    });
}

function memoryGraphSafeLinks(links = [], nodeMap = new Map()) {
  return links
    .filter((link) => link && nodeMap.has(String(link.source)) && nodeMap.has(String(link.target)))
    .map((link) => ({
      source: String(link.source),
      target: String(link.target),
      kind: memoryGraphClassToken(link.kind, "link"),
      weight: Math.max(0.2, Math.min(6, Number(link.weight) || 1)),
    }));
}

function memoryGraphCompactText(value, limit = 120) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length <= limit ? text : `${text.slice(0, Math.max(0, limit - 1)).trim()}…`;
}

function memoryGraphFallbackTerms(...values) {
  const stopWords = new Set([
    "und", "oder", "der", "die", "das", "den", "dem", "ein", "eine", "ist", "mit", "for",
    "the", "and", "oder", "von", "aus", "auf", "ich", "du", "wir", "you", "that", "this",
  ]);
  const seen = new Set();
  const terms = [];
  values.forEach((value) => {
    String(value || "").toLowerCase().replace(/[a-z0-9äöüß_-]{3,}/gi, (term) => {
      const normalized = term.trim();
      if (stopWords.has(normalized) || seen.has(normalized)) return "";
      seen.add(normalized);
      terms.push(normalized);
      return "";
    });
  });
  return terms.slice(0, 8);
}

function buildMemoryGraphFallbackData(payloads = {}) {
  const nodes = [];
  const links = [];
  const termsByNode = new Map();
  const termCounts = new Map();
  const addNode = (node) => {
    if (!node?.id || nodes.some((existing) => existing.id === node.id)) return;
    const compact = {
      ...node,
      label: memoryGraphCompactText(node.label || node.id, 80),
      preview: memoryGraphCompactText(node.preview || "", 160),
    };
    nodes.push(compact);
    const terms = new Set(memoryGraphFallbackTerms(compact.label, compact.preview, compact.type, compact.group));
    termsByNode.set(compact.id, terms);
    terms.forEach((term) => termCounts.set(term, (termCounts.get(term) || 0) + 1));
  };
  const addLink = (source, target, kind = "contains", weight = 1) => {
    if (!source || !target || source === target) return;
    if (!nodes.some((node) => node.id === source) || !nodes.some((node) => node.id === target)) return;
    if (links.some((link) => link.source === source && link.target === target && link.kind === kind)) return;
    links.push({ source, target, kind, weight });
  };

  addNode({
    id: "hub:memory",
    label: "Lexa Gedächtnis",
    type: "hub",
    group: "hub",
    weight: 10,
    preview: "Rückwärtskompatibler lokaler Graph aus vorhandenen Read-Endpoints.",
  });
  [
    ["group:conversations", "Chats", "conversations"],
    ["group:notes", "Notizen", "notes"],
    ["group:memories", "Erinnerungen", "memories"],
    ["group:routines", "Routinen", "routines"],
    ["group:snippets", "Snippets", "snippets"],
  ].forEach(([id, label, group]) => {
    addNode({ id, label, type: "group", group, weight: 5 });
    addLink("hub:memory", id, "contains", 2);
  });

  const conversations = Array.isArray(payloads.conversations?.conversations) ? payloads.conversations.conversations : [];
  conversations.slice(0, 90).forEach((conversation, index) => {
    const id = `conversation:${conversation.id ?? index}`;
    addNode({
      id,
      label: conversation.title || "Chat",
      type: "conversation",
      group: "conversations",
      weight: 2.2 + Math.min(5, Math.log((Number(conversation.message_count) || 0) + 1)),
      preview: conversation.last_message || "",
      meta: { message_count: Number(conversation.message_count) || 0 },
    });
    addLink("group:conversations", id, "contains", 1.2);
  });

  const notes = Array.isArray(payloads.notes?.notes) ? payloads.notes.notes : [];
  notes.slice(0, 60).forEach((note, index) => {
    const id = `note:${note.id ?? index}`;
    addNode({
      id,
      label: note.title || "Notiz",
      type: "note",
      group: "notes",
      weight: 3,
      preview: note.content || note.category || "",
      meta: { category: note.category || "" },
    });
    addLink("group:notes", id, "contains", 1.2);
  });

  const snippets = Array.isArray(payloads.snippets?.snippets) ? payloads.snippets.snippets : [];
  snippets.slice(0, 40).forEach((snippet, index) => {
    const id = `snippet:${snippet.name || index}`;
    addNode({
      id,
      label: snippet.name || "Snippet",
      type: "snippet",
      group: "snippets",
      weight: 2.2 + Math.min(4, Number(snippet.use_count || 0) * 0.2),
      preview: snippet.text || "",
      meta: { use_count: Number(snippet.use_count || 0) },
    });
    addLink("group:snippets", id, "contains", 1);
  });

  const routines = Array.isArray(payloads.routines?.routines) ? payloads.routines.routines : [];
  routines.slice(0, 40).forEach((routine, index) => {
    const id = `routine:${routine.id ?? index}`;
    addNode({
      id,
      label: routine.name || "Routine",
      type: "routine",
      group: "routines",
      weight: routine.enabled ? 3.4 : 2.4,
      preview: routine.description || routine.schedule || "",
      meta: { enabled: Boolean(routine.enabled), schedule: routine.schedule || "" },
    });
    addLink("group:routines", id, "contains", 1);
  });

  const stats = payloads.stats || {};
  const memoryCount = Number(stats.memories || 0);
  if (memoryCount > 0 && !nodes.some((node) => node.type === "memory")) {
    const id = "memory:summary";
    addNode({
      id,
      label: `${memoryCount} Erinnerungen`,
      type: "memory",
      group: "memories",
      weight: 2.8 + Math.min(5, Math.log(memoryCount + 1)),
      preview: "Backend ohne Detail-Graph: vorhandene Erinnerungen werden als lokaler Summary-Knoten angezeigt.",
      meta: { count: memoryCount },
    });
    addLink("group:memories", id, "contains", 1.4);
  }

  const keywordTerms = [...termCounts.entries()]
    .filter(([, count]) => count >= 2)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 16);
  keywordTerms.forEach(([term, count]) => {
    const keywordId = `keyword:${term}`;
    addNode({
      id: keywordId,
      label: term,
      type: "keyword",
      group: "keywords",
      weight: 1.6 + Math.min(4, count * 0.3),
      preview: `${count} lokale Treffer`,
    });
    addLink("hub:memory", keywordId, "keyword", 0.6);
    let linked = 0;
    termsByNode.forEach((terms, nodeId) => {
      if (linked >= 10) return;
      if (terms.has(term) && !nodeId.startsWith("group:") && !nodeId.startsWith("hub:") && nodeId !== keywordId) {
        addLink(keywordId, nodeId, "mentions", 1);
        linked += 1;
      }
    });
  });

  return {
    status: "ok",
    nodes,
    links,
    counts: {
      nodes: nodes.length,
      links: links.length,
      conversations: conversations.length,
      notes: notes.length,
      snippets: snippets.length,
      routines: routines.length,
      memories: memoryCount,
    },
    source: "frontend_fallback_readonly",
  };
}

async function loadMemoryGraphFallbackData() {
  const [stats, notes, snippets, routines, conversations] = await Promise.allSettled([
    typeof window.lexa.memoryStats === "function" ? window.lexa.memoryStats() : {},
    typeof window.lexa.notes === "function" ? window.lexa.notes() : { notes: [] },
    typeof window.lexa.snippets === "function" ? window.lexa.snippets() : { snippets: [] },
    typeof window.lexa.routines === "function" ? window.lexa.routines() : { routines: [] },
    typeof window.lexa.conversations === "function" ? window.lexa.conversations() : { conversations: [] },
  ]);
  return buildMemoryGraphFallbackData({
    stats: stats.status === "fulfilled" ? stats.value : {},
    notes: notes.status === "fulfilled" ? notes.value : { notes: [] },
    snippets: snippets.status === "fulfilled" ? snippets.value : { snippets: [] },
    routines: routines.status === "fulfilled" ? routines.value : { routines: [] },
    conversations: conversations.status === "fulfilled" ? conversations.value : { conversations: [] },
  });
}

function renderMemoryGraphEmpty(message) {
  const empty = document.getElementById("memory-graph-empty");
  const svg = document.getElementById("memory-graph-svg");
  if (memoryGraphState?.frame) cancelAnimationFrame(memoryGraphState.frame);
  memoryGraphState = null;
  if (svg) svg.replaceChildren();
  if (empty) {
    empty.textContent = message || "Kein Graph verfuegbar.";
    empty.classList.remove("hidden");
  }
}

function updateMemoryGraphInspector(node, graph) {
  const panel = document.getElementById("memory-graph-inspector");
  if (!panel) return;
  const typeEl = panel.querySelector(".memory-graph-inspector-type");
  const titleEl = panel.querySelector(".memory-graph-inspector-title");
  const metaEl = panel.querySelector(".memory-graph-inspector-meta");
  if (!node) {
    if (typeEl) typeEl.textContent = "Graph";
    if (titleEl) titleEl.textContent = `${graph.nodes.length} Knoten · ${graph.links.length} Linien`;
    if (metaEl) metaEl.textContent = "Hover oder Klick auf einen Punkt zeigt Details.";
    return;
  }
  const degree = graph.neighbors.get(node.id)?.size || 0;
  const metaBits = [];
  if (node.meta?.memory_type) metaBits.push(node.meta.memory_type);
  if (node.meta?.category) metaBits.push(node.meta.category);
  if (node.meta?.message_count) metaBits.push(`${node.meta.message_count} Nachrichten`);
  if (node.meta?.importance) metaBits.push(`Wichtigkeit ${node.meta.importance}`);
  if (typeEl) typeEl.textContent = `${node.type} · ${degree} Links`;
  if (titleEl) titleEl.textContent = node.label;
  if (metaEl) metaEl.textContent = [node.preview, metaBits.join(" · ")].filter(Boolean).join(" · ");
}

function memoryGraphCreateSvgElement(name, attrs = {}) {
  const el = document.createElementNS(MEMORY_GRAPH_NS, name);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, String(value)));
  return el;
}

function memoryGraphAppendGradient(defs, id, stops) {
  const gradient = memoryGraphCreateSvgElement("radialGradient", { id, cx: "50%", cy: "44%", r: "74%" });
  stops.forEach(([offset, color, opacity]) => {
    gradient.appendChild(memoryGraphCreateSvgElement("stop", {
      offset,
      "stop-color": color,
      "stop-opacity": opacity,
    }));
  });
  defs.appendChild(gradient);
}

function memoryGraphAppendBrainDefs(defs) {
  memoryGraphAppendGradient(defs, "memory-graph-brain-fill", [
    ["0%", "#2dd4bf", "0.18"],
    ["42%", "#8b5cf6", "0.14"],
    ["76%", "#60a5fa", "0.08"],
    ["100%", "#03040a", "0"],
  ]);
  memoryGraphAppendGradient(defs, "memory-graph-brain-aura", [
    ["0%", "#a78bfa", "0.22"],
    ["46%", "#2dd4bf", "0.12"],
    ["100%", "#03040a", "0"],
  ]);
}

function memoryGraphCreateBrainBackdrop(svg, width, height) {
  const x = (value) => (width * value).toFixed(1);
  const y = (value) => (height * value).toFixed(1);
  const layer = memoryGraphCreateSvgElement("g", {
    class: "memory-graph-brain-backdrop",
    "aria-hidden": "true",
  });

  const aura = memoryGraphCreateSvgElement("path", {
    class: "memory-graph-brain-aura",
    d: `M ${x(0.17)} ${y(0.56)}
      C ${x(0.10)} ${y(0.39)} ${x(0.21)} ${y(0.19)} ${x(0.36)} ${y(0.19)}
      C ${x(0.42)} ${y(0.08)} ${x(0.50)} ${y(0.17)} ${x(0.50)} ${y(0.28)}
      C ${x(0.51)} ${y(0.17)} ${x(0.60)} ${y(0.08)} ${x(0.66)} ${y(0.19)}
      C ${x(0.82)} ${y(0.19)} ${x(0.91)} ${y(0.40)} ${x(0.84)} ${y(0.57)}
      C ${x(0.93)} ${y(0.76)} ${x(0.74)} ${y(0.91)} ${x(0.61)} ${y(0.80)}
      C ${x(0.57)} ${y(0.91)} ${x(0.43)} ${y(0.91)} ${x(0.39)} ${y(0.80)}
      C ${x(0.25)} ${y(0.91)} ${x(0.08)} ${y(0.75)} ${x(0.17)} ${y(0.56)} Z`,
  });

  const outline = memoryGraphCreateSvgElement("path", {
    class: "memory-graph-brain-outline",
    d: `M ${x(0.19)} ${y(0.55)}
      C ${x(0.14)} ${y(0.42)} ${x(0.19)} ${y(0.29)} ${x(0.31)} ${y(0.24)}
      C ${x(0.35)} ${y(0.13)} ${x(0.48)} ${y(0.15)} ${x(0.50)} ${y(0.26)}
      C ${x(0.54)} ${y(0.14)} ${x(0.68)} ${y(0.13)} ${x(0.72)} ${y(0.25)}
      C ${x(0.84)} ${y(0.30)} ${x(0.89)} ${y(0.43)} ${x(0.85)} ${y(0.56)}
      C ${x(0.91)} ${y(0.71)} ${x(0.78)} ${y(0.84)} ${x(0.65)} ${y(0.80)}
      C ${x(0.58)} ${y(0.89)} ${x(0.43)} ${y(0.89)} ${x(0.35)} ${y(0.80)}
      C ${x(0.23)} ${y(0.84)} ${x(0.11)} ${y(0.70)} ${x(0.19)} ${y(0.55)} Z`,
  });

  const stem = memoryGraphCreateSvgElement("path", {
    class: "memory-graph-brain-stem",
    d: `M ${x(0.46)} ${y(0.78)}
      C ${x(0.47)} ${y(0.86)} ${x(0.42)} ${y(0.91)} ${x(0.48)} ${y(0.96)}
      C ${x(0.56)} ${y(0.92)} ${x(0.52)} ${y(0.86)} ${x(0.54)} ${y(0.78)}`,
  });

  const midline = memoryGraphCreateSvgElement("path", {
    class: "memory-graph-brain-midline",
    d: `M ${x(0.50)} ${y(0.25)}
      C ${x(0.47)} ${y(0.37)} ${x(0.53)} ${y(0.48)} ${x(0.49)} ${y(0.58)}
      C ${x(0.46)} ${y(0.68)} ${x(0.53)} ${y(0.75)} ${x(0.50)} ${y(0.84)}`,
  });

  const folds = [
    `M ${x(0.30)} ${y(0.34)} C ${x(0.40)} ${y(0.27)} ${x(0.45)} ${y(0.38)} ${x(0.35)} ${y(0.44)} C ${x(0.26)} ${y(0.50)} ${x(0.41)} ${y(0.56)} ${x(0.31)} ${y(0.65)}`,
    `M ${x(0.24)} ${y(0.47)} C ${x(0.34)} ${y(0.42)} ${x(0.42)} ${y(0.50)} ${x(0.34)} ${y(0.58)} C ${x(0.28)} ${y(0.64)} ${x(0.39)} ${y(0.71)} ${x(0.43)} ${y(0.78)}`,
    `M ${x(0.37)} ${y(0.25)} C ${x(0.30)} ${y(0.34)} ${x(0.43)} ${y(0.36)} ${x(0.40)} ${y(0.46)} C ${x(0.36)} ${y(0.58)} ${x(0.47)} ${y(0.62)} ${x(0.43)} ${y(0.73)}`,
    `M ${x(0.62)} ${y(0.25)} C ${x(0.70)} ${y(0.33)} ${x(0.57)} ${y(0.37)} ${x(0.61)} ${y(0.47)} C ${x(0.66)} ${y(0.58)} ${x(0.53)} ${y(0.63)} ${x(0.58)} ${y(0.74)}`,
    `M ${x(0.70)} ${y(0.34)} C ${x(0.60)} ${y(0.27)} ${x(0.55)} ${y(0.38)} ${x(0.65)} ${y(0.44)} C ${x(0.75)} ${y(0.51)} ${x(0.58)} ${y(0.57)} ${x(0.69)} ${y(0.66)}`,
    `M ${x(0.76)} ${y(0.47)} C ${x(0.65)} ${y(0.41)} ${x(0.57)} ${y(0.51)} ${x(0.66)} ${y(0.59)} C ${x(0.73)} ${y(0.65)} ${x(0.61)} ${y(0.72)} ${x(0.57)} ${y(0.79)}`,
    `M ${x(0.42)} ${y(0.43)} C ${x(0.48)} ${y(0.39)} ${x(0.53)} ${y(0.40)} ${x(0.58)} ${y(0.45)} C ${x(0.52)} ${y(0.50)} ${x(0.49)} ${y(0.54)} ${x(0.54)} ${y(0.61)}`,
  ];

  layer.append(aura, outline, stem, midline);
  folds.forEach((d, index) => {
    layer.appendChild(memoryGraphCreateSvgElement("path", {
      class: `memory-graph-brain-fold memory-graph-brain-fold-${index + 1}`,
      d,
    }));
  });
  svg.appendChild(layer);
}

function memoryGraphBrainSide(node) {
  if (node.type === "hub") return 0;
  const knownSides = {
    conversations: -1,
    notes: 1,
    memories: 1,
    snippets: -1,
    routines: 1,
    keywords: 0,
  };
  if (Object.prototype.hasOwnProperty.call(knownSides, node.group)) return knownSides[node.group];
  return memoryGraphHash(node.group || node.type) % 2 === 0 ? -1 : 1;
}

function memoryGraphBrainAnchor(node, index, total, width, height) {
  const seed = memoryGraphHash(`${node.group}:${node.id}`);
  const side = memoryGraphBrainSide(node);
  const centerX = width * 0.5;
  const centerY = height * 0.51;
  if (node.type === "hub") {
    return { x: centerX, y: centerY + height * 0.08, side: 0 };
  }

  const lobeSide = side || (seed % 2 === 0 ? -1 : 1);
  const lobeCenterX = centerX + lobeSide * width * 0.18;
  const lobeCenterY = centerY + (node.type === "keyword" ? -height * 0.01 : 0);
  const angle = seed * 0.0009 + index * MEMORY_GRAPH_GOLDEN_ANGLE;
  const edgeBias = node.type === "keyword" ? 0.88 : node.type === "group" ? 0.42 : 0.58;
  const seedDepth = ((seed % 997) / 997) * 0.32;
  const depth = Math.min(0.95, edgeBias + seedDepth);
  const rx = width * (node.type === "group" ? 0.14 : node.type === "keyword" ? 0.30 : 0.24);
  const ry = height * (node.type === "group" ? 0.18 : node.type === "keyword" ? 0.34 : 0.29);
  let x = lobeCenterX + Math.cos(angle) * rx * depth;
  let y = lobeCenterY + Math.sin(angle) * ry * depth;

  if (node.type === "group") {
    const groupRank = index / Math.max(1, total - 1);
    x = centerX + lobeSide * width * (0.08 + groupRank * 0.13);
    y = centerY - height * 0.08 + Math.sin(angle) * height * 0.18;
  } else if (node.type === "routine" || node.type === "snippet") {
    y += height * 0.07;
  }

  return {
    x: Math.max(width * 0.16, Math.min(width * 0.84, x)),
    y: Math.max(height * 0.18, Math.min(height * 0.84, y)),
    side: lobeSide,
  };
}

function memoryGraphBrainBounds(width, height) {
  return {
    left: width * 0.13,
    right: width * 0.87,
    top: height * 0.16,
    bottom: height * 0.88,
  };
}

function memoryGraphApplyFocus(graph, activeId = "") {
  graph.activeId = activeId || "";
  const query = (graph.filter || "").trim().toLowerCase();
  const neighborSet = activeId ? (graph.neighbors.get(activeId) || new Set()) : null;
  graph.nodes.forEach((node) => {
    const matches = !query
      || node.label.toLowerCase().includes(query)
      || node.type.toLowerCase().includes(query)
      || node.group.toLowerCase().includes(query)
      || node.preview.toLowerCase().includes(query);
    const related = !activeId || node.id === activeId || neighborSet?.has(node.id);
    node.el?.classList.toggle("is-active", node.id === activeId);
    node.el?.classList.toggle("is-neighbor", Boolean(activeId && neighborSet?.has(node.id)));
    node.el?.classList.toggle("is-dim", !matches || !related);
    node.labelEl?.classList.toggle("is-dim", !matches || !related);
    node.labelEl?.classList.toggle("is-visible", matches && (node.id === activeId || node.weight >= 4.8 || node.type === "group" || node.type === "hub"));
  });
  graph.links.forEach((link) => {
    const visible = !activeId || link.source === activeId || link.target === activeId;
    link.el?.classList.toggle("is-dim", !visible);
    link.el?.classList.toggle("is-active", visible && Boolean(activeId));
  });
}

function memoryGraphLayout(nodes, links, width, height) {
  nodes.forEach((node, index) => {
    const seed = memoryGraphHash(node.id);
    const anchor = memoryGraphBrainAnchor(node, index, nodes.length, width, height);
    const jitter = ((seed % 1000) / 1000 - 0.5) * 18;
    node.anchorX = anchor.x;
    node.anchorY = anchor.y;
    node.brainSide = anchor.side;
    node.x = anchor.x + Math.cos(seed) * jitter;
    node.y = anchor.y + Math.sin(seed) * jitter;
    node.vx = 0;
    node.vy = 0;
    node.radius = Math.max(3.2, Math.min(15, 3.2 + node.weight * 1.15));
    node.color = memoryGraphColor(node.type);
  });
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  links.forEach((link) => {
    link.sourceNode = nodeMap.get(link.source);
    link.targetNode = nodeMap.get(link.target);
  });
}

function memoryGraphStep(graph) {
  const { nodes, links, width, height } = graph;
  const bounds = memoryGraphBrainBounds(width, height);
  const phase = Date.now() / 9000;

  links.forEach((link) => {
    const a = link.sourceNode;
    const b = link.targetNode;
    if (!a || !b) return;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const desired = link.kind === "contains" ? 92 : link.kind === "mentions" ? 118 : 150;
    const pull = (dist - desired) * 0.004 * link.weight;
    const fx = (dx / dist) * pull;
    const fy = (dy / dist) * pull;
    if (!a.fixed) { a.vx += fx; a.vy += fy; }
    if (!b.fixed) { b.vx -= fx; b.vy -= fy; }
  });

  for (let i = 0; i < nodes.length; i += 1) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j += 1) {
      const b = nodes[j];
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distSq = Math.max(64, dx * dx + dy * dy);
      const force = (a.radius + b.radius + 38) / distSq;
      const fx = dx * force;
      const fy = dy * force;
      if (!a.fixed) { a.vx -= fx; a.vy -= fy; }
      if (!b.fixed) { b.vx += fx; b.vy += fy; }
    }
  }

  nodes.forEach((node) => {
    const nodeSeed = memoryGraphHash(node.id);
    const drift = node.type === "hub" ? 0 : 4;
    const anchorX = (node.anchorX || width / 2) + Math.cos(phase + nodeSeed) * drift;
    const anchorY = (node.anchorY || height / 2) + Math.sin(phase + nodeSeed) * drift;
    if (!node.fixed) {
      node.vx += (anchorX - node.x) * 0.0024;
      node.vy += (anchorY - node.y) * 0.0024;
      node.vx *= 0.84;
      node.vy *= 0.84;
      node.x += node.vx;
      node.y += node.vy;
      node.x = Math.max(bounds.left, Math.min(bounds.right, node.x));
      node.y = Math.max(bounds.top, Math.min(bounds.bottom, node.y));
    }
  });
}

function memoryGraphLinkPath(link) {
  const a = link.sourceNode;
  const b = link.targetNode;
  if (!a || !b) return "";
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  const sign = memoryGraphHash(`${link.source}:${link.target}:${link.kind}`) % 2 === 0 ? 1 : -1;
  const curve = Math.min(82, Math.max(14, dist * 0.17)) * sign;
  const nx = -dy / dist;
  const ny = dx / dist;
  const c1x = a.x + dx * 0.33 + nx * curve;
  const c1y = a.y + dy * 0.33 + ny * curve;
  const c2x = a.x + dx * 0.67 + nx * curve * 0.66;
  const c2y = a.y + dy * 0.67 + ny * curve * 0.66;
  return `M ${a.x.toFixed(1)} ${a.y.toFixed(1)} C ${c1x.toFixed(1)} ${c1y.toFixed(1)} ${c2x.toFixed(1)} ${c2y.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
}

function memoryGraphPaint(graph) {
  graph.links.forEach((link) => {
    if (!link.sourceNode || !link.targetNode) return;
    link.el.setAttribute("d", memoryGraphLinkPath(link));
  });
  graph.nodes.forEach((node) => {
    node.el.setAttribute("cx", node.x.toFixed(1));
    node.el.setAttribute("cy", node.y.toFixed(1));
    const labelOffset = node.brainSide < 0 ? -(node.radius + 8) : node.radius + 8;
    node.labelEl.setAttribute("x", (node.x + labelOffset).toFixed(1));
    node.labelEl.setAttribute("y", (node.y + 4).toFixed(1));
    node.labelEl.setAttribute("text-anchor", node.brainSide < 0 ? "end" : "start");
  });
}

function startMemoryGraphAnimation(graph) {
  if (memoryGraphState?.frame) cancelAnimationFrame(memoryGraphState.frame);
  memoryGraphState = graph;
  const animate = () => {
    if (memoryGraphState !== graph) return;
    if (typeof LexaState !== "undefined" && LexaState.get("currentView") !== "memory") {
      graph.frame = 0;
      return;
    }
    memoryGraphStep(graph);
    memoryGraphPaint(graph);
    graph.frame = requestAnimationFrame(animate);
  };
  animate();
}

function renderMemoryGraphLegend(graph) {
  const legend = document.getElementById("memory-graph-legend");
  if (!legend) return;
  legend.replaceChildren();
  const types = [...new Set(graph.nodes.map((node) => node.type))].sort((a, b) => a.localeCompare(b));
  types.forEach((type) => {
    const item = document.createElement("span");
    item.className = "memory-graph-legend-item";
    const dot = document.createElement("span");
    dot.className = `memory-graph-legend-dot memory-graph-legend-dot-${memoryGraphClassToken(type, "node")}`;
    const label = document.createElement("span");
    label.textContent = type;
    item.append(dot, label);
    legend.appendChild(item);
  });
}

function renderMemoryGraph(data) {
  const stage = document.getElementById("memory-graph-stage");
  const svg = document.getElementById("memory-graph-svg");
  const empty = document.getElementById("memory-graph-empty");
  if (!stage || !svg) return;

  const nodes = memoryGraphSafeNodes(data?.nodes || []);
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const links = memoryGraphSafeLinks(data?.links || [], nodeMap);
  if (!nodes.length) {
    renderMemoryGraphEmpty("Noch keine Knoten im lokalen Gedächtnis.");
    return;
  }
  if (empty) empty.classList.add("hidden");

  const rect = stage.getBoundingClientRect();
  const width = Math.max(720, Math.floor(rect.width || 960));
  const height = Math.max(480, Math.floor(rect.height || 620));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.replaceChildren();

  const defs = memoryGraphCreateSvgElement("defs");
  memoryGraphAppendBrainDefs(defs);
  const filter = memoryGraphCreateSvgElement("filter", { id: "memory-graph-glow", x: "-50%", y: "-50%", width: "200%", height: "200%" });
  filter.appendChild(memoryGraphCreateSvgElement("feGaussianBlur", { stdDeviation: "3.5", result: "coloredBlur" }));
  const merge = memoryGraphCreateSvgElement("feMerge");
  merge.appendChild(memoryGraphCreateSvgElement("feMergeNode", { in: "coloredBlur" }));
  merge.appendChild(memoryGraphCreateSvgElement("feMergeNode", { in: "SourceGraphic" }));
  filter.appendChild(merge);
  defs.appendChild(filter);
  svg.appendChild(defs);
  memoryGraphCreateBrainBackdrop(svg, width, height);

  const linkLayer = memoryGraphCreateSvgElement("g", { class: "memory-graph-links" });
  const nodeLayer = memoryGraphCreateSvgElement("g", { class: "memory-graph-nodes" });
  const labelLayer = memoryGraphCreateSvgElement("g", { class: "memory-graph-labels" });
  svg.append(linkLayer, nodeLayer, labelLayer);

  const neighbors = new Map(nodes.map((node) => [node.id, new Set()]));
  links.forEach((link) => {
    neighbors.get(link.source)?.add(link.target);
    neighbors.get(link.target)?.add(link.source);
  });

  memoryGraphLayout(nodes, links, width, height);
  const graph = { nodes, links, neighbors, width, height, activeId: "", filter: "", frame: 0 };

  links.forEach((link) => {
    const el = memoryGraphCreateSvgElement("path", {
      class: `memory-graph-link memory-graph-link-${link.kind}`,
      "data-kind": link.kind,
      d: memoryGraphLinkPath(link),
      "stroke-width": Math.max(0.5, Math.min(2.8, link.weight * 0.42)).toFixed(2),
    });
    link.el = el;
    linkLayer.appendChild(el);
  });

  nodes.forEach((node) => {
    const circle = memoryGraphCreateSvgElement("circle", {
      class: `memory-graph-node memory-graph-node-${node.type}`,
      r: node.radius.toFixed(1),
      fill: node.color,
      tabindex: "0",
      role: "button",
      "aria-label": `${node.type}: ${node.label}`,
    });
    const label = memoryGraphCreateSvgElement("text", {
      class: "memory-graph-label",
      "data-node-label": node.id,
    });
    label.textContent = node.label;
    node.el = circle;
    node.labelEl = label;
    circle.addEventListener("pointerenter", () => {
      updateMemoryGraphInspector(node, graph);
      memoryGraphApplyFocus(graph, node.id);
    });
    circle.addEventListener("focus", () => {
      updateMemoryGraphInspector(node, graph);
      memoryGraphApplyFocus(graph, node.id);
    });
    circle.addEventListener("click", () => {
      graph.activeId = graph.activeId === node.id ? "" : node.id;
      updateMemoryGraphInspector(graph.activeId ? node : null, graph);
      memoryGraphApplyFocus(graph, graph.activeId);
    });
    circle.addEventListener("pointerdown", (event) => {
      node.fixed = true;
      graph.dragNode = node;
      circle.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });
    circle.addEventListener("pointermove", (event) => {
      if (graph.dragNode !== node) return;
      const bounds = svg.getBoundingClientRect();
      const scaleX = width / Math.max(1, bounds.width);
      const scaleY = height / Math.max(1, bounds.height);
      node.x = (event.clientX - bounds.left) * scaleX;
      node.y = (event.clientY - bounds.top) * scaleY;
      node.vx = 0;
      node.vy = 0;
      memoryGraphPaint(graph);
    });
    const release = (event) => {
      if (graph.dragNode !== node) return;
      graph.dragNode = null;
      node.fixed = false;
      try { circle.releasePointerCapture?.(event.pointerId); } catch (_error) {}
    };
    circle.addEventListener("pointerup", release);
    circle.addEventListener("pointercancel", release);
    nodeLayer.appendChild(circle);
    labelLayer.appendChild(label);
  });

  const filterInput = document.getElementById("memory-graph-filter");
  graph.filter = filterInput?.value || "";
  if (filterInput && !filterInput.__memoryGraphBound) {
    filterInput.__memoryGraphBound = true;
    filterInput.addEventListener("input", () => {
      if (!memoryGraphState) return;
      memoryGraphState.filter = filterInput.value || "";
      memoryGraphApplyFocus(memoryGraphState, memoryGraphState.activeId);
    });
  }
  const fitBtn = document.getElementById("memory-graph-fit-btn");
  if (fitBtn && !fitBtn.__memoryGraphBound) {
    fitBtn.__memoryGraphBound = true;
    fitBtn.addEventListener("click", () => {
      if (!memoryGraphState) return;
      memoryGraphLayout(memoryGraphState.nodes, memoryGraphState.links, memoryGraphState.width, memoryGraphState.height);
      memoryGraphApplyFocus(memoryGraphState, "");
    });
  }

  renderMemoryGraphLegend(graph);
  updateMemoryGraphInspector(null, graph);
  memoryGraphPaint(graph);
  startMemoryGraphAnimation(graph);
  memoryGraphApplyFocus(graph, "");
}

async function refreshMemoryGraphView() {
  const requestId = ++memoryGraphRefreshSeq;
  const empty = document.getElementById("memory-graph-empty");
  if (empty) {
    empty.textContent = "Lade Gedächtnis-Graph...";
    empty.classList.remove("hidden");
  }
  if (!LexaState.get("backendOnline")) {
    renderMemoryGraphEmpty("Backend offline. Graph ist lokal bereit, sobald Lexa verbunden ist.");
    return;
  }
  try {
    const data = typeof window.lexa.memoryGraph === "function"
      ? await window.lexa.memoryGraph(180)
      : { nodes: [], links: [] };
    if (requestId !== memoryGraphRefreshSeq || LexaState.get("currentView") !== "memory") return;
    const graphData = Array.isArray(data?.nodes) && data.nodes.length > 0
      ? data
      : await loadMemoryGraphFallbackData();
    if (requestId !== memoryGraphRefreshSeq || LexaState.get("currentView") !== "memory") return;
    renderMemoryGraph(graphData);
  } catch (error) {
    if (requestId !== memoryGraphRefreshSeq || LexaState.get("currentView") !== "memory") return;
    console.warn("[Memory] Graph render failed:", error.message || error);
    try {
      const fallbackData = await loadMemoryGraphFallbackData();
      if (requestId !== memoryGraphRefreshSeq || LexaState.get("currentView") !== "memory") return;
      renderMemoryGraph(fallbackData);
    } catch (fallbackError) {
      if (requestId !== memoryGraphRefreshSeq || LexaState.get("currentView") !== "memory") return;
      console.warn("[Memory] Graph fallback failed:", fallbackError.message || fallbackError);
      renderMemoryGraphEmpty("Gedächtnis-Graph konnte nicht geladen werden.");
    }
  }
}

// ── MEMORY VIEW ──────────────────────────────────
function createMemoryEmptyState(message) {
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = message || "";
  return empty;
}

function memoryDisplayCount(value) {
  const count = Number(value);
  if (!Number.isFinite(count) || count < 0) return "0";
  return String(Math.floor(count));
}

function createMemoryInfoCard(label, value) {
  const card = document.createElement("div");
  card.className = "info-card";
  const labelEl = document.createElement("div");
  labelEl.className = "info-card-label";
  labelEl.textContent = label || "";
  const valueEl = document.createElement("div");
  valueEl.className = "info-card-value";
  valueEl.textContent = memoryDisplayCount(value);
  card.appendChild(labelEl);
  card.appendChild(valueEl);
  return card;
}

function createMemoryProviderCard(label, detail, available) {
  const card = document.createElement("div");
  card.className = "info-card provider-card";
  const dot = document.createElement("span");
  dot.className = "provider-dot " + (available ? "active" : "inactive");
  const body = document.createElement("div");
  const labelEl = document.createElement("div");
  labelEl.className = "fw-600 text-norm";
  labelEl.textContent = label || "";
  const detailEl = document.createElement("div");
  detailEl.className = "fs-11 text-muted";
  detailEl.textContent = available ? String(detail || t("memory.providerReady")) : t("memory.providerOffline");
  body.appendChild(labelEl);
  body.appendChild(detailEl);
  card.appendChild(dot);
  card.appendChild(body);
  return card;
}

async function refreshMemoryView() {
  await refreshMemoryGraphView();
  return;

  if (!LexaState.get("backendOnline")) return;

  // Fetch all memory data in parallel
  const [statsRes, notesRes, snippetsRes, aiRes, routinesRes] = await Promise.allSettled([
    window.lexa.memoryStats(),
    window.lexa.notes(),
    window.lexa.snippets(),
    window.lexa.aiStatus(),
    window.lexa.routines(),
  ]);

  const stats = statsRes.status === "fulfilled" ? statsRes.value : {};
  const statsGrid = document.getElementById("memory-stats-grid");
  if (statsGrid) {
    statsGrid.replaceChildren(
      createMemoryInfoCard(t("memory.statsNotes"), stats.notes),
      createMemoryInfoCard(t("memory.statsMemories"), stats.memories),
      createMemoryInfoCard(t("memory.statsChats"), stats.conversations),
      createMemoryInfoCard(t("memory.statsInteractions"), stats.interactions),
      createMemoryInfoCard(t("memory.statsRoutines"), stats.routines),
      createMemoryInfoCard(t("memory.statsClipboard"), stats.clipboard_entries),
    );
  }

  const notesData = notesRes.status === "fulfilled" ? notesRes.value : { notes: [] };
  const notesList = document.getElementById("notes-list");
  if (notesList) {
    if (notesData.notes?.length > 0) {
      notesList.replaceChildren();
      notesData.notes.forEach(n => {
        const card = document.createElement("div");
        card.className = "note-card note-card-clickable";
        card.title = t("memory.clickToEditTooltip");

        const titleEl = document.createElement("div");
        titleEl.className = "note-title";
        titleEl.textContent = n.title || "";
        card.appendChild(titleEl);

        const metaEl = document.createElement("div");
        metaEl.className = "note-meta";
        metaEl.textContent = (n.category || "") + " \u00b7 " + (n.created_at || "");
        card.appendChild(metaEl);

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "note-delete-btn";
        delBtn.title = t("memory.deleteNoteTooltip");
        delBtn.setAttribute("aria-label", t("memory.deleteNoteLabel", { title: n.title || "" }));
        delBtn.textContent = "\u00d7";
        delBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          if (_noteDeleteRunning) return;
          _noteDeleteRunning = true;
          setMemoryActionBusy(delBtn, true);
          try {
            const result = await showInputModal(t("common.confirm"), [
              { name: "confirm", label: t("memory.noteDeleteConfirm", {title: n.title}), type: "text", required: true }
            ], t("common.confirm"));
            if (!result || result.confirm.toLowerCase() !== "ja") return;
            await window.lexa.execute("note_delete", { title: n.title }, true);
            showToast(t("notes.deleted"), "info");
            refreshMemoryView();
          } catch (err) {
            console.warn("[Memory] Failed to delete note:", err.message || err);
            showToast(t("toast.executionError"), "error", 2200);
          } finally {
            _noteDeleteRunning = false;
            if (delBtn?.isConnected) setMemoryActionBusy(delBtn, false);
          }
        });
        card.appendChild(delBtn);

        bindMemoryCardAction(card, () => openNoteModal(n.id, n.title), t("memory.openNoteLabel", { title: n.title || "" }));
        notesList.appendChild(card);
      });
    } else {
      notesList.replaceChildren(createMemoryEmptyState(t("memory.emptyNotes")));
    }
  }

  // Snippets
  try {
    const snippetsData = snippetsRes.status === "fulfilled" ? snippetsRes.value : { snippets: [] };
    const snippetsList = document.getElementById("snippets-list");
    if (snippetsList) {
      if (snippetsData.snippets?.length > 0) {
        snippetsList.replaceChildren();
        snippetsData.snippets.forEach(s => {
          const card = document.createElement("div");
          card.className = "note-card snippet-card";
          const snippetText = String(s.text || "");
          const preview = snippetText.length > 50 ? snippetText.substring(0, 50) + "\u2026" : snippetText;
          const title = document.createElement("div");
          title.className = "note-title";
          title.textContent = s.name || "";
          const meta = document.createElement("div");
          meta.className = "note-meta";
          meta.textContent = preview;
          const deleteBtn = document.createElement("button");
          deleteBtn.type = "button";
          deleteBtn.className = "snippet-delete";
          deleteBtn.title = t("memory.deleteSnippetTooltip");
          deleteBtn.setAttribute("aria-label", t("memory.deleteSnippetLabel", { name: s.name || "" }));
          deleteBtn.textContent = "\u00d7";
          card.appendChild(title);
          card.appendChild(meta);
          card.appendChild(deleteBtn);
          bindMemoryCardAction(card, () => useSnippet(snippetText), t("memory.useSnippetLabel", { name: s.name || "" }));
          deleteBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            deleteSnippet(s.name, deleteBtn);
          });
          snippetsList.appendChild(card);
        });
      } else {
        snippetsList.replaceChildren(createMemoryEmptyState(t("memory.emptySnippets")));
      }
    }
  } catch (e) { console.warn("[Memory] Failed to render snippets:", e.message || e); }

  const aiStatus = aiRes.status === "fulfilled" ? aiRes.value : {
    groq: { available: false },
    openai: { available: false },
    gemini: { available: false },
  };
  const aiPanel = document.getElementById("ai-status-panel");
  if (aiPanel) {
    const providers = [
      ["groq", "Groq API", aiStatus.groq?.model_name || t("memory.groqFallback")],
      ["openai", "OpenAI API", aiStatus.openai?.model_name || t("memory.openaiFallback")],
      ["gemini", "Gemini API", aiStatus.gemini?.model_name || t("memory.geminiFallback")],
    ];
    const fragment = document.createDocumentFragment();
    providers.forEach(([key, label, detail]) => {
      fragment.appendChild(createMemoryProviderCard(label, detail, Boolean(aiStatus[key]?.available)));
    });
    aiPanel.replaceChildren(fragment);
  }

  const routinesData = routinesRes.status === "fulfilled" ? routinesRes.value : { routines: [] };
  const routinesList = document.getElementById("routines-list");
  if (routinesList) {
    if (routinesData.routines?.length > 0) {
      routinesList.replaceChildren();
      routinesData.routines.forEach(r => {
        const card = document.createElement("div");
        card.className = "routine-card";
        const info = document.createElement("div");
        info.className = "routine-info";
        const name = document.createElement("div");
        name.className = "routine-name";
        name.textContent = r.name || "";
        const schedule = document.createElement("div");
        schedule.className = "routine-schedule";
        schedule.textContent = (r.schedule || "") + (r.description ? ` \u00b7 ${r.description}` : "");
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "routine-toggle" + (r.enabled ? " enabled" : "");
        toggle.setAttribute("aria-pressed", r.enabled ? "true" : "false");
        toggle.setAttribute("aria-label", t("memory.toggleRoutineLabel", { name: r.name || "" }));
        info.appendChild(name);
        info.appendChild(schedule);
        card.appendChild(info);
        card.appendChild(toggle);
        toggle.addEventListener("click", () => toggleRoutine(r.name, toggle));
        routinesList.appendChild(card);
      });
    } else {
      routinesList.replaceChildren(createMemoryEmptyState(t("memory.emptyRoutines")));
    }
  }

  renderClipboardPrivacyPrompt();

  // Add cleanup info
  const cleanupEl = document.getElementById("memory-cleanup-info");
  if (cleanupEl) {
    cleanupEl.replaceChildren();
    const cleanBtn = document.createElement("button");
    cleanBtn.type = "button";
    cleanBtn.className = "action-btn memory-cleanup-btn";
    cleanBtn.textContent = t("memory.cleanupBtn", {count: parseInt(stats.memories) || 0});
    cleanBtn.addEventListener("click", runMemoryCleanup);
    cleanupEl.appendChild(cleanBtn);
  }
}

function renderClipboardEntries(entries = []) {
  const cbList = document.getElementById("clipboard-history-list");
  if (!cbList) return;
  if (entries.length > 0) {
    cbList.replaceChildren();
    entries.slice(0, 20).forEach(e => {
      const preview = String(e.text || "").substring(0, 80);
      const card = document.createElement("div");
      card.className = "note-card clipboard-entry";
      const title = document.createElement("div");
      title.className = "note-title";
      title.textContent = preview + ((e.text?.length > 80) ? "\u2026" : "");
      const meta = document.createElement("div");
      meta.className = "note-meta";
      meta.textContent = String(e.created_at || "").substring(0, 16);
      card.appendChild(title);
      card.appendChild(meta);
      const rawText = e.text || "";
      bindMemoryCardAction(card, () => {
        window.lexa.execute("clipboard_write", { text: rawText }, true);
        showToast(t("toast.clipboardCopied"), "success", 2000);
      }, t("memory.copyClipboardLabel"));
      cbList.appendChild(card);
    });
  } else {
    cbList.replaceChildren(createMemoryEmptyState(t("memory.emptyClipboard")));
  }
}

function renderClipboardPrivacyPrompt() {
  const cbList = document.getElementById("clipboard-history-list");
  if (!cbList) return;
  const card = document.createElement("div");
  card.className = "empty-state";
  const hint = document.createElement("div");
  hint.textContent = t("memory.clipboardPrivacyHint");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "action-btn mt-2";
  button.textContent = t("memory.revealClipboardHistory");
  button.addEventListener("click", (event) => revealClipboardHistory(event.currentTarget));
  card.appendChild(hint);
  card.appendChild(button);
  cbList.replaceChildren(card);
}

async function revealClipboardHistory(triggerBtn) {
  if (_clipboardHistoryRevealRunning) return;
  _clipboardHistoryRevealRunning = true;
  setMemoryActionBusy(triggerBtn, true);
  try {
    const cbData = await window.lexa.clipboardHistory();
    renderClipboardEntries(Array.isArray(cbData?.entries) ? cbData.entries : []);
  } catch (e) {
    console.warn("[Memory] Failed to reveal clipboard history:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _clipboardHistoryRevealRunning = false;
    if (triggerBtn?.isConnected) setMemoryActionBusy(triggerBtn, false);
  }
}

async function clearClipboardHistory() {
  await window.lexa.clipboardClear();
  showToast(t("toast.clipboardCleared"), "info");
  refreshMemoryView();
}

function createNote() {
  quickCreateNote();
}

function quickCreateNote() {
  // Open an inline modal for fast note creation (Ctrl+Shift+N)
  document.getElementById("note-modal")?.remove();

  const overlay = document.createElement("div");
  overlay.id = "note-modal";
  overlay.className = "note-modal-overlay";

  const panel = document.createElement("div");
  panel.className = "note-modal-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", t("notes.newNote"));

  const header = document.createElement("div");
  header.className = "note-modal-header";
  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.className = "note-modal-title-input";
  titleInput.placeholder = t("memory.noteTitlePlaceholder");
  header.appendChild(titleInput);
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "note-modal-close";
  closeBtn.setAttribute("aria-label", t("common.close"));
  closeBtn.textContent = "\u00d7";
  const escHandler = (e) => { if (e.key === "Escape") _closeOverlay(overlay, escHandler); };
  closeBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const textarea = document.createElement("textarea");
  textarea.className = "note-modal-textarea";
  textarea.placeholder = t("memory.noteContentPlaceholder");
  panel.appendChild(textarea);

  const footer = document.createElement("div");
  footer.className = "note-modal-footer";
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "action-btn";
  saveBtn.textContent = t("common.save");
  saveBtn.addEventListener("click", async () => {
    const ti = titleInput.value.trim();
    const c = textarea.value.trim();
    if (!ti) { showToast(t("notes.titleEmpty"), "error"); return; }
    if (!c) { showToast(t("notes.contentEmpty"), "error"); return; }
    await window.lexa.execute("note_create", { title: ti, content: c }, true);
    showToast(t("notes.created"), "success");
    _closeOverlay(overlay, escHandler);
    if (LexaState.get("currentView") === "memory") refreshMemoryView();
  });
  footer.appendChild(saveBtn);
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "action-btn action-btn-secondary";
  cancelBtn.textContent = t("common.cancel");
  cancelBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  footer.appendChild(cancelBtn);
  panel.appendChild(footer);
  overlay.appendChild(panel);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) _closeOverlay(overlay, escHandler); });
  document.addEventListener("keydown", escHandler);
  document.body.appendChild(overlay);
  titleInput.focus();
}

async function createRoutine() {
  switchView("chat");
  chatInput.value = t("memory.createRoutinePrompt");
  chatInput.focus();
}

async function toggleRoutine(name, triggerBtn) {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  if (_routineToggleRunning) return;
  _routineToggleRunning = true;
  setMemoryActionBusy(triggerBtn, true);
  try {
    await window.lexa.execute("routine_toggle", { name }, true);
    showToast(t("memory.routineToggled", {name}), "info");
    refreshMemoryView();
  } catch (e) {
    console.warn("[Memory] Failed to toggle routine:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _routineToggleRunning = false;
    if (triggerBtn?.isConnected) setMemoryActionBusy(triggerBtn, false);
  }
}

function filterNotes(query) {
  const cards = document.querySelectorAll("#notes-list .note-card");
  const q = query.toLowerCase().trim();
  cards.forEach(card => {
    const title = card.querySelector(".note-title")?.textContent.toLowerCase() || "";
    const meta = card.querySelector(".note-meta")?.textContent.toLowerCase() || "";
    card.classList.toggle("hidden", !(!q || title.includes(q) || meta.includes(q)));
  });
}

async function openNoteModal(noteId, noteTitle) {
  // Fetch full note content
  const note = await window.lexa.noteGet(noteId);
  if (!note || note.error) {
    showToast(t("notes.loadFailed"), "error");
    return;
  }

  // Remove any existing note modal
  document.getElementById("note-modal")?.remove();

  const overlay = document.createElement("div");
  overlay.id = "note-modal";
  overlay.className = "note-modal-overlay";

  const panel = document.createElement("div");
  panel.className = "note-modal-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", t("notes.editNote"));

  const header = document.createElement("div");
  header.className = "note-modal-header";

  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.className = "note-modal-title-input";
  titleInput.value = note.title || "";
  header.appendChild(titleInput);

  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "note-modal-close";
  closeBtn.setAttribute("aria-label", t("common.close"));
  closeBtn.textContent = "\u00d7";
  const escHandler = (e) => { if (e.key === "Escape") _closeOverlay(overlay, escHandler); };
  closeBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const metaEl = document.createElement("div");
  metaEl.className = "note-modal-meta";
  metaEl.textContent = (note.category || "general") + " \u00b7 " + (note.created_at || "");
  panel.appendChild(metaEl);

  const textarea = document.createElement("textarea");
  textarea.className = "note-modal-textarea";
  textarea.value = note.content || "";
  textarea.placeholder = t("memory.noteContentPlaceholderShort");
  panel.appendChild(textarea);

  const footer = document.createElement("div");
  footer.className = "note-modal-footer";

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "action-btn";
  saveBtn.textContent = t("common.save");
  saveBtn.addEventListener("click", async () => {
    const newTitle = titleInput.value.trim();
    const newContent = textarea.value.trim();
    if (!newTitle) { showToast(t("notes.titleEmpty"), "error"); return; }
    const result = await window.lexa.noteUpdate(noteId, { title: newTitle, content: newContent });
    if (result?.status === "ok") {
      showToast(t("notes.saved"), "success");
      _closeOverlay(overlay, escHandler);
      refreshMemoryView();
    } else {
      showToast(t("notes.saveFailed"), "error");
    }
  });
  footer.appendChild(saveBtn);

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "action-btn action-btn-secondary";
  cancelBtn.textContent = t("common.cancel");
  cancelBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  footer.appendChild(cancelBtn);

  panel.appendChild(footer);
  overlay.appendChild(panel);

  overlay.addEventListener("click", (e) => { if (e.target === overlay) _closeOverlay(overlay, escHandler); });
  document.addEventListener("keydown", escHandler);

  document.body.appendChild(overlay);
  textarea.focus();
}

// ── CLIPBOARD HISTORY & SNIPPETS (Phase 16) ─────
async function trackClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text && text.trim()) {
      await window.lexa.clipboardAdd(text.trim().substring(0, 1000));
    }
  } catch (e) { console.warn("[Memory] Failed to track clipboard:", e.message || e); }
}

function createSnippet() {
  document.getElementById("snippet-create-modal")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "snippet-create-modal";
  overlay.className = "note-modal-overlay";

  const panel = document.createElement("div");
  panel.className = "note-modal-panel note-modal-panel-narrow";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", t("memory.newSnippetTitle"));

  const header = document.createElement("div");
  header.className = "note-modal-header";
  const hTitle = document.createElement("div");
  hTitle.className = "note-modal-heading";
  hTitle.textContent = t("memory.newSnippetTitle");
  header.appendChild(hTitle);
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "note-modal-close";
  closeBtn.setAttribute("aria-label", t("common.close"));
  closeBtn.textContent = "\u00d7";
  const escHandler = (e) => { if (e.key === "Escape") _closeOverlay(overlay, escHandler); };
  closeBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const form = document.createElement("div");
  form.className = "note-modal-form";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.placeholder = t("memory.snippetNamePlaceholder");
  nameInput.className = "settings-input";
  form.appendChild(nameInput);

  const textArea = document.createElement("textarea");
  textArea.placeholder = t("memory.snippetTextPlaceholder");
  textArea.className = "note-modal-textarea note-modal-textarea-compact";
  form.appendChild(textArea);
  panel.appendChild(form);

  const footer = document.createElement("div");
  footer.className = "note-modal-footer";
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "action-btn";
  saveBtn.textContent = t("common.save");
  saveBtn.addEventListener("click", async () => {
    const name = nameInput.value.trim();
    const text = textArea.value.trim();
    if (!name) { showToast(t("snippets.nameEmpty"), "error"); return; }
    if (!text) { showToast(t("snippets.textEmpty"), "error"); return; }
    await window.lexa.snippetCreate(name, text);
    invalidateSnippetCache();
    showToast(t("snippets.saved"), "success");
    _closeOverlay(overlay, escHandler);
    refreshMemoryView();
  });
  footer.appendChild(saveBtn);
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "action-btn action-btn-secondary";
  cancelBtn.textContent = t("common.cancel");
  cancelBtn.addEventListener("click", () => _closeOverlay(overlay, escHandler));
  footer.appendChild(cancelBtn);
  panel.appendChild(footer);
  overlay.appendChild(panel);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) _closeOverlay(overlay, escHandler); });
  document.addEventListener("keydown", escHandler);
  document.body.appendChild(overlay);
  nameInput.focus();
}

async function deleteSnippet(name, triggerBtn) {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  if (_snippetDeleteRunning) return;
  _snippetDeleteRunning = true;
  setMemoryActionBusy(triggerBtn, true);
  try {
    await window.lexa.snippetDelete(name);
    invalidateSnippetCache();
    showToast(t("snippets.deleted"), "info");
    refreshMemoryView();
  } catch (e) {
    console.warn("[Memory] Failed to delete snippet:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _snippetDeleteRunning = false;
    if (triggerBtn?.isConnected) setMemoryActionBusy(triggerBtn, false);
  }
}

async function useSnippet(text) {
  chatInput.value = text;
  chatInput.focus();
  switchView("chat");
  showToast(t("snippets.inserted"), "info", 1500);
}

// ── DIAGNOSTICS ──────────────────────────────────
async function showDiagnostics() {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  try {
    const d = await window.lexa.diagnostics();
    const lines = [
      `Version: ${d.version}`,
      `Python: ${d.python}`,
      `DB: ${d.db_size_kb} KB`,
      `Audit-Log: ${d.audit_log_size_kb} KB`,
      t("memory.diagChatHistory", {count: d.conversation_history_len}),
      `Memories: ${d.memory?.memories || 0}`,
      `Notes: ${d.memory?.notes || 0}`,
      `Conversations: ${d.memory?.conversations || 0}`,
      t("memory.diagAiProvider", {provider: d.ai?.active_provider || t("memory.diagAiUnknown")}),
      `Scheduler: ${d.scheduler?.running ? t("memory.diagSchedulerActive") : t("memory.diagSchedulerInactive")}`,
    ].join('\n');
    addMessage('\uD83D\uDCCA Diagnostics:\n```\n' + lines + '\n```', 'system');
    switchView('chat');
  } catch (e) {
    showToast(t("memory.diagnosticsError", {error: e.message}), 'error');
  }
}

async function runMemoryCleanup() {
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  if (_memoryCleanupRunning) return;
  _memoryCleanupRunning = true;
  setMemoryActionButtonsBusy("runMemoryCleanup", true);
  try {
    const d = await window.lexa.memoryCleanup(90, 3);
    showToast(t("memory.cleanupDone", {count: d.deleted}), d.deleted > 0 ? "success" : "info");
  } catch (e) {
    showToast(t("memory.cleanupFailed", {error: e.message}), "error");
  } finally {
    _memoryCleanupRunning = false;
    setMemoryActionButtonsBusy("runMemoryCleanup", false);
  }
}
