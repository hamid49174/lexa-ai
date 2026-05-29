/* Personal OS DOM factory helpers. Classic script loaded before personal_os.js. */

function posRenderBadge(count) {
  const badge = document.getElementById("nav-pos-badge");
  if (!badge) return;
  const safe = Number.isFinite(count) ? count : 0;
  badge.textContent = safe > 99 ? "99+" : String(safe);
  badge.classList.toggle("hidden", safe <= 0);
}

function createPersonalOsEmptyState(message) {
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = message || "";
  return empty;
}

function setPersonalOsEmptyState(target, message) {
  if (target) target.replaceChildren(createPersonalOsEmptyState(message));
}

function createPersonalOsDraftRow(draft, selectedPath) {
  const row = document.createElement("button");
  const isSelected = draft.path === selectedPath;
  row.type = "button";
  row.className = "pos-draft-row";
  row.setAttribute("aria-current", isSelected ? "true" : "false");
  if (isSelected) row.classList.add("active");
  row.dataset.path = draft.path;

  const main = document.createElement("span");
  main.className = "pos-draft-main";
  const title = document.createElement("span");
  title.className = "pos-draft-title";
  title.textContent = posText(draft.title, posUiText("pos.untitledDraft", "Untitled Draft"));
  const subtitle = document.createElement("span");
  subtitle.className = "pos-draft-subtitle";
  subtitle.textContent = posDraftStatusText(draft.approval);
  main.append(title, subtitle);
  const pill = document.createElement("span");
  pill.className = "pos-pill " + posStatusClass(draft.approval);
  pill.textContent = posText(draft.approval, "unknown");
  row.append(main, pill);
  return row;
}

function createPersonalOsQueryMatchRow(match) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = "pos-query-row";
  const main = document.createElement("span");
  main.className = "pos-draft-main";
  const title = document.createElement("span");
  title.className = "pos-draft-title";
  title.textContent = posText(match.title, posUiText("pos.untitled", "Untitled"));
  const path = document.createElement("span");
  path.className = "pos-draft-path";
  path.textContent = posText(match.path);
  main.append(title, path);
  const pill = document.createElement("span");
  pill.className = "pos-pill";
  pill.textContent = posText(match.memory_level || match.type, posUiText("pos.kindFile", "file"));
  row.append(main, pill);
  return row;
}

function createPersonalOsQueryDocumentView(payload, title, tags) {
  const fm = payload.frontmatter || {};
  const fragment = document.createDocumentFragment();
  const header = document.createElement("div");
  header.className = "pos-query-read-header";

  const heading = document.createElement("div");
  const titleEl = document.createElement("div");
  titleEl.className = "pos-draft-title";
  titleEl.textContent = title;
  const pathEl = document.createElement("div");
  pathEl.className = "pos-draft-path";
  pathEl.textContent = posText(payload.path);
  heading.append(titleEl, pathEl);

  const actions = document.createElement("div");
  actions.className = "pos-query-actions";
  const pill = document.createElement("span");
  pill.className = "pos-pill";
  pill.textContent = posText(fm.memory_level || fm.type, posUiText("pos.kindFile", "file"));
  const chatButton = document.createElement("button");
  chatButton.type = "button";
  chatButton.className = "action-btn action-btn-sm";
  chatButton.dataset.action = "personalOsSendContextToChat";
  chatButton.textContent = posUiText("pos.actionChat", "Chat");
  actions.append(pill, chatButton);
  header.append(heading, actions);
  fragment.appendChild(header);

  if (tags) {
    const tagEl = document.createElement("div");
    tagEl.className = "pos-code";
    tagEl.textContent = tags;
    fragment.appendChild(tagEl);
  }

  const body = document.createElement("pre");
  body.className = "pos-markdown pos-query-markdown";
  body.textContent = posText(payload.body);
  fragment.appendChild(body);
  return fragment;
}

function createPersonalOsReviewMetricCard(label, value, valueClass = "") {
  const card = document.createElement("div");
  card.className = "pos-review-card";
  card.append(
    createPersonalOsTextElement("div", "pos-label", label),
    createPersonalOsTextElement("div", `pos-review-value${valueClass ? ` ${valueClass}` : ""}`, value)
  );
  return card;
}

function createPersonalOsRelatedFileRow(file) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = "pos-related-row";
  row.dataset.relatedPath = posText(file.path);
  const main = document.createElement("span");
  main.className = "pos-draft-main";
  main.append(
    createPersonalOsTextElement("span", "pos-draft-title", posText(file.title, file.path || posUiText("pos.osFileFallback", "OS file"))),
    createPersonalOsTextElement("span", "pos-draft-path", posText(file.path))
  );
  row.append(
    main,
    createPersonalOsPill(posText(file.memory_level || file.type, posUiText("pos.kindFile", "file")))
  );
  return row;
}

