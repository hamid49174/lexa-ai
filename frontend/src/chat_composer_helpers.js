/* Composer command metadata and search helpers loaded before chat.js. Keep this file free of module syntax. */

const LEXA_COMPOSER_COMMANDS = [
  { id: "agent", icon: "command", hint: "/agent", aliases: ["a", "plan", "multi", "multi-step", "mehrschritt"], prefixKey: "composer.agent.prefix", labelKey: "composer.agent.label", descKey: "composer.agent.desc", fallbackPrefix: "/agent ", fallbackLabel: "Plan", fallbackDesc: "Handle a multi-step task clearly." },
  { id: "hermes", icon: "monitor", hint: "/hermes", aliases: ["h", "pc", "hm", "hermespc", "computeragent", "pcagent", "systemagent", "steuerung"], prefixKey: "composer.hermes.prefix", labelKey: "composer.hermes.label", descKey: "composer.hermes.desc", fallbackPrefix: "/hermes ", fallbackLabel: "Hermes", fallbackDesc: "Control PC tasks through Lexa." },
  { id: "orchestrate", icon: "command", hint: "/orchestrate", aliases: ["ultra", "orchestrator", "multiagent", "multi-agent", "team", "agenten", "schwarm", "ultracode"], prefixKey: "composer.orchestrate.prefix", labelKey: "composer.orchestrate.label", descKey: "composer.orchestrate.desc", fallbackPrefix: "/orchestrate ", fallbackLabel: "Multi-Agenten", fallbackDesc: "Parallele Agenten: planen, recherchieren, verifizieren, zusammenfassen." },
  { id: "clone", icon: "image", hint: "/clone", aliases: ["cl", "cloneui", "screenshotui"], prefixKey: "composer.clone.prefix", labelKey: "composer.clone.label", descKey: "composer.clone.desc", fallbackPrefix: "/agent Clone or recreate this UI from the supplied screenshot. Preserve layout intent, accessibility, responsive behavior, and Lexa's product style: ", fallbackLabel: "Clone UI", fallbackDesc: "Generate UI from a screenshot." },
  { id: "figma", icon: "figma", hint: "/figma", aliases: ["fg", "design"], prefixKey: "composer.figma.prefix", labelKey: "composer.figma.label", descKey: "composer.figma.desc", fallbackPrefix: "/agent Import or translate this Figma design into Lexa-ready UI. Keep components accessible, responsive, and consistent with the existing codebase: ", fallbackLabel: "Import Figma", fallbackDesc: "Turn a design into UI." },
  { id: "page", icon: "monitor", hint: "/page", aliases: ["p", "seite", "webpage"], prefixKey: "composer.page.prefix", labelKey: "composer.page.label", descKey: "composer.page.desc", fallbackPrefix: "/agent Create a production-ready page or screen for Lexa. Include layout, states, accessibility, responsive behavior, and tests where useful: ", fallbackLabel: "Create Page", fallbackDesc: "Generate a new app page." },
  { id: "research", icon: "search", hint: "/research", aliases: ["r", "rb", "researchbrief", "recherche", "quellen", "quelle", "citations", "evidence", "brief", "bericht", "deepresearch"], prefixKey: "composer.research.prefix", labelKey: "composer.research.label", descKey: "composer.research.desc", fallbackPrefix: "/agent Create a source-backed research brief: start with a short research plan, use web/file/OS context only when relevant, include a source list, mark unchecked claims clearly, and separate facts, assumptions, evidence, risks, and next actions: ", fallbackLabel: "Research Brief", fallbackDesc: "Plan a source-backed research pass." },
  { id: "workspace", icon: "doc", hint: "/workspace", aliases: ["w", "ws", "wd", "workdoc", "draft", "entwurf", "arbeitsdokument", "artifact", "artefakt", "canvas", "markdown"], prefixKey: "composer.workspace.prefix", labelKey: "composer.workspace.label", descKey: "composer.workspace.desc", fallbackPrefix: "/agent Build a reusable workspace draft in Markdown with goal, context, working draft, facts, assumptions, ideas, decisions, evidence, open questions, and next actions. Keep it ready for Personal OS draft review, not stable memory writes: ", fallbackLabel: "Workspace Draft", fallbackDesc: "Create an artifact-style working draft." },
  { id: "context", icon: "layers", hint: "/context", aliases: ["c", "ctx", "cp", "contextpack", "kontext", "kontextpaket", "briefing", "project", "projekt"], prefixKey: "composer.context.prefix", labelKey: "composer.context.label", descKey: "composer.context.desc", fallbackPrefix: "/agent Build a compact Personal OS context pack for this task before answering. Use read-only OS tools when useful, cite relevant file paths, separate facts, assumptions, ideas, decisions, evidence, and tasks, and propose draft updates instead of stable-memory writes: ", fallbackLabel: "Context Pack", fallbackDesc: "Assemble OS context before solving." },
  { id: "review", icon: "check", hint: "/review", aliases: ["rv", "dr", "draftreview", "reviewdraft", "reviewdrafts", "draftqueue", "approval", "freigabe"], prefixKey: "composer.review.prefix", labelKey: "composer.review.label", descKey: "composer.review.desc", fallbackPrefix: "/agent Review Personal OS pending drafts before any apply. Use read-only draft/review tools, separate facts, assumptions, decisions, evidence, risks, and tasks, recommend approve/reject/defer, and ask for explicit human approval before stable-memory changes: ", fallbackLabel: "Draft Review", fallbackDesc: "Review pending OS drafts safely." },
  { id: "skill", icon: "wand", hint: "/skill", aliases: ["sk", "gem", "gems", "skills", "preset", "template", "customassistant", "customgpt", "spezialist", "assistentenprofil"], prefixKey: "composer.skill.prefix", labelKey: "composer.skill.label", descKey: "composer.skill.desc", fallbackPrefix: "/agent Design a reusable Lexa Skill as a Markdown draft. Include purpose, trigger phrases, scope, instructions, inputs, outputs, allowed context/tools, safety boundaries, examples, test checklist, and Personal OS draft handoff. Do not write stable memory without review: ", fallbackLabel: "Lexa Skill", fallbackDesc: "Design a reusable assistant skill." },
  { id: "think", icon: "brain", hint: "/think", aliases: ["dt", "decide", "decision", "entscheid", "entscheidung", "entscheidungsbrief", "deepthink", "extendedthinking", "tradeoff", "abwaegen"], prefixKey: "composer.think.prefix", labelKey: "composer.think.label", descKey: "composer.think.desc", fallbackPrefix: "/agent Create a Deep Think decision brief. Frame the decision, separate facts, assumptions, options, tradeoffs, evidence, risks, reversibility, recommendation, confidence, open questions, and next actions. Use OS/web context only when relevant and provide a concise reasoning summary, not hidden chain-of-thought: ", fallbackLabel: "Deep Think", fallbackDesc: "Compare options and make a decision brief." },
  { id: "ship", icon: "rocket", hint: "/ship", aliases: ["rl", "release", "launch", "publish", "qa", "shipcheck", "releasecheck", "produktreif", "veroeffentlichen"], prefixKey: "composer.ship.prefix", labelKey: "composer.ship.label", descKey: "composer.ship.desc", fallbackPrefix: "/agent Run a production Ship Check for Lexa. Inspect release readiness, user-facing UX, accessibility, performance, reliability, privacy/security, data-loss risk, docs/onboarding, tests, migration/rollback, launch blockers, and next actions. Separate facts, assumptions, evidence, risks, must-fix before publish, nice-to-have, and verification commands. Do not ship, commit, publish, or write stable OS memory without explicit approval: ", fallbackLabel: "Ship Check", fallbackDesc: "Audit release readiness before publishing." },
  { id: "improve", icon: "spark", hint: "/improve", aliases: ["i", "fix", "ui", "ux", "produkt", "product", "polish"], prefixKey: "composer.improve.prefix", labelKey: "composer.improve.label", descKey: "composer.improve.desc", fallbackPrefix: "/agent Verbessere Lexa UI/UX mit kleinen sicheren Code-Aenderungen und fuehre passende Tests aus: ", fallbackLabel: "Improve Lexa", fallbackDesc: "Start a professional UI/UX code pass." },
  { id: "os", icon: "map", hint: "/os", aliases: ["pos", "personalos", "memory"], prefixKey: "composer.os.prefix", labelKey: "composer.os.label", descKey: "composer.os.desc", fallbackPrefix: "Nutze das Personal OS als Kontext und fasse zusammen: ", fallbackLabel: "Personal OS", fallbackDesc: "Bring OS context into the current chat." },
  { id: "screen", icon: "image", hint: "/screen", aliases: ["s", "screenshot", "bildschirm", "visual"], prefixKey: "composer.screen.prefix", labelKey: "composer.screen.label", descKey: "composer.screen.desc", fallbackPrefix: "Analysiere den Bildschirm und gib mir konkrete UI/UX-Verbesserungen: ", fallbackLabel: "Screen Review", fallbackDesc: "Prepare a visual review prompt." },
  { id: "voice", icon: "wave", hint: "/voice", aliases: ["v", "stt", "tts", "wakeword", "wake"], prefixKey: "composer.voice.prefix", labelKey: "composer.voice.label", descKey: "composer.voice.desc", fallbackPrefix: "Pruefe Voice/STT/TTS/Wake-Word-Status und nenne die naechsten echten Blocker: ", fallbackLabel: "Voice Check", fallbackDesc: "Focus on diagnostics instead of demo feel." },
];

