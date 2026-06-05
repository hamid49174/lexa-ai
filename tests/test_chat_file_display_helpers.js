/**
 * Direct checks for file upload display helpers.
 * Run with: node tests/test_chat_file_display_helpers.js
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.join(__dirname, "..");
const helperSrc = fs.readFileSync(path.join(root, "frontend", "src", "chat_file_display_ui.js"), "utf8");

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

const context = {
  Number,
  String,
  t: (key, params = {}) => {
    if (key === "chat.fileLines") return `${params.count} lines`;
    if (key === "chat.fileVisionPendingBadge") return "Vision ready";
    if (key === "chat.fileAnalyzedBadge") return "Analyzed";
    if (key === "chat.fileAttachmentFallback") return "attachment";
    if (key === "chat.fileVisionProviderRequired") return `Vision provider needed for ${params.filename}`;
    return key;
  },
};
vm.createContext(context);
vm.runInContext(helperSrc, context, { filename: "chat_file_display_ui.js" });

console.log("\nchat file display helper boundaries:");

assert("file size labels preserve byte values", context.fileUploadSizeLabel({ size: 512 }) === "512 B");
assert("file size labels format kilobytes", context.fileUploadSizeLabel({ size: 1536 }) === "1.5 KB");
assert("file size labels format megabytes", context.fileUploadSizeLabel({ size: 2 * 1048576 }) === "2.0 MB");
assert("missing file size falls back safely", context.fileUploadSizeLabel(null) === "0 B");
assert("file extension helper uppercases suffix", context.fileUploadExtension({ name: "report.final.md" }) === "MD");
assert("file extension helper falls back when no suffix exists", context.fileUploadExtension({ name: "README" }) === "FILE");
assert("file extension helper preserves unsafe suffix as text", context.fileUploadExtension({ name: "bad.<script>" }) === "<SCRIPT>");
assert("image preview helper allows raster mime types", context.fileUploadCanPreview({ name: "screen.bin", type: "image/png" }) === true);
assert("image preview helper allows raster image extensions", context.fileUploadCanPreview({ name: "photo.jpg", type: "" }) === true);
assert("image preview helper blocks svg previews", context.fileUploadCanPreview({ name: "icon.svg", type: "image/svg+xml" }) === false);
assert("image preview helper rejects normal documents", context.fileUploadCanPreview({ name: "report.md", type: "text/markdown" }) === false);
assert("file info badge text includes type and size", context.fileInfoBadgeText({ type: "md", size_kb: 12 }) === "MD \u00b7 12 KB");
assert("file info badge prefers backend extension over semantic type", context.fileInfoBadgeText({ type: "image", extension: ".png", size_kb: 258.8 }) === "PNG \u00b7 258.8 KB");
assert("file info badge text includes line count when present", context.fileInfoBadgeText({ type: "txt", size_kb: 4, line_count: 7 }) === "TXT \u00b7 4 KB \u00b7 7 lines");
assert("file info badge text marks pending vision provider state", context.fileInfoBadgeText({ type: "png", size_kb: 20, analysis_status: "vision_provider_required" }) === "PNG \u00b7 20 KB \u00b7 Vision ready");
assert("file info badge text marks analyzed state", context.fileInfoBadgeText({ type: "txt", size_kb: 2, analysis_status: "text_analyzed" }) === "TXT \u00b7 2 KB \u00b7 Analyzed");
assert("file info badge text handles missing payload", context.fileInfoBadgeText(null) === "FILE \u00b7 0 KB");
assert("file info badge normalizes invalid numeric metadata", context.fileInfoBadgeText({ type: "txt", size_kb: "NaN", line_count: Infinity }) === "TXT \u00b7 0 KB");
assert("unsafe file info type remains plain text for renderer insertion", context.fileInfoBadgeText({ type: "<img src=x onerror=alert(1)>", size_kb: 1 }).includes("<IMG SRC=X ONERROR=ALERT(1)>"));
assert("vision provider fallback reply names the pending image", context.fileUploadDisplayReply({ analysis_status: "vision_provider_required", file_info: { filename: "screen.png" } }) === "Vision provider needed for screen.png");
assert("helper script remains classic", !/(^|\n)\s*(import|export)\b/.test(helperSrc));

console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed\n`);
if (failed > 0) process.exit(1);