function createPersonalOsRelatedInfoRow(titleText, detailText, pillText = "") {
  const row = document.createElement("div");
  row.className = "pos-related-row";
  const main = document.createElement("span");
  main.className = "pos-draft-main";
  main.append(
    createPersonalOsTextElement("span", "pos-draft-title", titleText),
    createPersonalOsTextElement("span", "pos-draft-path", detailText)
  );
  row.appendChild(main);
  if (pillText) row.appendChild(createPersonalOsPill(pillText));
  return row;
}

function posContextFilesPreview(files) {
  return files.map((file) => [
    `## ${posText(file.title, file.path)}`,
    `Path: ${posText(file.path)}`,
    `Tags: ${Array.isArray(file.tags) ? file.tags.join(", ") : "-"}`,
    "",
    posText(file.bodyPreview),
  ].join("\n")).join("\n\n");
}

function createPersonalOsContextPackView(query, files, errors, graphLabel, graphClass) {
  const fragment = document.createDocumentFragment();
  const header = document.createElement("div");
  header.className = "pos-query-read-header";
  const heading = document.createElement("div");
  const pathText = `${posText(query.areaPath, ".")}${query.tag ? ` / #${posText(query.tag)}` : ""}`;
  heading.append(
    createPersonalOsTextElement("div", "pos-draft-title", posUiText("pos.titleContextPack", "Context Pack")),
    createPersonalOsTextElement("div", "pos-draft-path", pathText)
  );
  const actions = document.createElement("div");
  actions.className = "pos-query-actions";
  const chatButton = document.createElement("button");
  chatButton.type = "button";
  chatButton.className = "action-btn action-btn-sm";
  chatButton.dataset.action = "personalOsSendContextPackToChat";
  chatButton.textContent = posUiText("pos.actionChat", "Chat");
  actions.append(
    createPersonalOsPill(posUiCount("pos.countFiles", "{{count}} files", query.includedCount || files.length)),
    chatButton
  );
  header.append(heading, actions);
  fragment.appendChild(header);

  const strip = document.createElement("div");
  strip.className = "pos-review-strip";
  strip.append(
    createPersonalOsReviewMetricCard(posUiText("pos.metricCandidates", "Candidates"), String(Number(query.candidateCount || 0))),
    createPersonalOsReviewMetricCard(posUiText("pos.metricIncluded", "Included"), String(Number(query.includedCount || files.length)), "pos-good"),
    createPersonalOsReviewMetricCard(posUiText("pos.metricContextMap", "Context Map"), graphLabel, graphClass),
    createPersonalOsReviewMetricCard(posUiText("pos.metricErrors", "Errors"), String(errors.length), errors.length ? "pos-warn" : "pos-good")
  );
  fragment.appendChild(strip);

  const list = document.createElement("div");
  list.className = "pos-related-list";
  for (const file of files) {
    list.appendChild(createPersonalOsRelatedFileRow(file));
  }
  fragment.appendChild(list);

  if (files.length) {
    const preview = document.createElement("pre");
    preview.className = "pos-markdown pos-query-markdown";
    preview.textContent = posContextFilesPreview(files);
    fragment.appendChild(preview);
  } else {
    fragment.appendChild(createPersonalOsEmptyState(posUiText("pos.noContextPackFiles", "No files in this Context Pack.")));
  }

  return fragment;
}

