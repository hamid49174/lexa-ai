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
    hub: "#dbeafe",
    group: "#7dd3fc",
    type: "#818cf8",
    keyword: "#38bdf8",
    note: "#8b9cff",
    memory: "#c4b5fd",
    conversation: "#60a5fa",
    routine: "#22d3ee",
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
    if (titleEl) titleEl.textContent = `${graph?.nodes?.length || 0} Knoten · ${graph?.links?.length || 0} Linien`;
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

function memoryGraphUnit(value) {
  return (memoryGraphHash(value) % 10000) / 10000;
}

function memoryGraphCloudPoint(index, total, width, height) {
  const seed = memoryGraphHash(`neural-cloud:${index}`);
  const angle = index * MEMORY_GRAPH_GOLDEN_ANGLE + memoryGraphUnit(`angle:${seed}`) * 0.45;
  const radius = Math.pow((index + 0.5) / Math.max(1, total), 0.48) * (0.88 + memoryGraphUnit(`r:${seed}`) * 0.18);
  const rx = width * (0.31 + memoryGraphUnit(`rx:${seed}`) * 0.08);
  const ry = height * (0.30 + memoryGraphUnit(`ry:${seed}`) * 0.08);
  const lobe = Math.sin(angle * 2.1) * width * 0.025;
  const x = width * 0.5 + Math.cos(angle) * rx * radius + lobe;
  const y = height * 0.52 + Math.sin(angle) * ry * radius + Math.sin(angle * 3.2) * height * 0.018;
  return {
    x: Math.max(width * 0.08, Math.min(width * 0.92, x)),
    y: Math.max(height * 0.08, Math.min(height * 0.92, y)),
    seed,
  };
}

function memoryGraphCreateNeuralCloud(svg, width, height, nodeCount, linkCount) {
  const pointCount = Math.max(160, Math.min(360, Math.round(nodeCount * 3.2 + linkCount * 0.9 + 140)));
  const filamentCount = Math.max(260, Math.min(720, Math.round(pointCount * 1.85)));
  const points = Array.from({ length: pointCount }, (_item, index) => memoryGraphCloudPoint(index, pointCount, width, height));
  const layer = memoryGraphCreateSvgElement("g", {
    class: "memory-graph-neural-cloud",
    "aria-hidden": "true",
  });
  const filamentLayer = memoryGraphCreateSvgElement("g", { class: "memory-graph-neural-filaments" });
  const dotLayer = memoryGraphCreateSvgElement("g", { class: "memory-graph-neural-dots" });

  for (let index = 0; index < filamentCount; index += 1) {
    const sourceIndex = index % pointCount;
    const seed = memoryGraphHash(`filament:${index}:${pointCount}`);
    const hop = 1 + (seed % 17) + Math.floor(index / pointCount) * 3;
    let targetIndex = (sourceIndex + hop) % pointCount;
    const source = points[sourceIndex];
    let target = points[targetIndex];
    let dx = target.x - source.x;
    let dy = target.y - source.y;
    let distance = Math.sqrt(dx * dx + dy * dy);
    if (distance > Math.min(width, height) * 0.42) {
      targetIndex = (sourceIndex + 1 + (index % 5)) % pointCount;
      target = points[targetIndex];
      dx = target.x - source.x;
      dy = target.y - source.y;
      distance = Math.sqrt(dx * dx + dy * dy);
    }
    if (distance > Math.min(width, height) * 0.48) continue;
    const filament = memoryGraphCreateSvgElement("line", {
      class: "memory-graph-neural-filament",
      x1: source.x.toFixed(1),
      y1: source.y.toFixed(1),
      x2: target.x.toFixed(1),
      y2: target.y.toFixed(1),
      "stroke-opacity": (0.08 + memoryGraphUnit(`opacity:${seed}`) * 0.16).toFixed(2),
    });
    filamentLayer.appendChild(filament);
  }

  points.forEach((point, index) => {
    const hub = index % 29 === 0 || index % 43 === 0;
    const dot = memoryGraphCreateSvgElement("circle", {
      class: hub ? "memory-graph-neural-dot memory-graph-neural-dot-hub" : "memory-graph-neural-dot",
      cx: point.x.toFixed(1),
      cy: point.y.toFixed(1),
      r: (hub ? 1.8 + memoryGraphUnit(`hub:${point.seed}`) * 1.7 : 0.55 + memoryGraphUnit(`dot:${point.seed}`) * 0.9).toFixed(2),
    });
    dotLayer.appendChild(dot);
  });

  layer.append(filamentLayer, dotLayer);
  svg.appendChild(layer);
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
    node.labelEl?.classList.toggle("is-visible", matches && (node.id === activeId || node.type === "hub" || node.weight >= 8.5));
  });
  graph.links.forEach((link) => {
    const visible = !activeId || link.source === activeId || link.target === activeId;
    link.el?.classList.toggle("is-dim", !visible);
    link.el?.classList.toggle("is-active", visible && Boolean(activeId));
  });
}

