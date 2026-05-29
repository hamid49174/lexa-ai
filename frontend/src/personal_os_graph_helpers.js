/* Personal OS context graph helpers. Classic script loaded before personal_os.js. */

function createPersonalOsSvgElement(tagName, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tagName);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === null || value === undefined || value === false) continue;
    element.setAttribute(name, String(value));
  }
  return element;
}

function createPersonalOsGraphExplorerView() {
  const explorer = document.createElement("div");
  explorer.className = "pos-graph-explorer";

  const filesColumn = document.createElement("div");
  const files = document.createElement("div");
  files.className = "pos-graph-files";
  files.id = "pos-graph-files";
  filesColumn.append(
    createPersonalOsTextElement("div", "pos-label", posUiText("pos.graphLaneImportantFiles", "Important Files")),
    files
  );

  const hubsColumn = document.createElement("div");
  const hubs = document.createElement("div");
  hubs.className = "pos-graph-hubs";
  hubs.id = "pos-graph-hubs";
  hubsColumn.append(
    createPersonalOsTextElement("div", "pos-label", posUiText("pos.labelHubs", "Hubs")),
    hubs
  );

  explorer.append(filesColumn, hubsColumn);
  return explorer;
}

function createPersonalOsGraphLegendItem(iconClass, label) {
  const item = document.createElement("span");
  const icon = document.createElement("i");
  icon.className = iconClass;
  item.append(icon, document.createTextNode(label));
  return item;
}

function createPersonalOsGraphLane(svg, rectAttrs, label, labelX, labelY) {
  svg.appendChild(createPersonalOsSvgElement("rect", { class: "pos-graph-lane-bg", ...rectAttrs }));
  const text = createPersonalOsSvgElement("text", { class: "pos-graph-lane", x: labelX, y: labelY });
  text.textContent = label;
  svg.appendChild(text);
}

function createPersonalOsGraphEdgeElement(edge, source, target) {
  const edgeClass = edge.type === "tag" ? "pos-graph-edge pos-graph-edge-tag" : "pos-graph-edge";
  const midX = source.x + ((target.x - source.x) * 0.5);
  return createPersonalOsSvgElement("path", {
    class: edgeClass,
    "data-source": edge.source,
    "data-target": edge.target,
    d: `M ${source.x.toFixed(1)} ${source.y.toFixed(1)} C ${midX.toFixed(1)} ${source.y.toFixed(1)}, ${midX.toFixed(1)} ${target.y.toFixed(1)}, ${target.x.toFixed(1)} ${target.y.toFixed(1)}`,
  });
}

function createPersonalOsGraphNodeElement(node, point) {
  const isFile = node.kind === "file";
  const nodeWidth = isFile ? 220 : (node.kind === "reference" ? 190 : 170);
  const nodeHeight = isFile ? 34 : 28;
  const group = createPersonalOsSvgElement("g", {
    class: `pos-graph-node ${posGraphNodeClass(node.kind)}`,
    "data-node-id": node.id,
    tabindex: "0",
    transform: `translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})`,
    "aria-label": posGraphLabel(node),
  });
  if (isFile && node.path) {
    group.setAttribute("data-path", node.path);
    group.setAttribute("role", "button");
  }

  const label = createPersonalOsSvgElement("text", { x: (-nodeWidth / 2 + 30).toFixed(1), y: "4" });
  label.textContent = posGraphDisplayName(node, isFile ? 28 : 22);
  const degree = createPersonalOsSvgElement("text", { class: "pos-graph-degree", x: (nodeWidth / 2 - 16).toFixed(1), y: "4" });
  degree.textContent = String(Number(node.degree || 0));
  const title = createPersonalOsSvgElement("title");
  title.textContent = posGraphLabel(node);

  group.append(
    createPersonalOsSvgElement("rect", {
      x: (-nodeWidth / 2).toFixed(1),
      y: (-nodeHeight / 2).toFixed(1),
      width: nodeWidth,
      height: nodeHeight,
      rx: "8",
    }),
    createPersonalOsSvgElement("circle", { cx: (-nodeWidth / 2 + 14).toFixed(1), r: "5" }),
    label,
    createPersonalOsSvgElement("rect", {
      class: "pos-graph-degree-bg",
      x: (nodeWidth / 2 - 34).toFixed(1),
      y: "-10",
      width: "26",
      height: "18",
      rx: "9",
    }),
    degree,
    title
  );
  return group;
}