function createPersonalOsObsidianContextView(vault, counts, product, quickFind, surfaces, files) {
  const fragment = document.createDocumentFragment();
  const header = document.createElement("div");
  header.className = "pos-query-read-header";
  const heading = document.createElement("div");
  heading.append(
    createPersonalOsTextElement("div", "pos-draft-title", posUiText("pos.titleObsidianContext", "Obsidian Context")),
    createPersonalOsTextElement("div", "pos-draft-path", posText(vault.root, "-"))
  );
  const actions = document.createElement("div");
  actions.className = "pos-query-actions";
  const chatButton = document.createElement("button");
  chatButton.type = "button";
  chatButton.className = "action-btn action-btn-sm";
  chatButton.dataset.action = "personalOsSendObsidianContextToChat";
  chatButton.textContent = posUiText("pos.actionChat", "Chat");
  actions.append(createPersonalOsPill(posText(product.providerMode, "api-backed")), chatButton);
  header.append(heading, actions);
  fragment.appendChild(header);

  const metricStrip = document.createElement("div");
  metricStrip.className = "pos-review-strip";
  metricStrip.append(
    createPersonalOsReviewMetricCard(posUiText("pos.metricBootstrap", "Bootstrap"), String(posCount(counts.bootstrapAvailable)), "pos-good"),
    createPersonalOsReviewMetricCard(posUiText("pos.metricAreaIndexes", "Area indexes"), String(posCount(counts.areaIndexes)), "pos-good"),
    createPersonalOsReviewMetricCard(posUiText("pos.metricQuickFind", "Quick Find"), String(quickFind.length), "pos-good"),
    createPersonalOsReviewMetricCard(posUiText("pos.metricLoadedAll", "Loaded all"), vault.loadedAll ? "true" : "false", vault.loadedAll ? "pos-warn" : "pos-good")
  );
  fragment.appendChild(metricStrip);

  fragment.appendChild(createPersonalOsTextElement("div", "pos-code", posText(product.rule, "Lexa uses configured provider APIs for model intelligence.")));

  const quickFindList = document.createElement("div");
  quickFindList.className = "pos-related-list";
  for (const item of quickFind.slice(0, 10)) {
    quickFindList.appendChild(createPersonalOsRelatedInfoRow(posText(item.need, "Context"), posText(item.goTo, "-")));
  }
  fragment.appendChild(quickFindList);

  const surfaceStrip = document.createElement("div");
  surfaceStrip.className = "pos-review-strip";
  for (const surface of surfaces.slice(0, 8)) {
    surfaceStrip.appendChild(createPersonalOsReviewMetricCard(posText(surface.id, "surface"), String(posCount(surface.fileCountApprox))));
  }
  fragment.appendChild(surfaceStrip);

  if (files.length) {
    const preview = document.createElement("pre");
    preview.className = "pos-markdown pos-query-markdown";
    preview.textContent = posContextFilesPreview(files);
    fragment.appendChild(preview);
  } else {
    fragment.appendChild(createPersonalOsEmptyState(posUiText("pos.noObsidianContextFiles", "No selected OS context files.")));
  }

  return fragment;
}

function createPersonalOsCodeLoopActionButton(action, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "action-btn action-btn-sm";
  button.dataset.action = action;
  button.textContent = label;
  return button;
}

function createPersonalOsCodeLoopPendingCard(evidence) {
  const card = document.createElement(evidence.pending ? "button" : "div");
  if (evidence.pending) {
    card.type = "button";
    card.dataset.codeLoopAction = "load-pending";
  }
  card.className = `pos-review-card${evidence.pending ? " pos-action-card" : ""}`;
  card.append(
    createPersonalOsTextElement("div", "pos-label", posUiText("pos.metricPending", "Pending")),
    createPersonalOsTextElement("div", `pos-review-value ${evidence.pending ? "pos-warn" : "pos-good"}`, String(evidence.pending))
  );
  return card;
}

function createPersonalOsPromptMeterCard(meta) {
  const card = createPersonalOsReviewMetricCard(
    posUiText("pos.metricPrompt", "Prompt"),
    `${meta.percent}%`,
    meta.compacted ? "pos-warn" : "pos-good"
  );
  const meter = document.createElement("div");
  meter.className = "meter";
  const fill = document.createElement("span");
  fill.className = posMeterWidthClass(meta.percent);
  meter.appendChild(fill);
  card.appendChild(meter);
  return card;
}

function createPersonalOsCodeLoopDraftRow(draft) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = "pos-related-row";
  row.dataset.codeLoopDraft = posText(draft.path);
  const main = document.createElement("span");
  main.className = "pos-draft-main";
  main.append(
    createPersonalOsTextElement("span", "pos-draft-title", posText(draft.title, posUiText("pos.untitled", "Untitled"))),
    createPersonalOsTextElement("span", "pos-draft-path", posText(draft.path))
  );
  row.append(
    main,
    createPersonalOsPill(posText(draft.approval, "unknown"), posStatusClass(draft.approval))
  );
  return row;
}

function createPersonalOsCodeLoopFileRow(file) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = "pos-related-row";
  row.dataset.codeLoopFile = posText(file.path);
  const main = document.createElement("span");
  main.className = "pos-draft-main";
  main.append(
    createPersonalOsTextElement("span", "pos-draft-title", posText(file.title, file.path || posUiText("pos.osFileFallback", "OS file"))),
    createPersonalOsTextElement("span", "pos-draft-path", posText(file.path))
  );
  row.append(
    main,
    createPersonalOsPill(posText(file.memory_level || file.type, posUiText("pos.kindFile", "file")))
  );
  return row;
}

