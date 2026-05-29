/* Personal OS prompt and chat handoff helpers. Classic script loaded before personal_os.js. */

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
