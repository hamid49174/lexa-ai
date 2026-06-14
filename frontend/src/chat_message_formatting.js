/* High-level chat message formatting helpers loaded before chat.js. Keep this file free of module syntax. */

function _listItemMatch(line) {
  // Erkennt ein Listen-Item (auch eingerückt): {indent, ordered, content} oder null.
  const m = /^(\s*)([-*]|\d+[.)])\s+(.*)$/.exec(String(line || ""));
  if (!m) return null;
  return {
    indent: m[1].replace(/\t/g, "  ").length,
    ordered: /\d/.test(m[2]),
    content: m[3],
  };
}

// Baut eine (ggf. verschachtelte) Liste ab Zeile `start`, liefert den neuen Index.
function appendNestedList(parent, lines, start) {
  let i = start;
  const first = _listItemMatch(lines[i]);
  const rootType = first.ordered ? "ol" : "ul";
  const root = document.createElement(rootType);
  root.className = rootType === "ol" ? "chat-ol" : "chat-ul";
  const stack = [{ indent: first.indent, listEl: root, lastItem: null }];

  while (i < lines.length) {
    const m = _listItemMatch(lines[i]);
    if (!m) break;
    while (stack.length > 1 && m.indent < stack[stack.length - 1].indent) stack.pop();
    let top = stack[stack.length - 1];
    if (m.indent > top.indent) {
      const nestedType = m.ordered ? "ol" : "ul";
      const nested = document.createElement(nestedType);
      nested.className = nestedType === "ol" ? "chat-ol" : "chat-ul";
      (top.lastItem || top.listEl).appendChild(nested);
      stack.push({ indent: m.indent, listEl: nested, lastItem: null });
      top = stack[stack.length - 1];
    }
    const item = document.createElement("li");
    appendInlineMarkdown(item, m.content);
    top.listEl.appendChild(item);
    top.lastItem = item;
    i += 1;
  }
  parent.appendChild(root);
  return i;
}

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

    const headingMatch = /^(#{1,6})\s+(.*)$/.exec(line);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const tag = level <= 1 ? "h2" : level === 2 ? "h3" : "h4";
      const heading = document.createElement(tag);
      heading.className = level <= 1 ? "chat-h2" : level === 2 ? "chat-h3" : "chat-h4";
      appendInlineMarkdown(heading, headingMatch[2]);
      parent.appendChild(heading);
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
    if (_listItemMatch(line)) {
      i = appendNestedList(parent, lines, i);
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