function createPersonalOsCodeLoopView(payload, diagnostics, draftRows, contextFiles, raw, evidence, meta) {
  const fragment = document.createDocumentFragment();
  const header = document.createElement("div");
  header.className = "pos-query-read-header";
  const heading = document.createElement("div");
  heading.append(
    createPersonalOsTextElement("div", "pos-draft-title", posUiText("pos.titleCodeLoop", "Lexa Code Loop")),
    createPersonalOsTextElement("div", "pos-draft-path", posText(payload.topic, "lexa-code-improvement"))
  );
  const actions = document.createElement("div");
  actions.className = "pos-query-actions";
  actions.append(
    createPersonalOsPill(posUiCount("pos.countFiles", "{{count}} files", contextFiles.length)),
    createPersonalOsCodeLoopActionButton("personalOsSendCodeLoopToAgent", posUiText("pos.actionAgent", "Agent")),
    createPersonalOsCodeLoopActionButton("personalOsSendCodeLoopToChat", posUiText("pos.actionChat", "Chat"))
  );
  header.append(heading, actions);
  fragment.appendChild(header);

  const metricStrip = document.createElement("div");
  metricStrip.className = "pos-review-strip";
  metricStrip.append(
    createPersonalOsReviewMetricCard(posUiText("pos.metricOsState", "OS State"), posText(diagnostics.state, "unknown"), posAssistClass(diagnostics.state)),
    createPersonalOsCodeLoopPendingCard(evidence),
    createPersonalOsReviewMetricCard(posUiText("pos.metricContext", "Context"), String(evidence.contextFiles), "pos-good"),
    createPersonalOsReviewMetricCard(posUiText("pos.metricDrafts", "Drafts"), String(evidence.drafts), evidence.drafts ? "pos-good" : "pos-warn"),
    createPersonalOsReviewMetricCard(posUiText("pos.metricWorker", "Worker"), String(evidence.workerFailures), raw.ok ? "pos-good" : "pos-warn"),
    createPersonalOsReviewMetricCard(posUiText("pos.metricContextMap", "Context Map"), String(evidence.graphErrors), evidence.graphOk ? "pos-good" : "pos-warn")
  );
  fragment.appendChild(metricStrip);

  const promptStrip = document.createElement("div");
  promptStrip.className = "pos-review-strip";
  promptStrip.appendChild(createPersonalOsPromptMeterCard(meta));
  fragment.appendChild(promptStrip);

  fragment.appendChild(createPersonalOsTextElement("div", "pos-code", posText(diagnostics.summary, posUiText("pos.noDiagnosticSummary", "No diagnostic summary."))));
  if (evidence.graphErrors) {
    fragment.appendChild(createPersonalOsTextElement(
      "div",
      "pos-code pos-warn",
      posUiText("pos.contextMapPartial", "Context Map partial: {{files}} files, {{edges}} edges, {{errors}} error(s).", {
        files: evidence.graphFiles,
        edges: evidence.graphEdges,
        errors: evidence.graphErrors,
      })
    ));
  }

  const graphErrors = Array.isArray(payload?.contextPack?.graph?.errors) ? payload.contextPack.graph.errors.slice(0, 5) : [];
  if (graphErrors.length) {
    fragment.appendChild(createPersonalOsTextElement("div", "pos-label", posUiText("pos.labelContextMapErrors", "Context Map Errors")));
    const errorsList = document.createElement("div");
    errorsList.className = "pos-related-list";
    for (const entry of graphErrors) {
      errorsList.appendChild(createPersonalOsRelatedInfoRow(
        posText(entry.path, posUiText("pos.contextMapErrorFallback", "Context Map error")),
        posClip(entry.error, 220),
        posUiText("pos.kindMap", "map")
      ));
    }
    fragment.appendChild(errorsList);
  }

  fragment.appendChild(createPersonalOsTextElement("div", "pos-label", posUiText("pos.labelDraftDecisions", "Draft Decisions")));
  const draftList = document.createElement("div");
  draftList.className = "pos-related-list";
  for (const draft of draftRows) {
    draftList.appendChild(createPersonalOsCodeLoopDraftRow(draft));
  }
  fragment.appendChild(draftList);

  fragment.appendChild(createPersonalOsTextElement("div", "pos-label", posUiText("pos.labelEvidenceFiles", "Evidence Files")));
  const fileList = document.createElement("div");
  fileList.className = "pos-related-list";
  for (const file of contextFiles.slice(0, 6)) {
    fileList.appendChild(createPersonalOsCodeLoopFileRow(file));
  }
  fragment.appendChild(fileList);

  const preview = document.createElement("pre");
  preview.className = "pos-markdown pos-query-markdown";
  preview.textContent = personalOsCodeLoopPrompt(payload);
  fragment.appendChild(preview);
  return fragment;
}