function composerCommandText(command, field) {
  const key = command?.[`${field}Key`];
  const fallback = command?.[`fallback${field[0].toUpperCase()}${field.slice(1)}`] || "";
  if (!key) return fallback;
  const translated = t(key);
  return translated === key ? fallback : translated;
}

function composerCommandLabel(command) { return composerCommandText(command, "label"); }
function composerCommandDesc(command) { return composerCommandText(command, "desc"); }
function composerCommandPrefix(command) { return composerCommandText(command, "prefix"); }
function composerCommandAliases(command) { return Array.isArray(command?.aliases) ? command.aliases : []; }

function composerCommandAliasKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[ä]/g, "ae")
    .replace(/[ö]/g, "oe")
    .replace(/[ü]/g, "ue")
    .replace(/[ß]/g, "ss")
    .replace(/[\s_-]+/g, "");
}

function composerCommandHintText(command) {
  const primary = command?.hint || composerCommandPrefix(command).trim().split(/\s+/)[0] || "/";
  const normalizedPrimary = primary.replace(/^\//, "").toLowerCase();
  const shortAliases = composerCommandAliases(command)
    .map((value) => String(value || "").toLowerCase())
    .filter((value) => value && value.length <= 3 && value !== normalizedPrimary && value !== command?.id);
  const shortAlias = shortAliases.find((value) => value.length > 1) || shortAliases[0];
  return shortAlias ? `${primary} /${shortAlias}` : primary;
}

function composerCommandSentence(value) {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/[.!?]+$/g, "");
}

