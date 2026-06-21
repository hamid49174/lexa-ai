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
let personalOsRefreshSeq = 0;

async function personalOsOpenIndex() {
  const area = document.getElementById("pos-area-input")?.value?.trim() || ".";
  const target = document.getElementById("pos-query-results");
  setPersonalOsEmptyState(target, posUiText("pos.loadingIndex", "Loading index..."));
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
  setPersonalOsEmptyState(target, posUiText("pos.searchingTag", "Searching tag..."));
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
  setPersonalOsEmptyState(stage, posUiText("pos.loadingContextMap", "Loading Context Map..."));
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
  setPersonalOsEmptyState(target, posUiText("pos.buildingContextPack", "Building Context Pack..."));
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

const POS_OBSIDIAN_DEFAULT_AREA = "08_Lexa";

async function personalOsLoadObsidianContext() {
  const area = document.getElementById("pos-area-input")?.value?.trim() || POS_OBSIDIAN_DEFAULT_AREA;
  const tagFilter = posTagFilter(document.getElementById("pos-tag-input")?.value);
  const target = document.getElementById("pos-query-results");
  if (tagFilter.invalid) {
    renderPersonalOsObsidianContext({ ok: false, error: posUiText("pos.invalidTag", "Tag is invalid.") });
    return;
  }
  let sharedTopic = "";
  try {
    if (typeof window.lexa?.personalOsSharedContext === "function") {
      const shared = await window.lexa.personalOsSharedContext();
      if (shared?.fresh && typeof shared.topic === "string") {
        sharedTopic = shared.topic.trim().slice(0, 180);
      }
    }
  } catch (e) {
    console.warn("[PersonalOS] Shared context unavailable:", e.message || e);
  }
  // Only fall back to a generic topic when no user-specific signal is present
  // (no shared topic, no tag, area still at default). Otherwise the hardcoded
  // term would pollute searches for vaults with a different vocabulary.
  const hasUserSignal = Boolean(tagFilter.tag) || area !== POS_OBSIDIAN_DEFAULT_AREA;
  const fallbackTopic = sharedTopic || (hasUserSignal ? "" : posUiText("pos.obsidianDefaultTopic", "lexa hermes obsidian"));
  const topic = [area, tagFilter.tag, fallbackTopic].filter(Boolean).join(" ");
  setPersonalOsEmptyState(target, posUiText("pos.buildingObsidianContext", "Building Obsidian context..."));
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
  setPersonalOsEmptyState(target, posUiText("pos.buildingCodeLoop", "Building Code Loop..."));
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
  setPersonalOsEmptyState(target, posUiText("pos.loadingFile", "Loading file..."));
  try {
    const payload = await window.lexa.personalOsReadFile(filepath);
    renderPersonalOsQueryPayload(payload);
  } catch (e) {
    renderPersonalOsQueryPayload({ ok: false, error: e.message || String(e) });
  }
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
  // Re-Entry-Guard: ein bereits laufender Entscheid (Modal offen oder Request unterwegs)
  // darf nicht parallel ein zweites Mal starten.
  if (PersonalOSState.isDeciding) return;
  const draft = PersonalOSState.selectedDraft;
  if (!draft?.path) return;

  const review = PersonalOSState.selectedReview;
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
  if (!result) return;

  PersonalOSState.isDeciding = true;
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
  if (!result) return;

  PersonalOSState.isApplying = true;
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
  setPersonalOsEmptyState(list, posUiText("pos.searchingDrafts", "Searching drafts..."));

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

async function refreshPersonalOsView(options = null) {
  const { preferredPath, auto } = posRefreshOptions(options);
  if (auto && !personalOsCanAutoRefresh()) return false;
  if (auto && PersonalOSState.isRefreshing) return false;
  const requestId = ++personalOsRefreshSeq;

  const list = document.getElementById("pos-draft-list");
  const detail = document.getElementById("pos-draft-detail");
  const filter = document.getElementById("pos-approval-filter");
  if (!list || !detail) return false;

  PersonalOSState.isRefreshing = true;
  setPersonalOsEmptyState(list, posUiText("pos.loadingDraftQueue", "Loading draft queue..."));
  setPersonalOsEmptyState(detail, posUiText("pos.noDraftSelected", "No draft selected."));

  const approval = filter?.value || "pending";
  try {
    const [diagnostics, queue] = await Promise.all([
      window.lexa.personalOsDiagnostics(),
      window.lexa.personalOsDrafts(approval, true),
    ]);
    if (requestId !== personalOsRefreshSeq) return false;
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
    if (requestId !== personalOsRefreshSeq) return false;
    const diagnostics = posOfflineDiagnostics({ error: e.message || String(e) }, posUiText("pos.draftQueueFailed", "Draft queue failed"));
    renderPersonalOsStatus(diagnostics.status, { ok: false, drafts: [], counts: diagnostics.counts }, diagnostics);
    setPersonalOsEmptyState(list, diagnostics.summary);
    clearPersonalOsDraftDetail(diagnostics.summary);
  } finally {
    if (requestId === personalOsRefreshSeq) PersonalOSState.isRefreshing = false;
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
