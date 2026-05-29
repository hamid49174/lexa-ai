/* Personal OS renderers. Classic script loaded before personal_os.js. */

function renderPersonalOsStatus(status, queue, diagnostics = null) {
  const grid = document.getElementById("pos-status-grid");
  if (!grid) return;

  const counts = posQueueCounts(queue);
  const toolsCount = Number.isFinite(status?.tools_count) ? status.tools_count : 0;
  const pending = counts.pending;
  const approved = counts.approved;
  const rejected = counts.rejected;
  const invalid = counts.invalid;
  const rawCapabilities = status?.capabilities || {};
  const capabilities = {
    draftQueue: rawCapabilities.draftQueue ?? Boolean(status?.draft_review),
    reviewPacket: rawCapabilities.reviewPacket ?? Boolean(status?.draft_review),
    auditHistory: rawCapabilities.auditHistory ?? false,
    contextBrowser: rawCapabilities.contextBrowser ?? false,
    graph: rawCapabilities.graph ?? false,
    explicitApply: rawCapabilities.explicitApply ?? Boolean(status?.draft_review),
  };
  const readyCount = ["draftQueue", "reviewPacket", "auditHistory", "contextBrowser", "graph", "explicitApply"]
    .filter((key) => capabilities[key]).length;
  const reviewReady = capabilities.reviewPacket
    ? posUiText("pos.reviewReady", "Review Ready")
    : (status?.draft_review ? posUiText("pos.queueReady", "Queue Ready") : posUiText("pos.valueMissing", "Missing"));
  const diagnosticState = posText(diagnostics?.state, status?.status === "connected" ? "ready" : "blocked");
  const diagnosticSummary = posDiagnosticHeadline(diagnostics, status?.status === "connected" ? posUiText("pos.connectedSummary", "Personal OS connected.") : posUiText("pos.unavailableSummary", "Personal OS unavailable."));
  const nextAction = posNextActionText(diagnostics, queue);
  const nextDraftPath = posNextDraftPath(queue);
  const nextCardAction = posNextCardAction(queue, diagnostics);
  const refreshLabel = posRefreshLabel(PersonalOSState.lastRefreshAt);
  const missingTools = status?.missing_tools || {};
  const capabilityRows = [
    [posUiText("pos.capabilityQueue", "Queue"), "draftQueue", missingTools.draftQueue],
    [posUiText("pos.capabilityReview", "Review"), "reviewPacket", missingTools.reviewPacket],
    [posUiText("pos.capabilityAudit", "Audit"), "auditHistory", capabilities.auditHistory ? [] : ["os_draft_history"]],
    [posUiText("pos.metricContext", "Context"), "contextBrowser", missingTools.contextBrowser],
    [posUiText("pos.metricContextMap", "Context Map"), "graph", missingTools.graph],
    [posUiText("pos.applyDraftAction", "Apply"), "explicitApply", capabilities.explicitApply ? [] : ["os_list_drafts", "os_view_draft"]],
  ];
  const nextValue = pending || invalid ? posStateLabel("review") : posStateLabel("ready");
  const nextValueClass = pending || invalid ? "pos-warn" : "pos-good";
  const draftSub = posUiText("pos.subNonSmokeDrafts", "Non-smoke Drafts");
  const approvedSub = posUiText("pos.subReadyNoAutoApply", "Ready / No auto-apply");
  const rejectedSub = posUiText("pos.subSupersededClosed", "Superseded / Closed");
  const invalidSub = posUiText("pos.subQueueErrors", "Queue Errors");
  const pendingWord = pending === 1 ? posUiText("pos.homeDraftSingular", "draft") : posUiText("pos.homeDraftPlural", "drafts");
  const connectionStatus = posLanguageText(posText(status?.status, "unknown"));
  const homeTitle = posIsOfflineDiagnostics(diagnostics)
    ? posUiText("pos.homeTitleOffline", "Personal OS needs attention")
    : pending > 0
      ? posUiText("pos.homeTitlePending", "{{count}} {{word}} waiting", { count: pending, word: pendingWord })
      : posUiText("pos.homeTitleReady", "Personal OS is clear");
  const homeSummary = posIsOfflineDiagnostics(diagnostics)
    ? diagnosticSummary
    : pending > 0
      ? posUiText("pos.homeSummaryPending", "Review the open drafts first. Stable memory changes stay protected until you approve them.")
      : posUiText("pos.homeSummaryReady", "No open review is blocking you. Capture a note, find context, or build the next Lexa step.");

  const homeCard = document.createElement("section");
  homeCard.className = "pos-home-card";

  const homeCopy = document.createElement("div");
  homeCopy.className = "pos-home-copy";
  homeCopy.append(
    createPersonalOsTextElement("div", "pos-kicker", posUiText("pos.homeKicker", "Personal OS")),
    createPersonalOsTextElement("h2", "", homeTitle),
    createPersonalOsTextElement("p", "", homeSummary)
  );

  const homeActions = document.createElement("div");
  homeActions.className = "pos-home-actions";
  homeActions.append(
    createPersonalOsHomeAction(
      "review",
      pending > 0 ? posUiText("pos.homeActionReview", "Review drafts") : posUiText("pos.homeActionOpenQueue", "Open reviews"),
      nextAction,
      "pos-home-action-primary pos-next-card",
      { nextDraftPath, nextAction: nextCardAction }
    ),
    createPersonalOsHomeAction("raw", posUiText("pos.homeActionCapture", "New note"), posUiText("pos.homeActionCaptureSub", "Capture first, sort later")),
    createPersonalOsHomeAction("search", posUiText("pos.homeActionFind", "Find context"), posUiText("pos.homeActionFindSub", "Search by area or topic")),
    createPersonalOsHomeAction("lexa", posUiText("pos.homeActionLexa", "Continue Lexa"), posUiText("pos.homeActionLexaSub", "Build the next plan"))
  );

  const homeStatus = document.createElement("div");
  homeStatus.className = "pos-home-status";
  homeStatus.append(
    createPersonalOsTextElement("span", posAssistClass(diagnosticState), posStateLabel(diagnosticState)),
    createPersonalOsTextElement("span", "", refreshLabel),
    createPersonalOsTextElement("span", "", posUiText("pos.homeStatusDrafts", "{{pending}} open / {{approved}} approved / {{rejected}} closed", { pending, approved, rejected }))
  );

  const details = document.createElement("details");
  details.className = "pos-technical-details";
  details.appendChild(createPersonalOsTextElement("summary", "", posUiText("pos.showTechnicalDetails", "Technical details")));

  const technicalGrid = document.createElement("div");
  technicalGrid.className = "pos-technical-grid";
  technicalGrid.append(
    createPersonalOsInfoCard(posUiText("pos.cardHealth", "HEALTH"), posStateLabel(diagnosticState), diagnosticSummary, posAssistClass(diagnosticState)),
    createPersonalOsInfoCard(posUiText("pos.cardNext", "NEXT"), nextValue, nextAction, nextValueClass),
    createPersonalOsInfoCard(posUiText("pos.cardMcp", "MCP"), connectionStatus, posText(status?.server, "personal_os"), posStatusClass(status?.status)),
    createPersonalOsInfoCard(posUiText("pos.cardSync", "SYNC"), posStateLabel("live"), refreshLabel, "pos-good"),
    createPersonalOsInfoCard(posUiText("pos.cardTools", "TOOLS"), String(toolsCount), posUiText("pos.subCapabilitiesReady", "{{reviewReady}} - {{readyCount}}/6 caps", { reviewReady, readyCount })),
    createPersonalOsInfoCard(posUiText("pos.cardPending", "PENDING"), String(pending), draftSub, pending ? "pos-warn" : "pos-good", "pending"),
    createPersonalOsInfoCard(posUiText("pos.cardApproved", "APPROVED"), String(approved), approvedSub, approved ? "pos-good" : "", "approved"),
    createPersonalOsInfoCard(posUiText("pos.cardRejected", "REJECTED"), String(rejected), rejectedSub, rejected ? "pos-bad" : "", "rejected"),
    createPersonalOsInfoCard(posUiText("pos.cardInvalid", "INVALID"), String(invalid), invalidSub, invalid ? "pos-bad" : "pos-good", "all")
  );

  const capabilityGrid = document.createElement("div");
  capabilityGrid.className = "pos-capability-grid";
  for (const [label, key, missing] of capabilityRows) {
    const ok = Boolean(capabilities[key]);
    const missingText = Array.isArray(missing) && missing.length
      ? posUiText("pos.capabilityMissingTools", "Missing: {{tools}}", { tools: missing.join(", ") })
      : posUiText("pos.capabilityReady", "Ready");
    capabilityGrid.appendChild(createPersonalOsCapabilityItem(label, ok, missingText));
  }

  details.append(technicalGrid, capabilityGrid);
  homeCard.append(homeCopy, homeActions, homeStatus, details);
  grid.replaceChildren(homeCard);

  grid.querySelectorAll("[data-pos-home-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.posHomeAction;
      if (action === "review") {
        if (nextCardAction === "open-draft" && nextDraftPath) selectPersonalOsDraft(nextDraftPath);
        else loadPersonalOsQueueFilter(nextCardAction === "load-all" ? "all" : "pending");
      } else if (action === "raw") {
        submitPersonalOsRawInbox();
      } else if (action === "search") {
        focusPersonalOsContextSearch();
      } else if (action === "lexa") {
        personalOsLoadCodeLoop();
      }
    });
  });
  grid.querySelectorAll("[data-queue-filter]").forEach((card) => {
    card.addEventListener("click", () => {
      loadPersonalOsQueueFilter(card.dataset.queueFilter || "pending");
    });
  });
  posRenderBadge(pending);
}