function createPersonalOsGraphNetworkView(width, height, visibleNodes, visibleEdges, positions) {
  const network = document.createElement("div");
  network.className = "pos-graph-network";
  const head = document.createElement("div");
  head.className = "pos-graph-network-head";
  const copy = document.createElement("div");
  copy.append(
    createPersonalOsTextElement("span", "pos-label", posUiText("pos.labelRelationshipMap", "Relationship Map")),
    createPersonalOsTextElement("span", "pos-draft-path", posUiText("pos.graphShown", `${visibleNodes.length} nodes / ${visibleEdges.length} edges shown`, { nodes: visibleNodes.length, edges: visibleEdges.length }))
  );

  const legend = document.createElement("div");
  legend.className = "pos-graph-legend";
  legend.setAttribute("aria-label", posUiText("pos.graphLegendLabel", "Context Map legend"));
  legend.append(
    createPersonalOsGraphLegendItem("pos-graph-legend-file", posUiText("pos.graphLegendFiles", "Files")),
    createPersonalOsGraphLegendItem("pos-graph-legend-tag", posUiText("pos.graphLegendTags", "Tags")),
    createPersonalOsGraphLegendItem("pos-graph-legend-ref", posUiText("pos.graphLegendRefs", "Refs")),
    createPersonalOsGraphLegendItem("pos-graph-legend-edge", posUiText("pos.graphLegendLinks", "Links"))
  );
  head.append(copy, legend);

  const svg = createPersonalOsSvgElement("svg", {
    class: "pos-graph-svg",
    viewBox: `0 0 ${width} ${height}`,
    role: "img",
    "aria-label": posUiText("pos.graphAriaLabel", "Personal OS Context Map"),
  });
  svg.appendChild(createPersonalOsSvgElement("rect", { class: "pos-graph-bg", x: "0", y: "0", width, height, rx: "8" }));
  createPersonalOsGraphLane(svg, { x: "30", y: "42", width: "550", height: "352", rx: "14" }, posUiText("pos.graphLaneImportantFiles", "Important Files"), "54", "66");
  createPersonalOsGraphLane(svg, { x: "640", y: "42", width: "250", height: "232", rx: "14" }, posUiText("pos.graphLaneTags", "Tags"), "664", "66");
  createPersonalOsGraphLane(svg, { x: "900", y: "274", width: "230", height: "120", rx: "14" }, posUiText("pos.graphLaneRefs", "Refs"), "924", "298");

  for (const edge of visibleEdges) {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (source && target) svg.appendChild(createPersonalOsGraphEdgeElement(edge, source, target));
  }
  for (const node of visibleNodes) {
    svg.appendChild(createPersonalOsGraphNodeElement(node, positions.get(node.id) || { x: 40, y: 40 }));
  }
  network.append(head, svg);
  return network;
}

function createPersonalOsGraphStageView(health, width, height, visibleNodes, visibleEdges, positions) {
  const fragment = document.createDocumentFragment();
  if (health.partial) {
    fragment.appendChild(createPersonalOsTextElement(
      "div",
      "pos-code pos-warn",
      posUiText("pos.partialContextMap", "Partial Context Map: {{count}} file error(s).", { count: health.errorCount })
    ));
  }
  fragment.append(
    createPersonalOsGraphExplorerView(),
    createPersonalOsGraphNetworkView(width, height, visibleNodes, visibleEdges, positions)
  );
  return fragment;
}

function posGraphNodeClass(kind) {
  if (kind === "tag") return "pos-graph-tag";
  if (kind === "reference") return "pos-graph-ref";
  return "pos-graph-file";
}

function posGraphLabel(node) {
  return posText(node?.label || node?.path || node?.id, "node");
}

function posGraphDisplayName(node, limit = 34) {
  const raw = posGraphLabel(node);
  if (node?.kind === "tag") return raw.replace(/^tag:/, "#");
  const clean = raw.replace(/\.md$/i, "");
  const parts = clean.split("/").filter(Boolean);
  const label = parts.length >= 2 ? `${parts[parts.length - 2]}/${parts[parts.length - 1]}` : clean;
  return label.length > limit ? `${label.slice(0, Math.max(0, limit - 3))}...` : label;
}

