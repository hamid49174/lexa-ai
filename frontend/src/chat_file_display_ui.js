/* File upload display helpers loaded before chat.js. Keep this file free of module syntax. */

function fileUploadSizeLabel(file) {
  const size = Number(file?.size || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1048576) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1048576).toFixed(1)} MB`;
}

function fileUploadExtension(file) {
  const name = String(file?.name || "");
  return name.includes(".") ? name.split(".").pop().toUpperCase() : "FILE";
}

function fileInfoBadgeText(fileInfo) {
  const parts = [
    String(fileInfo?.type || "file").toUpperCase(),
    `${fileInfo?.size_kb || 0} KB`,
  ];
  if (fileInfo?.line_count) parts.push(t("chat.fileLines", {count: fileInfo.line_count}));
  return parts.join(" \u00b7 ");
}