function renderPersonalOsDraftList(payload) {
  const list = document.getElementById("pos-draft-list");
  if (!list) return;

  const drafts = Array.isArray(payload?.drafts) ? payload.drafts : [];
  const visibleDrafts = posVisibleDrafts(drafts, PersonalOSState.draftSearch);
  PersonalOSState.drafts = drafts;
  const queueError = posDraftQueueError(payload);
  if (queueError) {
    setPersonalOsEmptyState(list, queueError);
    clearPersonalOsDraftDetail(queueError);
    return;
  }
  if (drafts.length === 0) {
    const filterValue = document.getElementById("pos-approval-filter")?.value || "all";
    setPersonalOsEmptyState(list, posDraftEmptyMessage(filterValue));
    clearPersonalOsDraftDetail();
    return;
  }
  if (visibleDrafts.length === 0) {
    setPersonalOsEmptyState(list, posUiText("pos.noDraftSearchResult", "No draft found for this search."));
    clearPersonalOsDraftDetail();
    return;
  }

  list.replaceChildren();
  for (const draft of visibleDrafts) {
    const row = createPersonalOsDraftRow(draft, PersonalOSState.selectedPath);
    row.addEventListener("click", () => selectPersonalOsDraft(draft.path));
    list.appendChild(row);
  }
}

