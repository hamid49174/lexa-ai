/* ════════════════════════════════════════════════
   LEXA AI — Developer Tools Module
   Git integration, Docker controls, HTTP request tester,
   Server monitor, Log analysis, Dev utilities
   (JSON, Regex, Base64, Hash, UUID, Timestamp),
   File tools (Archive, Backup, Image conversion)
   Extracted from tools.js
   ════════════════════════════════════════════════ */

// ── EXTENDED FILE TOOLS (Phase 20) ──────────────

async function archiveCreate() {
  const vals = await showInputModal(t("devtools.archiveCreateTitle"), [
    { id: "source", label: t("devtools.archiveCreateLabel"), type: "text", placeholder: "C:\\Users\\admin\\Dokumente", required: true }
  ], t("devtools.archiveCreateBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("devtools.archiveCreateMsg", {source: vals.source}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("archive_create", { source: vals.source }, true);
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("devtools.archiveCreated") : t("devtools.archiveFailed"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function archiveExtract() {
  const vals = await showInputModal(t("devtools.archiveExtractTitle"), [
    { id: "path", label: t("devtools.archiveExtractLabel"), type: "text", placeholder: "C:\\Users\\admin\\archiv.zip", required: true }
  ], t("devtools.archiveExtractBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("devtools.archiveExtractMsg", {path: vals.path}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("archive_extract", { archive_path: vals.path }, true);
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("devtools.extracted") : t("devtools.extractFailed"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function backupCreate() {
  const vals = await showInputModal(t("devtools.backupCreateTitle"), [
    { id: "source", label: t("devtools.backupCreateLabel"), type: "text", placeholder: "C:\\Users\\admin\\Dokumente", required: true }
  ], t("devtools.backupCreateBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("devtools.backupCreateMsg", {source: vals.source}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("backup_create", { source: vals.source }, true);
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("devtools.backupCreated") : t("devtools.backupFailed"), res.success ? "success" : "error");
    sendNotification("Lexa AI", res.success ? t("devtools.backupCreatedNotif") : t("devtools.backupFailedNotif"));
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function backupListView() {
  switchView("chat");
  addMessage(t("devtools.backupListMsg"), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("backup_list");
    hideTyping();
    if (res.success && Array.isArray(res.data) && res.data.length > 0) {
      const list = res.data.map(b =>
        `${b.exists ? "\u2713" : "\u2717"} ${b.path.split("\\").pop()} \u2014 ${b.size_mb} MB, ${b.files} ${t("devtools.backupListFiles")} (${b.created.split("T")[0]})`
      ).join("\n");
      addMessage(t("devtools.backupListTitle") + "\n" + list, "system");
    } else {
      addMessage(t("empty.noBackups"), "system");
    }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function imageConvert() {
  const vals = await showInputModal(t("devtools.imageConvertTitle"), [
    { id: "source", label: t("devtools.imageConvertLabel"), type: "text", placeholder: "C:\\Users\\admin\\foto.jpg", required: true },
    { id: "format", label: t("devtools.imageConvertFormatLabel"), type: "select", default: "png",
      options: [{ value: "png", label: "PNG" }, { value: "jpg", label: "JPG" }, { value: "webp", label: "WEBP" }, { value: "bmp", label: "BMP" }, { value: "gif", label: "GIF" }] }
  ], t("devtools.imageConvertBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("devtools.imageConvertMsg", {source: vals.source, format: vals.format}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("image_convert", { source: vals.source, output_format: vals.format });
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("devtools.imageConverted") : t("common.error"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function imageResize() {
  const vals = await showInputModal(t("devtools.imageResizeTitle"), [
    { id: "source", label: t("devtools.imageResizeLabel"), type: "text", placeholder: "C:\\Users\\admin\\foto.jpg", required: true },
    { id: "width", label: t("devtools.imageResizeWidthLabel"), type: "number", default: 800, min: 1, max: 10000, required: true }
  ], t("devtools.imageResizeBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("devtools.imageResizeMsg", {source: vals.source, width: vals.width}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("image_resize", { source: vals.source, width: Number(vals.width) });
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("devtools.imageResized") : t("common.error"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function imageBatchResize() {
  const vals = await showInputModal(t("devtools.batchResizeTitle"), [
    { id: "folder", label: t("devtools.batchResizeFolderLabel"), type: "text", placeholder: "C:\\Users\\admin\\Fotos", required: true },
    { id: "width", label: t("devtools.batchResizeWidthLabel"), type: "number", default: 800, min: 1, max: 10000, required: true }
  ], t("devtools.batchResizeBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("devtools.batchResizeMsg", {folder: vals.folder, width: vals.width}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("image_batch_resize", { folder: vals.folder, width: Number(vals.width) }, true);
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("devtools.batchResizeDone") : t("common.error"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

// ── DEVELOPER TOOLS (Phase 22) ──────────────────

// ── Git (with persistent repo path) ──

const GIT_REPO_KEY = "lexa-git-repo";
function getLastGitRepo() {
  return lexaStorageGet(GIT_REPO_KEY, "C:\\Users\\admin\\OneDrive\\Desktop\\lexa\\lexa-ai");
}
function setLastGitRepo(path) {
  if (path) lexaStorageSet(GIT_REPO_KEY, path);
}

async function gitStatusAction() {
  const vals = await showInputModal(t("devtools.gitStatusTitle"), [
    { id: "repo", label: t("devtools.gitRepoLabel"), type: "text", default: getLastGitRepo(), required: true }
  ], t("devtools.gitStatusBtn"));
  if (!vals) return;
  setLastGitRepo(vals.repo);
  switchView("chat");
  addMessage(t("devtools.gitStatusMsg", {repo: vals.repo}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("git_status", { repo_path: vals.repo });
    hideTyping();
    if (res.success) {
      const d = res.data;
      const status = d.clean ? "\u2713 Clean" :
        `${d.modified?.length || 0} modified, ${d.staged?.length || 0} staged, ${d.untracked?.length || 0} untracked`;
      addMessage(`Branch: **${d.branch}**\nStatus: ${status}\nTotal: ${d.total_changes} ${t("devtools.gitChanges")}`, "system");
    } else { addMessage(t("common.error") + ": " + res.error, "system"); }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function gitLogAction() {
  const vals = await showInputModal(t("devtools.gitLogTitle"), [
    { id: "repo", label: t("devtools.gitRepoLabel"), type: "text", default: getLastGitRepo(), required: true }
  ], t("devtools.gitLogBtn"));
  if (!vals) return;
  setLastGitRepo(vals.repo);
  switchView("chat");
  addMessage(t("devtools.gitLogMsg", {repo: vals.repo}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("git_log", { repo_path: vals.repo, count: 10 });
    hideTyping();
    if (res.success && Array.isArray(res.data)) {
      const list = res.data.map(c =>
        `\`${c.short_hash}\` ${c.message} \u2014 *${c.author}* (${c.date})`
      ).join("\n");
      addMessage(`${t("devtools.gitLogCommits", {count: res.data.length})}\n${list}`, "system");
    } else { addMessage(t("common.error") + ": " + (res.error || ""), "system"); }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function gitDiffAction() {
  const vals = await showInputModal(t("devtools.gitDiffTitle"), [
    { id: "repo", label: t("devtools.gitRepoLabel"), type: "text", default: getLastGitRepo(), required: true }
  ], t("devtools.gitDiffBtn"));
  if (!vals) return;
  setLastGitRepo(vals.repo);
  switchView("chat");
  addMessage(t("devtools.gitDiffMsg", {repo: vals.repo}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("git_diff", { repo_path: vals.repo });
    hideTyping();
    addMessage(res.success ? "```\n" + res.data + "\n```" : t("common.error") + ": " + res.error, "system");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function gitBranchAction() {
  const vals = await showInputModal(t("devtools.gitBranchTitle"), [
    { id: "repo", label: t("devtools.gitRepoLabel"), type: "text", default: getLastGitRepo(), required: true }
  ], t("devtools.gitBranchBtn"));
  if (!vals) return;
  setLastGitRepo(vals.repo);
  switchView("chat");
  addMessage(t("devtools.gitBranchMsg", {repo: vals.repo}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("git_branch_list", { repo_path: vals.repo });
    hideTyping();
    if (res.success && res.data.branches) {
      const list = res.data.branches.map(b =>
        `${b.current ? "\u27A1 " : "  "} ${b.name} (${b.hash}) ${b.message}`
      ).join("\n");
      addMessage(`${t("devtools.gitActiveBranch")} **${res.data.current}**\n${list}`, "system");
    } else { addMessage(t("common.error") + ": " + (res.error || ""), "system"); }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function gitCommitAction() {
  const vals = await showInputModal(t("devtools.gitCommitTitle"), [
    { id: "repo", label: t("devtools.gitRepoLabel"), type: "text", default: getLastGitRepo(), required: true },
    { id: "message", label: t("devtools.gitCommitMsgLabel"), type: "text", placeholder: "feat: beschreibe deine \u00c4nderungen", required: true }
  ], t("devtools.gitCommitBtn"));
  if (!vals) return;
  setLastGitRepo(vals.repo);
  switchView("chat");
  addMessage(t("devtools.gitCommitMsg", {message: vals.message}), "user");
  showTyping();
  try {
    await window.lexa.execute("git_add", { repo_path: vals.repo, files: "." }, true);
    const res = await window.lexa.execute("git_commit", { repo_path: vals.repo, message: vals.message }, true);
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("devtools.commitCreated") : t("devtools.commitFailed"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function gitPullPushAction(action) {
  const vals = await showInputModal(action === "pull" ? t("devtools.gitPullTitle") : t("devtools.gitPushTitle"), [
    { id: "repo", label: t("devtools.gitRepoLabel"), type: "text", default: getLastGitRepo(), required: true }
  ], action === "pull" ? t("devtools.gitPullBtn") : t("devtools.gitPushBtn"));
  if (!vals) return;
  setLastGitRepo(vals.repo);
  switchView("chat");
  addMessage(`Git ${action}: ${vals.repo}`, "user");
  showTyping();
  try {
    const cmd = action === "pull" ? "git_pull" : "git_push";
    const res = await window.lexa.execute(cmd, { repo_path: vals.repo }, true);
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? t("devtools.gitSuccess", {action}) : t("common.error"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

// ── Docker ──

async function dockerLogsAction() {
  const vals = await showInputModal(t("devtools.dockerLogsTitle"), [
    { id: "container", label: t("devtools.dockerContainerLabel"), type: "text", placeholder: "my-container", required: true }
  ], t("devtools.dockerLogsBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("devtools.dockerLogsMsg", {container: vals.container}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("docker_logs", { container: vals.container, tail: 50 });
    hideTyping();
    addMessage(res.success ? "```\n" + res.data + "\n```" : t("common.error") + ": " + res.error, "system");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function dockerStartStopAction(action) {
  const label = action === "start" ? t("devtools.dockerStartLabel") : t("devtools.dockerStopLabel");
  const vals = await showInputModal(t("devtools.containerActionTitle", {action: label}), [
    { id: "container", label: t("devtools.dockerContainerLabel"), type: "text", placeholder: "my-container", required: true }
  ], label);
  if (!vals) return;
  switchView("chat");
  addMessage(`Docker ${action}: ${vals.container}`, "user");
  showTyping();
  try {
    const cmd = action === "start" ? "docker_start" : "docker_stop";
    const res = await window.lexa.execute(cmd, { container: vals.container }, true);
    hideTyping();
    addMessage(res.success ? res.data : t("common.error") + ": " + res.error, "system");
    showToast(res.success ? (action === "start" ? t("devtools.containerStarted") : t("devtools.containerStopped")) : t("common.error"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

// ── API & Server ──

async function httpRequestAction() {
  const vals = await showInputModal(t("devtools.httpRequestTitle"), [
    { id: "url", label: t("devtools.httpUrlLabel"), type: "text", placeholder: "https://api.github.com", required: true },
    { id: "method", label: t("devtools.httpMethodLabel"), type: "select", default: "GET",
      options: [{ value: "GET", label: "GET" }, { value: "POST", label: "POST" }, { value: "PUT", label: "PUT" }, { value: "DELETE", label: "DELETE" }] }
  ], t("devtools.httpSendBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(`HTTP ${vals.method}: ${vals.url}`, "user");
  showTyping();
  try {
    const res = await window.lexa.execute("http_request", { url: vals.url, method: vals.method });
    hideTyping();
    if (res.success) {
      const d = res.data;
      const info = d.error ? t("devtools.httpErrorStatus", {status: d.status_code, reason: d.reason}) :
        `Status: **${d.status_code} ${d.reason}** (${d.elapsed_sec}s)\n${t("devtools.httpBodyInfo", {length: d.body_length})}`;
      addMessage(`${info}\n\`\`\`\n${d.body?.substring(0, 1500) || t("devtools.httpEmpty")}\n\`\`\``, "system");
    } else { addMessage(t("common.error") + ": " + res.error, "system"); }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function serverCheckAction() {
  const vals = await showInputModal(t("devtools.serverCheckTitle"), [
    { id: "host", label: t("devtools.serverHostLabel"), type: "text", placeholder: "127.0.0.1", default: "127.0.0.1", required: true },
    { id: "port", label: t("devtools.serverPortLabel"), type: "number", default: 8000, min: 1, max: 65535, required: true }
  ], t("devtools.serverCheckBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("devtools.serverCheckMsg", {host: vals.host, port: vals.port}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("server_check", { host: vals.host, port: Number(vals.port) });
    hideTyping();
    if (res.success) {
      const d = res.data;
      addMessage(`${d.up ? "\u{1F7E2}" : "\u{1F534}"} ${d.name}: ${d.status}${d.response_ms ? " (" + d.response_ms + "ms)" : ""}`, "system");
    } else { addMessage(t("common.error") + ": " + res.error, "system"); }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function logAnalyzeAction() {
  const vals = await showInputModal(t("devtools.logAnalyzeTitle"), [
    { id: "path", label: t("devtools.logPathLabel"), type: "text", placeholder: "C:\\logs\\app.log", required: true },
    { id: "level", label: t("devtools.logLevelLabel"), type: "select", default: "",
      options: [{ value: "", label: t("devtools.logLevelAll") }, { value: "ERROR", label: "ERROR" }, { value: "WARN", label: "WARN" }, { value: "INFO", label: "INFO" }] }
  ], t("devtools.logAnalyzeBtn"));
  if (!vals) return;
  const path = vals.path;
  const level = vals.level;
  switchView("chat");
  addMessage(t("devtools.logAnalyzeMsg", {path: path, level: level ? "(" + level + ")" : ""}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("log_analyze", { path, lines: 100, level });
    hideTyping();
    if (res.success && res.data) {
      const d = res.data;
      const levels = d.level_counts ? `ERROR: ${d.level_counts.ERROR}, WARN: ${d.level_counts.WARN}, INFO: ${d.level_counts.INFO}` : "";
      addMessage(`${t("devtools.logResult", {file: d.file, lines: d.total_lines})}\n${levels}\n\`\`\`\n${d.content?.substring(0, 2000) || t("devtools.httpEmpty")}\n\`\`\``, "system");
    } else { addMessage(t("common.error") + ": " + (res.error || ""), "system"); }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

// ── Dev Utilities ──

async function jsonFormatAction() {
  const vals = await showInputModal(t("devtools.jsonFormatTitle"), [
    { id: "text", label: t("devtools.jsonInputLabel"), type: "textarea", placeholder: '{"key": "value"}', required: true, rows: 6 }
  ], t("devtools.jsonFormatBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("devtools.jsonFormatMsg"), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("json_format", { text: vals.text });
    hideTyping();
    addMessage(res.success ? "```json\n" + res.data + "\n```" : t("common.error") + ": " + res.error, "system");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function regexTestAction() {
  const vals = await showInputModal(t("devtools.regexTestTitle"), [
    { id: "pattern", label: t("devtools.regexPatternLabel"), type: "text", placeholder: "\\d+\\.\\d+", required: true },
    { id: "text", label: t("devtools.regexTextLabel"), type: "textarea", placeholder: "Text zum Testen...", required: true, rows: 4 }
  ], t("devtools.regexTestBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(t("devtools.regexTestMsg", {pattern: vals.pattern}), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("regex_test", { pattern: vals.pattern, text: vals.text });
    hideTyping();
    if (res.success && res.data) {
      const d = res.data;
      const matches = d.matches?.map(m => `"${m.match}" (${m.start}-${m.end})`).join(", ") || t("devtools.regexNoMatch");
      addMessage(`Regex: /${d.pattern}/\n${t("devtools.regexMatches")} **${d.matches_count}**\n${matches}`, "system");
    } else { addMessage(t("common.error") + ": " + (res.error || t("common.noResults")), "system"); }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function base64Action() {
  const vals = await showInputModal(t("devtools.base64Title"), [
    { id: "mode", label: t("devtools.base64ModeLabel"), type: "select", default: "encode",
      options: [{ value: "encode", label: t("devtools.base64Encode") }, { value: "decode", label: t("devtools.base64Decode") }] },
    { id: "text", label: t("devtools.base64InputLabel"), type: "textarea", placeholder: "Eingabe...", required: true, rows: 4 }
  ], t("devtools.base64Btn"));
  if (!vals) return;
  switchView("chat");
  addMessage(`Base64 ${vals.mode}: ${vals.text.substring(0, 50)}...`, "user");
  showTyping();
  try {
    const cmd = vals.mode === "decode" ? "base64_decode" : "base64_encode";
    const res = await window.lexa.execute(cmd, { text: vals.text });
    hideTyping();
    addMessage(res.success ? "`" + res.data + "`" : t("common.error") + ": " + res.error, "system");
    if (res.success) navigator.clipboard.writeText(res.data).catch(() => { });
    showToast(res.success ? t("devtools.resultCopied") : t("common.error"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function hashAction() {
  const vals = await showInputModal(t("devtools.hashTitle"), [
    { id: "text", label: t("devtools.hashInputLabel"), type: "textarea", placeholder: "Geheimer Text...", required: true, rows: 3 },
    { id: "algo", label: t("devtools.hashAlgoLabel"), type: "select", default: "sha256",
      options: [{ value: "md5", label: "MD5" }, { value: "sha1", label: "SHA-1" }, { value: "sha256", label: "SHA-256" }, { value: "sha512", label: "SHA-512" }] }
  ], t("devtools.hashBtn"));
  if (!vals) return;
  switchView("chat");
  addMessage(`Hash (${vals.algo}): ${vals.text.substring(0, 30)}...`, "user");
  showTyping();
  try {
    const res = await window.lexa.execute("hash_text", { text: vals.text, algorithm: vals.algo });
    hideTyping();
    if (res.success && res.data) {
      addMessage(`${res.data.algorithm}: \`${res.data.hash}\``, "system");
      navigator.clipboard.writeText(res.data.hash).catch(() => { });
      showToast(t("toast.hashCopied"), "success");
    } else { addMessage(t("common.error") + ": " + res.error, "system"); }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function uuidAction() {
  switchView("chat");
  addMessage(t("devtools.uuidMsg"), "user");
  showTyping();
  try {
    const res = await window.lexa.execute("generate_uuid");
    hideTyping();
    addMessage(res.success ? "`" + res.data + "`" : t("common.error") + ": " + res.error, "system");
    if (res.success) navigator.clipboard.writeText(res.data).catch(() => { });
    showToast(res.success ? t("devtools.uuidCopied") : t("common.error"), res.success ? "success" : "error");
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}

async function timestampAction() {
  const vals = await showInputModal(t("devtools.timestampTitle"), [
    { id: "ts", label: t("devtools.timestampLabel"), type: "text", placeholder: "1700000000 oder leer lassen" }
  ], t("devtools.timestampBtn"));
  if (!vals) return;
  const ts = vals.ts || "";
  switchView("chat");
  addMessage(`Timestamp: ${ts || t("devtools.timestampNow")}`, "user");
  showTyping();
  try {
    const res = await window.lexa.execute("timestamp_convert", { timestamp: ts });
    hideTyping();
    if (res.success && res.data) {
      const d = res.data;
      addMessage(`Unix: \`${d.unix}\`\nISO: \`${d.iso}\`\nFormatiert: **${d.formatted}**`, "system");
    } else { addMessage(t("common.error") + ": " + (res.error || ""), "system"); }
  } catch (e) { hideTyping(); addMessage(t("common.error") + ": " + e.message, "system"); }
}
