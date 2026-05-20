/* Pure chat download helpers loaded before chat.js. Keep this file free of module syntax. */

function messageExportMarkdownFromText(sourceText, options) {
  const source = String(sourceText || "").trim();
  if (!source) return "";
  const exportOptions = options || {};
  const title = String(exportOptions.title || "Lexa Answer").trim() || "Lexa Answer";
  const exportedAt = String(exportOptions.exportedAt || new Date().toISOString());
  return `# ${title}\n\n- Exported: ${exportedAt}\n- Source: Lexa chat\n\n---\n\n${source}\n`;
}

function messageExportFilename(date = new Date()) {
  const stamp = date.toISOString().replace(/[:.]/g, "-");
  return `lexa-answer-${stamp}.md`;
}