function composerCommandAssistiveText(label, desc, prefixHint) {
  const cleanLabel = composerCommandSentence(label);
  const cleanDesc = composerCommandSentence(desc);
  const cleanHint = String(prefixHint || "").trim();
  const summary = cleanDesc ? `${cleanLabel}: ${cleanDesc}` : cleanLabel;
  return cleanHint ? `${summary}. ${cleanHint}` : summary;
}

function composerCommandTitleText(label, desc, prefixHint) {
  const cleanLabel = composerCommandSentence(label);
  const cleanDesc = composerCommandSentence(desc);
  const cleanHint = String(prefixHint || "").trim();
  const summary = cleanDesc ? `${cleanLabel}: ${cleanDesc}` : cleanLabel;
  return cleanHint ? `${summary} (${cleanHint})` : summary;
}

function composerCommandAliasValues(command) {
  const hint = String(command?.hint || "").replace(/^\//, "");
  return [command?.id, hint, ...composerCommandAliases(command)]
    .map((value) => composerCommandAliasKey(value))
    .filter(Boolean);
}

function composerCommandIconSvg(icon) {
  const icons = {
    command: '<path d="M18 6 6 18"/><path d="m8 6 4 6-4 6"/><path d="M14 18h4"/>',
    figma: '<path d="M8 3h4v6H8a3 3 0 0 1 0-6Z"/><path d="M12 3h4a3 3 0 0 1 0 6h-4V3Z"/><path d="M12 9h4a3 3 0 0 1 0 6h-4V9Z"/><path d="M8 9h4v6H8a3 3 0 0 1 0-6Z"/><path d="M8 15h4v3a3 3 0 1 1-4-3Z"/>',
    monitor: '<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4.5-4.5"/><path d="M8 11h6"/>',
    doc: '<path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h5"/>',
    layers: '<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 16 9 5 9-5"/>',
    check: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 12l2 2 4-5"/><path d="M8 7h8"/>',
    wand: '<path d="M15 4l5 5"/><path d="M14 5l5 5-9 9-5-5 9-9Z"/><path d="M5 4v3"/><path d="M3.5 5.5h3"/><path d="M20 17v3"/><path d="M18.5 18.5h3"/>',
    brain: '<path d="M9 5a3 3 0 0 0-3 3v1a3 3 0 0 0-1 5.2A3.5 3.5 0 0 0 8.5 19H10V5H9Z"/><path d="M15 5a3 3 0 0 1 3 3v1a3 3 0 0 1 1 5.2A3.5 3.5 0 0 1 15.5 19H14V5h1Z"/><path d="M10 9H7.5"/><path d="M14 9h2.5"/><path d="M10 14H7"/><path d="M14 14h3"/>',
    rocket: '<path d="M5 19c1.6-.3 3.2-.9 4.4-2.1"/><path d="M4 14l6 6"/><path d="M13 6c2.5-2.5 5.3-3 7-2-.2 2.1-1 4.5-3.1 6.6L10 17l-4-4 7-7Z"/><path d="M15 8h.01"/><path d="M6 13l-2 1 1-4 3-1"/><path d="M11 18l-1 3 4-1 1-2"/>',
    spark: '<path d="M12 2l1.8 6.1L20 10l-6.2 1.9L12 18l-1.8-6.1L4 10l6.2-1.9L12 2Z"/><path d="M19 15l.9 3.1L23 19l-3.1.9L19 23l-.9-3.1L15 19l3.1-.9L19 15Z"/>',
    map: '<path d="M4 6l5-2 6 2 5-2v14l-5 2-6-2-5 2V6Z"/><path d="M9 4v14"/><path d="M15 6v14"/>',
    image: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8" cy="10" r="1.5"/><path d="M21 15l-5-5L5 19"/>',
    wave: '<path d="M4 12h2l2-6 4 12 3-8 2 2h3"/>',
  };
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${icons[icon] || icons.command}</svg>`;
}

function createComposerCommandIconElement(icon) {
  const specs = {
    command: [
      { tag: "path", attrs: { d: "M18 6 6 18" } },
      { tag: "path", attrs: { d: "m8 6 4 6-4 6" } },
      { tag: "path", attrs: { d: "M14 18h4" } },
    ],
    figma: [
      { tag: "path", attrs: { d: "M8 3h4v6H8a3 3 0 0 1 0-6Z" } },
      { tag: "path", attrs: { d: "M12 3h4a3 3 0 0 1 0 6h-4V3Z" } },
      { tag: "path", attrs: { d: "M12 9h4a3 3 0 0 1 0 6h-4V9Z" } },
      { tag: "path", attrs: { d: "M8 9h4v6H8a3 3 0 0 1 0-6Z" } },
      { tag: "path", attrs: { d: "M8 15h4v3a3 3 0 1 1-4-3Z" } },
    ],
    monitor: [
      { tag: "rect", attrs: { x: "3", y: "5", width: "18", height: "12", rx: "2" } },
      { tag: "path", attrs: { d: "M8 21h8" } },
      { tag: "path", attrs: { d: "M12 17v4" } },
    ],
    search: [
      { tag: "circle", attrs: { cx: "11", cy: "11", r: "7" } },
      { tag: "path", attrs: { d: "M20 20l-4.5-4.5" } },
      { tag: "path", attrs: { d: "M8 11h6" } },
    ],
    doc: [
      { tag: "path", attrs: { d: "M6 3h8l4 4v14H6V3Z" } },
      { tag: "path", attrs: { d: "M14 3v5h5" } },
      { tag: "path", attrs: { d: "M9 13h6" } },
      { tag: "path", attrs: { d: "M9 17h5" } },
    ],
    layers: [
      { tag: "path", attrs: { d: "M12 3 3 8l9 5 9-5-9-5Z" } },
      { tag: "path", attrs: { d: "m3 12 9 5 9-5" } },
      { tag: "path", attrs: { d: "m3 16 9 5 9-5" } },
    ],
    check: [
      { tag: "rect", attrs: { x: "4", y: "3", width: "16", height: "18", rx: "2" } },
      { tag: "path", attrs: { d: "M9 12l2 2 4-5" } },
      { tag: "path", attrs: { d: "M8 7h8" } },
    ],
    wand: [
      { tag: "path", attrs: { d: "M15 4l5 5" } },
      { tag: "path", attrs: { d: "M14 5l5 5-9 9-5-5 9-9Z" } },
      { tag: "path", attrs: { d: "M5 4v3" } },
      { tag: "path", attrs: { d: "M3.5 5.5h3" } },
      { tag: "path", attrs: { d: "M20 17v3" } },
      { tag: "path", attrs: { d: "M18.5 18.5h3" } },
    ],
    brain: [
      { tag: "path", attrs: { d: "M9 5a3 3 0 0 0-3 3v1a3 3 0 0 0-1 5.2A3.5 3.5 0 0 0 8.5 19H10V5H9Z" } },
      { tag: "path", attrs: { d: "M15 5a3 3 0 0 1 3 3v1a3 3 0 0 1 1 5.2A3.5 3.5 0 0 1 15.5 19H14V5h1Z" } },
      { tag: "path", attrs: { d: "M10 9H7.5" } },
      { tag: "path", attrs: { d: "M14 9h2.5" } },
      { tag: "path", attrs: { d: "M10 14H7" } },
      { tag: "path", attrs: { d: "M14 14h3" } },
    ],
    rocket: [
      { tag: "path", attrs: { d: "M5 19c1.6-.3 3.2-.9 4.4-2.1" } },
      { tag: "path", attrs: { d: "M4 14l6 6" } },
      { tag: "path", attrs: { d: "M13 6c2.5-2.5 5.3-3 7-2-.2 2.1-1 4.5-3.1 6.6L10 17l-4-4 7-7Z" } },
      { tag: "path", attrs: { d: "M15 8h.01" } },
      { tag: "path", attrs: { d: "M6 13l-2 1 1-4 3-1" } },
      { tag: "path", attrs: { d: "M11 18l-1 3 4-1 1-2" } },
    ],
    spark: [
      { tag: "path", attrs: { d: "M12 2l1.8 6.1L20 10l-6.2 1.9L12 18l-1.8-6.1L4 10l6.2-1.9L12 2Z" } },
      { tag: "path", attrs: { d: "M19 15l.9 3.1L23 19l-3.1.9L19 23l-.9-3.1L15 19l3.1-.9L19 15Z" } },
    ],
    map: [
      { tag: "path", attrs: { d: "M4 6l5-2 6 2 5-2v14l-5 2-6-2-5 2V6Z" } },
      { tag: "path", attrs: { d: "M9 4v14" } },
      { tag: "path", attrs: { d: "M15 6v14" } },
    ],
    image: [
      { tag: "rect", attrs: { x: "3", y: "5", width: "18", height: "14", rx: "2" } },
      { tag: "circle", attrs: { cx: "8", cy: "10", r: "1.5" } },
      { tag: "path", attrs: { d: "M21 15l-5-5L5 19" } },
    ],
    wave: [
      { tag: "path", attrs: { d: "M4 12h2l2-6 4 12 3-8 2 2h3" } },
    ],
  };
  const children = specs[icon] || specs.command;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "16");
  svg.setAttribute("height", "16");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  children.forEach((child) => {
    const el = document.createElementNS("http://www.w3.org/2000/svg", child.tag);
    Object.entries(child.attrs || {}).forEach(([name, value]) => el.setAttribute(name, value));
    svg.appendChild(el);
  });
  return svg;
}

function composerCommandMatches(command, query) {
  return composerCommandScore(command, query) > 0;
}

function composerCommandScore(command, query) {
  const q = composerCommandAliasKey(query);
  if (!q) return 1;
  const aliases = composerCommandAliasValues(command);
  if (aliases.some((alias) => alias === q)) return 100;
  if (aliases.some((alias) => alias.startsWith(q))) return 90;
  const label = composerCommandAliasKey(composerCommandLabel(command));
  if (label.startsWith(q)) return 75;
  if (label.includes(q)) return 60;
  const desc = composerCommandAliasKey(composerCommandDesc(command));
  if (desc.includes(q)) return 35;
  const prompt = composerCommandAliasKey(composerCommandPrefix(command));
  if (prompt.includes(q)) return 15;
  return 0;
}

function composerCommandSearchItems(query) {
  return LEXA_COMPOSER_COMMANDS
    .map((command, index) => ({ command, index, score: composerCommandScore(command, query) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => (b.score - a.score) || (a.index - b.index))
    .map((item) => item.command);
}

function composerCommandForAlias(alias, options) {
  const key = composerCommandAliasKey(alias);
  const allowPrefix = Boolean(options?.allowPrefix);
  if (!key) return null;
  const exact = LEXA_COMPOSER_COMMANDS.find((item) => composerCommandAliasValues(item).includes(key));
  if (exact || !allowPrefix) return exact || null;
  const prefixMatches = LEXA_COMPOSER_COMMANDS.filter((item) =>
    composerCommandAliasValues(item).some((value) => value.startsWith(key))
  );
  return prefixMatches.length === 1 ? prefixMatches[0] : null;
}

function expandComposerSlashAlias(text) {
  const source = String(text || "").trim();
  const match = source.match(/^\/([a-z0-9_-]+)(?:\s+([\s\S]*))?$/i);
  if (!match || match[1].toLowerCase() === "agent") return "";
  const command = composerCommandForAlias(match[1], { allowPrefix: true });
  if (!command) return "";
  const remainder = String(match[2] || "").trim();
  return `${composerCommandPrefix(command)}${remainder}`.trim();
}
