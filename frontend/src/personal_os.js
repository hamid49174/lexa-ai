/* Personal OS cockpit: draft queue and human review */

const PersonalOSState = {
  drafts: [],
  draftSearch: "",
  selectedPath: null,
  selectedDraft: null,
  selectedReview: null,
  queryMatches: [],
  graph: null,
  selectedContext: null,
  selectedContextPack: null,
  selectedObsidianContext: null,
  selectedCodeLoop: null,
  rawInboxStatus: null,
  lastRefreshAt: null,
  isRefreshing: false,
  isSelecting: false,
  isDeciding: false,
  isApplying: false,
};

function posChatPromptLimit(limit = 3600) {
  const configured = Number(globalThis?.LexaConfig?.MAX_CHAT_INPUT_LENGTH);
  const safeConfigured = Number.isFinite(configured) ? Math.max(500, configured - 250) : limit;
  return Math.max(500, Math.min(limit, safeConfigured));
}

function posClipChatPrompt(value, limit = posChatPromptLimit()) {
  const text = posText(value);
  const safeLimit = posChatPromptLimit(limit);
  if (text.length <= safeLimit) return text;
  const suffix = posUiText("pos.promptCompactedSuffix", "\n\n[Prompt compacted to fit Lexa chat limit.]\n\nMeine Frage dazu: Bitte gib mir eine knappe Review-Empfehlung.");
  return `${text.slice(0, Math.max(0, safeLimit - suffix.length))}${suffix}`;
}

function personalOsReviewPromptMeta(draft, review) {
  const prompt = personalOsReviewPrompt(draft, review);
  const limit = posChatPromptLimit();
  return {
    length: prompt.length,
    limit,
    percent: Math.min(100, Math.round((prompt.length / limit) * 100)),
    compacted: prompt.includes("Prompt compacted"),
  };
}

function personalOsCodeLoopPrompt(payload) {
  return posClipChatPrompt(posText(payload?.prompt));
}

function personalOsCodeLoopAgentPrompt(payload) {
  const prompt = posText(payload?.prompt);
  return prompt.trim() ? posClipChatPrompt(`/agent ${prompt}`) : "";
}

function personalOsCodeLoopPromptMeta(payload) {
  const prompt = posText(payload?.prompt);
  const limit = posChatPromptLimit();
  return {
    length: prompt.length,
    limit,
    percent: Math.min(100, Math.round((prompt.length / limit) * 100)),
    compacted: personalOsCodeLoopPrompt(payload).includes("Prompt compacted"),
  };
}

function posCodeLoopEvidenceCounts(payload) {
  const diagnostics = payload?.diagnostics || {};
  const counts = diagnostics.counts || {};
  const contextFiles = Array.isArray(payload?.contextPack?.files) ? payload.contextPack.files : [];
  const drafts = Array.isArray(payload?.drafts?.items) ? payload.drafts.items : [];
  const raw = payload?.rawInbox || {};
  const failures = raw.failureState || {};
  const graph = payload?.contextPack?.graph || {};
  const graphCounts = graph.counts || {};
  const graphErrors = Array.isArray(graph.errors) ? graph.errors : [];
  return {
    pending: posCount(counts.pending),
    approved: posCount(counts.approved),
    rejected: posCount(counts.rejected),
    invalid: posCount(counts.invalid),
    contextFiles: contextFiles.length,
    drafts: drafts.length,
    workerFailures: posCount(failures.failed),
    graphFiles: posCount(graphCounts.files),
    graphEdges: posCount(graphCounts.edges),
    graphErrors: posCount(graphCounts.errors) || graphErrors.length,
    graphOk: graph.ok !== false,
  };
}

function posCodeLoopDraftRank(draft) {
  const approval = posText(draft?.approval).toLowerCase();
  if (approval === "invalid" || approval === "conflict" || approval === "missing") return 0;
  if (approval === "pending" || approval === "review") return 1;
  if (approval === "approved") return 2;
  if (approval === "rejected") return 3;
  return 4;
}

function posCodeLoopDraftRows(drafts, limit = 8) {
  return (Array.isArray(drafts) ? drafts : [])
    .map((draft, index) => ({ draft, index, rank: posCodeLoopDraftRank(draft) }))
    .sort((a, b) => (a.rank - b.rank) || (a.index - b.index))
    .slice(0, limit)
    .map((entry) => entry.draft);
}

function posMeterWidthClass(percent) {
  const safe = Math.max(0, Math.min(100, Number(percent) || 0));
  return `meter-width-${Math.round(safe / 5) * 5}`;
}

function personalOsPlacePromptInChat(prompt, successMessage, emptyMessage = posUiText("pos.promptNotReady", "No OS prompt ready.")) {
  const original = posText(prompt);
  const prepared = posClipChatPrompt(original);
  if (!prepared.trim()) {
    showToast(emptyMessage, "warning");
    return false;
  }
  if (!chatInput) {
    showToast(posUiText("pos.chatInputUnavailable", "Chat input is not ready."), "error");
    return false;
  }

  switchView("chat");
  chatInput.value = prepared;
  chatInput.dispatchEvent(new Event("input", { bubbles: true }));
  chatInput.focus();
  const clippedMessage = posUiText("pos.promptClipped", "{{message}} Prompt was shortened.", { message: successMessage });
  showToast(prepared.length < original.length ? clippedMessage : successMessage, prepared.length < original.length ? "info" : "success");
  return true;
}

function personalOsHasOpenModal() {
  if (typeof document === "undefined") return false;
  return Boolean(document.querySelector(
    ".note-modal-overlay, .cmd-palette-overlay.visible, .search-overlay.visible, #shortcuts-overlay, #onboarding-overlay"
  ));
}

function personalOsCanAutoRefresh(state = PersonalOSState) {
  return !state?.isRefreshing
    && !state?.isSelecting
    && !state?.isDeciding
    && !state?.isApplying
    && !state?.selectedPath
    && !personalOsHasOpenModal();
}

function posRenderBadge(count) {
  const badge = document.getElementById("nav-pos-badge");
  if (!badge) return;
  const safe = Number.isFinite(count) ? count : 0;
  badge.textContent = safe > 99 ? "99+" : String(safe);
  badge.classList.toggle("hidden", safe <= 0);
}

