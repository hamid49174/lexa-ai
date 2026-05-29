/* Personal OS review display helpers. Classic script loaded before personal_os.js. */

function createPosApplyHint(review) {
  const hint = review?.applyHint || {};
  if (!hint.reason && !hint.target) return null;

  const wrapper = document.createElement("div");
  wrapper.className = "pos-apply-hint";
  wrapper.append(
    createPersonalOsTextElement("div", "pos-label", posUiText("pos.labelApplyBoundary", "Apply Boundary")),
    createPersonalOsTextElement("div", "pos-draft-path", posText(hint.target, posUiText("pos.noApplyTarget", "No target"))),
    createPersonalOsTextElement("div", hint.enabled ? "pos-good" : "pos-warn", posText(hint.reason))
  );
  return wrapper;
}

function createPosPromptHint(draft, review) {
  if (!draft?.path || !review) return null;
  const meta = personalOsReviewPromptMeta(draft, review);
  const cls = meta.percent >= 90 ? "pos-warn" : "pos-good";
  const mode = meta.compacted
    ? posUiText("pos.promptCompacted", "compacted")
    : posUiText("pos.promptCompact", "compact");

  const wrapper = document.createElement("div");
  wrapper.className = "pos-prompt-hint";
  const copy = document.createElement("div");
  copy.append(
    createPersonalOsTextElement("div", "pos-label", posUiText("pos.labelChatReviewPrompt", "Chat Review Prompt")),
    createPersonalOsTextElement("div", cls, `${mode} - ${meta.length}/${meta.limit} ${posUiText("pos.unitChars", "chars")}`)
  );
  const meter = document.createElement("div");
  meter.className = "pos-prompt-meter";
  const fill = document.createElement("span");
  fill.className = posMeterWidthClass(meta.percent);
  meter.appendChild(fill);
  wrapper.append(copy, meter);
  return wrapper;
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