function createPersonalOsReviewChecklist(review, approval) {
  const checklist = review?.checklist || {};
  const target = review?.targetCandidate || "";
  const relatedCount = Number(review?.reviewHints?.relatedCount || 0);
  const items = [
    [posUiText("pos.metricApprovedBox", "Approved box"), checklist.hasApproved ? posUiText("pos.valuePresent", "present") : posUiText("pos.valueMissing", "missing"), checklist.hasApproved ? "pos-good" : "pos-bad"],
    [posUiText("pos.metricRejectedBox", "Rejected box"), checklist.hasRejected ? posUiText("pos.valuePresent", "present") : posUiText("pos.valueMissing", "missing"), checklist.hasRejected ? "pos-good" : "pos-bad"],
    [posUiText("pos.metricState", "State"), approval, posStatusClass(approval)],
    [posUiText("pos.labelRelated", "Related"), String(relatedCount), relatedCount ? "pos-good" : "pos-warn"],
    [posUiText("pos.metricTarget", "Target"), target ? target : posUiText("pos.targetNotInferred", "not inferred"), target ? "pos-good" : "pos-warn"],
  ];

  const strip = document.createElement("div");
  strip.className = "pos-review-strip";
  for (const [label, value, cls] of items) {
    strip.appendChild(createPersonalOsReviewMetricCard(label, value, cls));
  }
  return strip;
}