function clearPersonalOsDraftDetail(message = null) {
  PersonalOSState.selectedPath = null;
  PersonalOSState.selectedDraft = null;
  PersonalOSState.selectedReview = null;
  const emptyMessage = message ?? posUiText("pos.noDraftSelected", "Kein Entwurf ausgewählt.");
  const detail = document.getElementById("pos-draft-detail");
  const title = document.getElementById("pos-detail-title");
  const approveBtn = document.getElementById("pos-approve-btn");
  const rejectBtn = document.getElementById("pos-reject-btn");
  const applyBtn = document.getElementById("pos-apply-btn");
  const chatReviewBtn = document.getElementById("pos-chat-review-btn");
  if (title) title.textContent = posUiText("pos.draftTitle", "Draft");
  [approveBtn, rejectBtn, applyBtn, chatReviewBtn].forEach((button) => {
    if (button) button.disabled = true;
  });
  if (applyBtn) applyBtn.title = "";
  if (detail) detail.innerHTML = `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
}

function clearPersonalOsQuerySelection() {
  PersonalOSState.queryMatches = [];
  PersonalOSState.selectedContext = null;
  PersonalOSState.selectedContextPack = null;
  PersonalOSState.selectedObsidianContext = null;
  PersonalOSState.selectedCodeLoop = null;
}

function posCount(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function posQueueCounts(queue) {
  const counts = queue?.counts || {};
  return {
    total: posCount(counts.total),
    pending: posCount(counts.pending),
    approved: posCount(counts.approved),
    rejected: posCount(counts.rejected),
    invalid: posCount(counts.invalid),
  };
}

function posDraftEmptyMessage(approval) {
  switch (approval) {
    case "pending":
      return posUiText("pos.emptyPendingDrafts", "No pending drafts. Review queue is clear.");
    case "approved":
      return posUiText("pos.emptyApprovedDrafts", "No approved drafts in this filter.");
    case "rejected":
      return posUiText("pos.emptyRejectedDrafts", "No rejected drafts in this filter.");
    case "conflict":
      return posUiText("pos.emptyConflictDrafts", "No conflict drafts.");
    case "missing":
      return posUiText("pos.emptyMissingApprovalDrafts", "No drafts with a missing approval box.");
    default:
      return posUiText("pos.emptyDrafts", "No drafts in this filter.");
  }
}

function posDraftQueueError(payload) {
  if (payload?.ok !== false) return "";
  if (Array.isArray(payload?.errors) && payload.errors.length) {
    return posErrorMessage(payload.errors[0], posUiText("pos.draftQueueFailed", "Draft queue failed"));
  }
  return posErrorMessage(payload, posUiText("pos.draftQueueFailed", "Draft queue failed"));
}

function posDraftMatchesSearch(draft, search) {
  const needle = posText(search).trim().toLowerCase();
  if (!needle) return true;
  return [
    draft?.title,
    draft?.path,
    draft?.approval,
    draft?.memory_level,
    draft?.source,
    Array.isArray(draft?.tags) ? draft.tags.join(" ") : "",
  ].some((value) => posText(value).toLowerCase().includes(needle));
}

function posVisibleDrafts(drafts, search) {
  const rows = Array.isArray(drafts) ? drafts : [];
  const needle = posText(search).trim();
  return needle ? rows.filter((draft) => posDraftMatchesSearch(draft, needle)) : rows;
}

function posRawProcessorOptions(status) {
  const processors = Array.isArray(status?.processors) ? status.processors : [];
  const allowed = new Set(["deterministic", "lexa"]);
  const seen = new Set();
  const options = [];

  for (const entry of processors) {
    const name = posText(entry?.name).toLowerCase();
    if (!allowed.has(name) || entry?.status !== "available" || seen.has(name)) continue;
    seen.add(name);
    options.push({
      value: name,
      label: name === "lexa"
        ? posUiText("pos.rawProcessorLexa", "lexa (local extraction)")
        : posUiText("pos.rawProcessorSafeDefault", "deterministic (safe default)"),
    });
  }

  if (!seen.has("deterministic")) {
    options.unshift({ value: "deterministic", label: posUiText("pos.rawProcessorSafeDefault", "deterministic (safe default)") });
  }
  return options;
}

function posRawStatusSummary(status) {
  const processors = Array.isArray(status?.processors) ? status.processors : [];
  const available = processors
    .filter((entry) => ["deterministic", "lexa"].includes(posText(entry?.name).toLowerCase()) && entry?.status === "available")
    .map((entry) => {
      const name = posText(entry.name).toLowerCase();
      if (posUiLanguage().startsWith("de")) {
        if (name === "deterministic") return posUiText("pos.rawProcessorSafeDefault", "sicherer Standard");
        if (name === "lexa") return "Lexa";
      }
      return posText(entry.name);
    });
  const failed = posCount(status?.failureState?.failed);
  const names = available.length
    ? available.join(", ")
    : (posUiLanguage().startsWith("de") ? posUiText("pos.rawProcessorSafeDefault", "sicherer Standard") : "deterministic");
  return posUiText("pos.rawReadySummary", "Raw Inbox ready: {{names}}; {{failed}} worker failure{{plural}}.", {
    names,
    failed,
    plural: failed === 1 ? "" : "s",
  });
}

function posUiLanguage() {
  try {
    if (typeof LexaI18n === "object" && typeof LexaI18n.getCurrentLanguage === "function") {
      return posText(LexaI18n.getCurrentLanguage()).toLowerCase();
    }
  } catch (_) { }
  try {
    if (typeof document !== "undefined" && document.documentElement?.lang) {
      return posText(document.documentElement.lang).toLowerCase();
    }
  } catch (_) { }
  return "en";
}

function posLanguageText(value) {
  const text = posText(value);
  if (!text || !posUiLanguage().startsWith("de")) return text;
  const exact = {
    "connected": "verbunden",
    "offline": "offline",
    "unknown": "unbekannt",
    "Personal OS connected.": "Personal OS verbunden.",
    "Personal OS unavailable.": "Personal OS nicht verfügbar.",
    "Personal OS integration is connected and the review queue is clear.": "Personal OS ist verbunden. Keine Prüfung offen.",
    "Personal OS integration is connected but needs review attention.": "Personal OS ist verbunden. Prüfungen brauchen Aufmerksamkeit.",
    "Personal OS integration has blocking issues.": "Personal OS hat blockierende Probleme.",
    "Continue with context browsing, Context Map review, or new controlled draft intake.": "Kontext suchen, Kontextkarte prüfen oder neue Notiz ablegen.",
    "Continue with context browsing or Code Loop.": "Kontext suchen oder Lexa-Plan starten.",
    "Continue with context browsing.": "Kontext suchen.",
    "Review pending drafts through the cockpit.": "Offene Entwürfe in Lexa prüfen.",
    "Review pending drafts.": "Offene Entwürfe prüfen.",
    "Review queue is free.": "Keine Prüfung offen.",
    "Reconnect Personal OS and refresh the cockpit.": "Personal OS neu verbinden und Cockpit aktualisieren.",
    "Pending drafts": "Offene Entwürfe",
    "MCP connection": "MCP-Verbindung",
    "Capabilities": "Fähigkeiten",
    "Personal OS tools unavailable.": "Personal-OS-Werkzeuge nicht verfügbar.",
    "Fix blocking diagnostics before continuing.": "Blockierende Diagnose vor dem Fortfahren beheben.",
    "Low disk space.": "Wenig freier Speicher.",
  };
  if (Object.prototype.hasOwnProperty.call(exact, text)) return exact[text];
  let translated = text
    .replace(/\bContext Map\b/g, "Kontextkarte")
    .replace(/\bContext Pack\b/g, "Kontextpaket")
    .replace(/\bCode Loop\b/g, "Lexa-Plan")
    .replace(/\bDrafts\b/g, "Entwürfe")
    .replace(/\bdrafts\b/g, "Entwürfe")
    .replace(/\bDraft\b/g, "Entwurf")
    .replace(/\bdraft\b/g, "Entwurf")
    .replace(/\bReview\b/g, "Prüfung")
    .replace(/\breview\b/g, "Prüfung")
    .replace(/\bQueue\b/g, "Liste")
    .replace(/\bqueue\b/g, "Liste")
    .replace(/\bMissing capabilities\b/g, "Fehlende Fähigkeiten")
    .replace(/\bgraph\b/g, "Kontextkarte")
    .replace(/\bLow disk space\b/g, "Wenig freier Speicher")
    .replace(/\bfree\b/g, "frei")
    .replace(/\bconnected\b/g, "verbunden");
  translated = translated.replace(/(\d+) Entwurf\(s\) still need human Prüfung\./g, (_match, count) => {
    const one = Number(count) === 1;
    return `${count} ${one ? "Entwurf braucht" : "Entwürfe brauchen"} menschliche Prüfung.`;
  });
  return translated;
}

function posDiagnosticHeadline(diagnostics, fallback = "Personal OS connected.") {
  const summary = posLanguageText(posText(diagnostics?.summary, fallback));
  const checks = Array.isArray(diagnostics?.checks) ? diagnostics.checks : [];
  const priority = checks.find((check) => check?.state === "block") || checks.find((check) => check?.state === "warn");
  if (!priority) return summary;
  const label = posLanguageText(posText(priority.label, posUiText("pos.metricDiagnostic", "Diagnostic")));
  const detail = posLanguageText(posText(priority.detail, summary));
  return `${label}: ${detail}`;
}

function posOfflineDiagnostics(error, fallback = "Personal OS unavailable.") {
  const detail = posErrorMessage(error && typeof error === "object" ? error : { error: posText(error) }, fallback);
  const counts = { total: 0, pending: 0, approved: 0, rejected: 0, conflict: 0, missing: 0, invalid: 1 };
  return {
    ok: false,
    state: "blocked",
    summary: detail,
    checks: [
      { id: "mcp", label: posUiText("pos.cardMcpConnection", "MCP connection"), state: "block", detail },
      { id: "capabilities", label: posUiText("pos.cardCapabilities", "Capabilities"), state: "block", detail: posUiText("pos.toolsUnavailable", "Personal OS tools unavailable.") },
    ],
    counts,
    status: {
      status: "offline",
      server: "personal_os",
      tools: [],
      tools_count: 0,
      draft_review: false,
      capabilities: {
        draftQueue: false,
        reviewPacket: false,
        auditHistory: false,
        contextBrowser: false,
        graph: false,
        explicitApply: false,
      },
      missing_tools: {
        draftQueue: ["os_list_drafts"],
        reviewPacket: ["os_view_draft"],
        contextBrowser: ["os_query_index"],
        graph: ["os_graph_index"],
      },
    },
    nextAction: posUiText("pos.nextReconnect", "Reconnect Personal OS and refresh the cockpit."),
  };
}

function posIsOfflineDiagnostics(diagnostics) {
  return posText(diagnostics?.status?.status) === "offline";
}

function posNextActionText(diagnostics, queue) {
  if (posIsOfflineDiagnostics(diagnostics)) {
    return posLanguageText(posText(diagnostics?.nextAction, posUiText("pos.nextReconnect", "Reconnect Personal OS and refresh the cockpit.")));
  }
  const counts = posQueueCounts(queue);
  const drafts = Array.isArray(queue?.drafts) ? queue.drafts : [];
  const checks = Array.isArray(diagnostics?.checks) ? diagnostics.checks : [];
  const storageWarning = checks.find((check) => check?.id === "system-storage" && check?.state === "warn");
  const pendingDraft = drafts.find((draft) => draft?.approval === "pending") || null;
  if (counts.invalid > 0) return posUiText("pos.nextFixInvalidDrafts", "Fix {{count}} invalid draft{{plural}}", { count: counts.invalid, plural: counts.invalid === 1 ? "" : "s" });
  if (posText(diagnostics?.state) === "blocked") {
    return posLanguageText(posText(diagnostics?.nextAction, posUiText("pos.nextFixBlocking", "Fix blocking diagnostics before continuing.")));
  }
  if (storageWarning) {
    return posUiText("pos.nextSystemStorage", "System storage: {{detail}}", { detail: posLanguageText(posText(storageWarning.detail, posUiText("pos.lowDiskSpace", "Low disk space."))) });
  }
  if (counts.pending > 0) {
    const title = pendingDraft ? posText(pendingDraft.title || pendingDraft.path, posUiText("pos.pendingDraftFallback", "Pending draft")) : posUiText("pos.pendingDraftFallback", "Pending draft");
    return counts.pending === 1
      ? posUiText("pos.nextReviewTitle", "Review: {{title}}", { title })
      : posUiText("pos.nextReviewCount", "Review {{count}} pending drafts", { count: counts.pending });
  }
  return posLanguageText(posText(diagnostics?.nextAction, posUiText("pos.nextContinueContext", "Continue with context browsing or Code Loop.")));
}

function posNextDraftPath(queue) {
  const drafts = Array.isArray(queue?.drafts) ? queue.drafts : [];
  const pendingDraft = drafts.find((draft) => draft?.approval === "pending" && draft?.path);
  return posText(pendingDraft?.path);
}

function posNextCardAction(queue, diagnostics = null) {
  if (posIsOfflineDiagnostics(diagnostics)) return "";
  const counts = posQueueCounts(queue);
  if (counts.invalid > 0) return "load-all";
  if (posText(diagnostics?.state) === "blocked") return "";
  const checks = Array.isArray(diagnostics?.checks) ? diagnostics.checks : [];
  if (checks.some((check) => check?.id === "system-storage" && check?.state === "warn")) return "";
  if (posNextDraftPath(queue)) return "open-draft";
  if (counts.pending > 0) return "load-pending";
  return "";
}

function focusPersonalOsContextSearch() {
  const panel = document.querySelector(".pos-query-panel");
  const input = document.getElementById("pos-tag-input") || document.getElementById("pos-area-input");
  if (panel && panel.tagName === "DETAILS") panel.open = true;
  panel?.scrollIntoView({ behavior: "smooth", block: "start" });
  setTimeout(() => input?.focus(), 180);
}

function loadPersonalOsQueueFilter(approval = "pending") {
  const filter = document.getElementById("pos-approval-filter");
  const search = document.getElementById("pos-draft-search");
  if (filter) filter.value = approval;
  if (search) search.value = "";
  PersonalOSState.draftSearch = "";
  PersonalOSState.selectedPath = null;
  PersonalOSState.selectedDraft = null;
  PersonalOSState.selectedReview = null;
  refreshPersonalOsView({ preserveSelection: false });
}

function loadPersonalOsPendingQueue() {
  loadPersonalOsQueueFilter("pending");
}

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

  grid.innerHTML = `
    <section class="pos-home-card">
      <div class="pos-home-copy">
        <div class="pos-kicker">${escapeHtml(posUiText("pos.homeKicker", "Personal OS"))}</div>
        <h2>${escapeHtml(homeTitle)}</h2>
        <p>${escapeHtml(homeSummary)}</p>
      </div>
      <div class="pos-home-actions">
        <button type="button" class="pos-home-action pos-home-action-primary pos-next-card" data-pos-home-action="review" data-next-draft-path="${escapeHtml(nextDraftPath)}" data-next-action="${escapeHtml(nextCardAction)}">
          <span>${escapeHtml(pending > 0 ? posUiText("pos.homeActionReview", "Review drafts") : posUiText("pos.homeActionOpenQueue", "Open reviews"))}</span>
          <small>${escapeHtml(nextAction)}</small>
        </button>
        <button type="button" class="pos-home-action" data-pos-home-action="raw">
          <span>${escapeHtml(posUiText("pos.homeActionCapture", "New note"))}</span>
          <small>${escapeHtml(posUiText("pos.homeActionCaptureSub", "Capture first, sort later"))}</small>
        </button>
        <button type="button" class="pos-home-action" data-pos-home-action="search">
          <span>${escapeHtml(posUiText("pos.homeActionFind", "Find context"))}</span>
          <small>${escapeHtml(posUiText("pos.homeActionFindSub", "Search by area or topic"))}</small>
        </button>
        <button type="button" class="pos-home-action" data-pos-home-action="lexa">
          <span>${escapeHtml(posUiText("pos.homeActionLexa", "Continue Lexa"))}</span>
          <small>${escapeHtml(posUiText("pos.homeActionLexaSub", "Build the next plan"))}</small>
        </button>
      </div>
      <div class="pos-home-status">
        <span class="${posAssistClass(diagnosticState)}">${escapeHtml(posStateLabel(diagnosticState))}</span>
        <span>${escapeHtml(refreshLabel)}</span>
        <span>${escapeHtml(posUiText("pos.homeStatusDrafts", "{{pending}} open / {{approved}} approved / {{rejected}} closed", { pending, approved, rejected }))}</span>
      </div>
      <details class="pos-technical-details">
        <summary>${escapeHtml(posUiText("pos.showTechnicalDetails", "Technical details"))}</summary>
        <div class="pos-technical-grid">
          <div class="info-card">
            <div class="info-card-label">${escapeHtml(posUiText("pos.cardHealth", "HEALTH"))}</div>
            <div class="info-card-value ${posAssistClass(diagnosticState)}">${escapeHtml(posStateLabel(diagnosticState))}</div>
            <div class="info-card-sub">${escapeHtml(diagnosticSummary)}</div>
          </div>
          <div class="info-card">
            <div class="info-card-label">${escapeHtml(posUiText("pos.cardNext", "NEXT"))}</div>
            <div class="info-card-value ${nextValueClass}">${escapeHtml(nextValue)}</div>
            <div class="info-card-sub">${escapeHtml(nextAction)}</div>
          </div>
          <div class="info-card">
            <div class="info-card-label">${escapeHtml(posUiText("pos.cardMcp", "MCP"))}</div>
            <div class="info-card-value ${posStatusClass(status?.status)}">${escapeHtml(connectionStatus)}</div>
            <div class="info-card-sub">${escapeHtml(posText(status?.server, "personal_os"))}</div>
          </div>
          <div class="info-card">
            <div class="info-card-label">${escapeHtml(posUiText("pos.cardSync", "SYNC"))}</div>
            <div class="info-card-value pos-good">${escapeHtml(posStateLabel("live"))}</div>
            <div class="info-card-sub">${escapeHtml(refreshLabel)}</div>
          </div>
          <div class="info-card">
            <div class="info-card-label">${escapeHtml(posUiText("pos.cardTools", "TOOLS"))}</div>
            <div class="info-card-value">${toolsCount}</div>
            <div class="info-card-sub">${escapeHtml(posUiText("pos.subCapabilitiesReady", "{{reviewReady}} - {{readyCount}}/6 caps", { reviewReady, readyCount }))}</div>
          </div>
          <button type="button" class="info-card pos-action-card" data-queue-filter="pending">
            <div class="info-card-label">${escapeHtml(posUiText("pos.cardPending", "PENDING"))}</div>
            <div class="info-card-value ${pending ? "pos-warn" : "pos-good"}">${pending}</div>
            <div class="info-card-sub">${escapeHtml(draftSub)}</div>
          </button>
          <button type="button" class="info-card pos-action-card" data-queue-filter="approved">
            <div class="info-card-label">${escapeHtml(posUiText("pos.cardApproved", "APPROVED"))}</div>
            <div class="info-card-value ${approved ? "pos-good" : ""}">${approved}</div>
            <div class="info-card-sub">${escapeHtml(approvedSub)}</div>
          </button>
          <button type="button" class="info-card pos-action-card" data-queue-filter="rejected">
            <div class="info-card-label">${escapeHtml(posUiText("pos.cardRejected", "REJECTED"))}</div>
            <div class="info-card-value ${rejected ? "pos-bad" : ""}">${rejected}</div>
            <div class="info-card-sub">${escapeHtml(rejectedSub)}</div>
          </button>
          <button type="button" class="info-card pos-action-card" data-queue-filter="all">
            <div class="info-card-label">${escapeHtml(posUiText("pos.cardInvalid", "INVALID"))}</div>
            <div class="info-card-value ${invalid ? "pos-bad" : "pos-good"}">${invalid}</div>
            <div class="info-card-sub">${escapeHtml(invalidSub)}</div>
          </button>
        </div>
        <div class="pos-capability-grid">
          ${capabilityRows.map(([label, key, missing]) => {
            const ok = Boolean(capabilities[key]);
            const missingText = Array.isArray(missing) && missing.length
              ? posUiText("pos.capabilityMissingTools", "Missing: {{tools}}", { tools: missing.join(", ") })
              : posUiText("pos.capabilityReady", "Ready");
            return `
              <div class="pos-capability-item" title="${escapeHtml(missingText)}">
                <span class="pos-history-dot ${ok ? "pos-good" : "pos-bad"}"></span>
                <span>${escapeHtml(label)}</span>
              </div>
            `;
          }).join("")}
        </div>
      </details>
    </section>
  `;

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
    list.innerHTML = `<div class="empty-state">${escapeHtml(queueError)}</div>`;
    clearPersonalOsDraftDetail(queueError);
    return;
  }
  if (drafts.length === 0) {
    const filterValue = document.getElementById("pos-approval-filter")?.value || "all";
    list.innerHTML = `<div class="empty-state">${escapeHtml(posDraftEmptyMessage(filterValue))}</div>`;
    clearPersonalOsDraftDetail();
    return;
  }
  if (visibleDrafts.length === 0) {
    list.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.noDraftSearchResult", "No draft found for this search."))}</div>`;
    clearPersonalOsDraftDetail();
    return;
  }

  list.innerHTML = "";
  for (const draft of visibleDrafts) {
    const row = document.createElement("button");
    const isSelected = draft.path === PersonalOSState.selectedPath;
    row.type = "button";
    row.className = "pos-draft-row";
    row.setAttribute("aria-current", isSelected ? "true" : "false");
    if (isSelected) row.classList.add("active");
    row.dataset.path = draft.path;
    row.innerHTML = `
      <span class="pos-draft-main">
        <span class="pos-draft-title">${escapeHtml(posText(draft.title, posUiText("pos.untitledDraft", "Untitled Draft")))}</span>
        <span class="pos-draft-subtitle">${escapeHtml(posDraftStatusText(draft.approval))}</span>
      </span>
      <span class="pos-pill ${posStatusClass(draft.approval)}">${escapeHtml(posText(draft.approval, "unknown"))}</span>
    `;
    row.addEventListener("click", () => selectPersonalOsDraft(draft.path));
    list.appendChild(row);
  }
}

