/* Personal OS state and status helpers. Classic script loaded before personal_os.js. */

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
  setPersonalOsEmptyState(detail, emptyMessage);
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