function createPersonalOsGraphFileRow(node) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = "pos-graph-file-row";
  const main = document.createElement("span");
  main.className = "pos-draft-main";
  const title = document.createElement("span");
  title.className = "pos-draft-title";
  title.textContent = posGraphLabel(node);
  const path = document.createElement("span");
  path.className = "pos-draft-path";
  path.textContent = posText(node.path || node.id);
  main.append(title, path);
  const pill = document.createElement("span");
  pill.className = "pos-pill";
  pill.textContent = posText(node.memory_level || node.type, posUiText("pos.kindFile", "file"));
  row.append(main, pill);
  return row;
}

function createPersonalOsGraphHubRow(node, tagQuery) {
  const row = document.createElement(tagQuery ? "button" : "div");
  if (tagQuery) {
    row.type = "button";
    row.dataset.graphTag = tagQuery;
    row.title = posUiText("pos.searchTagTitle", "Search tag #{{tag}}", { tag: tagQuery });
  }
  row.className = `pos-graph-file-row pos-graph-hub-row ${tagQuery ? "pos-graph-hub-action" : ""} ${posGraphNodeClass(node.kind)}`;
  const main = document.createElement("span");
  main.className = "pos-draft-main";
  const title = document.createElement("span");
  title.className = "pos-draft-title";
  title.textContent = posGraphDisplayName(node, 34);
  const path = document.createElement("span");
  path.className = "pos-draft-path";
  path.textContent = posGraphLabel(node);
  main.append(title, path);
  const pill = document.createElement("span");
  pill.className = "pos-pill";
  pill.textContent = String(Number(node.degree || 0));
  row.append(main, pill);
  return row;
}

function createPersonalOsPill(text, extraClass = "") {
  const pill = document.createElement("span");
  pill.className = `pos-pill${extraClass ? ` ${extraClass}` : ""}`;
  pill.textContent = text;
  return pill;
}

function renderPersonalOsGraphSummary(summary, payload, counts, nodes, edges, visibleNodes, visibleEdges, health) {
  const pills = [
    createPersonalOsPill(posText(payload.areaPath, ".")),
    createPersonalOsPill(posUiCount("pos.countFiles", "{{count}} files", counts.files || nodes.filter((node) => node.kind === "file").length)),
    createPersonalOsPill(posUiCount("pos.countEdges", "{{count}} edges", counts.edges || edges.length)),
    createPersonalOsPill(posUiCount("pos.countMapNodes", "{{count}} map nodes", visibleNodes.length)),
    createPersonalOsPill(posUiCount("pos.countMapEdges", "{{count}} map edges", visibleEdges.length)),
    createPersonalOsPill(posGraphHealthNote(health.note), health.partial ? "pos-warn" : ""),
  ];
  if (health.errorCount) {
    pills.push(createPersonalOsPill(posUiCount("pos.countErrors", "{{count}} errors", health.errorCount), "pos-warn"));
  }
  summary.replaceChildren(...pills);
}

function createPersonalOsTextElement(tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) element.className = className;
  element.textContent = text;
  return element;
}

function createPersonalOsHomeAction(action, label, subLabel, extraClass = "", dataset = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `pos-home-action${extraClass ? ` ${extraClass}` : ""}`;
  button.dataset.posHomeAction = action;
  for (const [key, value] of Object.entries(dataset)) {
    button.dataset[key] = value;
  }
  button.append(
    createPersonalOsTextElement("span", "", label),
    createPersonalOsTextElement("small", "", subLabel)
  );
  return button;
}

function createPersonalOsInfoCard(label, value, subText, valueClass = "", queueFilter = "") {
  const card = document.createElement(queueFilter ? "button" : "div");
  if (queueFilter) {
    card.type = "button";
    card.dataset.queueFilter = queueFilter;
  }
  card.className = `info-card${queueFilter ? " pos-action-card" : ""}`;
  card.append(
    createPersonalOsTextElement("div", "info-card-label", label),
    createPersonalOsTextElement("div", `info-card-value${valueClass ? ` ${valueClass}` : ""}`, value),
    createPersonalOsTextElement("div", "info-card-sub", subText)
  );
  return card;
}

function createPersonalOsCapabilityItem(label, ok, missingText) {
  const item = document.createElement("div");
  item.className = "pos-capability-item";
  item.title = missingText;
  const dot = document.createElement("span");
  dot.className = `pos-history-dot ${ok ? "pos-good" : "pos-bad"}`;
  item.append(dot, createPersonalOsTextElement("span", "", label));
  return item;
}
