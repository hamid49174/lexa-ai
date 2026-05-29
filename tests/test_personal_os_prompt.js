/**
 * Smoke tests for Personal OS chat handoff prompt sizing.
 * Run with: node tests/test_personal_os_prompt.js
 */

const fs = require("fs");
const path = require("path");

const personalOsSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "personal_os.js"),
  "utf8"
);
const displayHelpersSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "personal_os_display_helpers.js"),
  "utf8"
);
const promptHelpersSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "personal_os_prompt_helpers.js"),
  "utf8"
);
const domHelpersSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "personal_os_dom_helpers.js"),
  "utf8"
);
const stateHelpersSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "personal_os_state_helpers.js"),
  "utf8"
);
const graphHelpersSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "personal_os_graph_helpers.js"),
  "utf8"
);
const reviewHelpersSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "personal_os_review_helpers.js"),
  "utf8"
);
const renderersSrc = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "personal_os_renderers.js"),
  "utf8"
);
const src = [
  displayHelpersSrc,
  promptHelpersSrc,
  domHelpersSrc,
  stateHelpersSrc,
  graphHelpersSrc,
  reviewHelpersSrc,
  renderersSrc,
  personalOsSrc,
].join("\n");
const combinedPersonalOsSrc = src;
const html = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "index.html"),
  "utf8"
);
const viewsCss = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "css", "views.css"),
  "utf8"
);
const viewsPersonalOsCss = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "css", "views_personal_os.css"),
  "utf8"
);
const css = `${viewsCss}\n${viewsPersonalOsCss}`;
const overridesBaseCss = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "css", "overrides.css"),
  "utf8"
);
const overridesPersonalOsCss = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "css", "overrides_personal_os.css"),
  "utf8"
);
const overridesCss = `${overridesBaseCss}\n${overridesPersonalOsCss}`;
const preload = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "preload.js"),
  "utf8"
);
const i18nDe = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "i18n", "de.json"),
  "utf8"
);
const i18nEn = fs.readFileSync(
  path.join(__dirname, "..", "frontend", "src", "i18n", "en.json"),
  "utf8"
);

