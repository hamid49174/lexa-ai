/* High-level chat message formatting helpers loaded before chat.js. Keep this file free of module syntax. */

function appendMarkdownSegment(parent, segment) {
  const lines = String(segment || "").replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      appendLineBreak(parent);
      i += 1;
      continue;
    }

    if (/^###\s+/.test(line)) {
      const h4 = document.createElement("h4");
      h4.className = "chat-h4";
      appendInlineMarkdown(h4, line.replace(/^###\s+/, ""));
      parent.appendChild(h4);
      i += 1;
      continue;
    }
    if (/^##\s+/.test(line)) {
      const h3 = document.createElement("h3");
      h3.className = "chat-h3";
      appendInlineMarkdown(h3, line.replace(/^##\s+/, ""));
      parent.appendChild(h3);
      i += 1;
      continue;
    }
    if (/^-{3,}\s*$/.test(line)) {
      const hr = document.createElement("hr");
      hr.className = "chat-hr";
      parent.appendChild(hr);
      i += 1;
      continue;
    }
    if (/^>\s+/.test(line)) {
      const quote = document.createElement("blockquote");
      quote.className = "chat-quote";
      let first = true;
      while (i < lines.length && /^>\s+/.test(lines[i])) {
        if (!first) appendLineBreak(quote);
        appendInlineMarkdown(quote, lines[i].replace(/^>\s+/, ""));
        first = false;
        i += 1;
      }
      parent.appendChild(quote);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const list = document.createElement("ol");
      list.className = "chat-ol";
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        const item = document.createElement("li");
        appendInlineMarkdown(item, lines[i].replace(/^\d+\.\s+/, ""));
        list.appendChild(item);
        i += 1;
      }
      parent.appendChild(list);
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const list = document.createElement("ul");
      list.className = "chat-ul";
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        const item = document.createElement("li");
        appendInlineMarkdown(item, lines[i].replace(/^[-*]\s+/, ""));
        list.appendChild(item);
        i += 1;
      }
      parent.appendChild(list);
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && isChatTableSeparator(lines[i + 1])) {
      const tableRows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        tableRows.push(lines[i]);
        i += 1;
      }
      appendChatTable(parent, tableRows);
      continue;
    }

    let first = true;
    while (i < lines.length && lines[i].trim() && !isMarkdownBlockStart(lines[i])) {
      if (!first) appendLineBreak(parent);
      appendInlineMarkdown(parent, lines[i]);
      first = false;
      i += 1;
    }
  }
}

function appendFormattedMessage(parent, text) {
  const source = stripModelFunctionTags(text);
  if (!source) return;
  const codePattern = /```([A-Za-z0-9_.+-]*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;
  while ((match = codePattern.exec(source)) !== null) {
    appendMarkdownSegment(parent, source.slice(lastIndex, match.index));
    appendCodeBlock(parent, match[1], match[2]);
    lastIndex = codePattern.lastIndex;
  }
  appendMarkdownSegment(parent, source.slice(lastIndex));
}

function formatMessage(text) {
  const wrapper = document.createElement("div");
  appendFormattedMessage(wrapper, String(text || ""));
  return wrapper.innerHTML;
}