function createPersonalOsAssistCard(review) {
  const assist = review?.assist || {};
  const checks = Array.isArray(assist.checks) ? assist.checks : [];
  if (!assist.status || checks.length === 0) return null;
  const blocked = Number(assist.blocked || 0);
  const warnings = Number(assist.warnings || 0);

  const card = document.createElement("div");
  card.className = "pos-assist-card";
  const head = document.createElement("div");
  head.className = "pos-assist-head";
  const copy = document.createElement("div");
  copy.append(
    createPersonalOsTextElement("div", "pos-label", posUiText("pos.labelReviewAssist", "Review Assist")),
    createPersonalOsTextElement("div", `pos-assist-title ${posAssistClass(assist.status)}`, posText(assist.status))
  );
  head.append(
    copy,
    createPersonalOsPill(posUiText("pos.reviewAssistCounts", "{{blocked}} block / {{warnings}} warn", { blocked, warnings }), posAssistClass(assist.status))
  );

  const checksList = document.createElement("div");
  checksList.className = "pos-assist-checks";
  for (const check of checks) {
    const item = document.createElement("div");
    item.className = "pos-assist-check";
    const dot = document.createElement("span");
    dot.className = `pos-history-dot ${posAssistClass(check.state)}`;
    const main = document.createElement("span");
    main.className = "pos-draft-main";
    main.append(
      createPersonalOsTextElement("span", "pos-draft-title", posText(check.label)),
      createPersonalOsTextElement("span", "pos-draft-path", posText(check.detail))
    );
    item.append(dot, main);
    checksList.appendChild(item);
  }

  card.append(
    head,
    createPersonalOsTextElement("div", "pos-assist-summary", posText(assist.summary)),
    checksList
  );
  if (assist.nextAction) {
    card.appendChild(createPersonalOsTextElement("div", "pos-assist-summary", posText(assist.nextAction)));
  }
  return card;
}

function createPersonalOsDiffView(diff) {
  if (!diff) {
    return createPersonalOsTextElement("div", "pos-code", posUiText("pos.noAutomaticTargetComparison", "No automatic target comparison available."));
  }
  const lines = Array.isArray(diff.lines) ? diff.lines : [];
  if (!diff.changed) {
    return createPersonalOsTextElement("div", "pos-code pos-good", posUiText("pos.targetBodyIdentical", "Draft and target body are identical."));
  }
  const diffEl = document.createElement("pre");
  diffEl.className = "pos-diff";
  lines.forEach((line, index) => {
    const cls = line.startsWith("+") && !line.startsWith("+++") ? "pos-diff-add"
      : line.startsWith("-") && !line.startsWith("---") ? "pos-diff-del"
      : line.startsWith("@@") ? "pos-diff-meta"
      : "";
    const span = document.createElement("span");
    if (cls) span.className = cls;
    span.textContent = line;
    diffEl.appendChild(span);
    if (index < lines.length - 1) diffEl.appendChild(document.createTextNode("\n"));
  });
  return diffEl;
}

function createPersonalOsReviewSection(label, content, extraClass = "") {
  const section = document.createElement("div");
  section.className = `pos-review-section${extraClass ? ` ${extraClass}` : ""}`;
  section.appendChild(createPersonalOsTextElement("div", "pos-label", label));
  const nodes = Array.isArray(content) ? content : [content];
  for (const node of nodes) {
    if (node) section.appendChild(node);
  }
  return section;
}

function posTargetSummary(review) {
  const target = review?.target && typeof review.target === "object" ? review.target : {};
  const candidate = posText(review?.targetCandidate || target.path).trim();
  const source = posText(review?.targetSource, candidate ? "inferred" : "").trim();
  const error = posText(target.error).trim();
  const hasDiff = Boolean(review?.diff);

  if (error) {
    return {
      candidate,
      source,
      status: "error",
      hasDiff,
      message: posClip(error, 900),
    };
  }
  if (hasDiff) {
    return { candidate, source, status: "diff", hasDiff, message: "" };
  }
  if (candidate) {
    const sourceText = source ? ` from ${source}` : "";
    return {
      candidate,
      source,
      status: "target",
      hasDiff,
      message: posUiText("pos.targetLoadedNoDiff", "Target loaded{{source}}; no automatic body diff for this draft.", { source: sourceText }),
    };
  }
  return { candidate: "", source: "", status: "none", hasDiff: false, message: posUiText("pos.noTargetAvailable", "No target available.") };
}