function renderPosChecklist(review, approval) {
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

  return `
    <div class="pos-review-strip">
      ${items.map(([label, value, cls]) => `
        <div class="pos-review-card">
          <div class="pos-label">${escapeHtml(label)}</div>
          <div class="pos-review-value ${cls}">${escapeHtml(value)}</div>
        </div>
      `).join("")}
    </div>
  `;
}

function renderPosAssist(review) {
  const assist = review?.assist || {};
  const checks = Array.isArray(assist.checks) ? assist.checks : [];
  if (!assist.status || checks.length === 0) return "";
  const blocked = Number(assist.blocked || 0);
  const warnings = Number(assist.warnings || 0);

  return `
    <div class="pos-assist-card">
      <div class="pos-assist-head">
        <div>
          <div class="pos-label">${escapeHtml(posUiText("pos.labelReviewAssist", "Review Assist"))}</div>
          <div class="pos-assist-title ${posAssistClass(assist.status)}">${escapeHtml(posText(assist.status))}</div>
        </div>
        <span class="pos-pill ${posAssistClass(assist.status)}">${escapeHtml(posUiText("pos.reviewAssistCounts", "{{blocked}} block / {{warnings}} warn", { blocked, warnings }))}</span>
      </div>
      <div class="pos-assist-summary">${escapeHtml(posText(assist.summary))}</div>
      <div class="pos-assist-checks">
        ${checks.map((check) => `
          <div class="pos-assist-check">
            <span class="pos-history-dot ${posAssistClass(check.state)}"></span>
            <span class="pos-draft-main">
              <span class="pos-draft-title">${escapeHtml(posText(check.label))}</span>
              <span class="pos-draft-path">${escapeHtml(posText(check.detail))}</span>
            </span>
          </div>
        `).join("")}
      </div>
      ${assist.nextAction ? `<div class="pos-assist-summary">${escapeHtml(posText(assist.nextAction))}</div>` : ""}
    </div>
  `;
}

function renderPosApplyHint(review) {
  const hint = review?.applyHint || {};
  if (!hint.reason && !hint.target) return "";

  return `
    <div class="pos-apply-hint">
      <div class="pos-label">${escapeHtml(posUiText("pos.labelApplyBoundary", "Apply Boundary"))}</div>
      <div class="pos-draft-path">${escapeHtml(posText(hint.target, posUiText("pos.noApplyTarget", "No target")))}</div>
      <div class="${hint.enabled ? "pos-good" : "pos-warn"}">${escapeHtml(posText(hint.reason))}</div>
    </div>
  `;
}

function renderPosPromptHint(draft, review) {
  if (!draft?.path || !review) return "";
  const meta = personalOsReviewPromptMeta(draft, review);
  const cls = meta.percent >= 90 ? "pos-warn" : "pos-good";
  const mode = meta.compacted
    ? posUiText("pos.promptCompacted", "compacted")
    : posUiText("pos.promptCompact", "compact");

  return `
    <div class="pos-prompt-hint">
      <div>
        <div class="pos-label">${escapeHtml(posUiText("pos.labelChatReviewPrompt", "Chat Review Prompt"))}</div>
        <div class="${cls}">${escapeHtml(mode)} - ${meta.length}/${meta.limit} ${escapeHtml(posUiText("pos.unitChars", "chars"))}</div>
      </div>
      <div class="pos-prompt-meter">
        <span class="${posMeterWidthClass(meta.percent)}"></span>
      </div>
    </div>
  `;
}