function posNormalizeTagQuery(value) {
  return posText(value)
    .replace(/^tag:/i, "")
    .replace(/^#/, "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80);
}

function posTagFilter(value) {
  const raw = posText(value).trim();
  const tag = posNormalizeTagQuery(raw);
  return {
    raw,
    tag,
    invalid: Boolean(raw && (!tag || !/^[a-z0-9][a-z0-9_-]{0,79}$/.test(tag))),
  };
}

function posGraphTagQuery(node) {
  if (node?.kind !== "tag") return "";
  return posNormalizeTagQuery(posGraphLabel(node));
}

function posGraphDegreeMap(edges) {
  const degree = new Map();
  const rows = Array.isArray(edges) ? edges : [];
  for (const edge of rows) {
    if (!edge?.source || !edge?.target) continue;
    degree.set(edge.source, (degree.get(edge.source) || 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) || 0) + 1);
  }
  return degree;
}

function posGraphRankedNodes(nodes, edges, kind, limit) {
  const degree = posGraphDegreeMap(edges);
  return (Array.isArray(nodes) ? nodes : [])
    .filter((node) => node?.kind === kind)
    .sort((a, b) => {
      const indexScoreA = /(^|\/)INDEX\.md$/i.test(posText(a.path || a.id)) ? 1000 : 0;
      const indexScoreB = /(^|\/)INDEX\.md$/i.test(posText(b.path || b.id)) ? 1000 : 0;
      return (indexScoreB + (degree.get(b.id) || 0)) - (indexScoreA + (degree.get(a.id) || 0))
        || posGraphLabel(a).localeCompare(posGraphLabel(b));
    })
    .slice(0, limit)
    .map((node) => ({ ...node, degree: degree.get(node.id) || 0 }));
}

function posGraphHealth(payload) {
  const nodes = Array.isArray(payload?.nodes) ? payload.nodes : [];
  const errors = Array.isArray(payload?.errors) ? payload.errors : [];
  const counts = payload?.counts || {};
  const hasTopLevelError = Boolean(payload?.error || payload?.detail);
  const errorCount = posCount(counts.errors) || errors.length || (hasTopLevelError ? 1 : 0);
  const hasNodes = nodes.length > 0;
  const partial = Boolean(hasNodes && (payload?.ok === false || hasTopLevelError));
  return {
    hasNodes,
    errorCount,
    partial,
    failed: Boolean(!payload || (payload.ok === false && !hasNodes) || (hasTopLevelError && !hasNodes)),
    note: payload?.truncated ? "truncated" : (partial ? "partial" : "complete"),
  };
}

function posGraphHealthNote(note) {
  const value = posText(note);
  if (value === "truncated") return posUiText("pos.graphNoteTruncated", "truncated");
  if (value === "partial") return posUiText("pos.graphNotePartial", "partial");
  return posUiText("pos.graphNoteComplete", "complete");
}

function setupPersonalOsGraphFocus(stage) {
  if (!stage) return;
  const nodes = [...stage.querySelectorAll(".pos-graph-node[data-node-id]")];
  const edges = [...stage.querySelectorAll(".pos-graph-edge[data-source][data-target]")];
  const clear = () => {
    nodes.forEach((node) => node.classList.remove("is-active", "is-related", "is-dim"));
    edges.forEach((edge) => edge.classList.remove("is-active", "is-dim"));
  };
  const focusNode = (nodeEl) => {
    const id = nodeEl?.dataset?.nodeId;
    if (!id) return;
    const related = new Set([id]);
    edges.forEach((edge) => {
      if (edge.dataset.source === id || edge.dataset.target === id) {
        edge.classList.add("is-active");
        related.add(edge.dataset.source);
        related.add(edge.dataset.target);
      } else {
        edge.classList.add("is-dim");
      }
    });
    nodes.forEach((node) => {
      const nodeId = node.dataset.nodeId;
      node.classList.toggle("is-active", nodeId === id);
      node.classList.toggle("is-related", nodeId !== id && related.has(nodeId));
      node.classList.toggle("is-dim", !related.has(nodeId));
    });
  };
  nodes.forEach((node) => {
    node.addEventListener("mouseenter", () => focusNode(node));
    node.addEventListener("focusin", () => focusNode(node));
    node.addEventListener("mouseleave", clear);
    node.addEventListener("focusout", clear);
    node.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && node.dataset.path) {
        e.preventDefault();
        personalOsReadContextFile(node.dataset.path);
      }
    });
  });
}