function createPersonalOsTargetReview(review) {
  const summary = posTargetSummary(review);
  const fragment = document.createDocumentFragment();
  if (summary.candidate) {
    fragment.appendChild(createPersonalOsTextElement(
      "div",
      "pos-detail-path",
      `${summary.candidate}${summary.source ? ` (${summary.source})` : ""}`
    ));
  }
  if (summary.status === "error") {
    fragment.appendChild(createPersonalOsTextElement("div", "pos-code pos-bad", summary.message));
  } else if (summary.hasDiff) {
    fragment.appendChild(createPersonalOsDiffView(review.diff));
  } else {
    fragment.appendChild(createPersonalOsTextElement("div", "pos-code", summary.message));
  }
  return fragment;
}

function createPersonalOsReviewRelated(review) {
  const related = Array.isArray(review?.related) ? review.related : [];
  if (related.length === 0) {
    return createPersonalOsTextElement("div", "pos-code", posUiText("pos.noReadableRelatedFiles", "No readable related files in the review package."));
  }
  const list = document.createElement("div");
  list.className = "pos-related-list";
  for (const item of related) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "pos-related-row";
    row.dataset.relatedPath = posText(item.path);
    if (item.error) row.disabled = true;
    const main = document.createElement("span");
    main.className = "pos-draft-main";
    main.append(
      createPersonalOsTextElement("span", "pos-draft-title", posText(item.title, item.path || posUiText("pos.relatedFileFallback", "Related file"))),
      createPersonalOsTextElement("span", "pos-draft-path", posText(item.path))
    );
    row.append(
      main,
      createPersonalOsPill(
        item.error ? posUiText("pos.statusError", "error") : posText(item.memory_level || item.type, posUiText("pos.kindFile", "file")),
        item.error ? "pos-bad" : ""
      )
    );
    list.appendChild(row);
  }
  return list;
}

function createPersonalOsReviewHistory(review) {
  const history = review?.history || {};
  const events = Array.isArray(history.events) ? history.events : [];
  if (history.error) {
    return createPersonalOsTextElement("div", "pos-code pos-bad", posText(history.error));
  }
  if (events.length === 0) {
    return createPersonalOsTextElement("div", "pos-code", posUiText("pos.noDraftHistory", "No draft history in the event log."));
  }

  const list = document.createElement("div");
  list.className = "pos-history-list";
  for (const event of events.slice().reverse()) {
    const row = document.createElement("div");
    row.className = "pos-history-row";
    const dot = document.createElement("span");
    dot.className = `pos-history-dot ${posEventClass(event.type)}`;
    const main = document.createElement("span");
    main.className = "pos-draft-main";
    main.append(
      createPersonalOsTextElement("span", "pos-draft-title", posText(event.type, posUiText("pos.historyEventFallback", "Event"))),
      createPersonalOsTextElement("span", "pos-draft-path", `${posText(event.timestamp)} - ${posText(event.agent, "unknown")}`)
    );
    if (event.reason) {
      main.appendChild(createPersonalOsTextElement("span", "pos-history-reason", posText(event.reason)));
    }
    row.append(dot, main);
    list.appendChild(row);
  }
  return list;
}

