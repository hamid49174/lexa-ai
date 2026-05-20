/* Low-level chat markdown helpers loaded before chat.js. Keep this file free of module syntax. */

function appendInlineMarkdown(parent, source) {
  const text = String(source || "");
  if (!text) return;

  const tokenPattern = /(`([^`\n]+)`|!\[([^\]\n]*)\]\(([^)\s]+(?:\s+[^)]*)?)\)|\[([^\]\n]+)\]\(([^)\s]+(?:\s+[^)]*)?)\)|\*\*([^*\n]+)\*\*|~~([^~\n]+)~~|\*([^*\n]+)\*)/g;
  let lastIndex = 0;
  let match;

  while ((match = tokenPattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parent.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
    }

    const raw = match[0];
    if (raw.startsWith("`")) {
      const code = document.createElement("code");
      code.className = "inline-code";
      code.textContent = match[2] || "";
      parent.appendChild(code);
    } else if (raw.startsWith("![")) {
      const safeUrl = normalizeChatUrl(match[4], { image: true });
      if (safeUrl) {
        const img = document.createElement("img");
        img.className = "chat-img";
        img.src = safeUrl;
        img.alt = match[3] || "";
        parent.appendChild(img);
      } else if (match[3]) {
        parent.appendChild(document.createTextNode(match[3]));
      }
    } else if (raw.startsWith("[")) {
      const safeUrl = normalizeChatUrl(match[6]);
      if (safeUrl) {
        const link = document.createElement("a");
        link.className = "chat-link";
        link.href = safeUrl;
        link.rel = "noopener noreferrer";
        if (!safeUrl.toLowerCase().startsWith("mailto:")) link.target = "_blank";
        link.textContent = match[5] || safeUrl;
        parent.appendChild(link);
      } else {
        parent.appendChild(document.createTextNode(match[5] || raw));
      }
    } else if (raw.startsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = match[7] || "";
      parent.appendChild(strong);
    } else if (raw.startsWith("~~")) {
      const strike = document.createElement("s");
      strike.textContent = match[8] || "";
      parent.appendChild(strike);
    } else if (raw.startsWith("*")) {
      const em = document.createElement("em");
      em.textContent = match[9] || "";
      parent.appendChild(em);
    } else {
      parent.appendChild(document.createTextNode(raw));
    }
    lastIndex = tokenPattern.lastIndex;
  }

  if (lastIndex < text.length) {
    parent.appendChild(document.createTextNode(text.slice(lastIndex)));
  }
}

function appendLineBreak(parent) {
  parent.appendChild(document.createElement("br"));
}

function chatTableCells(row) {
  return String(row || "").trim().replace(/^\|/, "").replace(/\|$/, "").split("|");
}

function isChatTableSeparator(row) {
  return /^\s*\|?[\s:-]+\|[\s|:-]*\s*$/.test(String(row || ""));
}

function appendChatTable(parent, rows) {
  const tableWrap = document.createElement("div");
  tableWrap.className = "table-wrap";
  const table = document.createElement("table");
  table.className = "chat-table";
  const hasHeader = rows.length > 1 && isChatTableSeparator(rows[1]);
  const dataRows = hasHeader ? [rows[0], ...rows.slice(2)] : rows;

  dataRows.forEach((row, index) => {
    const tr = document.createElement("tr");
    const tag = hasHeader && index === 0 ? "th" : "td";
    chatTableCells(row).forEach((cell) => {
      const el = document.createElement(tag);
      appendInlineMarkdown(el, cell.trim());
      tr.appendChild(el);
    });
    table.appendChild(tr);
  });

  tableWrap.appendChild(table);
  parent.appendChild(tableWrap);
}

function appendCodeBlock(parent, lang, codeText) {
  const wrap = document.createElement("div");
  wrap.className = "code-block-wrap";
  const header = document.createElement("div");
  header.className = "code-block-header";
  const safeLang = String(lang || "").replace(/[^\w.+-]/g, "").slice(0, 32);
  if (safeLang) {
    const label = document.createElement("span");
    label.className = "code-lang";
    label.textContent = safeLang;
    header.appendChild(label);
  }
  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "code-copy-btn";
  copyButton.dataset.action = "copy-code";
  const copyLabel = typeof t === "function" ? t("chat.copyTooltip") : "Copy code";
  copyButton.title = copyLabel;
  copyButton.setAttribute("aria-label", copyLabel);
  copyButton.dataset.icon = "\u2398";
  header.appendChild(copyButton);

  const pre = document.createElement("pre");
  pre.className = "code-block";
  const code = document.createElement("code");
  code.textContent = String(codeText || "").trim();
  pre.appendChild(code);
  wrap.appendChild(header);
  wrap.appendChild(pre);
  parent.appendChild(wrap);
}

function isMarkdownBlockStart(line) {
  return /^(#{2,3}\s+|>\s+|-{3,}\s*$|\d+\.\s+|[-*]\s+)/.test(line)
    || (/^\s*\|.*\|\s*$/.test(line));
}