function renderPosDiff(diff) {
  if (!diff) {
    return `<div class="pos-code">${escapeHtml(posUiText("pos.noAutomaticTargetComparison", "No automatic target comparison available."))}</div>`;
  }
  const lines = Array.isArray(diff.lines) ? diff.lines : [];
  if (!diff.changed) {
    return `<div class="pos-code pos-good">${escapeHtml(posUiText("pos.targetBodyIdentical", "Draft and target body are identical."))}</div>`;
  }
  return `
    <pre class="pos-diff">${lines.map((line) => {
      const cls = line.startsWith("+") && !line.startsWith("+++") ? "pos-diff-add"
        : line.startsWith("-") && !line.startsWith("---") ? "pos-diff-del"
        : line.startsWith("@@") ? "pos-diff-meta"
        : "";
      return `<span class="${cls}">${escapeHtml(line)}</span>`;
    }).join("\n")}</pre>
  `;
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

function renderPosTargetReview(review) {
  const summary = posTargetSummary(review);
  const meta = summary.candidate
    ? `<div class="pos-detail-path">${escapeHtml(summary.candidate)}${summary.source ? ` (${escapeHtml(summary.source)})` : ""}</div>`
    : "";
  if (summary.status === "error") {
    return `${meta}<div class="pos-code pos-bad">${escapeHtml(summary.message)}</div>`;
  }
  if (summary.hasDiff) {
    return `${meta}${renderPosDiff(review.diff)}`;
  }
  return `${meta}<div class="pos-code">${escapeHtml(summary.message)}</div>`;
}

function renderPosRelated(review) {
  const related = Array.isArray(review?.related) ? review.related : [];
  if (related.length === 0) {
    return `<div class="pos-code">${escapeHtml(posUiText("pos.noReadableRelatedFiles", "No readable related files in the review package."))}</div>`;
  }
  return `
    <div class="pos-related-list">
      ${related.map((item) => `
        <button type="button" class="pos-related-row" data-related-path="${escapeHtml(posText(item.path))}" ${item.error ? "disabled" : ""}>
            <span class="pos-draft-main">
              <span class="pos-draft-title">${escapeHtml(posText(item.title, item.path || posUiText("pos.relatedFileFallback", "Related file")))}</span>
              <span class="pos-draft-path">${escapeHtml(posText(item.path))}</span>
            </span>
          <span class="pos-pill ${item.error ? "pos-bad" : ""}">${escapeHtml(item.error ? posUiText("pos.statusError", "error") : posText(item.memory_level || item.type, posUiText("pos.kindFile", "file")))}</span>
        </button>
      `).join("")}
    </div>
  `;
}

function renderPosHistory(review) {
  const history = review?.history || {};
  const events = Array.isArray(history.events) ? history.events : [];
  if (history.error) {
    return `<div class="pos-code pos-bad">${escapeHtml(posText(history.error))}</div>`;
  }
  if (events.length === 0) {
    return `<div class="pos-code">${escapeHtml(posUiText("pos.noDraftHistory", "No draft history in the event log."))}</div>`;
  }

  return `
    <div class="pos-history-list">
      ${events.slice().reverse().map((event) => `
        <div class="pos-history-row">
            <span class="pos-history-dot ${posEventClass(event.type)}"></span>
          <span class="pos-draft-main">
            <span class="pos-draft-title">${escapeHtml(posText(event.type, posUiText("pos.historyEventFallback", "Event")))}</span>
            <span class="pos-draft-path">${escapeHtml(posText(event.timestamp))} - ${escapeHtml(posText(event.agent, "unknown"))}</span>
            ${event.reason ? `<span class="pos-history-reason">${escapeHtml(posText(event.reason))}</span>` : ""}
          </span>
        </div>
      `).join("")}
    </div>
  `;
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
    detail.innerHTML = `<div class="empty-state">${escapeHtml(posErrorMessage(payload, posUiText("pos.draftLoadFailed", "Draft konnte nicht geladen werden.")))}</div>`;
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

  detail.innerHTML = `
    <div class="pos-detail-meta pos-detail-meta-friendly">
      <span class="pos-pill ${posStatusClass(approval)}">${escapeHtml(posDraftStatusText(approval))}</span>
      <span>${escapeHtml(posUiText("pos.memoryChangeProtected", "Stable memory stays protected until approval."))}</span>
    </div>
    ${review ? `
      ${renderPosAssist(review)}
    ` : ""}
    <div class="pos-review-section pos-review-section-main">
      <div class="pos-label">${escapeHtml(posUiText("pos.labelDraftBodyUser", "Proposal"))}</div>
      <pre class="pos-markdown">${escapeHtml(body)}</pre>
    </div>
    <details class="pos-technical-details pos-draft-technical">
      <summary>${escapeHtml(posUiText("pos.showTechnicalDetails", "Technical details"))}</summary>
      <div class="pos-detail-path">${escapeHtml(posText(payload.path))}</div>
      <div class="pos-detail-grid">
        <div>
          <div class="pos-label">${escapeHtml(posUiText("pos.labelTags", "Tags"))}</div>
          <div class="pos-code">${escapeHtml(tags || "-")}</div>
        </div>
        <div>
          <div class="pos-label">${escapeHtml(posUiText("pos.labelRelated", "Related"))}</div>
          <pre class="pos-code">${escapeHtml(related || "-")}</pre>
        </div>
      </div>
      ${review ? `
        ${renderPosPromptHint(payload, review)}
        ${renderPosApplyHint(review)}
        ${renderPosChecklist(review, approval)}
        <div class="pos-review-section">
          <div class="pos-label">${escapeHtml(posUiText("pos.labelHistory", "History"))}</div>
          ${renderPosHistory(review)}
        </div>
        <div class="pos-review-section">
          <div class="pos-label">${escapeHtml(posUiText("pos.labelTargetReview", "Target Review"))}</div>
          ${renderPosTargetReview(review)}
        </div>
        <div class="pos-review-section">
          <div class="pos-label">${escapeHtml(posUiText("pos.labelRelatedContext", "Related Context"))}</div>
          ${renderPosRelated(review)}
        </div>
      ` : ""}
    </details>
  `;
  attachPosReviewHandlers(detail);
}

function renderPersonalOsQueryPayload(payload) {
  const target = document.getElementById("pos-query-results");
  if (!target) return;

  if (!payload || payload.error || payload.detail || payload.ok === false) {
    clearPersonalOsQuerySelection();
    target.innerHTML = `<div class="empty-state">${escapeHtml(posErrorMessage(payload, posUiText("pos.queryFailed", "Query failed")))}</div>`;
    return;
  }

  if (Array.isArray(payload.matches)) {
    clearPersonalOsQuerySelection();
    PersonalOSState.queryMatches = payload.matches;
    if (payload.matches.length === 0) {
      target.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.noQueryMatches", "No matches."))}</div>`;
      return;
    }
    target.innerHTML = "";
    for (const match of payload.matches) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "pos-query-row";
      row.innerHTML = `
        <span class="pos-draft-main">
          <span class="pos-draft-title">${escapeHtml(posText(match.title, posUiText("pos.untitled", "Untitled")))}</span>
          <span class="pos-draft-path">${escapeHtml(posText(match.path))}</span>
        </span>
        <span class="pos-pill">${escapeHtml(posText(match.memory_level || match.type, posUiText("pos.kindFile", "file")))}</span>
      `;
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
  target.innerHTML = `
    <div class="pos-query-read-header">
      <div>
        <div class="pos-draft-title">${escapeHtml(title)}</div>
        <div class="pos-draft-path">${escapeHtml(posText(payload.path))}</div>
      </div>
      <div class="pos-query-actions">
        <span class="pos-pill">${escapeHtml(posText(fm.memory_level || fm.type, posUiText("pos.kindFile", "file")))}</span>
        <button type="button" class="action-btn action-btn-sm" data-action="personalOsSendContextToChat">${escapeHtml(posUiText("pos.actionChat", "Chat"))}</button>
      </div>
    </div>
    ${tags ? `<div class="pos-code">${escapeHtml(tags)}</div>` : ""}
    <pre class="pos-markdown pos-query-markdown">${escapeHtml(posText(payload.body))}</pre>
  `;
}

function renderPersonalOsContextPack(payload) {
  const target = document.getElementById("pos-query-results");
  if (!target) return;

  if (!payload || payload.error || payload.detail || payload.ok === false) {
    clearPersonalOsQuerySelection();
    target.innerHTML = `<div class="empty-state">${escapeHtml(posErrorMessage(payload, posUiText("pos.contextPackFailed", "Context Pack failed")))}</div>`;
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

  target.innerHTML = `
    <div class="pos-query-read-header">
      <div>
        <div class="pos-draft-title">${escapeHtml(posUiText("pos.titleContextPack", "Context Pack"))}</div>
        <div class="pos-draft-path">${escapeHtml(posText(query.areaPath, "."))}${query.tag ? ` / #${escapeHtml(posText(query.tag))}` : ""}</div>
      </div>
      <div class="pos-query-actions">
        <span class="pos-pill">${escapeHtml(posUiCount("pos.countFiles", "{{count}} files", query.includedCount || files.length))}</span>
        <button type="button" class="action-btn action-btn-sm" data-action="personalOsSendContextPackToChat">${escapeHtml(posUiText("pos.actionChat", "Chat"))}</button>
      </div>
    </div>
    <div class="pos-review-strip">
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricCandidates", "Candidates"))}</div>
        <div class="pos-review-value">${Number(query.candidateCount || 0)}</div>
      </div>
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricIncluded", "Included"))}</div>
        <div class="pos-review-value pos-good">${Number(query.includedCount || files.length)}</div>
      </div>
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricContextMap", "Context Map"))}</div>
        <div class="pos-review-value ${graphClass}">${escapeHtml(graphLabel)}</div>
      </div>
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricErrors", "Errors"))}</div>
        <div class="pos-review-value ${errors.length ? "pos-warn" : "pos-good"}">${errors.length}</div>
      </div>
    </div>
    <div class="pos-related-list">
      ${files.map((file) => `
        <button type="button" class="pos-related-row" data-related-path="${escapeHtml(posText(file.path))}">
          <span class="pos-draft-main">
            <span class="pos-draft-title">${escapeHtml(posText(file.title, file.path || posUiText("pos.osFileFallback", "OS file")))}</span>
            <span class="pos-draft-path">${escapeHtml(posText(file.path))}</span>
          </span>
          <span class="pos-pill">${escapeHtml(posText(file.memory_level || file.type, posUiText("pos.kindFile", "file")))}</span>
        </button>
      `).join("")}
    </div>
    ${files.length ? `<pre class="pos-markdown pos-query-markdown">${escapeHtml(files.map((file) => [
      `## ${posText(file.title, file.path)}`,
      `Path: ${posText(file.path)}`,
      `Tags: ${Array.isArray(file.tags) ? file.tags.join(", ") : "-"}`,
      "",
      posText(file.bodyPreview),
    ].join("\n")).join("\n\n"))}</pre>` : `<div class="empty-state">${escapeHtml(posUiText("pos.noContextPackFiles", "No files in this Context Pack."))}</div>`}
  `;

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
    target.innerHTML = `<div class="empty-state">${escapeHtml(posErrorMessage(payload, posUiText("pos.obsidianContextFailed", "Obsidian context failed")))}</div>`;
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

  target.innerHTML = `
    <div class="pos-query-read-header">
      <div>
        <div class="pos-draft-title">${escapeHtml(posUiText("pos.titleObsidianContext", "Obsidian Context"))}</div>
        <div class="pos-draft-path">${escapeHtml(posText(vault.root, "-"))}</div>
      </div>
      <div class="pos-query-actions">
        <span class="pos-pill">${escapeHtml(posText(product.providerMode, "api-backed"))}</span>
        <button type="button" class="action-btn action-btn-sm" data-action="personalOsSendObsidianContextToChat">${escapeHtml(posUiText("pos.actionChat", "Chat"))}</button>
      </div>
    </div>
    <div class="pos-review-strip">
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricBootstrap", "Bootstrap"))}</div>
        <div class="pos-review-value pos-good">${posCount(counts.bootstrapAvailable)}</div>
      </div>
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricAreaIndexes", "Area indexes"))}</div>
        <div class="pos-review-value pos-good">${posCount(counts.areaIndexes)}</div>
      </div>
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricQuickFind", "Quick Find"))}</div>
        <div class="pos-review-value pos-good">${quickFind.length}</div>
      </div>
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricLoadedAll", "Loaded all"))}</div>
        <div class="pos-review-value ${vault.loadedAll ? "pos-warn" : "pos-good"}">${vault.loadedAll ? "true" : "false"}</div>
      </div>
    </div>
    <div class="pos-code">${escapeHtml(posText(product.rule, "Lexa uses configured provider APIs for model intelligence."))}</div>
    <div class="pos-related-list">
      ${quickFind.slice(0, 10).map((item) => `
        <div class="pos-related-row">
          <span class="pos-draft-main">
            <span class="pos-draft-title">${escapeHtml(posText(item.need, "Context"))}</span>
            <span class="pos-draft-path">${escapeHtml(posText(item.goTo, "-"))}</span>
          </span>
        </div>
      `).join("")}
    </div>
    <div class="pos-review-strip">
      ${surfaces.slice(0, 8).map((surface) => `
        <div class="pos-review-card">
          <div class="pos-label">${escapeHtml(posText(surface.id, "surface"))}</div>
          <div class="pos-review-value">${posCount(surface.fileCountApprox)}</div>
        </div>
      `).join("")}
    </div>
    ${files.length ? `<pre class="pos-markdown pos-query-markdown">${escapeHtml(files.map((file) => [
      `## ${posText(file.title, file.path)}`,
      `Path: ${posText(file.path)}`,
      `Tags: ${Array.isArray(file.tags) ? file.tags.join(", ") : "-"}`,
      "",
      posText(file.bodyPreview),
    ].join("\n")).join("\n\n"))}</pre>` : `<div class="empty-state">${escapeHtml(posUiText("pos.noObsidianContextFiles", "No selected OS context files."))}</div>`}
  `;
}