function extractFn(source, name) {
  const needle = `function ${name}(`;
  const start = source.indexOf(needle);
  if (start === -1) throw new Error(`'${name}' not found`);
  let depth = 0;
  for (let i = start; i < source.length; i += 1) {
    if (source[i] === "{") depth += 1;
    if (source[i] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`No closing brace for '${name}'`);
}

const sandbox = new Function(`
  "use strict";
  const PersonalOSState = { selectedPath: null, isRefreshing: false, isSelecting: false, isDeciding: false, isApplying: false };
  ${extractFn(displayHelpersSrc, "posText")}
  ${extractFn(displayHelpersSrc, "posClip")}
  ${extractFn(displayHelpersSrc, "posUiText")}
  ${extractFn(displayHelpersSrc, "posStatusClass")}
  ${extractFn(displayHelpersSrc, "posEventClass")}
  ${extractFn(displayHelpersSrc, "posAssistClass")}
  ${extractFn(displayHelpersSrc, "posErrorDetailText")}
  ${extractFn(displayHelpersSrc, "posErrorMessage")}
  ${extractFn(displayHelpersSrc, "posRefreshLabel")}
  ${extractFn(displayHelpersSrc, "posStateLabel")}
  ${extractFn(displayHelpersSrc, "posDraftStatusText")}
  ${extractFn(src, "posChatPromptLimit")}
  ${extractFn(src, "posClipChatPrompt")}
  ${extractFn(src, "personalOsHasOpenModal")}
  ${extractFn(src, "personalOsCanAutoRefresh")}
  ${extractFn(src, "clearPersonalOsQuerySelection")}
  ${extractFn(src, "posCount")}
  ${extractFn(src, "posQueueCounts")}
  ${extractFn(src, "posRefreshOptions")}
  ${extractFn(src, "posDraftSelectionAfterRefresh")}
  ${extractFn(src, "posDraftEmptyMessage")}
  ${extractFn(src, "posDraftQueueError")}
  ${extractFn(src, "posDraftMatchesSearch")}
  ${extractFn(src, "posVisibleDrafts")}
  ${extractFn(src, "posRawProcessorOptions")}
  ${extractFn(src, "posRawStatusSummary")}
  ${extractFn(src, "posUiLanguage")}
  ${extractFn(src, "posLanguageText")}
  ${extractFn(src, "posDiagnosticHeadline")}
  ${extractFn(src, "posOfflineDiagnostics")}
  ${extractFn(src, "posIsOfflineDiagnostics")}
  ${extractFn(src, "posNextActionText")}
  ${extractFn(src, "posNextDraftPath")}
  ${extractFn(src, "posNextCardAction")}
  ${extractFn(src, "personalOsReviewPrompt")}
  ${extractFn(src, "personalOsReviewPromptMeta")}
  ${extractFn(src, "personalOsObsidianPrompt")}
  ${extractFn(src, "personalOsCodeLoopPrompt")}
  ${extractFn(src, "personalOsCodeLoopAgentPrompt")}
  ${extractFn(src, "personalOsCodeLoopPromptMeta")}
  ${extractFn(src, "posCodeLoopEvidenceCounts")}
  ${extractFn(src, "posCodeLoopDraftRank")}
  ${extractFn(src, "posCodeLoopDraftRows")}
  ${extractFn(src, "posGraphLabel")}
  ${extractFn(src, "posNormalizeTagQuery")}
  ${extractFn(src, "posTagFilter")}
  ${extractFn(src, "posGraphDisplayName")}
  ${extractFn(src, "posGraphTagQuery")}
  ${extractFn(src, "posGraphDegreeMap")}
  ${extractFn(src, "posGraphRankedNodes")}
  ${extractFn(src, "posGraphHealth")}
  ${extractFn(src, "posTargetSummary")}
  ${extractFn(src, "posMeterWidthClass")}
  return { PersonalOSState, posClip, posStatusClass, posEventClass, posAssistClass, posErrorDetailText, posErrorMessage, posRefreshLabel, posStateLabel, posDraftStatusText, posChatPromptLimit, posClipChatPrompt, personalOsCanAutoRefresh, clearPersonalOsQuerySelection, posQueueCounts, posRefreshOptions, posDraftSelectionAfterRefresh, posDraftEmptyMessage, posDraftQueueError, posDraftMatchesSearch, posVisibleDrafts, posRawProcessorOptions, posRawStatusSummary, posUiLanguage, posLanguageText, posDiagnosticHeadline, posOfflineDiagnostics, posIsOfflineDiagnostics, posNextActionText, posNextDraftPath, posNextCardAction, personalOsReviewPrompt, personalOsReviewPromptMeta, personalOsObsidianPrompt, personalOsCodeLoopPrompt, personalOsCodeLoopAgentPrompt, personalOsCodeLoopPromptMeta, posCodeLoopEvidenceCounts, posCodeLoopDraftRank, posCodeLoopDraftRows, posNormalizeTagQuery, posTagFilter, posGraphDisplayName, posGraphTagQuery, posGraphDegreeMap, posGraphRankedNodes, posGraphHealth, posTargetSummary, posMeterWidthClass };
`);

let PersonalOSState;
let posClip;
let posStatusClass;
let posEventClass;
let posAssistClass;
let posErrorDetailText;
let posErrorMessage;
let posRefreshLabel;
let posStateLabel;
let posDraftStatusText;
let posChatPromptLimit;
let posClipChatPrompt;
let personalOsCanAutoRefresh;
let clearPersonalOsQuerySelection;
let posQueueCounts;
let posRefreshOptions;
let posDraftSelectionAfterRefresh;
let posDraftEmptyMessage;
let posDraftQueueError;
let posDraftMatchesSearch;
let posVisibleDrafts;
let posRawProcessorOptions;
let posRawStatusSummary;
let posUiLanguage;
let posLanguageText;
let posDiagnosticHeadline;
let posOfflineDiagnostics;
let posIsOfflineDiagnostics;
let posNextActionText;
let posNextDraftPath;
let posNextCardAction;
let personalOsReviewPrompt;
let personalOsReviewPromptMeta;
let personalOsObsidianPrompt;
let personalOsCodeLoopPrompt;
let personalOsCodeLoopAgentPrompt;
let personalOsCodeLoopPromptMeta;
let posCodeLoopEvidenceCounts;
let posCodeLoopDraftRank;
let posCodeLoopDraftRows;
let posNormalizeTagQuery;
let posTagFilter;
let posGraphDisplayName;
let posGraphTagQuery;
let posGraphDegreeMap;
let posGraphRankedNodes;
let posGraphHealth;
let posTargetSummary;
let posMeterWidthClass;
try {
  ({ PersonalOSState, posClip, posStatusClass, posEventClass, posAssistClass, posErrorDetailText, posErrorMessage, posRefreshLabel, posStateLabel, posDraftStatusText, posChatPromptLimit, posClipChatPrompt, personalOsCanAutoRefresh, clearPersonalOsQuerySelection, posQueueCounts, posRefreshOptions, posDraftSelectionAfterRefresh, posDraftEmptyMessage, posDraftQueueError, posDraftMatchesSearch, posVisibleDrafts, posRawProcessorOptions, posRawStatusSummary, posUiLanguage, posLanguageText, posDiagnosticHeadline, posOfflineDiagnostics, posIsOfflineDiagnostics, posNextActionText, posNextDraftPath, posNextCardAction, personalOsReviewPrompt, personalOsReviewPromptMeta, personalOsObsidianPrompt, personalOsCodeLoopPrompt, personalOsCodeLoopAgentPrompt, personalOsCodeLoopPromptMeta, posCodeLoopEvidenceCounts, posCodeLoopDraftRank, posCodeLoopDraftRows, posNormalizeTagQuery, posTagFilter, posGraphDisplayName, posGraphTagQuery, posGraphDegreeMap, posGraphRankedNodes, posGraphHealth, posTargetSummary, posMeterWidthClass } = sandbox());
} catch (e) {
  console.error("Sandbox setup failed:", e.message);
  process.exit(1);
}

let passed = 0;
let failed = 0;
function assert(desc, ok, detail = "") {
  if (ok) {
    console.log(`  ok: ${desc}`);
    passed += 1;
  } else {
    console.error(`  FAIL: ${desc}${detail ? " - " + detail : ""}`);
    failed += 1;
  }
}

const huge = "Long draft body. ".repeat(700);
const draft = {
  path: "06_Inbox/Drafts/example.md",
  approval: "pending",
  frontmatter: {
    title: "Example Draft",
    type: "draft",
    memory_level: "working",
    source: "agent",
    confidence: "high",
    tags: ["lexa", "personal-os", "review"],
  },
  body: huge,
};

const review = {
  assist: {
    status: "ready",
    summary: "No deterministic blockers found.",
    checks: [
      { state: "ok", label: "Draft state", detail: "Draft is pending." },
      { state: "ok", label: "Approval checklist", detail: "Both boxes are present." },
    ],
  },
  checklist: {
    hasApproved: true,
    hasRejected: true,
    approvedChecked: false,
    rejectedChecked: false,
  },
  applyHint: {
    enabled: false,
    target: null,
    reason: "Draft must be approved before it can be applied.",
  },
  history: {
    events: Array.from({ length: 20 }, (_, index) => ({
      timestamp: `2026-05-15T00:${String(index).padStart(2, "0")}:00Z`,
      type: "File.Read",
      agent: "Test",
      reason: huge,
    })),
  },
  related: Array.from({ length: 8 }, (_, index) => ({
    title: `Related ${index}`,
    path: `05_Memory/Rollups/related-${index}.md`,
    type: "memory-summary",
    bodyPreview: huge,
  })),
  diff: {
    lines: Array.from({ length: 200 }, (_, index) => `+ diff line ${index} ${huge}`),
  },
};

console.log("\nposClip():");
const clippedGeneric = posClip("x".repeat(100), 30);
assert("keeps generic clip within limit", clippedGeneric.length <= 30, `len=${clippedGeneric.length}`);
assert("keeps generic clip marker", clippedGeneric.includes("[truncated]"), clippedGeneric);
assert("handles tiny clip limits", posClip("abcdef", 4).length === 4);
assert("keeps unclipped text unchanged", posClip("short", 30) === "short");

console.log("\nposClipChatPrompt():");
const clipped = posClipChatPrompt(huge, 3600);
assert("clips long text under limit", clipped.length <= 3600, `len=${clipped.length}`);
assert("keeps compacted marker", clipped.includes("Prompt compacted"), clipped.slice(-120));
const originalLexaConfig = globalThis.LexaConfig;
globalThis.LexaConfig = { MAX_CHAT_INPUT_LENGTH: 1200 };
const clippedByConfig = posClipChatPrompt(huge, 3600);
assert("respects configured chat input headroom", clippedByConfig.length <= 950, `len=${clippedByConfig.length}`);
assert("reports configured prompt limit", posChatPromptLimit(3600) === 950, `limit=${posChatPromptLimit(3600)}`);
globalThis.LexaConfig = originalLexaConfig;

console.log("\nposErrorMessage():");
assert("keeps structured detail error text", posErrorMessage({ detail: { message: "MCP missing" } }) === "MCP missing");
assert("formats validation detail arrays", posErrorMessage({ detail: [{ loc: ["query", "tag"], msg: "Invalid tag filter" }] }) === "query.tag: Invalid tag filter");
assert("formats object errors without detail", posErrorMessage({ error: { msg: "Tool failed" } }) === "Tool failed");
assert("appends request id to rendered errors", posErrorMessage({ error: "MCP missing", requestId: "req-123" }).includes("Request ID: req-123"));
const longError = posErrorMessage({ error: "transport failed ".repeat(100) });
assert("clips long Personal OS errors", longError.length <= 720 && longError.includes("[truncated]"), `len=${longError.length}`);
const longErrorWithRequestId = posErrorMessage({ error: "transport failed ".repeat(100), requestId: "req-keep" });
assert("keeps request id when clipping long errors", longErrorWithRequestId.length <= 720 && longErrorWithRequestId.includes("[truncated]") && longErrorWithRequestId.includes("Request ID: req-keep"), `len=${longErrorWithRequestId.length}`);
const narrowErrorWithRequestId = posErrorMessage({ error: "transport failed ".repeat(30), requestId: "req-small" }, "fallback", 90);
assert("keeps request-id errors within custom limit", narrowErrorWithRequestId.length <= 90 && narrowErrorWithRequestId.includes("Request ID: req-small"), `len=${narrowErrorWithRequestId.length}`);
assert("normalizes request id to one line", posErrorMessage({ error: "MCP missing", requestId: "req\nline\twith space" }).includes("Request ID: req line with space"));
assert("clips oversized request ids", posErrorMessage({ error: "MCP missing", requestId: "r".repeat(300) }).includes("...[truncated]"));

console.log("\nposRefreshLabel():");
const baseTime = Date.UTC(2026, 4, 16, 14, 30, 0);
assert("formats empty refresh state", posRefreshLabel(null, baseTime) === "Not checked yet");
assert("formats fresh refresh state", posRefreshLabel(baseTime - 3000, baseTime).includes("just now"));
assert("formats second refresh age", posRefreshLabel(baseTime - 12000, baseTime).endsWith("12s ago"));
assert("formats minute refresh age", posRefreshLabel(baseTime - 120000, baseTime).endsWith("2m ago"));
assert("UI text fallback interpolates values", combinedPersonalOsSrc.includes("Object.entries(values)") && combinedPersonalOsSrc.includes("replaceAll(`{{${name}}}`"));
assert("refresh labels route through localized UI text", combinedPersonalOsSrc.includes('posUiText("pos.refreshNotChecked"') && combinedPersonalOsSrc.includes('posUiText("pos.refreshJustNow"') && combinedPersonalOsSrc.includes('posUiText("pos.refreshSecondsAgo"') && combinedPersonalOsSrc.includes('posUiText("pos.refreshMinutesAgo"') && combinedPersonalOsSrc.includes('posUiText("pos.refreshHoursAgo"') && i18nDe.includes('"pos.refreshNotChecked"') && i18nEn.includes('"pos.refreshNotChecked"'));

console.log("\nPersonal OS display helpers:");
assert("count helper remains in extracted display helpers", displayHelpersSrc.includes('function posUiCount(') && displayHelpersSrc.includes('return posUiText(key, fallback, { count: Number(count) });'));
assert("status classes map known states", posStatusClass("connected") === "pos-good" && posStatusClass("pending") === "pos-warn" && posStatusClass("offline") === "pos-bad");
assert("event classes map audit-like events", posEventClass("DraftCreated") === "pos-warn" && posEventClass("ApplyFailed") === "pos-bad");
assert("assist classes map review states", posAssistClass("ready") === "pos-good" && posAssistClass("attention") === "pos-warn" && posAssistClass("blocked") === "pos-bad");
assert("state labels normalize display states", posStateLabel("ready") === "READY" && posStateLabel("custom") === "CUSTOM");
assert("draft status labels normalize approvals", posDraftStatusText("pending") === "Needs review" && posDraftStatusText("approved") === "Approved" && posDraftStatusText("unknown-state") === "Unknown state");

console.log("\npersonalOsCanAutoRefresh():");
assert("allows idle auto refresh", personalOsCanAutoRefresh({ selectedPath: null, isRefreshing: false, isSelecting: false, isDeciding: false, isApplying: false }) === true);
assert("skips auto refresh while a draft is selected", personalOsCanAutoRefresh({ selectedPath: "06_Inbox/Drafts/a.md", isRefreshing: false, isSelecting: false, isDeciding: false, isApplying: false }) === false);
assert("skips auto refresh while deciding", personalOsCanAutoRefresh({ selectedPath: null, isRefreshing: false, isSelecting: false, isDeciding: true, isApplying: false }) === false);
PersonalOSState.selectedContext = { path: "OS_MANIFEST.md" };
PersonalOSState.selectedContextPack = { ok: true };
PersonalOSState.selectedCodeLoop = { ok: true };
PersonalOSState.queryMatches = [{ path: "OS_MANIFEST.md" }];
clearPersonalOsQuerySelection();
assert("clears stale Personal OS query handoff state", !PersonalOSState.selectedContext && !PersonalOSState.selectedContextPack && !PersonalOSState.selectedCodeLoop && PersonalOSState.queryMatches.length === 0);
assert("normalizes manual refresh argument", posRefreshOptions("draft.md").preferredPath === "draft.md" && posRefreshOptions("draft.md").auto === false);
assert("normalizes auto refresh options", posRefreshOptions({ auto: true, preferredPath: "draft.md" }).auto === true);
assert("keeps selected draft on manual refresh", posRefreshOptions(null, { selectedPath: "06_Inbox/Drafts/current.md" }).preferredPath === "06_Inbox/Drafts/current.md");
assert("does not keep selected draft on auto refresh", posRefreshOptions({ auto: true }, { selectedPath: "06_Inbox/Drafts/current.md" }).preferredPath === null);
assert("can explicitly drop selected draft on manual refresh", posRefreshOptions({ preserveSelection: false }, { selectedPath: "06_Inbox/Drafts/current.md" }).preferredPath === null);
const refreshDraftRows = [
  { title: "Pending Draft", path: "06_Inbox/Drafts/pending.md" },
  { title: "Approved Draft", path: "06_Inbox/Drafts/approved.md" },
];
assert("refresh selection prefers requested draft", posDraftSelectionAfterRefresh(refreshDraftRows, "missing", "06_Inbox/Drafts/approved.md")?.path === "06_Inbox/Drafts/approved.md");
assert("refresh selection uses first visible search match", posDraftSelectionAfterRefresh(refreshDraftRows, "pending")?.path === "06_Inbox/Drafts/pending.md");
assert("refresh selection does not choose hidden drafts for empty search result", posDraftSelectionAfterRefresh(refreshDraftRows, "no-match") === null);
assert("refresh selection falls back to first draft without search", posDraftSelectionAfterRefresh(refreshDraftRows, "")?.path === "06_Inbox/Drafts/pending.md");

console.log("\nposDiagnosticHeadline():");
const diagnosticAttention = posDiagnosticHeadline({
  summary: "Personal OS integration is connected but needs review attention.",
  checks: [
    { id: "mcp", label: "MCP connection", state: "ok", detail: "personal_os connected." },
    { id: "pending-drafts", label: "Pending drafts", state: "warn", detail: "1 draft(s) still need human review." },
  ],
});
const diagnosticBlocked = posDiagnosticHeadline({
  summary: "Personal OS integration has blocking issues.",
  checks: [
    { id: "pending-drafts", label: "Pending drafts", state: "warn", detail: "1 draft(s) still need human review." },
    { id: "capabilities", label: "Capabilities", state: "block", detail: "Missing capabilities: graph" },
  ],
});
assert("diagnostic headline surfaces warning detail", diagnosticAttention === "Pending drafts: 1 draft(s) still need human review.");
assert("diagnostic headline prioritizes blocked checks", diagnosticBlocked === "Capabilities: Missing capabilities: graph");
const offlineDiagnostics = posOfflineDiagnostics({ error: "MCP offline" });
assert("offline diagnostics mark Personal OS blocked", offlineDiagnostics.state === "blocked" && offlineDiagnostics.status.status === "offline");
assert("offline diagnostics surface refresh recovery", offlineDiagnostics.nextAction.includes("refresh") && offlineDiagnostics.counts.invalid === 1);
assert("detects offline diagnostics", posIsOfflineDiagnostics(offlineDiagnostics) === true);
assert("diagnostic headline falls back to summary", posDiagnosticHeadline({ summary: "Ready.", checks: [] }) === "Ready.");
const originalLexaI18n = globalThis.LexaI18n;
globalThis.LexaI18n = { getCurrentLanguage: () => "de" };
assert("detects German Personal OS UI language", posUiLanguage() === "de");
assert(
  "translates backend next-action copy for German OS UI",
  posLanguageText("Continue with context browsing, Context Map review, or new controlled draft intake.") === "Kontext suchen, Kontextkarte prüfen oder neue Notiz ablegen."
);
assert(
  "translates backend diagnostic summaries for German OS UI",
  posDiagnosticHeadline({ summary: "Personal OS integration is connected and the review queue is clear.", checks: [] }) === "Personal OS ist verbunden. Keine Prüfung offen."
);
assert(
  "translates backend next actions for German OS UI",
  posNextActionText({ nextAction: "Continue with context browsing or Code Loop." }, { counts: { pending: 0, invalid: 0 } }) === "Kontext suchen oder Lexa-Plan starten."
);
if (originalLexaI18n === undefined) {
  delete globalThis.LexaI18n;
} else {
  globalThis.LexaI18n = originalLexaI18n;
}
assert("offline next action prioritizes reconnect over invalid count", posNextActionText(offlineDiagnostics, { counts: offlineDiagnostics.counts }) === "Reconnect Personal OS and refresh the cockpit.");
assert("next action names one pending draft", posNextActionText({ nextAction: "Review pending drafts." }, {
  counts: { pending: 1, invalid: 0 },
  drafts: [{ title: "Lexa Autonomous Improvement Loop Update", approval: "pending" }],
}) === "Review: Lexa Autonomous Improvement Loop Update");
assert("next action does not name non-pending filtered rows", posNextActionText({ nextAction: "Review pending drafts." }, {
  counts: { pending: 1, invalid: 0 },
  drafts: [{ title: "Already approved", approval: "approved" }],
}) === "Review: Pending draft");
assert("next action counts multiple pending drafts", posNextActionText(null, { counts: { pending: 2 }, drafts: [] }) === "Review 2 pending drafts");
assert("next action prioritizes invalid drafts", posNextActionText(null, { counts: { pending: 0, invalid: 1 } }) === "Fix 1 invalid draft");
assert("next action treats invalid drafts as more urgent than pending", posNextActionText(null, { counts: { pending: 1, invalid: 1 }, drafts: [{ title: "Pending", approval: "pending" }] }) === "Fix 1 invalid draft");
assert("next action surfaces blocked diagnostics before pending review", posNextActionText({
  state: "blocked",
  nextAction: "Free disk space before write-heavy Lexa or Personal OS work.",
}, {
  counts: { pending: 1, invalid: 0 },
  drafts: [{ title: "Pending", approval: "pending" }],
}) === "Free disk space before write-heavy Lexa or Personal OS work.");
const storageWarnDiagnostics = {
  state: "attention",
  nextAction: "Review pending drafts.",
  checks: [{ id: "system-storage", label: "System storage", state: "warn", detail: "Low disk space: 512 MiB free." }],
};
assert("next action surfaces storage warning before pending review", posNextActionText(storageWarnDiagnostics, {
  counts: { pending: 1, invalid: 0 },
  drafts: [{ title: "Pending", approval: "pending" }],
}) === "System storage: Low disk space: 512 MiB free.");
assert("next action falls back to diagnostics", posNextActionText({ nextAction: "Continue with context browsing." }, { counts: { pending: 0, invalid: 0 } }) === "Continue with context browsing.");
assert("next draft path selects loaded pending draft", posNextDraftPath({
  drafts: [{ title: "Pending", path: "06_Inbox/Drafts/pending.md", approval: "pending" }],
}) === "06_Inbox/Drafts/pending.md");
assert("next draft path ignores non-pending rows", posNextDraftPath({
  drafts: [{ title: "Approved", path: "06_Inbox/Drafts/approved.md", approval: "approved" }],
}) === "");
assert("next card opens loaded pending draft", posNextCardAction({
  counts: { pending: 1 },
  drafts: [{ title: "Pending", path: "06_Inbox/Drafts/pending.md", approval: "pending" }],
}) === "open-draft");
assert("next card routes invalid queue states to all drafts", posNextCardAction({
  counts: { pending: 1, invalid: 1 },
  drafts: [{ title: "Pending", path: "06_Inbox/Drafts/pending.md", approval: "pending" }],
}) === "load-all");
assert("next card is inert while Personal OS is offline", posNextCardAction({ counts: { invalid: 1 } }, offlineDiagnostics) === "");
assert("next card is inert for blocked non-queue diagnostics", posNextCardAction({
  counts: { pending: 1, invalid: 0 },
  drafts: [{ title: "Pending", path: "06_Inbox/Drafts/pending.md", approval: "pending" }],
}, {
  state: "blocked",
  nextAction: "Free disk space before write-heavy Lexa or Personal OS work.",
}) === "");
assert("next card is inert for storage warnings", posNextCardAction({
  counts: { pending: 1, invalid: 0 },
  drafts: [{ title: "Pending", path: "06_Inbox/Drafts/pending.md", approval: "pending" }],
}, storageWarnDiagnostics) === "");
assert("next card loads pending filter when pending draft is not visible", posNextCardAction({
  counts: { pending: 1 },
  drafts: [{ title: "Approved", path: "06_Inbox/Drafts/approved.md", approval: "approved" }],
}) === "load-pending");
assert("next card is rendered as actionable button", src.includes("{ nextDraftPath, nextAction: nextCardAction }") && src.includes("pos-next-card"));
assert("actionable Personal OS cards reset native button chrome", css.includes(".pos-next-card,\n.pos-action-card") && css.includes("appearance: none") && css.includes("-webkit-appearance: none"));
assert("status metric cards can switch draft filters", src.includes('createPersonalOsInfoCard(posUiText("pos.cardPending", "PENDING"), String(pending), draftSub, pending ? "pos-warn" : "pos-good", "pending")') && src.includes('createPersonalOsInfoCard(posUiText("pos.cardApproved", "APPROVED"), String(approved), approvedSub, approved ? "pos-good" : "", "approved")') && src.includes('createPersonalOsInfoCard(posUiText("pos.cardRejected", "REJECTED"), String(rejected), rejectedSub, rejected ? "pos-bad" : "", "rejected")') && src.includes('createPersonalOsInfoCard(posUiText("pos.cardInvalid", "INVALID"), String(invalid), invalidSub, invalid ? "pos-bad" : "pos-good", "all")') && src.includes("loadPersonalOsQueueFilter"));
assert("active draft rows expose current selection", src.includes('row.setAttribute("aria-current"') && css.includes(".pos-draft-row.active") && css.includes("inset 3px 0 0 rgba(165, 154, 255, 0.9)"));
assert("Personal OS cockpit uses calmer product surfaces", css.includes("#personal-os-view .info-card") && css.includes("box-shadow: none") && css.includes(".pos-panel") && css.includes("background: rgba(12, 12, 20, 0.7)") && css.includes("border-radius: 8px"));
assert("Personal OS context search stays out of the default path", html.includes('class="pos-panel pos-query-panel pos-collapsible-panel"') && html.includes('class="pos-panel-summary"') && html.includes("Nur öffnen, wenn du Wissen aus dem OS brauchst.") && src.includes('panel.tagName === "DETAILS") panel.open = true') && overridesCss.includes(".pos-collapsible-panel") && overridesCss.includes(".pos-panel-summary::after"));
assert("empty draft states clear stale detail controls", src.includes("function clearPersonalOsDraftDetail") && src.includes('posUiText("pos.draftTitle"') && src.includes("button.disabled = true"));
assert("Personal OS draft detail fallbacks are localized", combinedPersonalOsSrc.includes("function posUiText") && src.includes('posUiText("pos.noDraftSelected"') && src.includes('posUiText("pos.draftLoadFailed"') && src.includes('posUiText("pos.applyApprovedOnly"') && src.includes('posUiText("pos.applyApprovedTitle"') && i18nDe.includes('"pos.noDraftSelected"') && i18nEn.includes('"pos.noDraftSelected"') && i18nDe.includes('"pos.applyApprovedTitle"') && i18nEn.includes('"pos.applyApprovedTitle"'));
assert("empty draft detail messages use safe text nodes", src.includes("function createPersonalOsEmptyState") && src.includes("empty.textContent = message || \"\"") && src.includes("setPersonalOsEmptyState(detail, emptyMessage)") && !src.includes("${message}</div>") && !src.includes("${emptyMessage}</div>"));
assert("Personal OS empty and loading states use safe DOM helpers", src.includes("setPersonalOsEmptyState(list, posDraftEmptyMessage(filterValue))") && src.includes("setPersonalOsEmptyState(target, posUiText(\"pos.noQueryMatches\"") && src.includes("summary.replaceChildren();") && src.includes("setPersonalOsEmptyState(stage, posUiText(\"pos.loadingContextMap\"") && src.includes("setPersonalOsEmptyState(list, posUiText(\"pos.loadingDraftQueue\"") && src.includes("setPersonalOsEmptyState(detail, posUiText(\"pos.noDraftSelected\"") && !src.includes("list.innerHTML = `<div class=\"empty-state\"") && !src.includes("detail.innerHTML = `<div class=\"empty-state\"") && !src.includes("stage.innerHTML = `<div class=\"empty-state\""));
assert("Personal OS home grid uses safe DOM helpers", src.includes("function createPersonalOsHomeAction") && src.includes("button.dataset.posHomeAction = action") && src.includes("function createPersonalOsInfoCard") && src.includes("card.dataset.queueFilter = queueFilter") && src.includes("function createPersonalOsCapabilityItem") && src.includes("grid.replaceChildren(homeCard)") && !src.includes("grid.innerHTML = `"));
assert("Personal OS draft and query rows use safe DOM helpers", src.includes("function createPersonalOsDraftRow") && src.includes("title.textContent = posText(draft.title") && src.includes("subtitle.textContent = posDraftStatusText(draft.approval)") && src.includes("pill.textContent = posText(draft.approval") && src.includes("const row = createPersonalOsDraftRow(draft, PersonalOSState.selectedPath)") && src.includes("function createPersonalOsQueryMatchRow") && src.includes("path.textContent = posText(match.path)") && src.includes("pill.textContent = posText(match.memory_level || match.type") && src.includes("const row = createPersonalOsQueryMatchRow(match)") && !src.includes('row.className = "pos-query-row";\n      row.innerHTML = `'));
assert("Personal OS read payloads use safe DOM helpers", src.includes("function createPersonalOsQueryDocumentView") && src.includes("const fragment = document.createDocumentFragment()") && src.includes("titleEl.textContent = title") && src.includes("pathEl.textContent = posText(payload.path)") && src.includes("tagEl.textContent = tags") && src.includes("body.textContent = posText(payload.body)") && src.includes("target.replaceChildren(createPersonalOsQueryDocumentView(payload, title, tags))") && src.includes("setPersonalOsEmptyState(target, posErrorMessage(payload, posUiText(\"pos.contextPackFailed\"") && src.includes("setPersonalOsEmptyState(target, posErrorMessage(payload, posUiText(\"pos.obsidianContextFailed\"") && src.includes("setPersonalOsEmptyState(target, posErrorMessage(payload, posUiText(\"pos.codeLoopFailed\"") && !src.includes("target.innerHTML = `<div class=\"empty-state\">${escapeHtml(posErrorMessage(payload, posUiText(\"pos.contextPackFailed\"") && !src.includes("target.innerHTML = `<div class=\"empty-state\">${escapeHtml(posErrorMessage(payload, posUiText(\"pos.obsidianContextFailed\"") && !src.includes("target.innerHTML = `<div class=\"empty-state\">${escapeHtml(posErrorMessage(payload, posUiText(\"pos.codeLoopFailed\""));
assert("Personal OS context pack render uses safe DOM helpers", src.includes("function createPersonalOsContextPackView") && src.includes("function createPersonalOsRelatedFileRow") && src.includes("row.dataset.relatedPath = posText(file.path)") && src.includes("preview.textContent = posContextFilesPreview(files)") && src.includes("target.replaceChildren(createPersonalOsContextPackView(query, files, errors, graphLabel, graphClass))") && !src.includes('data-action="personalOsSendContextPackToChat">${escapeHtml') && !src.includes('data-related-path="${escapeHtml(posText(file.path))}"'));
assert("Personal OS Obsidian context render uses safe DOM helpers", src.includes("function createPersonalOsObsidianContextView") && src.includes("function createPersonalOsRelatedInfoRow") && src.includes("chatButton.dataset.action = \"personalOsSendObsidianContextToChat\"") && src.includes("quickFindList.appendChild(createPersonalOsRelatedInfoRow(posText(item.need, \"Context\"), posText(item.goTo, \"-\")))") && src.includes("preview.textContent = posContextFilesPreview(files)") && src.includes("target.replaceChildren(createPersonalOsObsidianContextView(vault, counts, product, quickFind, surfaces, files))") && !src.includes('data-action="personalOsSendObsidianContextToChat">${escapeHtml') && !src.includes('${quickFind.slice(0, 10).map((item) => `'));
assert("Personal OS Code Loop render uses safe DOM helpers", src.includes("function createPersonalOsCodeLoopView") && src.includes("button.dataset.action = action") && src.includes("card.dataset.codeLoopAction = \"load-pending\"") && src.includes("row.dataset.codeLoopDraft = posText(draft.path)") && src.includes("row.dataset.codeLoopFile = posText(file.path)") && src.includes("preview.textContent = personalOsCodeLoopPrompt(payload)") && src.includes("target.replaceChildren(createPersonalOsCodeLoopView(payload, diagnostics, draftRows, contextFiles, raw, evidence, meta))") && !src.includes('data-action="personalOsSendCodeLoopToAgent">${escapeHtml') && !src.includes('data-code-loop-draft="${escapeHtml(posText(draft.path))}"') && !src.includes('data-code-loop-file="${escapeHtml(posText(file.path))}"'));
assert("Personal OS draft detail render uses safe DOM helpers", src.includes("function createPersonalOsDraftDetailView") && src.includes("bodyEl.textContent = body") && src.includes("createPosPromptHint(payload, review)") && src.includes("createPosApplyHint(review)") && src.includes("detail.replaceChildren(createPersonalOsDraftDetailView(payload, review, body, approval, tags, related))") && !src.includes("detail.innerHTML = `"));
assert("Personal OS review hint helpers build DOM nodes", reviewHelpersSrc.includes("function createPosApplyHint") && reviewHelpersSrc.includes("function createPosPromptHint") && reviewHelpersSrc.includes('wrapper.className = "pos-prompt-hint"') && reviewHelpersSrc.includes('createPersonalOsTextElement("div", "pos-label", posUiText("pos.labelChatReviewPrompt"'));
assert("Personal OS apply-draft modal copy is localized", src.includes('posUiText("pos.applyDraftTitle"') && src.includes('posUiText("pos.applyReasonLabel"') && src.includes('posUiText("pos.applyDefaultTarget"') && src.includes('posUiText("pos.applyReasonDefault"') && src.includes('posUiText("pos.applyDraftAction"') && src.includes('posUiText("pos.applyFailed"') && src.includes('posUiText("pos.applySuccess"') && i18nDe.includes('"pos.applyDraftTitle"') && i18nEn.includes('"pos.applyDraftTitle"') && i18nDe.includes('"pos.applySuccess"') && i18nEn.includes('"pos.applySuccess"'));
assert("Personal OS draft loading and search states are localized", src.includes('posUiText("pos.loadingDraftQueue"') && src.includes('posUiText("pos.searchingDrafts"') && src.includes('posUiText("pos.noDraftSearchResult"') && src.includes('posUiText("pos.draftFoundLoaded"') && src.includes('posUiText("pos.draftsFoundSelect"') && i18nDe.includes('"pos.loadingDraftQueue"') && i18nEn.includes('"pos.loadingDraftQueue"') && i18nDe.includes('"pos.draftsFoundSelect"') && i18nEn.includes('"pos.draftsFoundSelect"'));
assert("Personal OS find-draft modal copy is localized", src.includes('posUiText("pos.findDraftTitle"') && src.includes('posUiText("pos.findDraftSearchLabel"') && src.includes('posUiText("pos.findDraftSearchPlaceholder"') && src.includes('posUiText("pos.findDraftAction"') && i18nDe.includes('"pos.findDraftTitle"') && i18nEn.includes('"pos.findDraftTitle"') && i18nDe.includes('"pos.findDraftAction"') && i18nEn.includes('"pos.findDraftAction"'));
assert("Personal OS raw inbox modal copy is localized", src.includes('posUiText("pos.rawProcessorSafeDefault"') && src.includes('posUiText("pos.rawProcessorLexa"') && src.includes('posUiText("pos.rawReadySummary"') && src.includes('posUiText("pos.rawStatusUnavailable"') && src.includes('posUiText("pos.rawInboxTitle"') && src.includes('posUiText("pos.rawTitleLabel"') && src.includes('posUiText("pos.rawBodyLabel"') && src.includes('posUiText("pos.rawProcessorLabel"') && src.includes('posUiText("pos.rawCreateDraftAction"') && src.includes('posUiText("pos.rawProcessing"') && src.includes('posUiText("pos.rawIntakeFailed"') && src.includes('posUiText("pos.rawDraftCreated"') && src.includes('posUiText("pos.rawProcessed"') && i18nDe.includes('"pos.rawInboxTitle"') && i18nEn.includes('"pos.rawInboxTitle"') && i18nDe.includes('"pos.rawProcessorLexa"') && i18nEn.includes('"pos.rawProcessorLexa"') && i18nDe.includes('"pos.rawProcessed"') && i18nEn.includes('"pos.rawProcessed"'));
assert("Personal OS draft empty and queue error copy is localized", src.includes('posUiText("pos.emptyPendingDrafts"') && src.includes('posUiText("pos.emptyApprovedDrafts"') && src.includes('posUiText("pos.emptyRejectedDrafts"') && src.includes('posUiText("pos.emptyConflictDrafts"') && src.includes('posUiText("pos.emptyMissingApprovalDrafts"') && src.includes('posUiText("pos.emptyDrafts"') && src.includes('posUiText("pos.draftQueueFailed"') && i18nDe.includes('"pos.emptyPendingDrafts"') && i18nEn.includes('"pos.emptyPendingDrafts"') && i18nDe.includes('"pos.draftQueueFailed"') && i18nEn.includes('"pos.draftQueueFailed"'));
assert("Personal OS approve/reject modal copy is localized", src.includes('posUiText("pos.decideApproveAction"') && src.includes('posUiText("pos.decideApproveOverrideAction"') && src.includes('posUiText("pos.decideRejectAction"') && src.includes('posUiText("pos.decideApproveTitle"') && src.includes('posUiText("pos.decideApproveOverrideTitle"') && src.includes('posUiText("pos.decideRejectTitle"') && src.includes('posUiText("pos.decideReasonLabel"') && src.includes('posUiText("pos.decideApproveDefault"') && src.includes('posUiText("pos.decideApproveOverrideDefault"') && src.includes('posUiText("pos.decideRejectDefault"') && src.includes('posUiText("pos.decideFailed"') && src.includes('posUiText("pos.decideApproved"') && src.includes('posUiText("pos.decideRejected"') && i18nDe.includes('"pos.decideApproveAction"') && i18nEn.includes('"pos.decideApproveAction"') && i18nDe.includes('"pos.decideRejected"') && i18nEn.includes('"pos.decideRejected"'));
assert("Personal OS chat handoff toasts are localized", src.includes('posUiText("pos.promptNotReady"') && src.includes('posUiText("pos.chatInputUnavailable"') && src.includes('posUiText("pos.promptClipped"') && src.includes('posUiText("pos.noContextSelected"') && src.includes('posUiText("pos.contextPromptReady"') && src.includes('posUiText("pos.noContextPackSelected"') && src.includes('posUiText("pos.contextPackPromptReady"') && src.includes('posUiText("pos.noCodeLoopReady"') && src.includes('posUiText("pos.codeLoopPromptReady"') && src.includes('posUiText("pos.codeLoopAgentPromptReady"') && src.includes('posUiText("pos.noReviewPackageSelected"') && src.includes('posUiText("pos.reviewPromptReady"') && src.includes('posUiText("pos.draftSearchFailed"') && i18nDe.includes('"pos.promptNotReady"') && i18nEn.includes('"pos.promptNotReady"') && i18nDe.includes('"pos.reviewPromptReady"') && i18nEn.includes('"pos.reviewPromptReady"'));
assert("Personal OS chat handoff prompt scaffolds are localized", src.includes('posUiText("pos.promptCompactedSuffix"') && src.includes('posUiText("pos.contextPromptIntro"') && src.includes('posUiText("pos.contextPackPromptIntro"') && src.includes('posUiText("pos.promptPathLabel"') && src.includes('posUiText("pos.promptFilesIncluded"') && src.includes('posUiText("pos.promptGraphCounts"') && i18nDe.includes('"pos.contextPromptIntro"') && i18nEn.includes('"pos.contextPromptIntro"') && i18nDe.includes('"pos.promptGraphCounts"') && i18nEn.includes('"pos.promptGraphCounts"'));
assert("Personal OS draft-review prompt scaffold is localized", src.includes('posUiText("pos.reviewPromptIntro"') && src.includes('posUiText("pos.reviewPromptNoAutoDecision"') && src.includes('posUiText("pos.promptApprovalChecklistHeading"') && src.includes('posUiText("pos.promptCanApplyLabel"') && src.includes('posUiText("pos.noHistoryEvents"') && src.includes('posUiText("pos.reviewPromptFinalQuestion"') && i18nDe.includes('"pos.reviewPromptIntro"') && i18nEn.includes('"pos.reviewPromptIntro"') && i18nDe.includes('"pos.reviewPromptFinalQuestion"') && i18nEn.includes('"pos.reviewPromptFinalQuestion"'));
assert("Personal OS query, context, and loading states are localized", src.includes('posUiText("pos.queryFailed"') && src.includes('posUiText("pos.noQueryMatches"') && src.includes('posUiText("pos.contextPackFailed"') && src.includes('posUiText("pos.noContextPackFiles"') && src.includes('posUiText("pos.codeLoopFailed"') && src.includes('posUiText("pos.contextMapFailed"') && src.includes('posUiText("pos.noContextMapNodes"') && src.includes('posUiText("pos.loadingIndex"') && src.includes('posUiText("pos.invalidTag"') && src.includes('posUiText("pos.tagRequired"') && src.includes('posUiText("pos.searchingTag"') && src.includes('posUiText("pos.loadingContextMap"') && src.includes('posUiText("pos.buildingContextPack"') && src.includes('posUiText("pos.buildingCodeLoop"') && src.includes('posUiText("pos.loadingFile"') && src.includes('posUiText("pos.loadingDraftTitle"') && src.includes('posUiText("pos.loadingDraftBody"') && i18nDe.includes('"pos.queryFailed"') && i18nEn.includes('"pos.queryFailed"') && i18nDe.includes('"pos.buildingCodeLoop"') && i18nEn.includes('"pos.buildingCodeLoop"'));
assert("Personal OS target/review empty detail copy is localized", src.includes('posUiText("pos.noAutomaticTargetComparison"') && src.includes('posUiText("pos.targetBodyIdentical"') && src.includes('posUiText("pos.noTargetAvailable"') && src.includes('posUiText("pos.noReadableRelatedFiles"') && src.includes('posUiText("pos.noDraftHistory"') && i18nDe.includes('"pos.noAutomaticTargetComparison"') && i18nEn.includes('"pos.noAutomaticTargetComparison"') && i18nDe.includes('"pos.noDraftHistory"') && i18nEn.includes('"pos.noDraftHistory"'));
assert("Personal OS detail and review labels are localized", combinedPersonalOsSrc.includes('posUiText("pos.labelReviewAssist"') && combinedPersonalOsSrc.includes('posUiText("pos.labelApplyBoundary"') && combinedPersonalOsSrc.includes('posUiText("pos.labelChatReviewPrompt"') && combinedPersonalOsSrc.includes('posUiText("pos.labelTargetReview"') && combinedPersonalOsSrc.includes('posUiText("pos.metricApprovedBox"') && combinedPersonalOsSrc.includes('posUiText("pos.targetLoadedNoDiff"') && i18nDe.includes('"pos.labelReviewAssist"') && i18nEn.includes('"pos.labelReviewAssist"') && i18nDe.includes('"pos.metricApprovedBox"') && i18nEn.includes('"pos.metricApprovedBox"'));
assert("Personal OS context pack and code-loop labels are localized", src.includes('posUiText("pos.titleContextPack"') && src.includes('posUiText("pos.titleCodeLoop"') && src.includes('posUiText("pos.actionAgent"') && src.includes('posUiText("pos.metricCandidates"') && src.includes('posUiText("pos.metricOsState"') && src.includes('posUiText("pos.labelDraftDecisions"') && src.includes('posUiCount("pos.countFiles"') && i18nDe.includes('"pos.titleContextPack"') && i18nEn.includes('"pos.titleContextPack"') && i18nDe.includes('"pos.labelDraftDecisions"') && i18nEn.includes('"pos.labelDraftDecisions"'));
assert("Personal OS code-loop agent prompt clips after agent prefix", src.includes("function personalOsCodeLoopAgentPrompt") && src.includes('posClipChatPrompt(`/agent ${prompt}`)') && !src.includes("return prompt ? `/agent ${prompt}` : \"\";"));
assert("Personal OS graph labels and counters are localized", src.includes('posUiText("pos.graphLaneImportantFiles"') && src.includes('posUiText("pos.labelRelationshipMap"') && src.includes('posUiText("pos.graphLegendLabel"') && src.includes('posUiText("pos.graphAriaLabel"') && src.includes('posUiCount("pos.countMapNodes"') && src.includes('posUiText("pos.searchTagTitle"') && i18nDe.includes('"pos.graphLaneImportantFiles"') && i18nEn.includes('"pos.graphLaneImportantFiles"') && i18nDe.includes('"pos.graphAriaLabel"') && i18nEn.includes('"pos.graphAriaLabel"'));
assert("Personal OS status cards are localized", src.includes('posUiText("pos.cardHealth"') && src.includes('posUiText("pos.cardPending"') && src.includes('posUiText("pos.subNonSmokeDrafts"') && src.includes('posUiText("pos.subCapabilitiesReady"') && src.includes('posUiText("pos.capabilityMissingTools"') && src.includes('posUiText("pos.nextReviewTitle"') && src.includes('posStateLabel("live"') && i18nDe.includes('"pos.cardHealth"') && i18nEn.includes('"pos.cardHealth"') && i18nDe.includes('"pos.subCapabilitiesReady"') && i18nEn.includes('"pos.subCapabilitiesReady"'));

console.log("\npersonalOsReviewPrompt():");
const prompt = personalOsReviewPrompt(draft, review);
assert("fits Lexa chat limit", prompt.length <= 3600, `len=${prompt.length}`);
assert("includes draft path", prompt.includes(draft.path));
assert("includes review assist", prompt.includes("## Review Assist"));
assert("includes apply boundary", prompt.includes("## Apply Boundary"));
assert("includes final question", prompt.includes("Meine Frage dazu"));

console.log("\npersonalOsReviewPromptMeta():");
const meta = personalOsReviewPromptMeta(draft, review);
assert("reports same prompt length", meta.length === prompt.length, `meta=${meta.length} prompt=${prompt.length}`);
assert("reports chat prompt limit", meta.limit === posChatPromptLimit(), `limit=${meta.limit}`);
assert("reports bounded percent", meta.percent >= 0 && meta.percent <= 100, `percent=${meta.percent}`);
assert("meter width class is rounded safely", posMeterWidthClass(97) === "meter-width-95");
assert("meter width class clamps high values", posMeterWidthClass(999) === "meter-width-100");
globalThis.LexaConfig = { MAX_CHAT_INPUT_LENGTH: 1200 };
const configuredReviewPrompt = personalOsReviewPrompt(draft, review);
const configuredReviewMeta = personalOsReviewPromptMeta(draft, review);
assert("configured review prompt respects chat headroom", configuredReviewPrompt.length <= posChatPromptLimit(), `len=${configuredReviewPrompt.length} limit=${posChatPromptLimit()}`);
assert("configured review meta reports chat headroom", configuredReviewMeta.limit === posChatPromptLimit(), `limit=${configuredReviewMeta.limit}`);
globalThis.LexaConfig = originalLexaConfig;

console.log("\npersonalOsCodeLoopPrompt():");
const codeLoop = { ok: true, prompt: `Code loop context.\n${huge}` };
const codeLoopPrompt = personalOsCodeLoopPrompt(codeLoop);
const codeLoopAgentPrompt = personalOsCodeLoopAgentPrompt(codeLoop);
const codeLoopMeta = personalOsCodeLoopPromptMeta(codeLoop);
assert("clips code loop prompt under limit", codeLoopPrompt.length <= 3600, `len=${codeLoopPrompt.length}`);
assert("prefixes code loop agent prompt", codeLoopAgentPrompt.startsWith("/agent "));
assert("keeps code loop agent prompt under chat prompt limit", codeLoopAgentPrompt.length <= posChatPromptLimit(), `len=${codeLoopAgentPrompt.length}`);
assert("keeps code loop agent compacted marker", codeLoopAgentPrompt.includes("Prompt compacted"));
assert("reports raw code loop prompt length", codeLoopMeta.length === codeLoop.prompt.length, `meta=${codeLoopMeta.length}`);
assert("marks compacted code loop prompts", codeLoopMeta.compacted === true);
globalThis.LexaConfig = { MAX_CHAT_INPUT_LENGTH: 1200 };
const configuredCodeLoopPrompt = personalOsCodeLoopPrompt(codeLoop);
const configuredCodeLoopAgentPrompt = personalOsCodeLoopAgentPrompt(codeLoop);
const configuredCodeLoopMeta = personalOsCodeLoopPromptMeta(codeLoop);
assert("configured code loop prompt respects chat headroom", configuredCodeLoopPrompt.length <= posChatPromptLimit(), `len=${configuredCodeLoopPrompt.length} limit=${posChatPromptLimit()}`);
assert("configured code loop agent prompt respects chat headroom", configuredCodeLoopAgentPrompt.length <= posChatPromptLimit(), `len=${configuredCodeLoopAgentPrompt.length} limit=${posChatPromptLimit()}`);
assert("configured code loop meta reports chat headroom", configuredCodeLoopMeta.limit === posChatPromptLimit(), `limit=${configuredCodeLoopMeta.limit}`);
globalThis.LexaConfig = originalLexaConfig;

console.log("\npersonalOsObsidianPrompt():");
const obsidianPayload = {
  ok: true,
  topic: "lexa hermes obsidian",
  vault: { root: "C:\\Users\\admin\\OneDrive\\Desktop\\OS", loadedAll: false },
  counts: { bootstrapAvailable: 7, areaIndexes: 15 },
  lexaProductContract: {
    providerMode: "api-backed",
    rule: "Lexa uses configured provider APIs for model intelligence.",
  },
  lexaInventory: {
    quickFind: [
      { need: "Hermes bridge", goTo: "backend/hermes_adapter.py" },
      { need: "Obsidian context", goTo: "backend/obsidian_context.py" },
    ],
    surfaces: [
      { id: "backend-api", purpose: "FastAPI routers", fileCountApprox: 63 },
      { id: "hermes-vendor", purpose: "Telegram gateway", fileCountApprox: 4 },
    ],
  },
  files: [
    {
      title: "Lexa Context Index",
      path: "08_Lexa/Architecture/Lexa_Context_Index.md",
      memory_level: "working",
      tags: ["lexa", "obsidian"],
      bodyPreview: huge,
    },
  ],
};
const obsidianPrompt = personalOsObsidianPrompt(obsidianPayload);
assert("builds Obsidian prompt with provider mode", obsidianPrompt.includes("Provider mode: api-backed"));
assert("builds Obsidian prompt with quick-find routes", obsidianPrompt.includes("backend/hermes_adapter.py") && obsidianPrompt.includes("backend/obsidian_context.py"));
assert("keeps Obsidian prompt under chat limit", obsidianPrompt.length <= posChatPromptLimit(), `len=${obsidianPrompt.length}`);
assert("personal OS view exposes Obsidian context action", html.includes('data-action="personalOsLoadObsidianContext"') && src.includes("function personalOsLoadObsidianContext") && src.includes("personalOsObsidianContext"));
assert("preload exposes Obsidian context endpoint", preload.includes("personalOsObsidianContext") && preload.includes("/personal-os/obsidian-context"));
assert("Obsidian context uses shared chat context when available", src.includes("personalOsSharedContext") && src.includes("shared?.fresh") && src.includes('sharedTopic || "lexa hermes obsidian"'));
assert("renders Obsidian context card and chat handoff", src.includes("function renderPersonalOsObsidianContext") && src.includes("personalOsSendObsidianContextToChat") && src.includes("selectedObsidianContext"));
assert("i18n includes Obsidian context labels", i18nDe.includes('"pos.titleObsidianContext"') && i18nEn.includes('"pos.obsidianContextPromptReady"'));

const codeLoopCounts = posCodeLoopEvidenceCounts({
  diagnostics: { counts: { pending: "0", approved: "2", rejected: "3", invalid: null } },
  contextPack: {
    files: [{ path: "OS_MANIFEST.md" }, { path: "05_Memory/Rollups/Current_AI_Brief.md" }],
    graph: { ok: false, counts: { files: "3", edges: "4", errors: "2" }, errors: [{ path: "bad.md" }] },
  },
  drafts: { items: [{ path: "06_Inbox/Drafts/a.md" }] },
  rawInbox: { failureState: { failed: "1" } },
});
assert("counts code loop context files", codeLoopCounts.contextFiles === 2, `context=${codeLoopCounts.contextFiles}`);
assert("counts code loop draft decisions", codeLoopCounts.drafts === 1, `drafts=${codeLoopCounts.drafts}`);
assert("normalizes code loop approval counts", codeLoopCounts.approved === 2 && codeLoopCounts.rejected === 3);
assert("normalizes code loop worker failures", codeLoopCounts.workerFailures === 1);
assert("normalizes code loop graph counts", codeLoopCounts.graphFiles === 3 && codeLoopCounts.graphEdges === 4);
assert("marks partial code loop graph", codeLoopCounts.graphOk === false && codeLoopCounts.graphErrors === 2);
assert("code loop pending card can load review queue", src.includes('card.dataset.codeLoopAction = "load-pending"') && src.includes("loadPersonalOsPendingQueue"));
const codeLoopDraftRows = posCodeLoopDraftRows([
  { title: "Approved", approval: "approved", path: "approved.md" },
  { title: "Rejected", approval: "rejected", path: "rejected.md" },
  { title: "Pending", approval: "pending", path: "pending.md" },
  { title: "Missing", approval: "missing", path: "missing.md" },
], 3);
assert("ranks code loop draft attention before closed decisions", codeLoopDraftRows.map((row) => row.title).join(",") === "Missing,Pending,Approved");
assert("ranks pending code loop drafts ahead of approved ones", posCodeLoopDraftRank({ approval: "pending" }) < posCodeLoopDraftRank({ approval: "approved" }));

console.log("\nposGraphHealth():");
const partialGraph = posGraphHealth({
  ok: false,
  nodes: [{ id: "OS_MANIFEST.md" }],
  counts: { errors: 1 },
  errors: [{ path: "bad.md" }],
});
assert("renders partial graphs with nodes", partialGraph.partial === true && partialGraph.failed === false);
assert("counts partial graph errors", partialGraph.errorCount === 1 && partialGraph.note === "partial");
const failedGraph = posGraphHealth({ ok: false, nodes: [], error: "Graph failed" });
assert("fails graphs without nodes", failedGraph.failed === true && failedGraph.hasNodes === false);
const partialGraphWithError = posGraphHealth({ ok: false, nodes: [{ id: "OS_MANIFEST.md" }], error: "One file failed" });
assert("keeps partial graphs visible with top-level errors", partialGraphWithError.partial === true && partialGraphWithError.failed === false && partialGraphWithError.errorCount === 1);
const okGraphWithError = posGraphHealth({ ok: true, nodes: [{ id: "OS_MANIFEST.md" }], error: "One file failed" });
assert("marks graph payloads with top-level errors as partial", okGraphWithError.partial === true && okGraphWithError.note === "partial");
assert("labels graph view as context map", html.includes(">Context Map<"));
assert("uses context map accessibility label", src.includes('posUiText("pos.graphAriaLabel"') && i18nDe.includes('"pos.graphAriaLabel"') && i18nEn.includes('"pos.graphAriaLabel"'));
assert("uses context map label in status and detail UI", src.includes("Context Map Errors") && src.includes("Context Map failed"));
assert("does not leave standalone graph label in visible cards", !src.includes('<div class="pos-label">Graph</div>'));
assert("context map prioritizes navigable rows before mini network", src.indexOf('explorer.className = "pos-graph-explorer"') > -1 && src.indexOf('explorer.className = "pos-graph-explorer"') < src.indexOf('class: "pos-graph-svg"'));
assert("context map network is labeled as a full relationship map", src.includes('posUiText("pos.labelRelationshipMap"') && src.includes('posUiText("pos.graphShown"'));
assert("context map renders a visible legend", src.includes('legend.className = "pos-graph-legend"') && src.includes("pos-graph-legend-file") && css.includes(".pos-graph-legend"));
assert("context map uses a larger readable stage", src.includes("const width = 1160") && src.includes("const height = 430") && css.includes("height: 430px"));
assert("context map tag hubs are actionable searches", src.includes("dataset.graphTag") && src.includes("personalOsSearchTag()") && css.includes(".pos-graph-hub-action"));
assert("context map explorer rows use safe DOM helpers", src.includes("function createPersonalOsGraphFileRow") && src.includes("function createPersonalOsGraphHubRow") && src.includes("title.textContent = posGraphLabel(node)") && src.includes("path.textContent = posText(node.path || node.id)") && src.includes("title.textContent = posGraphDisplayName(node, 34)") && src.includes("pill.textContent = String(Number(node.degree || 0))") && src.includes("rows.replaceChildren();") && src.includes("hubs.replaceChildren();") && src.includes("const row = createPersonalOsGraphFileRow(node)") && src.includes("const row = createPersonalOsGraphHubRow(node, tagQuery)") && !src.includes("rows.innerHTML = \"\"") && !src.includes("hubs.innerHTML = \"\"") && !src.includes("row.innerHTML = `"));
assert("context map summary uses safe DOM helpers", src.includes("function createPersonalOsPill") && src.includes("pill.textContent = text") && src.includes("function renderPersonalOsGraphSummary") && src.includes("summary.replaceChildren(...pills)") && src.includes("renderPersonalOsGraphSummary(summary, payload, counts, nodes, edges, visibleNodes, visibleEdges, health)") && !src.includes("summary.innerHTML = `"));
assert("context map network uses safe SVG helpers", src.includes("function createPersonalOsSvgElement") && src.includes("function createPersonalOsGraphStageView") && src.includes("stage.replaceChildren(createPersonalOsGraphStageView(health, width, height, visibleNodes, visibleEdges, positions))") && !src.includes("stage.innerHTML = `"));
assert("context map supports focus highlights for related nodes", src.includes("function setupPersonalOsGraphFocus") && src.includes('"data-node-id": node.id') && src.includes('"data-source": edge.source') && overridesCss.includes(".pos-graph-node.is-active") && overridesCss.includes(".pos-graph-edge.is-active"));

console.log("\nposGraphRankedNodes():");
const graphNodes = [
  { id: "00_System/Rules/metadata_schema.md", kind: "file", path: "00_System/Rules/metadata_schema.md" },
  { id: "00_System/INDEX.md", kind: "file", path: "00_System/INDEX.md" },
  { id: "tag:sdk", kind: "tag" },
];
const graphEdges = [
  { source: "00_System/Rules/metadata_schema.md", target: "tag:sdk", type: "tag" },
  { source: "00_System/INDEX.md", target: "tag:sdk", type: "tag" },
  { source: "00_System/INDEX.md", target: "00_System/Rules/metadata_schema.md", type: "related" },
];
const degree = posGraphDegreeMap(graphEdges);
const rankedFiles = posGraphRankedNodes(graphNodes, graphEdges, "file", 2);
assert("graph display name keeps useful path context", posGraphDisplayName(graphNodes[0]) === "Rules/metadata_schema");
assert("graph display name formats tags", posGraphDisplayName(graphNodes[2]) === "#sdk");
assert("normalizes visible tag input", posNormalizeTagQuery("#Lexa") === "lexa" && posNormalizeTagQuery("tag:Personal OS") === "personal-os");
assert("detects invalid visible tag input", posTagFilter("#!!!").invalid === true && posTagFilter("").invalid === false);
assert("rejects backend-incompatible visible tags", posTagFilter("#___").invalid === true);
assert("graph tag query strips tag prefix", posGraphTagQuery({ id: "tag:Personal OS", kind: "tag" }) === "personal-os");
assert("graph tag query ignores non-tag nodes", posGraphTagQuery({ id: "00_System/INDEX.md", kind: "file" }) === "");
assert("graph degree map counts both edge ends", degree.get("tag:sdk") === 2 && degree.get("00_System/INDEX.md") === 2);
assert("graph ranking prioritizes index files", rankedFiles[0].id === "00_System/INDEX.md");
assert("graph ranking annotates degree", rankedFiles[0].degree === 2);

console.log("\nposTargetSummary():");
const targetError = posTargetSummary({
  targetCandidate: "00_System/SDK/os-sdk/README.md",
  targetSource: "frontmatter",
  target: { error: "missing metadata ".repeat(100) },
});
const targetNoDiff = posTargetSummary({
  targetCandidate: "00_System/SDK/os-sdk/README.md",
  targetSource: "frontmatter",
  target: { path: "00_System/SDK/os-sdk/README.md" },
});
const targetWithDiff = posTargetSummary({
  targetCandidate: "00_System/INDEX.md",
  targetSource: "sdk-draft-path",
  diff: { changed: true, lines: ["-old", "+new"] },
});
assert("target summary keeps candidate and source", targetError.candidate.endsWith("README.md") && targetError.source === "frontmatter");
assert("target summary clips long target errors", targetError.status === "error" && targetError.message.includes("[truncated]"));
assert("target summary explains frontmatter targets without diff", targetNoDiff.status === "target" && targetNoDiff.message.includes("no automatic body diff"));
assert("target summary detects body diff", targetWithDiff.status === "diff" && targetWithDiff.hasDiff === true);

console.log("\nposQueueCounts():");
const queueCounts = posQueueCounts({ counts: { total: "5", pending: 0, approved: 2, rejected: 3, invalid: null } });
assert("normalizes string totals", queueCounts.total === 5, `total=${queueCounts.total}`);
assert("keeps zero pending", queueCounts.pending === 0, `pending=${queueCounts.pending}`);
assert("keeps approved count", queueCounts.approved === 2, `approved=${queueCounts.approved}`);
assert("keeps rejected count", queueCounts.rejected === 3, `rejected=${queueCounts.rejected}`);
assert("falls back invalid count to zero", queueCounts.invalid === 0, `invalid=${queueCounts.invalid}`);

console.log("\nposDraftEmptyMessage():");
assert("names empty pending queue", posDraftEmptyMessage("pending").includes("Review queue is clear"));
assert("names missing approval queue", posDraftEmptyMessage("missing").includes("missing approval box"));

console.log("\nposDraftQueueError():");
assert("keeps direct draft queue error payloads", posDraftQueueError({ ok: false, error: "Invalid tag filter" }) === "Invalid tag filter");
assert("keeps legacy draft queue error arrays", posDraftQueueError({ ok: false, errors: [{ error: "MCP offline" }] }) === "MCP offline");
assert("ignores successful draft queue payloads", posDraftQueueError({ ok: true, drafts: [] }) === "");

console.log("\nposDraftMatchesSearch():");
const searchDraft = {
  title: "Lexa Personal OS Cockpit Integration",
  path: "06_Inbox/Drafts/cockpit.md",
  approval: "approved",
  tags: ["lexa", "cockpit"],
};
assert("matches draft title", posDraftMatchesSearch(searchDraft, "cockpit integration"));
assert("matches draft tag", posDraftMatchesSearch(searchDraft, "lexa"));
assert("rejects unrelated query", !posDraftMatchesSearch(searchDraft, "raw inbox"));
assert("filters visible drafts", posVisibleDrafts([
  searchDraft,
  { title: "Raw Inbox Result", path: "06_Inbox/Drafts/raw.md", approval: "rejected" },
], "cockpit").length === 1);
assert("keeps all drafts without search", posVisibleDrafts([searchDraft], "").length === 1);

console.log("\nposRawProcessorOptions():");
const rawOptions = posRawProcessorOptions({
  processors: [
    { name: "deterministic", status: "available" },
    { name: "lexa", status: "disabled" },
    { name: "llm", status: "available" },
  ],
});
assert("keeps deterministic available", rawOptions.some((option) => option.value === "deterministic"));
assert("hides disabled lexa processor", !rawOptions.some((option) => option.value === "lexa"));
assert("falls back to deterministic without status", posRawProcessorOptions(null)[0].value === "deterministic");
assert("summarizes raw worker status", posRawStatusSummary({
  processors: [{ name: "deterministic", status: "available" }],
  failureState: { failed: 0 },
}).includes("deterministic; 0 worker failures"));
assert("summarizes raw worker failures", posRawStatusSummary({
  processors: [{ name: "lexa", status: "available" }],
  failureState: { failed: 1 },
}).includes("lexa; 1 worker failure"));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
