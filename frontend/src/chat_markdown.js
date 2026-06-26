/* Low-level chat markdown helpers loaded before chat.js. Keep this file free of module syntax. */

// Waehrend des Token-Streams wird pro Tick neu gerendert. hljs.highlightElement ist teuer
// und wurde so jeder Codeblock dutzendfach neu hervorgehoben (O(n^2)). Im Streaming-Modus
// ueberspringen wir das Highlighting; der finale Render (Stream-Ende) highlightet einmal.
let _lexaStreamingRender = false;
function setStreamingRenderMode(on) { _lexaStreamingRender = !!on; }

function splitChatLinkTarget(rawTarget) {
  // Trennt das CommonMark-Linkziel von einem optionalen Titel:
  // (url "titel") / (url 'titel') / (url (titel)). Ohne diese Trennung
  // wuerde der Titel mit in die URL geraten und new URL() kaputt machen.
  const value = String(rawTarget || "").trim();
  if (!value) return { url: "", title: "" };
  const match = /^(\S+)\s+(.*)$/.exec(value);
  if (!match) return { url: value, title: "" };
  const title = match[2].trim().replace(/^["'(]|[")']$/g, "").trim();
  return { url: match[1], title };
}

// Linkifiziert nackte URLs (https://… ohne Markdown-Klammern) im Klartext — GFM-Verhalten
// wie bei ChatGPT/Claude. normalizeChatUrl() haelt es XSS-sicher; nachgestellte Satzzeichen
// (".,;:!?)") bleiben Text, nicht Teil des Links.
function appendTextWithBareUrls(parent, textChunk) {
  const str = String(textChunk || "");
  if (!str) return;
  // Klammern () im Pfad zulassen (z.B. Wikipedia /Funktion_(Mathematik)); eine
  // ueberzaehlige schliessende Klammer (Satz-Klammer) wird unten wieder abgetrennt.
  const urlPattern = /https?:\/\/[^\s<>\[\]]+/g;
  let last = 0;
  let m;
  const _count = (s, ch) => s.split(ch).length - 1;
  while ((m = urlPattern.exec(str)) !== null) {
    if (m.index > last) parent.appendChild(document.createTextNode(str.slice(last, m.index)));
    let url = m[0];
    let trailing = "";
    const trail = /[.,;:!?]+$/.exec(url);
    if (trail) { trailing = trail[0]; url = url.slice(0, url.length - trailing.length); }
    // Nachgestellte unbalancierte ')' (z.B. "(siehe https://x.org/a)") als Text abtrennen,
    // balancierte Klammern im Pfad aber behalten.
    while (url.endsWith(")") && _count(url, ")") > _count(url, "(")) {
      trailing = ")" + trailing;
      url = url.slice(0, -1);
    }
    const safeUrl = normalizeChatUrl(url);
    if (safeUrl) {
      const link = document.createElement("a");
      link.className = "chat-link";
      link.href = safeUrl;
      link.rel = "noopener noreferrer";
      link.target = "_blank";
      link.textContent = url;
      parent.appendChild(link);
    } else {
      parent.appendChild(document.createTextNode(url));
    }
    if (trailing) parent.appendChild(document.createTextNode(trailing));
    last = urlPattern.lastIndex;
  }
  if (last < str.length) parent.appendChild(document.createTextNode(str.slice(last)));
}

function appendInlineMarkdown(parent, source) {
  const text = String(source || "");
  if (!text) return;

  const tokenPattern = /(`([^`\n]+)`|!\[([^\]\n]*)\]\(([^)\s]+(?:\s+[^)]*)?)\)|\[([^\]\n]+)\]\(([^)\s]+(?:\s+[^)]*)?)\)|\*\*([^*\n]+)\*\*|~~([^~\n]+)~~|\*([^*\n]+)\*|\[(\d{1,3})\])/g;
  let lastIndex = 0;
  let match;

  while ((match = tokenPattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      appendTextWithBareUrls(parent, text.slice(lastIndex, match.index));
    }

    const raw = match[0];
    if (raw.startsWith("`")) {
      const code = document.createElement("code");
      code.className = "inline-code";
      code.textContent = match[2] || "";
      parent.appendChild(code);
    } else if (raw.startsWith("![")) {
      const target = splitChatLinkTarget(match[4]);
      const safeUrl = normalizeChatUrl(target.url, { image: true });
      if (safeUrl) {
        const img = document.createElement("img");
        img.className = "chat-img chat-img-clickable";
        img.src = safeUrl;
        img.alt = match[3] || "";
        img.loading = "lazy";
        img.decoding = "async";
        if (target.title) img.title = target.title;
        img.addEventListener("click", () => {
          if (typeof openImageLightbox === "function") openImageLightbox(safeUrl);
        });
        parent.appendChild(img);
      } else if (match[3]) {
        parent.appendChild(document.createTextNode(match[3]));
      }
    } else if (match[10] !== undefined) {
      // Inline-Zitat [n] -> klickbare hochgestellte Quellennummer (wie ChatGPT/Gemini).
      // Klick oeffnet das Quellen-Panel der zugehoerigen Nachricht.
      const sup = document.createElement("sup");
      sup.className = "citation-ref";
      sup.dataset.citation = match[10];
      sup.textContent = match[10];
      sup.setAttribute("role", "button");
      sup.setAttribute("tabindex", "0");
      sup.title = "Quelle " + match[10];
      const openCite = () => {
        let el = sup.parentElement;
        while (el && !(el.classList && el.classList.contains("message"))) el = el.parentElement;
        const toggle = el && typeof el.querySelector === "function" ? el.querySelector(".chat-sources-toggle") : null;
        if (toggle) toggle.click();
      };
      sup.addEventListener("click", openCite);
      sup.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openCite(); }
      });
      parent.appendChild(sup);
    } else if (raw.startsWith("[")) {
      const target = splitChatLinkTarget(match[6]);
      const safeUrl = normalizeChatUrl(target.url);
      if (safeUrl) {
        const link = document.createElement("a");
        link.className = "chat-link";
        link.href = safeUrl;
        link.rel = "noopener noreferrer";
        if (target.title) link.title = target.title;
        if (!safeUrl.toLowerCase().startsWith("mailto:")) link.target = "_blank";
        link.textContent = match[5] || safeUrl;
        parent.appendChild(link);
      } else {
        parent.appendChild(document.createTextNode(match[5] || raw));
      }
    } else if (raw.startsWith("**")) {
      const strong = document.createElement("strong");
      appendInlineMarkdown(strong, match[7] || ""); // recurse -> nested *italic*/`code` inside bold
      parent.appendChild(strong);
    } else if (raw.startsWith("~~")) {
      const strike = document.createElement("s");
      appendInlineMarkdown(strike, match[8] || "");
      parent.appendChild(strike);
    } else if (raw.startsWith("*")) {
      const em = document.createElement("em");
      appendInlineMarkdown(em, match[9] || "");
      parent.appendChild(em);
    } else {
      parent.appendChild(document.createTextNode(raw));
    }
    lastIndex = tokenPattern.lastIndex;
  }

  if (lastIndex < text.length) {
    appendTextWithBareUrls(parent, text.slice(lastIndex));
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

// GFM-Spalten-Ausrichtung aus der Trennzeile: :--- = left, :---: = center, ---: = right.
function chatTableAlignments(separatorRow) {
  return chatTableCells(separatorRow).map((cell) => {
    const c = cell.trim();
    const left = c.startsWith(":");
    const right = c.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    if (left) return "left";
    return "";
  });
}

function appendChatTable(parent, rows) {
  const tableWrap = document.createElement("div");
  tableWrap.className = "table-wrap";
  const table = document.createElement("table");
  table.className = "chat-table";
  const hasHeader = rows.length > 1 && isChatTableSeparator(rows[1]);
  const aligns = hasHeader ? chatTableAlignments(rows[1]) : [];
  const dataRows = hasHeader ? [rows[0], ...rows.slice(2)] : rows;

  dataRows.forEach((row, index) => {
    const tr = document.createElement("tr");
    const tag = hasHeader && index === 0 ? "th" : "td";
    chatTableCells(row).forEach((cell, col) => {
      const el = document.createElement(tag);
      const align = aligns[col];
      // CSP-konform: Ausrichtung über Klasse statt Inline-Style (script-src 'self').
      if (align === "left" || align === "center" || align === "right") {
        el.classList.add("md-align-" + align);
      }
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
  // Sichtbares Label neben dem Icon (ChatGPT-Stil, besser auffindbar als nur Icon).
  const copyBtnLabel = document.createElement("span");
  copyBtnLabel.className = "code-btn-label";
  copyBtnLabel.textContent = typeof t === "function" ? t("chat.copyShort") : "Kopieren";
  copyButton.appendChild(copyBtnLabel);

  const wrapButton = document.createElement("button");
  wrapButton.type = "button";
  wrapButton.className = "code-tool-btn";
  wrapButton.title = "Zeilenumbruch umschalten";
  wrapButton.setAttribute("aria-label", "Zeilenumbruch umschalten");
  const wrapIcon = document.createElement("span");
  wrapIcon.textContent = "\u21a9";
  const wrapBtnLabel = document.createElement("span");
  wrapBtnLabel.className = "code-btn-label";
  wrapBtnLabel.textContent = "Umbruch";
  wrapButton.append(wrapIcon, wrapBtnLabel);

  const actions = document.createElement("div");
  actions.className = "code-actions";
  actions.appendChild(wrapButton);
  actions.appendChild(copyButton);
  header.appendChild(actions);

  const pre = document.createElement("pre");
  pre.className = "code-block";
  const code = document.createElement("code");
  code.textContent = String(codeText || "").trim();
  // Syntax-Highlighting via vendored highlight.js. Arbeitet auf textContent (XSS-sicher);
  // setzt nur Klassen + von hljs erzeugtes, escaptes Markup. Fehler -> roher Code bleibt.
  if (!_lexaStreamingRender && typeof hljs !== "undefined" && code.textContent) {
    try {
      if (safeLang && hljs.getLanguage(safeLang)) {
        code.className = "language-" + safeLang;
      }
      hljs.highlightElement(code);
    } catch (e) { /* Fallback: nicht-hervorgehobener Code */ }
  }
  pre.appendChild(code);
  wrapButton.addEventListener("click", () => pre.classList.toggle("code-wrap"));

  wrap.appendChild(header);
  wrap.appendChild(pre);

  // Sehr lange Bloecke einklappen (Mehr/Weniger anzeigen). Schwelle bewusst hoch (60),
  // damit normale 30-50-Zeilen-Snippets NICHT eingeklappt werden (war vorher 24 = zu aggressiv).
  const CODE_COLLAPSE_LINES = 60;
  const lineCount = (code.textContent.match(/\n/g) || []).length + 1;
  if (lineCount > CODE_COLLAPSE_LINES) {
    wrap.classList.add("code-collapsed");
    const expandBtn = document.createElement("button");
    expandBtn.type = "button";
    expandBtn.className = "code-expand-btn";
    const collapsedLabel = `Mehr anzeigen (${lineCount} Zeilen)`;
    expandBtn.textContent = collapsedLabel;
    expandBtn.addEventListener("click", () => {
      const stillCollapsed = wrap.classList.toggle("code-collapsed");
      expandBtn.textContent = stillCollapsed ? collapsedLabel : "Weniger anzeigen";
    });
    wrap.appendChild(expandBtn);
  }
  parent.appendChild(wrap);
}

function isMarkdownBlockStart(line) {
  return /^(#{1,6}\s+|>\s+|-{3,}\s*$|\s*\d+[.)]\s+|\s*[-*]\s+)/.test(line)
    || (/^\s*\|.*\|\s*$/.test(line));
}