function createPersonalOsDraftDetailView(payload, review, body, approval, tags, related) {
  const fragment = document.createDocumentFragment();
  const meta = document.createElement("div");
  meta.className = "pos-detail-meta pos-detail-meta-friendly";
  meta.append(
    createPersonalOsPill(posDraftStatusText(approval), posStatusClass(approval)),
    createPersonalOsTextElement("span", "", posUiText("pos.memoryChangeProtected", "Stable memory stays protected until approval."))
  );
  fragment.appendChild(meta);

  const assist = review ? createPersonalOsAssistCard(review) : null;
  if (assist) fragment.appendChild(assist);

  const bodyEl = document.createElement("pre");
  bodyEl.className = "pos-markdown";
  bodyEl.textContent = body;
  fragment.appendChild(createPersonalOsReviewSection(posUiText("pos.labelDraftBodyUser", "Proposal"), bodyEl, "pos-review-section-main"));

  const details = document.createElement("details");
  details.className = "pos-technical-details pos-draft-technical";
  details.append(
    createPersonalOsTextElement("summary", "", posUiText("pos.showTechnicalDetails", "Technical details")),
    createPersonalOsTextElement("div", "pos-detail-path", posText(payload.path))
  );

  const grid = document.createElement("div");
  grid.className = "pos-detail-grid";
  const tagsCell = document.createElement("div");
  tagsCell.append(
    createPersonalOsTextElement("div", "pos-label", posUiText("pos.labelTags", "Tags")),
    createPersonalOsTextElement("div", "pos-code", tags || "-")
  );
  const relatedCell = document.createElement("div");
  relatedCell.appendChild(createPersonalOsTextElement("div", "pos-label", posUiText("pos.labelRelated", "Related")));
  const relatedEl = document.createElement("pre");
  relatedEl.className = "pos-code";
  relatedEl.textContent = related || "-";
  relatedCell.appendChild(relatedEl);
  grid.append(tagsCell, relatedCell);
  details.appendChild(grid);

  if (review) {
    const promptHint = typeof createPosPromptHint === "function" ? createPosPromptHint(payload, review) : null;
    const applyHint = typeof createPosApplyHint === "function" ? createPosApplyHint(review) : null;
    if (promptHint) details.appendChild(promptHint);
    if (applyHint) details.appendChild(applyHint);
    details.append(
      createPersonalOsReviewChecklist(review, approval),
      createPersonalOsReviewSection(posUiText("pos.labelHistory", "History"), createPersonalOsReviewHistory(review)),
      createPersonalOsReviewSection(posUiText("pos.labelTargetReview", "Target Review"), createPersonalOsTargetReview(review)),
      createPersonalOsReviewSection(posUiText("pos.labelRelatedContext", "Related Context"), createPersonalOsReviewRelated(review))
    );
  }

  fragment.appendChild(details);
  return fragment;
}

function attachPosReviewHandlers(detail) {
  detail.querySelectorAll("[data-related-path]").forEach((row) => {
    row.addEventListener("click", () => {
      const path = row.dataset.relatedPath;
      if (path) personalOsReadContextFile(path);
    });
  });
}

function renderPersonalOsDetail(payload, review = null) {
  const detail = document.getElementById("pos-draft-detail");
  const title = document.getElementById("pos-detail-title");
  const approveBtn = document.getElementById("pos-approve-btn");
  const rejectBtn = document.getElementById("pos-reject-btn");
  const applyBtn = document.getElementById("pos-apply-btn");
  const chatReviewBtn = document.getElementById("pos-chat-review-btn");
  if (!detail || !title || !approveBtn || !rejectBtn || !applyBtn || !chatReviewBtn) return;

  if (!payload?.ok) {
    title.textContent = posUiText("pos.draftTitle", "Draft");
    approveBtn.disabled = true;
    rejectBtn.disabled = true;
    applyBtn.disabled = true;
    applyBtn.title = "";
    chatReviewBtn.disabled = true;
    setPersonalOsEmptyState(detail, posErrorMessage(payload, posUiText("pos.draftLoadFailed", "Draft konnte nicht geladen werden.")));
    return;
  }

  const fm = payload.frontmatter || {};
  const body = posText(payload.body);
  const tags = Array.isArray(fm.tags) ? fm.tags.join(", ") : "";
  const related = Array.isArray(fm.related) ? fm.related.join("\n") : "";
  const approval = posText(payload.approval, "unknown");

  PersonalOSState.selectedDraft = payload;
  PersonalOSState.selectedReview = review;
  title.textContent = posText(fm.title, posUiText("pos.draftTitle", "Draft"));
  approveBtn.disabled = approval === "approved";
  rejectBtn.disabled = approval === "rejected";
  const applyHint = review?.applyHint || {};
  applyBtn.disabled = !(approval === "approved" && applyHint.enabled);
  applyBtn.title = applyBtn.disabled
    ? posText(applyHint.reason, posUiText("pos.applyApprovedOnly", "Apply is available only for approved supported drafts."))
    : posUiText("pos.applyApprovedTitle", "Apply approved draft through the SDK boundary.");
  chatReviewBtn.disabled = !review;

  detail.replaceChildren(createPersonalOsDraftDetailView(payload, review, body, approval, tags, related));
  attachPosReviewHandlers(detail);
}