function renderPersonalOsGraphPayload(payload) {
  const summary = document.getElementById("pos-graph-summary");
  const stage = document.getElementById("pos-graph-stage");
  if (!summary || !stage) return;

  const health = posGraphHealth(payload);
  if (health.failed) {
    summary.replaceChildren();
    setPersonalOsEmptyState(stage, posErrorMessage(payload, posUiText("pos.contextMapFailed", "Context Map failed")));
    return;
  }

  const nodes = Array.isArray(payload.nodes) ? payload.nodes.slice(0, 120) : [];
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = Array.isArray(payload.edges)
    ? payload.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)).slice(0, 260)
    : [];
  const counts = payload.counts || {};
  PersonalOSState.graph = payload;

  if (!health.hasNodes) {
    summary.replaceChildren();
    setPersonalOsEmptyState(stage, posUiText("pos.noContextMapNodes", "No Context Map nodes."));
    return;
  }

  const width = 1160;
  const height = 430;
  const positions = new Map();
  const fileNodes = posGraphRankedNodes(nodes, edges, "file", 16);
  const tagNodes = posGraphRankedNodes(nodes, edges, "tag", 8);
  const refNodes = posGraphRankedNodes(nodes, edges, "reference", 5);
  const visibleNodes = [...fileNodes, ...tagNodes, ...refNodes];
  const visibleIds = new Set(visibleNodes.map((node) => node.id));

  const placeColumn = (items, x, top, bottom, columns = 1, columnGap = 260) => {
    const totalRows = Math.max(1, Math.ceil(items.length / columns));
    const gap = totalRows <= 1 ? 0 : (bottom - top) / (totalRows - 1);
    items.forEach((node, index) => {
      const col = index % columns;
      const row = Math.floor(index / columns);
      positions.set(node.id, {
        x: x + col * columnGap,
        y: top + row * gap,
      });
    });
  };

  placeColumn(fileNodes, 170, 72, 360, 2, 270);
  placeColumn(tagNodes, 760, 72, 248, 1);
  placeColumn(refNodes, 960, 300, 372, 1);

  const visibleEdgeCandidates = edges.filter((edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target));
  const relatedEdges = visibleEdgeCandidates.filter((edge) => edge.type === "related").slice(0, 22);
  const tagEdges = visibleEdgeCandidates.filter((edge) => edge.type !== "related").slice(0, 28);
  const visibleEdges = [...relatedEdges, ...tagEdges];

  renderPersonalOsGraphSummary(summary, payload, counts, nodes, edges, visibleNodes, visibleEdges, health);
  stage.replaceChildren(createPersonalOsGraphStageView(health, width, height, visibleNodes, visibleEdges, positions));

  const rows = document.getElementById("pos-graph-files");
  if (rows) {
    rows.replaceChildren();
    for (const node of fileNodes.slice(0, 12)) {
      const row = createPersonalOsGraphFileRow(node);
      row.addEventListener("click", () => personalOsReadContextFile(node.path || node.id));
      rows.appendChild(row);
    }
  }

  const hubs = document.getElementById("pos-graph-hubs");
  if (hubs) {
    hubs.replaceChildren();
    for (const node of [...tagNodes.slice(0, 8), ...refNodes.slice(0, 4)]) {
      const tagQuery = posGraphTagQuery(node);
      const row = createPersonalOsGraphHubRow(node, tagQuery);
      if (tagQuery) {
        row.addEventListener("click", () => {
          const tagInput = document.getElementById("pos-tag-input");
          if (tagInput) tagInput.value = tagQuery;
          personalOsSearchTag();
        });
      }
      hubs.appendChild(row);
    }
  }

  stage.querySelectorAll(".pos-graph-node[data-path]").forEach((nodeEl) => {
    nodeEl.addEventListener("click", () => personalOsReadContextFile(nodeEl.dataset.path));
  });
  setupPersonalOsGraphFocus(stage);
}