function renderPersonalOsCodeLoop(payload) {
  const target = document.getElementById("pos-query-results");
  if (!target) return;

  if (!payload || payload.error || payload.detail || payload.ok === false) {
    clearPersonalOsQuerySelection();
    target.innerHTML = `<div class="empty-state">${escapeHtml(posErrorMessage(payload, posUiText("pos.codeLoopFailed", "Code Loop failed")))}</div>`;
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

  target.innerHTML = `
    <div class="pos-query-read-header">
      <div>
        <div class="pos-draft-title">${escapeHtml(posUiText("pos.titleCodeLoop", "Lexa Code Loop"))}</div>
        <div class="pos-draft-path">${escapeHtml(posText(payload.topic, "lexa-code-improvement"))}</div>
      </div>
      <div class="pos-query-actions">
        <span class="pos-pill">${escapeHtml(posUiCount("pos.countFiles", "{{count}} files", contextFiles.length))}</span>
        <button type="button" class="action-btn action-btn-sm" data-action="personalOsSendCodeLoopToAgent">${escapeHtml(posUiText("pos.actionAgent", "Agent"))}</button>
        <button type="button" class="action-btn action-btn-sm" data-action="personalOsSendCodeLoopToChat">${escapeHtml(posUiText("pos.actionChat", "Chat"))}</button>
      </div>
    </div>
    <div class="pos-review-strip">
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricOsState", "OS State"))}</div>
        <div class="pos-review-value ${posAssistClass(diagnostics.state)}">${escapeHtml(posText(diagnostics.state, "unknown"))}</div>
      </div>
      ${evidence.pending ? `
      <button type="button" class="pos-review-card pos-action-card" data-code-loop-action="load-pending">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricPending", "Pending"))}</div>
        <div class="pos-review-value pos-warn">${evidence.pending}</div>
      </button>
      ` : `
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricPending", "Pending"))}</div>
        <div class="pos-review-value pos-good">${evidence.pending}</div>
      </div>
      `}
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricContext", "Context"))}</div>
        <div class="pos-review-value pos-good">${evidence.contextFiles}</div>
      </div>
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricDrafts", "Drafts"))}</div>
        <div class="pos-review-value ${evidence.drafts ? "pos-good" : "pos-warn"}">${evidence.drafts}</div>
      </div>
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricWorker", "Worker"))}</div>
        <div class="pos-review-value ${raw.ok ? "pos-good" : "pos-warn"}">${evidence.workerFailures}</div>
      </div>
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricContextMap", "Context Map"))}</div>
        <div class="pos-review-value ${evidence.graphOk ? "pos-good" : "pos-warn"}">${evidence.graphErrors}</div>
      </div>
    </div>
    <div class="pos-review-strip">
      <div class="pos-review-card">
        <div class="pos-label">${escapeHtml(posUiText("pos.metricPrompt", "Prompt"))}</div>
        <div class="pos-review-value ${meta.compacted ? "pos-warn" : "pos-good"}">${meta.percent}%</div>
        <div class="meter"><span class="${posMeterWidthClass(meta.percent)}"></span></div>
      </div>
    </div>
    <div class="pos-code">${escapeHtml(posText(diagnostics.summary, posUiText("pos.noDiagnosticSummary", "No diagnostic summary.")))}</div>
    ${evidence.graphErrors ? `<div class="pos-code pos-warn">${escapeHtml(posUiText("pos.contextMapPartial", "Context Map partial: {{files}} files, {{edges}} edges, {{errors}} error(s).", { files: evidence.graphFiles, edges: evidence.graphEdges, errors: evidence.graphErrors }))}</div>` : ""}
    ${Array.isArray(payload?.contextPack?.graph?.errors) && payload.contextPack.graph.errors.length ? `
      <div class="pos-label">${escapeHtml(posUiText("pos.labelContextMapErrors", "Context Map Errors"))}</div>
      <div class="pos-related-list">
        ${payload.contextPack.graph.errors.slice(0, 5).map((entry) => `
          <div class="pos-related-row">
            <span class="pos-draft-main">
              <span class="pos-draft-title">${escapeHtml(posText(entry.path, posUiText("pos.contextMapErrorFallback", "Context Map error")))}</span>
              <span class="pos-draft-path">${escapeHtml(posClip(entry.error, 220))}</span>
            </span>
            <span class="pos-pill">${escapeHtml(posUiText("pos.kindMap", "map"))}</span>
          </div>
        `).join("")}
      </div>
    ` : ""}
    <div class="pos-label">${escapeHtml(posUiText("pos.labelDraftDecisions", "Draft Decisions"))}</div>
    <div class="pos-related-list">
      ${draftRows.map((draft) => `
        <button type="button" class="pos-related-row" data-code-loop-draft="${escapeHtml(posText(draft.path))}">
          <span class="pos-draft-main">
            <span class="pos-draft-title">${escapeHtml(posText(draft.title, posUiText("pos.untitled", "Untitled")))}</span>
            <span class="pos-draft-path">${escapeHtml(posText(draft.path))}</span>
          </span>
          <span class="pos-pill ${posStatusClass(draft.approval)}">${escapeHtml(posText(draft.approval, "unknown"))}</span>
        </button>
      `).join("")}
    </div>
    <div class="pos-label">${escapeHtml(posUiText("pos.labelEvidenceFiles", "Evidence Files"))}</div>
    <div class="pos-related-list">
      ${contextFiles.slice(0, 6).map((file) => `
        <button type="button" class="pos-related-row" data-code-loop-file="${escapeHtml(posText(file.path))}">
          <span class="pos-draft-main">
            <span class="pos-draft-title">${escapeHtml(posText(file.title, file.path || posUiText("pos.osFileFallback", "OS file")))}</span>
            <span class="pos-draft-path">${escapeHtml(posText(file.path))}</span>
          </span>
          <span class="pos-pill">${escapeHtml(posText(file.memory_level || file.type, posUiText("pos.kindFile", "file")))}</span>
        </button>
      `).join("")}
    </div>
    <pre class="pos-markdown pos-query-markdown">${escapeHtml(personalOsCodeLoopPrompt(payload))}</pre>
  `;

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
    summary.innerHTML = "";
    stage.innerHTML = `<div class="empty-state">${escapeHtml(posErrorMessage(payload, posUiText("pos.contextMapFailed", "Context Map failed")))}</div>`;
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
    summary.innerHTML = "";
    stage.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.noContextMapNodes", "No Context Map nodes."))}</div>`;
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

  const edgeMarkup = visibleEdges.map((edge) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) return "";
    const edgeClass = edge.type === "tag" ? "pos-graph-edge pos-graph-edge-tag" : "pos-graph-edge";
    const midX = source.x + ((target.x - source.x) * 0.5);
    return `<path class="${edgeClass}" data-source="${escapeHtml(edge.source)}" data-target="${escapeHtml(edge.target)}" d="M ${source.x.toFixed(1)} ${source.y.toFixed(1)} C ${midX.toFixed(1)} ${source.y.toFixed(1)}, ${midX.toFixed(1)} ${target.y.toFixed(1)}, ${target.x.toFixed(1)} ${target.y.toFixed(1)}"></path>`;
  }).join("");

  const laneMarkup = `
    <rect class="pos-graph-lane-bg" x="30" y="42" width="550" height="352" rx="14"></rect>
    <rect class="pos-graph-lane-bg" x="640" y="42" width="250" height="232" rx="14"></rect>
    <rect class="pos-graph-lane-bg" x="900" y="274" width="230" height="120" rx="14"></rect>
    <text class="pos-graph-lane" x="54" y="66">${escapeHtml(posUiText("pos.graphLaneImportantFiles", "Important Files"))}</text>
    <text class="pos-graph-lane" x="664" y="66">${escapeHtml(posUiText("pos.graphLaneTags", "Tags"))}</text>
    <text class="pos-graph-lane" x="924" y="298">${escapeHtml(posUiText("pos.graphLaneRefs", "Refs"))}</text>
  `;

  const nodeMarkup = visibleNodes.map((node) => {
    const point = positions.get(node.id) || { x: 40, y: 40 };
    const isFile = node.kind === "file";
    const nodeWidth = isFile ? 220 : (node.kind === "reference" ? 190 : 170);
    const nodeHeight = isFile ? 34 : 28;
    const pathAttr = node.kind === "file" && node.path ? ` data-path="${escapeHtml(node.path)}" role="button"` : "";
    const ariaLabel = ` aria-label="${escapeHtml(posGraphLabel(node))}"`;
    return `
      <g class="pos-graph-node ${posGraphNodeClass(node.kind)}" data-node-id="${escapeHtml(node.id)}" tabindex="0"${pathAttr}${ariaLabel} transform="translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})">
        <rect x="${(-nodeWidth / 2).toFixed(1)}" y="${(-nodeHeight / 2).toFixed(1)}" width="${nodeWidth}" height="${nodeHeight}" rx="8"></rect>
        <circle cx="${(-nodeWidth / 2 + 14).toFixed(1)}" r="5"></circle>
        <text x="${(-nodeWidth / 2 + 30).toFixed(1)}" y="4">${escapeHtml(posGraphDisplayName(node, isFile ? 28 : 22))}</text>
        <rect class="pos-graph-degree-bg" x="${(nodeWidth / 2 - 34).toFixed(1)}" y="-10" width="26" height="18" rx="9"></rect>
        <text class="pos-graph-degree" x="${(nodeWidth / 2 - 16).toFixed(1)}" y="4">${Number(node.degree || 0)}</text>
        <title>${escapeHtml(posGraphLabel(node))}</title>
      </g>
    `;
  }).join("");

  summary.innerHTML = `
    <span class="pos-pill">${escapeHtml(posText(payload.areaPath, "."))}</span>
    <span class="pos-pill">${escapeHtml(posUiCount("pos.countFiles", "{{count}} files", counts.files || nodes.filter((node) => node.kind === "file").length))}</span>
    <span class="pos-pill">${escapeHtml(posUiCount("pos.countEdges", "{{count}} edges", counts.edges || edges.length))}</span>
    <span class="pos-pill">${escapeHtml(posUiCount("pos.countMapNodes", "{{count}} map nodes", visibleNodes.length))}</span>
    <span class="pos-pill">${escapeHtml(posUiCount("pos.countMapEdges", "{{count}} map edges", visibleEdges.length))}</span>
    <span class="pos-pill ${health.partial ? "pos-warn" : ""}">${escapeHtml(posGraphHealthNote(health.note))}</span>
    ${health.errorCount ? `<span class="pos-pill pos-warn">${escapeHtml(posUiCount("pos.countErrors", "{{count}} errors", health.errorCount))}</span>` : ""}
  `;
  stage.innerHTML = `
    ${health.partial ? `<div class="pos-code pos-warn">${escapeHtml(posUiText("pos.partialContextMap", "Partial Context Map: {{count}} file error(s).", { count: health.errorCount }))}</div>` : ""}
    <div class="pos-graph-explorer">
      <div>
        <div class="pos-label">${escapeHtml(posUiText("pos.graphLaneImportantFiles", "Important Files"))}</div>
        <div class="pos-graph-files" id="pos-graph-files"></div>
      </div>
      <div>
        <div class="pos-label">${escapeHtml(posUiText("pos.labelHubs", "Hubs"))}</div>
        <div class="pos-graph-hubs" id="pos-graph-hubs"></div>
      </div>
    </div>
    <div class="pos-graph-network">
      <div class="pos-graph-network-head">
        <div>
          <span class="pos-label">${escapeHtml(posUiText("pos.labelRelationshipMap", "Relationship Map"))}</span>
          <span class="pos-draft-path">${escapeHtml(posUiText("pos.graphShown", `${visibleNodes.length} nodes / ${visibleEdges.length} edges shown`, { nodes: visibleNodes.length, edges: visibleEdges.length }))}</span>
        </div>
        <div class="pos-graph-legend" aria-label="${escapeHtml(posUiText("pos.graphLegendLabel", "Context Map legend"))}">
          <span><i class="pos-graph-legend-file"></i>${escapeHtml(posUiText("pos.graphLegendFiles", "Files"))}</span>
          <span><i class="pos-graph-legend-tag"></i>${escapeHtml(posUiText("pos.graphLegendTags", "Tags"))}</span>
          <span><i class="pos-graph-legend-ref"></i>${escapeHtml(posUiText("pos.graphLegendRefs", "Refs"))}</span>
          <span><i class="pos-graph-legend-edge"></i>${escapeHtml(posUiText("pos.graphLegendLinks", "Links"))}</span>
        </div>
      </div>
      <svg class="pos-graph-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(posUiText("pos.graphAriaLabel", "Personal OS Context Map"))}">
        <rect class="pos-graph-bg" x="0" y="0" width="${width}" height="${height}" rx="8"></rect>
        ${laneMarkup}
        ${edgeMarkup}
        ${nodeMarkup}
      </svg>
    </div>
  `;

  const rows = document.getElementById("pos-graph-files");
  if (rows) {
    rows.innerHTML = "";
    for (const node of fileNodes.slice(0, 12)) {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "pos-graph-file-row";
      row.innerHTML = `
        <span class="pos-draft-main">
          <span class="pos-draft-title">${escapeHtml(posGraphLabel(node))}</span>
          <span class="pos-draft-path">${escapeHtml(posText(node.path || node.id))}</span>
        </span>
        <span class="pos-pill">${escapeHtml(posText(node.memory_level || node.type, posUiText("pos.kindFile", "file")))}</span>
      `;
      row.addEventListener("click", () => personalOsReadContextFile(node.path || node.id));
      rows.appendChild(row);
    }
  }

  const hubs = document.getElementById("pos-graph-hubs");
  if (hubs) {
    hubs.innerHTML = "";
    for (const node of [...tagNodes.slice(0, 8), ...refNodes.slice(0, 4)]) {
      const tagQuery = posGraphTagQuery(node);
      const row = document.createElement(tagQuery ? "button" : "div");
      if (tagQuery) {
        row.type = "button";
        row.dataset.graphTag = tagQuery;
        row.title = posUiText("pos.searchTagTitle", "Search tag #{{tag}}", { tag: tagQuery });
      }
      row.className = `pos-graph-file-row pos-graph-hub-row ${tagQuery ? "pos-graph-hub-action" : ""} ${posGraphNodeClass(node.kind)}`;
      row.innerHTML = `
        <span class="pos-draft-main">
          <span class="pos-draft-title">${escapeHtml(posGraphDisplayName(node, 34))}</span>
          <span class="pos-draft-path">${escapeHtml(posGraphLabel(node))}</span>
        </span>
        <span class="pos-pill">${Number(node.degree || 0)}</span>
      `;
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

async function personalOsOpenIndex() {
  const area = document.getElementById("pos-area-input")?.value?.trim() || ".";
  const target = document.getElementById("pos-query-results");
  if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.loadingIndex", "Loading index..."))}</div>`;
  try {
    const payload = await window.lexa.personalOsQuery({ areaPath: area, maxMatches: 50 });
    renderPersonalOsQueryPayload(payload);
  } catch (e) {
    renderPersonalOsQueryPayload({ ok: false, error: e.message || String(e) });
  }
}

async function personalOsSearchTag() {
  const tagFilter = posTagFilter(document.getElementById("pos-tag-input")?.value);
  const area = document.getElementById("pos-area-input")?.value?.trim() || ".";
  const target = document.getElementById("pos-query-results");
  if (tagFilter.invalid || !tagFilter.tag) {
    renderPersonalOsQueryPayload({ ok: false, error: tagFilter.invalid ? posUiText("pos.invalidTag", "Tag is invalid.") : posUiText("pos.tagRequired", "Tag is required.") });
    return;
  }
  if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.searchingTag", "Searching tag..."))}</div>`;
  try {
    const payload = await window.lexa.personalOsQuery({ areaPath: area, tag: tagFilter.tag, maxMatches: 50 });
    renderPersonalOsQueryPayload(payload);
  } catch (e) {
    renderPersonalOsQueryPayload({ ok: false, error: e.message || String(e) });
  }
}

async function personalOsLoadGraph() {
  const area = document.getElementById("pos-area-input")?.value?.trim() || ".";
  const stage = document.getElementById("pos-graph-stage");
  if (stage) stage.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.loadingContextMap", "Loading Context Map..."))}</div>`;
  try {
    const payload = await window.lexa.personalOsGraph({
      areaPath: area,
      maxFiles: 120,
      includeTags: true,
      hideSmoke: true,
    });
    renderPersonalOsGraphPayload(payload);
  } catch (e) {
    renderPersonalOsGraphPayload({ ok: false, error: e.message || String(e) });
  }
}

async function personalOsLoadContextPack() {
  const area = document.getElementById("pos-area-input")?.value?.trim() || ".";
  const tagFilter = posTagFilter(document.getElementById("pos-tag-input")?.value);
  const target = document.getElementById("pos-query-results");
  if (tagFilter.invalid) {
    renderPersonalOsContextPack({ ok: false, error: posUiText("pos.invalidTag", "Tag is invalid.") });
    return;
  }
  if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.buildingContextPack", "Building Context Pack..."))}</div>`;
  try {
    const payload = await window.lexa.personalOsContextPack({
      areaPath: area,
      tag: tagFilter.tag,
      maxFiles: 5,
      bodyChars: 700,
      includeGraph: true,
      hideSmoke: true,
    });
    renderPersonalOsContextPack(payload);
  } catch (e) {
    renderPersonalOsContextPack({ ok: false, error: e.message || String(e) });
  }
}

async function personalOsLoadObsidianContext() {
  const area = document.getElementById("pos-area-input")?.value?.trim() || "08_Lexa";
  const tagFilter = posTagFilter(document.getElementById("pos-tag-input")?.value);
  const target = document.getElementById("pos-query-results");
  if (tagFilter.invalid) {
    renderPersonalOsObsidianContext({ ok: false, error: posUiText("pos.invalidTag", "Tag is invalid.") });
    return;
  }
  const topic = [area, tagFilter.tag, "lexa hermes obsidian"].filter(Boolean).join(" ");
  if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.buildingObsidianContext", "Building Obsidian context..."))}</div>`;
  try {
    const payload = await window.lexa.personalOsObsidianContext({
      topic,
      maxFiles: 5,
      bodyChars: 600,
      includePreviews: true,
    });
    renderPersonalOsObsidianContext(payload);
  } catch (e) {
    renderPersonalOsObsidianContext({ ok: false, error: e.message || String(e) });
  }
}

async function personalOsLoadCodeLoop() {
  const area = document.getElementById("pos-area-input")?.value?.trim() || "00_System";
  const tagFilter = posTagFilter(document.getElementById("pos-tag-input")?.value);
  const target = document.getElementById("pos-query-results");
  if (tagFilter.invalid) {
    renderPersonalOsCodeLoop({ ok: false, error: posUiText("pos.invalidTag", "Tag is invalid.") });
    return;
  }
  const tag = tagFilter.tag || "lexa";
  if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.buildingCodeLoop", "Building Code Loop..."))}</div>`;
  try {
    const payload = await window.lexa.personalOsCodeLoop({
      areaPath: area,
      tag,
      maxFiles: 5,
      bodyChars: 650,
      includeGraph: true,
      hideSmoke: true,
    });
    renderPersonalOsCodeLoop(payload);
  } catch (e) {
    renderPersonalOsCodeLoop({ ok: false, error: e.message || String(e) });
  }
}

async function personalOsReadContextFile(filepath) {
  const target = document.getElementById("pos-query-results");
  if (target) target.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.loadingFile", "Loading file..."))}</div>`;
  try {
    const payload = await window.lexa.personalOsReadFile(filepath);
    renderPersonalOsQueryPayload(payload);
  } catch (e) {
    renderPersonalOsQueryPayload({ ok: false, error: e.message || String(e) });
  }
}

function personalOsSendContextToChat() {
  const payload = PersonalOSState.selectedContext;
  if (!payload?.path) {
    showToast(posUiText("pos.noContextSelected", "No OS context selected."), "warning");
    return;
  }

  const fm = payload.frontmatter || {};
  const body = posText(payload.body);
  const bodyLimit = 2200;
  const clippedBody = body.length > bodyLimit ? `${body.slice(0, bodyLimit)}\n\n${posUiText("pos.promptTruncatedMarker", "[gekürzt]")}` : body;
  const prompt = [
    posUiText("pos.contextPromptIntro", "Nutze diesen Personal-OS-Kontext als Quelle:"),
    "",
    `${posUiText("pos.promptPathLabel", "Pfad")}: ${payload.path}`,
    `${posUiText("pos.promptTitleLabel", "Titel")}: ${posText(fm.title, "Untitled")}`,
    `${posUiText("pos.promptTypeLabel", "Typ")}: ${posText(fm.type, "unknown")}`,
    `${posUiText("pos.promptMemoryLevelLabel", "Memory-Level")}: ${posText(fm.memory_level, "unknown")}`,
    `${posUiText("pos.promptTagsLabel", "Tags")}: ${Array.isArray(fm.tags) ? fm.tags.join(", ") : "-"}`,
    "",
    posUiText("pos.promptContentLabel", "Inhalt:"),
    clippedBody,
    "",
    posUiText("pos.promptQuestionBlank", "Meine Frage dazu: "),
  ].join("\n");

  personalOsPlacePromptInChat(prompt, posUiText("pos.contextPromptReady", "OS context is ready in chat."));
}

function personalOsSendContextPackToChat() {
  const payload = PersonalOSState.selectedContextPack;
  if (!payload?.ok) {
    showToast(posUiText("pos.noContextPackSelected", "No Context Pack selected."), "warning");
    return;
  }

  const query = payload.query || {};
  const files = Array.isArray(payload.files) ? payload.files.slice(0, 5) : [];
  const graph = payload.graph || {};
  const prompt = [
    posUiText("pos.contextPackPromptIntro", "Nutze dieses Personal-OS-Context-Pack als Quelle:"),
    "",
    `${posUiText("pos.promptAreaLabel", "Area")}: ${posText(query.areaPath, ".")}`,
    `${posUiText("pos.promptTagLabel", "Tag")}: ${posText(query.tag, "-")}`,
    `${posUiText("pos.promptFilesLabel", "Files")}: ${posUiText("pos.promptFilesIncluded", "{{included}} von {{candidates}} Kandidaten", { included: Number(query.includedCount || files.length), candidates: Number(query.candidateCount || files.length) })}`,
    `${posUiText("pos.metricContextMap", "Context Map")}: ${posUiText("pos.promptGraphCounts", "{{files}} files / {{edges}} edges", { files: Number(graph?.counts?.files || 0), edges: Number(graph?.counts?.edges || 0) })}`,
    "",
    files.map((file) => [
      `## ${posText(file.title, file.path)}`,
      `${posUiText("pos.promptPathLabel", "Pfad")}: ${posText(file.path)}`,
      `${posUiText("pos.promptTypeLabel", "Typ")}: ${posText(file.type, "unknown")}`,
      `${posUiText("pos.promptMemoryLevelLabel", "Memory-Level")}: ${posText(file.memory_level, "unknown")}`,
      `${posUiText("pos.promptTagsLabel", "Tags")}: ${Array.isArray(file.tags) ? file.tags.join(", ") : "-"}`,
      "",
      posClip(file.bodyPreview, 700),
    ].join("\n")).join("\n\n"),
    "",
    posUiText("pos.promptQuestionBlank", "Meine Frage dazu: "),
  ].join("\n");

  personalOsPlacePromptInChat(prompt, posUiText("pos.contextPackPromptReady", "Context Pack is ready in chat."));
}

function personalOsSendObsidianContextToChat() {
  const payload = PersonalOSState.selectedObsidianContext;
  const prompt = personalOsObsidianPrompt(payload);
  if (!payload?.ok || !prompt) {
    showToast(posUiText("pos.noObsidianContextSelected", "No Obsidian context selected."), "warning");
    return;
  }

  personalOsPlacePromptInChat(prompt, posUiText("pos.obsidianContextPromptReady", "Obsidian context is ready in chat."), posUiText("pos.noObsidianContextSelected", "No Obsidian context selected."));
}

function personalOsSendCodeLoopToChat() {
  const payload = PersonalOSState.selectedCodeLoop;
  const prompt = personalOsCodeLoopPrompt(payload);
  if (!payload?.ok || !prompt) {
    showToast(posUiText("pos.noCodeLoopReady", "No Code Loop ready."), "warning");
    return;
  }

  personalOsPlacePromptInChat(prompt, posUiText("pos.codeLoopPromptReady", "Code Loop is ready in chat."), posUiText("pos.noCodeLoopReady", "No Code Loop ready."));
}

function personalOsSendCodeLoopToAgent() {
  const payload = PersonalOSState.selectedCodeLoop;
  const prompt = personalOsCodeLoopAgentPrompt(payload);
  if (!payload?.ok || !prompt) {
    showToast(posUiText("pos.noCodeLoopReady", "No Code Loop ready."), "warning");
    return;
  }

  personalOsPlacePromptInChat(prompt, posUiText("pos.codeLoopAgentPromptReady", "Code Loop is ready as an agent prompt."), posUiText("pos.noCodeLoopReady", "No Code Loop ready."));
}

function personalOsReviewPrompt(draft, review) {
  const fm = draft?.frontmatter || {};
  const assist = review?.assist || {};
  const checks = Array.isArray(assist.checks) ? assist.checks : [];
  const historyEvents = Array.isArray(review?.history?.events) ? review.history.events.slice(-5) : [];
  const related = Array.isArray(review?.related) ? review.related.slice(0, 3) : [];
  const diffLines = Array.isArray(review?.diff?.lines) ? review.diff.lines.slice(0, 35).join("\n") : "";
  const checklist = review?.checklist || {};
  const applyHint = review?.applyHint || {};
  const tags = Array.isArray(fm.tags) ? fm.tags.join(", ") : "-";

  const prompt = [
    posUiText("pos.reviewPromptIntro", "Bitte hilf mir, diesen Personal-OS-Draft zu reviewen."),
    "",
    posUiText("pos.reviewPromptImportant", "Wichtig:"),
    `- ${posUiText("pos.reviewPromptNoAutoDecision", "Triff keine Approval-, Reject- oder Apply-Entscheidung automatisch.")}`,
    `- ${posUiText("pos.reviewPromptDraftAsProposal", "Behandle den Draft als Vorschlag, nicht als kanonische Wahrheit.")}`,
    `- ${posUiText("pos.reviewPromptRiskRecommendation", "Nenne Risiken, fehlende Evidenz und eine knappe Empfehlung für die menschliche Entscheidung.")}`,
    "",
    `## ${posUiText("pos.promptDraftHeading", "Draft")}`,
    `${posUiText("pos.promptPathLabel", "Pfad")}: ${posText(draft?.path)}`,
    `${posUiText("pos.promptTitleLabel", "Titel")}: ${posText(fm.title, "Untitled")}`,
    `${posUiText("pos.promptApprovalLabel", "Approval")}: ${posText(draft?.approval, "unknown")}`,
    `${posUiText("pos.promptTypeLabel", "Typ")}: ${posText(fm.type, "unknown")}`,
    `${posUiText("pos.promptMemoryLevelLabel", "Memory-Level")}: ${posText(fm.memory_level, "unknown")}`,
    `${posUiText("pos.promptSourceLabel", "Quelle")}: ${posText(fm.source, "unknown")}`,
    `${posUiText("pos.promptConfidenceLabel", "Confidence")}: ${posText(fm.confidence, "unknown")}`,
    `${posUiText("pos.promptTagsLabel", "Tags")}: ${tags}`,
    "",
    `## ${posUiText("pos.labelReviewAssist", "Review Assist")}`,
    `${posUiText("pos.promptStatusLabel", "Status")}: ${posText(assist.status, "unknown")}`,
    `${posUiText("pos.promptSummaryLabel", "Summary")}: ${posText(assist.summary, "-")}`,
    checks.length ? checks.map((check) => `- ${posText(check.state)} | ${posText(check.label)}: ${posText(check.detail)}`).join("\n") : `- ${posUiText("pos.noAssistChecks", "Keine Assist-Checks.")}`,
    "",
    `## ${posUiText("pos.promptApprovalChecklistHeading", "Approval Checklist")}`,
    `${posUiText("pos.promptApprovedBoxLabel", "Approved box")}: ${checklist.hasApproved ? posUiText("pos.valuePresent", "present") : posUiText("pos.valueMissing", "missing")} / ${posUiText("pos.promptCheckedLabel", "checked")}: ${checklist.approvedChecked ? posUiText("common.yes", "yes") : posUiText("common.no", "no")}`,
    `${posUiText("pos.promptRejectedBoxLabel", "Rejected box")}: ${checklist.hasRejected ? posUiText("pos.valuePresent", "present") : posUiText("pos.valueMissing", "missing")} / ${posUiText("pos.promptCheckedLabel", "checked")}: ${checklist.rejectedChecked ? posUiText("common.yes", "yes") : posUiText("common.no", "no")}`,
    "",
    `## ${posUiText("pos.labelApplyBoundary", "Apply Boundary")}`,
    `${posUiText("pos.promptCanApplyLabel", "Can apply")}: ${applyHint.enabled ? posUiText("common.yes", "yes") : posUiText("common.no", "no")}`,
    `${posUiText("pos.promptTargetLabel", "Target")}: ${posText(applyHint.target, "-")}`,
    `${posUiText("pos.promptReasonLabel", "Reason")}: ${posText(applyHint.reason, "-")}`,
    "",
    `## ${posUiText("pos.promptAuditHistoryHeading", "Audit History")}`,
    historyEvents.length ? historyEvents.map((event) => (
      `- ${posText(event.timestamp)} | ${posText(event.type)} | ${posText(event.agent, "unknown")} | ${posText(event.reason, "")}`
    )).join("\n") : `- ${posUiText("pos.noHistoryEvents", "Keine History Events.")}`,
    "",
    `## ${posUiText("pos.labelRelatedContext", "Related Context")}`,
    related.length ? related.map((item) => [
      `### ${posText(item.title, item.path || posUiText("pos.relatedFileFallback", "Related file"))}`,
      `${posUiText("pos.promptPathLabel", "Pfad")}: ${posText(item.path)}`,
      `${posUiText("pos.promptTypeLabel", "Typ")}: ${posText(item.type || item.memory_level, "unknown")}`,
      item.error ? `${posUiText("pos.statusError", "Error")}: ${posText(item.error)}` : posClip(item.bodyPreview, 240),
    ].join("\n")).join("\n\n") : `- ${posUiText("pos.noRelatedContextFiles", "Keine Related Context Dateien.")}`,
    "",
    `## ${posUiText("pos.promptTargetDiffHeading", "Target Diff")}`,
    diffLines ? posClip(diffLines, 900) : posUiText("pos.noTargetDiff", "Kein Target Diff vorhanden."),
    "",
    `## ${posUiText("pos.promptDraftBodyHeading", "Draft Body")}`,
    posClip(draft?.body, 1100),
    "",
    posUiText("pos.reviewPromptFinalQuestion", "Meine Frage dazu: Soll ich diesen Draft eher approven, rejecten oder vorher bearbeiten? Bitte begruende knapp und konkret."),
  ].join("\n");
  return posClipChatPrompt(prompt);
}

function personalOsSendReviewToChat() {
  const draft = PersonalOSState.selectedDraft;
  const review = PersonalOSState.selectedReview;
  if (!draft?.path || !review) {
    showToast(posUiText("pos.noReviewPackageSelected", "No review package selected."), "warning");
    return;
  }

  personalOsPlacePromptInChat(personalOsReviewPrompt(draft, review), posUiText("pos.reviewPromptReady", "Draft review is ready in chat."));
}

async function selectPersonalOsDraft(path) {
  if (!path) return;
  PersonalOSState.isSelecting = true;
  PersonalOSState.selectedPath = path;
  renderPersonalOsDraftList({ ok: true, drafts: PersonalOSState.drafts });
  renderPersonalOsDetail({
    ok: true,
    frontmatter: { title: posUiText("pos.loadingDraftTitle", "Loading") },
    path,
    approval: "pending",
    body: posUiText("pos.loadingDraftBody", "Loading..."),
  });

  try {
    const review = await window.lexa.personalOsDraftReview(path);
    if (review?.error || review?.detail || review?.ok === false) {
      const fallback = await window.lexa.personalOsDraftView(path);
      renderPersonalOsDetail(fallback?.ok ? fallback : { ok: false, error: posErrorMessage(review) });
      return;
    }
    renderPersonalOsDetail(review.draft, review);
  } catch (e) {
    renderPersonalOsDetail({ ok: false, error: e.message || String(e) });
  } finally {
    PersonalOSState.isSelecting = false;
  }
}

async function decidePersonalOsDraft(decision) {
  const draft = PersonalOSState.selectedDraft;
  if (!draft?.path) return;

  const review = PersonalOSState.selectedReview;
  PersonalOSState.isDeciding = true;
  const blockedApproval = decision === "approve" && review?.assist?.status === "blocked";
  const actionLabel = decision === "approve"
    ? (blockedApproval ? posUiText("pos.decideApproveOverrideAction", "Approve Override") : posUiText("pos.decideApproveAction", "Approve"))
    : posUiText("pos.decideRejectAction", "Reject");
  const modalTitle = decision === "approve"
    ? (blockedApproval ? posUiText("pos.decideApproveOverrideTitle", "Approve Draft Override") : posUiText("pos.decideApproveTitle", "Approve Draft"))
    : posUiText("pos.decideRejectTitle", "Reject Draft");
  const defaultReason = decision === "approve"
    ? (blockedApproval
      ? posUiText("pos.decideApproveOverrideDefault", "Explicit human override after reviewing blocked Review Assist checks.")
      : posUiText("pos.decideApproveDefault", "Reviewed and accepted in Lexa."))
    : posUiText("pos.decideRejectDefault", "Reviewed and rejected in Lexa.");
  const result = await showInputModal(modalTitle, [
    {
      name: "reason",
      label: posUiText("pos.decideReasonLabel", "Reason"),
      type: "textarea",
      required: true,
      rows: 3,
      default: defaultReason,
    },
  ], actionLabel);
  if (!result) {
    PersonalOSState.isDeciding = false;
    return;
  }

  const approveBtn = document.getElementById("pos-approve-btn");
  const rejectBtn = document.getElementById("pos-reject-btn");
  if (approveBtn) approveBtn.disabled = true;
  if (rejectBtn) rejectBtn.disabled = true;

  let completed = false;
  try {
    const payload = await window.lexa.personalOsDraftDecision(draft.path, decision, result.reason, blockedApproval);
    if (payload?.error || payload?.detail || payload?.ok === false) {
      showToast(posErrorMessage(payload, posUiText("pos.decideFailed", "Draft decision failed")), "error");
    } else {
      const successMessage = decision === "approve" ? posUiText("pos.decideApproved", "Draft approved.") : posUiText("pos.decideRejected", "Draft rejected.");
      showToast(successMessage, "success");
      PersonalOSState.selectedPath = null;
      PersonalOSState.selectedDraft = null;
      PersonalOSState.selectedReview = null;
      completed = true;
      await refreshPersonalOsView();
    }
  } catch (e) {
    showToast(posErrorMessage({ error: e.message || String(e) }, posUiText("pos.decideFailed", "Draft decision failed")), "error");
  } finally {
    PersonalOSState.isDeciding = false;
    if (!completed && PersonalOSState.selectedDraft) {
      renderPersonalOsDetail(PersonalOSState.selectedDraft, PersonalOSState.selectedReview);
    }
  }
}

async function applyPersonalOsDraft() {
  const draft = PersonalOSState.selectedDraft;
  const review = PersonalOSState.selectedReview;
  const applyHint = review?.applyHint || {};
  if (!draft?.path || !applyHint.enabled) return;

  PersonalOSState.isApplying = true;
  const applyTarget = posText(applyHint.target, posUiText("pos.applyDefaultTarget", "its target"));
  const result = await showInputModal(posUiText("pos.applyDraftTitle", "Apply Draft"), [
    {
      name: "reason",
      label: posUiText("pos.applyReasonLabel", "Reason"),
      type: "textarea",
      required: true,
      rows: 3,
      default: posUiText("pos.applyReasonDefault", "Apply approved draft to {{target}}.", { target: applyTarget }),
    },
  ], posUiText("pos.applyDraftAction", "Apply"));
  if (!result) {
    PersonalOSState.isApplying = false;
    return;
  }

  const approveBtn = document.getElementById("pos-approve-btn");
  const rejectBtn = document.getElementById("pos-reject-btn");
  const applyBtn = document.getElementById("pos-apply-btn");
  if (approveBtn) approveBtn.disabled = true;
  if (rejectBtn) rejectBtn.disabled = true;
  if (applyBtn) applyBtn.disabled = true;

  let completed = false;
  try {
    const payload = await window.lexa.personalOsDraftApply(draft.path, result.reason);
    if (payload?.error || payload?.detail || payload?.ok === false) {
      showToast(posErrorMessage(payload, posUiText("pos.applyFailed", "Draft apply failed")), "error");
    } else {
      showToast(posUiText("pos.applySuccess", "Draft applied through Personal OS SDK."), "success");
      PersonalOSState.selectedPath = null;
      PersonalOSState.selectedDraft = null;
      PersonalOSState.selectedReview = null;
      completed = true;
      await refreshPersonalOsView();
    }
  } catch (e) {
    showToast(posErrorMessage({ error: e.message || String(e) }, posUiText("pos.applyFailed", "Draft apply failed")), "error");
  } finally {
    PersonalOSState.isApplying = false;
    if (!completed && PersonalOSState.selectedDraft) {
      renderPersonalOsDetail(PersonalOSState.selectedDraft, PersonalOSState.selectedReview);
    }
  }
}

async function submitPersonalOsRawInbox() {
  let processorOptions = [{ value: "deterministic", label: posUiText("pos.rawProcessorSafeDefault", "deterministic (safe default)") }];
  try {
    const status = await window.lexa.personalOsRawStatus();
    if (status?.error || status?.detail || status?.ok === false) {
      showToast(posErrorMessage(status, posUiText("pos.rawStatusUnavailable", "Raw Inbox status unavailable; using deterministic.")), "warning");
    } else {
      PersonalOSState.rawInboxStatus = status;
      processorOptions = posRawProcessorOptions(status);
      const failed = posCount(status?.failureState?.failed);
      showToast(posRawStatusSummary(status), failed ? "warning" : "info", 2500);
    }
  } catch (e) {
    PersonalOSState.rawInboxStatus = null;
    showToast(posErrorMessage({ error: e.message || String(e) }, posUiText("pos.rawStatusUnavailable", "Raw Inbox status unavailable; using deterministic.")), "warning");
  }

  const result = await showInputModal(posUiText("pos.rawInboxTitle", "New Raw Inbox"), [
    {
      name: "title",
      label: posUiText("pos.rawTitleLabel", "Title"),
      type: "text",
      required: false,
      placeholder: posUiText("pos.rawTitlePlaceholder", "Optional short title"),
    },
    {
      name: "body",
      label: posUiText("pos.rawBodyLabel", "Raw text"),
      type: "textarea",
      required: true,
      rows: 8,
      placeholder: posUiText("pos.rawBodyPlaceholder", "Paste untrusted raw note, transcript, idea, or task text."),
    },
    {
      name: "processor",
      label: posUiText("pos.rawProcessorLabel", "Processor"),
      type: "select",
      default: "deterministic",
      options: processorOptions,
    },
  ], posUiText("pos.rawCreateDraftAction", "Create Draft"));
  if (!result) return;

  try {
    showToast(posUiText("pos.rawProcessing", "Processing Raw Inbox..."), "info");
    const payload = await window.lexa.personalOsRawSubmit({
      title: result.title || "",
      body: result.body || "",
      processor: result.processor || "deterministic",
    });
    if (payload?.error || payload?.detail || payload?.ok === false) {
      showToast(posErrorMessage(payload, posUiText("pos.rawIntakeFailed", "Raw Inbox intake failed")), "error");
      return;
    }
    const count = Array.isArray(payload.drafts) ? payload.drafts.length : 0;
    showToast(count ? posUiText("pos.rawDraftCreated", "Raw Inbox draft created.") : posUiText("pos.rawProcessed", "Raw Inbox processed."), "success");
    const filter = document.getElementById("pos-approval-filter");
    if (filter) filter.value = "pending";
    const createdDraft = count ? payload.drafts[0] : null;
    await refreshPersonalOsView(createdDraft);
  } catch (e) {
    showToast(posErrorMessage({ error: e.message || String(e) }, posUiText("pos.rawIntakeFailed", "Raw Inbox intake failed")), "error");
  }
}

async function findPersonalOsDraft() {
  const result = await showInputModal(posUiText("pos.findDraftTitle", "Find Draft"), [
    {
      name: "query",
      label: posUiText("pos.findDraftSearchLabel", "Search"),
      type: "text",
      required: true,
      placeholder: posUiText("pos.findDraftSearchPlaceholder", "Title, path, approval, tag, source, or memory level"),
      default: PersonalOSState.draftSearch || "",
    },
  ], posUiText("pos.findDraftAction", "Find"));
  if (!result) return;

  const query = posText(result.query).trim();
  if (!query) return;

  const list = document.getElementById("pos-draft-list");
  const filter = document.getElementById("pos-approval-filter");
  const search = document.getElementById("pos-draft-search");
  if (list) list.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.searchingDrafts", "Searching drafts..."))}</div>`;

  try {
    const queue = await window.lexa.personalOsDrafts("all", true);
    if (queue?.error || queue?.detail || queue?.ok === false) {
      showToast(posErrorMessage(queue, posUiText("pos.draftSearchFailed", "Draft search failed")), "error");
      renderPersonalOsDraftList(queue);
      return;
    }

    const drafts = Array.isArray(queue.drafts) ? queue.drafts : [];
    const matches = drafts.filter((draft) => posDraftMatchesSearch(draft, query));
    if (filter) filter.value = "all";
    if (search) search.value = query;
    PersonalOSState.draftSearch = query;
    renderPersonalOsDraftList({ ...queue, drafts });

    if (matches.length === 0) {
      clearPersonalOsDraftDetail();
      showToast(posUiText("pos.noDraftSearchResult", "No draft found for this search."), "warning");
      return;
    }

    if (matches.length === 1) {
      await selectPersonalOsDraft(matches[0].path);
      showToast(posUiText("pos.draftFoundLoaded", "Draft found and loaded."), "success");
      return;
    }

    showToast(posUiText("pos.draftsFoundSelect", "{{count}} drafts found. Select a result.", { count: matches.length }), "info");
  } catch (e) {
    showToast(posErrorMessage({ error: e.message || String(e) }, posUiText("pos.draftSearchFailed", "Draft search failed")), "error");
  }
}

function posRefreshOptions(value, state = PersonalOSState) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const auto = Boolean(value.auto);
    const preserveSelection = value.preserveSelection !== false;
    return {
      preferredPath: value.preferredPath || (auto || !preserveSelection ? null : state?.selectedPath || null),
      auto,
      preserveSelection,
    };
  }
  return { preferredPath: value || state?.selectedPath || null, auto: false, preserveSelection: true };
}