function renderPersonalOsQueryPayload(payload) {
  const target = document.getElementById("pos-query-results");
  if (!target) return;

  if (!payload || payload.error || payload.detail || payload.ok === false) {
    clearPersonalOsQuerySelection();
    setPersonalOsEmptyState(target, posErrorMessage(payload, posUiText("pos.queryFailed", "Query failed")));
    return;
  }

  if (Array.isArray(payload.matches)) {
    clearPersonalOsQuerySelection();
    PersonalOSState.queryMatches = payload.matches;
    if (payload.matches.length === 0) {
      setPersonalOsEmptyState(target, posUiText("pos.noQueryMatches", "No matches."));
      return;
    }
    target.replaceChildren();
    for (const match of payload.matches) {
      const row = createPersonalOsQueryMatchRow(match);
      row.addEventListener("click", () => personalOsReadContextFile(match.path));
      target.appendChild(row);
    }
    return;
  }

  const fm = payload.frontmatter || {};
  const title = posText(fm.title, payload.path || "Index");
  const tags = Array.isArray(fm.tags) ? fm.tags.join(", ") : "";
  clearPersonalOsQuerySelection();
  PersonalOSState.selectedContext = payload;
  target.replaceChildren(createPersonalOsQueryDocumentView(payload, title, tags));
}

function renderPersonalOsContextPack(payload) {
  const target = document.getElementById("pos-query-results");
  if (!target) return;

  if (!payload || payload.error || payload.detail || payload.ok === false) {
    clearPersonalOsQuerySelection();
    setPersonalOsEmptyState(target, posErrorMessage(payload, posUiText("pos.contextPackFailed", "Context Pack failed")));
    return;
  }

  const query = payload.query || {};
  const files = Array.isArray(payload.files) ? payload.files : [];
  const errors = Array.isArray(payload.errors) ? payload.errors : [];
  const graph = payload.graph || {};
  const graphEdges = Number(graph?.counts?.edges || 0);
  const graphLabel = graph?.ok === false
    ? (graphEdges ? posUiText("pos.graphNotePartial", "partial") : posUiText("pos.statusError", "error"))
    : String(graphEdges);
  const graphClass = graph?.ok === false ? "pos-warn" : "pos-good";
  clearPersonalOsQuerySelection();
  PersonalOSState.selectedContextPack = payload;

  target.replaceChildren(createPersonalOsContextPackView(query, files, errors, graphLabel, graphClass));

  target.querySelectorAll("[data-related-path]").forEach((row) => {
    row.addEventListener("click", () => {
      const path = row.dataset.relatedPath;
      if (path) personalOsReadContextFile(path);
    });
  });
}

