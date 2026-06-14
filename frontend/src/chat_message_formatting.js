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
      const field = appendChatFieldLine(parent, lines[i]);
      if (!field) {
        if (!first) appendLineBreak(parent);
        appendInlineMarkdown(parent, lines[i]);
      }
      first = false;
      i += 1;
    }
  }
}

function chatFieldLineParts(line) {
  const raw = String(line || "").trim();
  if (!raw || raw.includes("://")) return null;
  const match = raw.match(/^(?:\*\*|\*)?([^*:\n][^:\n]{1,56}?):(?:\*\*|\*)?\s+(.+)$/);
  if (!match) return null;
  const label = match[1].trim();
  const value = match[2].trim();
  if (!label || !value || label.length > 56) return null;
  if (/[.!?]$/.test(label) || /\s{2,}/.test(label)) return null;
  return { label, value };
}

function appendChatFieldLine(parent, line) {
  const parts = chatFieldLineParts(line);
  if (!parts) return false;
  const row = document.createElement("div");
  row.className = "chat-field";
  const label = document.createElement("strong");
  label.className = "chat-field-label";
  label.textContent = `${parts.label}:`;
  const value = document.createElement("span");
  value.className = "chat-field-value";
  appendInlineMarkdown(value, parts.value);
  row.appendChild(label);
  row.appendChild(value);
  parent.appendChild(row);
  return true;
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

// SECURITY: formatMessage() returns a serialized HTML string and exists only as a
// test/serialization helper (see tests/test_chat_rendering.js). It is NOT the runtime
// rendering path. Never do `element.innerHTML = formatMessage(text)` — that re-parses the
// already-sanitized DOM tree and reopens an injection surface. For live rendering always use
// renderFormattedMessage()/appendFormattedMessage(), which build DOM nodes directly.
function formatMessage(text) {
  const wrapper = document.createElement("div");
  appendFormattedMessage(wrapper, String(text || ""));
  return wrapper.innerHTML;
}