function memoryGraphLayout(nodes, links, width, height) {
  const groups = [...new Set(nodes.map((node) => node.group || node.type))].sort();
  const groupAngles = new Map(groups.map((group, index) => [group, -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(1, groups.length)]));
  nodes.forEach((node, index) => {
    const seed = memoryGraphHash(node.id);
    const groupAngle = groupAngles.get(node.group) ?? 0;
    const cloudAngle = index * MEMORY_GRAPH_GOLDEN_ANGLE + memoryGraphUnit(`layout:${node.id}`) * 0.7;
    const cloudRadius = node.type === "hub"
      ? 0
      : Math.min(width, height) * (0.08 + Math.pow(memoryGraphUnit(`radius:${node.id}`), 0.55) * 0.34);
    const groupPull = node.type === "hub" ? 0 : Math.min(width, height) * 0.11;
    const anchorX = width / 2
      + Math.cos(cloudAngle) * cloudRadius * 1.18
      + Math.cos(groupAngle) * groupPull;
    const anchorY = height / 2
      + Math.sin(cloudAngle) * cloudRadius * 0.86
      + Math.sin(groupAngle) * groupPull * 0.72;
    node.anchorX = Math.max(width * 0.12, Math.min(width * 0.88, anchorX));
    node.anchorY = Math.max(height * 0.12, Math.min(height * 0.88, anchorY));
    node.x = node.anchorX;
    node.y = node.anchorY;
    node.vx = 0;
    node.vy = 0;
    node.radius = Math.max(2.4, Math.min(12.5, 2.8 + node.weight * 0.95));
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
  const centerX = width / 2;
  const centerY = height / 2;
  const phase = Date.now() / 9000;

  links.forEach((link) => {
    const a = link.sourceNode;
    const b = link.targetNode;
    if (!a || !b) return;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const desired = link.kind === "contains" ? 62 : link.kind === "mentions" ? 86 : 112;
    const pull = (dist - desired) * 0.005 * link.weight;
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
      const force = (a.radius + b.radius + 22) / distSq;
      const fx = dx * force;
      const fy = dy * force;
      if (!a.fixed) { a.vx -= fx; a.vy -= fy; }
      if (!b.fixed) { b.vx += fx; b.vy += fy; }
    }
  }

  nodes.forEach((node) => {
    const nodeSeed = memoryGraphHash(node.id);
    const drift = node.type === "hub" ? 0 : 3.8;
    const anchorX = (node.anchorX || centerX) + Math.cos(phase + nodeSeed) * drift;
    const anchorY = (node.anchorY || centerY) + Math.sin(phase + nodeSeed) * drift;
    if (!node.fixed) {
      node.vx += (anchorX - node.x) * 0.0026;
      node.vy += (anchorY - node.y) * 0.0026;
      node.vx *= 0.85;
      node.vy *= 0.85;
      node.x += node.vx;
      node.y += node.vy;
      node.x = Math.max(width * 0.07, Math.min(width * 0.93, node.x));
      node.y = Math.max(height * 0.08, Math.min(height * 0.92, node.y));
    }
  });
}

function memoryGraphPaint(graph) {
  graph.links.forEach((link) => {
    if (!link.sourceNode || !link.targetNode) return;
    link.el.setAttribute("x1", link.sourceNode.x.toFixed(1));
    link.el.setAttribute("y1", link.sourceNode.y.toFixed(1));
    link.el.setAttribute("x2", link.targetNode.x.toFixed(1));
    link.el.setAttribute("y2", link.targetNode.y.toFixed(1));
  });
  graph.nodes.forEach((node) => {
    node.el.setAttribute("cx", node.x.toFixed(1));
    node.el.setAttribute("cy", node.y.toFixed(1));
    node.labelEl.setAttribute("x", (node.x + node.radius + 7).toFixed(1));
    node.labelEl.setAttribute("y", (node.y + 4).toFixed(1));
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
  const filter = memoryGraphCreateSvgElement("filter", { id: "memory-graph-glow", x: "-50%", y: "-50%", width: "200%", height: "200%" });
  filter.appendChild(memoryGraphCreateSvgElement("feGaussianBlur", { stdDeviation: "3.5", result: "coloredBlur" }));
  const merge = memoryGraphCreateSvgElement("feMerge");
  merge.appendChild(memoryGraphCreateSvgElement("feMergeNode", { in: "coloredBlur" }));
  merge.appendChild(memoryGraphCreateSvgElement("feMergeNode", { in: "SourceGraphic" }));
  filter.appendChild(merge);
  defs.appendChild(filter);
  svg.appendChild(defs);
  memoryGraphCreateNeuralCloud(svg, width, height, nodes.length, links.length);

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
    const el = memoryGraphCreateSvgElement("line", {
      class: `memory-graph-link memory-graph-link-${link.kind}`,
      "data-kind": link.kind,
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
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  try {
    await window.lexa.clipboardClear();
    showToast(t("toast.clipboardCleared"), "info");
    refreshMemoryView();
  } catch (e) {
    console.warn("[Memory] Failed to clear clipboard history:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  }
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
// Erkennt wahrscheinlich sensible Zwischenablage-Inhalte (Schlüssel/Tokens/Passwörter),
// damit diese nicht in die lokale Historie persistiert werden.
function isLikelySensitiveClipboard(text) {
  const value = String(text || "").trim();
  if (!value) return false;
  // Bekannte Schlüssel-/Token-Präfixe (Stripe, OpenAI, GitHub, Slack, AWS, Bearer, JWT ...).
  if (/\b(sk|pk|rk)_[a-z0-9]/i.test(value)) return true;
  if (/\b(gh[pousr]|xox[baprs]|AKIA|ASIA|ya29|eyJ[A-Za-z0-9_-]{10,})/i.test(value)) return true;
  if (/\bBearer\s+[A-Za-z0-9._-]{16,}/i.test(value)) return true;
  if (/\b(api[_-]?key|secret|token|passwor[dt])\b\s*[:=]/i.test(value)) return true;
  // Lange, leerzeichenfreie Hex-/Base64-artige Strings (typisch für Keys/Hashes).
  if (/^[A-Za-z0-9+/=_-]{40,}$/.test(value) && !/\s/.test(value)) return true;
  return false;
}

async function trackClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    const trimmed = text ? text.trim() : "";
    if (!trimmed) return;
    // Sensible Inhalte (Schlüssel/Tokens/Passwörter) bewusst NICHT speichern.
    if (isLikelySensitiveClipboard(trimmed)) {
      console.info("[Memory] Skipped clipboard capture: content looks sensitive.");
      return;
    }
    await window.lexa.clipboardAdd(trimmed.substring(0, 1000));
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
  // Destructive action: require explicit confirmation before deleting memories.
  // Kriterien werden genannt; "ja" muss explizit eingegeben werden (analog Notiz-/Snippet-Löschung).
  const confirmLabel = `${t("memory.cleanupOld")} — Erinnerungen älter als 90 Tage mit Wichtigkeit < 3 werden unwiderruflich gelöscht. Zum Bestätigen "ja" eingeben.`;
  const confirmResult = await showInputModal(t("common.confirm"), [
    { name: "confirm", label: confirmLabel, type: "text", required: true }
  ], t("common.confirm"));
  if (!confirmResult || confirmResult.confirm.trim().toLowerCase() !== "ja") return;
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