function personalOsObsidianPrompt(payload) {
  const vault = payload?.vault || {};
  const counts = payload?.counts || {};
  const product = payload?.lexaProductContract || {};
  const inventory = payload?.lexaInventory || {};
  const quickFind = Array.isArray(inventory.quickFind) ? inventory.quickFind.slice(0, 12) : [];
  const surfaces = Array.isArray(inventory.surfaces) ? inventory.surfaces.slice(0, 8) : [];
  const files = Array.isArray(payload?.files) ? payload.files.slice(0, 5) : [];
  const rows = [
    posUiText("pos.obsidianPromptIntro", "Use this Obsidian/Personal OS context map as source material:"),
    "",
    `${posUiText("pos.promptTopicLabel", "Topic")}: ${posText(payload?.topic, "-")}`,
    `${posUiText("pos.promptVaultLabel", "Vault")}: ${posText(vault.root, "-")}`,
    `${posUiText("pos.promptProviderModeLabel", "Provider mode")}: ${posText(product.providerMode, "api-backed")}`,
    `${posUiText("pos.promptLoadedAllLabel", "Loaded all files")}: ${vault.loadedAll === true ? "true" : "false"}`,
    `${posUiText("pos.promptBootstrapLabel", "Bootstrap")}: ${posCount(counts.bootstrapAvailable)}`,
    `${posUiText("pos.promptAreaIndexesLabel", "Area indexes")}: ${posCount(counts.areaIndexes)}`,
    "",
    "Product contract:",
    `- ${posText(product.rule, "Lexa uses configured provider APIs for model intelligence.")}`,
    "",
    "Quick find:",
    quickFind.length ? quickFind.map((item) => `- ${posText(item.need, "Context")}: ${posText(item.goTo, "-")}`).join("\n") : "-",
    "",
    "Context surfaces:",
    surfaces.length ? surfaces.map((surface) => `- ${posText(surface.id)}: ${posText(surface.purpose)} (${posCount(surface.fileCountApprox)} files)`).join("\n") : "-",
    "",
    "Selected OS context:",
    files.length ? files.map((file) => [
      `## ${posText(file.title, file.path)}`,
      `${posUiText("pos.promptPathLabel", "Path")}: ${posText(file.path)}`,
      `${posUiText("pos.promptMemoryLevelLabel", "Memory-Level")}: ${posText(file.memory_level, "unknown")}`,
      `${posUiText("pos.promptTagsLabel", "Tags")}: ${Array.isArray(file.tags) ? file.tags.join(", ") : "-"}`,
      "",
      posClip(file.bodyPreview, 500),
    ].join("\n")).join("\n\n") : "-",
    "",
    posUiText("pos.promptQuestionBlank", "My question: "),
  ];
  return posClipChatPrompt(rows.join("\n"));
}

function renderPersonalOsObsidianContext(payload) {
  const target = document.getElementById("pos-query-results");
  if (!target) return;

  if (!payload || payload.error || payload.detail || payload.ok === false) {
    clearPersonalOsQuerySelection();
    setPersonalOsEmptyState(target, posErrorMessage(payload, posUiText("pos.obsidianContextFailed", "Obsidian context failed")));
    return;
  }

  const vault = payload.vault || {};
  const counts = payload.counts || {};
  const product = payload.lexaProductContract || {};
  const inventory = payload.lexaInventory || {};
  const quickFind = Array.isArray(inventory.quickFind) ? inventory.quickFind : [];
  const surfaces = Array.isArray(inventory.surfaces) ? inventory.surfaces : [];
  const files = Array.isArray(payload.files) ? payload.files : [];
  clearPersonalOsQuerySelection();
  PersonalOSState.selectedObsidianContext = payload;

  target.replaceChildren(createPersonalOsObsidianContextView(vault, counts, product, quickFind, surfaces, files));
}

function renderPersonalOsCodeLoop(payload) {
  const target = document.getElementById("pos-query-results");
  if (!target) return;

  if (!payload || payload.error || payload.detail || payload.ok === false) {
    clearPersonalOsQuerySelection();
    setPersonalOsEmptyState(target, posErrorMessage(payload, posUiText("pos.codeLoopFailed", "Code Loop failed")));
    return;
  }

  const diagnostics = payload.diagnostics || {};
  const drafts = Array.isArray(payload?.drafts?.items) ? payload.drafts.items : [];
  const draftRows = posCodeLoopDraftRows(drafts, 8);
  const contextFiles = Array.isArray(payload?.contextPack?.files) ? payload.contextPack.files : [];
  const raw = payload.rawInbox || {};
  const evidence = posCodeLoopEvidenceCounts(payload);
  const meta = personalOsCodeLoopPromptMeta(payload);
  clearPersonalOsQuerySelection();
  PersonalOSState.selectedCodeLoop = payload;

  target.replaceChildren(createPersonalOsCodeLoopView(payload, diagnostics, draftRows, contextFiles, raw, evidence, meta));

  target.querySelectorAll("[data-code-loop-draft]").forEach((row) => {
    row.addEventListener("click", () => {
      const path = row.dataset.codeLoopDraft;
      if (path) selectPersonalOsDraft(path);
    });
  });
  target.querySelector("[data-code-loop-action='load-pending']")?.addEventListener("click", () => {
    loadPersonalOsPendingQueue();
  });
  target.querySelectorAll("[data-code-loop-file]").forEach((row) => {
    row.addEventListener("click", () => {
      const path = row.dataset.codeLoopFile;
      if (path) personalOsReadContextFile(path);
    });
  });
}