function posDraftSelectionAfterRefresh(drafts, search, preferredPath = null) {
  const rows = Array.isArray(drafts) ? drafts : [];
  const preferredDraft = preferredPath
    ? rows.find((draft) => draft?.path === preferredPath)
    : null;
  if (preferredDraft) return preferredDraft;
  const visibleDrafts = posVisibleDrafts(rows, search);
  if (visibleDrafts.length > 0) return visibleDrafts[0];
  return posText(search).trim() ? null : (rows[0] || null);
}

async function refreshPersonalOsView(options = null) {
  const { preferredPath, auto } = posRefreshOptions(options);
  if (auto && !personalOsCanAutoRefresh()) return false;
  if (PersonalOSState.isRefreshing) return false;

  const list = document.getElementById("pos-draft-list");
  const detail = document.getElementById("pos-draft-detail");
  const filter = document.getElementById("pos-approval-filter");
  if (!list || !detail) return;

  PersonalOSState.isRefreshing = true;
  list.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.loadingDraftQueue", "Loading draft queue..."))}</div>`;
  detail.innerHTML = `<div class="empty-state">${escapeHtml(posUiText("pos.noDraftSelected", "No draft selected."))}</div>`;

  const approval = filter?.value || "pending";
  try {
    const [diagnostics, queue] = await Promise.all([
      window.lexa.personalOsDiagnostics(),
      window.lexa.personalOsDrafts(approval, true),
    ]);
    const status = diagnostics?.status || { status: "offline", tools_count: 0, draft_review: false };
    PersonalOSState.lastRefreshAt = Date.now();
    renderPersonalOsStatus(status, { ...queue, counts: diagnostics?.counts || queue?.counts || {} }, diagnostics);
    renderPersonalOsDraftList(queue);
    if (PersonalOSState.drafts.length > 0) {
      const selectedDraft = posDraftSelectionAfterRefresh(PersonalOSState.drafts, PersonalOSState.draftSearch, preferredPath);
      if (selectedDraft?.path) {
        await selectPersonalOsDraft(selectedDraft.path);
      } else {
        clearPersonalOsDraftDetail();
        posRenderBadge(posQueueCounts({ counts: diagnostics?.counts || {} }).pending);
      }
    } else {
      clearPersonalOsDraftDetail();
      posRenderBadge(posQueueCounts({ counts: diagnostics?.counts || {} }).pending);
    }
  } catch (e) {
    const diagnostics = posOfflineDiagnostics({ error: e.message || String(e) }, posUiText("pos.draftQueueFailed", "Draft queue failed"));
    renderPersonalOsStatus(diagnostics.status, { ok: false, drafts: [], counts: diagnostics.counts }, diagnostics);
    list.innerHTML = `<div class="empty-state">${escapeHtml(diagnostics.summary)}</div>`;
    clearPersonalOsDraftDetail(diagnostics.summary);
  } finally {
    PersonalOSState.isRefreshing = false;
  }
  return true;
}

function setupPersonalOsView() {
  document.getElementById("pos-approval-filter")?.addEventListener("change", () => {
    clearPersonalOsDraftDetail();
    refreshPersonalOsView();
  });
  document.getElementById("pos-draft-search")?.addEventListener("input", (event) => {
    PersonalOSState.draftSearch = event.target.value || "";
    renderPersonalOsDraftList({ ok: true, drafts: PersonalOSState.drafts });
  });
  document.getElementById("pos-draft-search")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") findPersonalOsDraft();
  });
  document.getElementById("pos-approve-btn")?.addEventListener("click", () => decidePersonalOsDraft("approve"));
  document.getElementById("pos-reject-btn")?.addEventListener("click", () => decidePersonalOsDraft("reject"));
  document.getElementById("pos-apply-btn")?.addEventListener("click", applyPersonalOsDraft);
  document.getElementById("pos-area-input")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") personalOsOpenIndex();
  });
  document.getElementById("pos-tag-input")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") personalOsSearchTag();
  });
}

document.addEventListener("DOMContentLoaded", setupPersonalOsView);
