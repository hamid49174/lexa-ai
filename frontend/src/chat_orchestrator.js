/* Multi-Agenten-Orchestrator im Chat (Phase 48 E).
 * Eigenstaendig, CSP-sicher (nur createElement/textContent, keine Inline-Styles/Handler).
 * Konsumiert den /orchestrator/run SSE-Stream ueber den bestehenden agentStream-Transport
 * und rendert einen Live-Baum: Plan -> Sub-Agenten (mit Schritten) -> Verifikation -> Antwort.
 * Loaded vor chat.js; alle chat.js-Globals werden erst zur Laufzeit referenziert.
 */
(function () {
  "use strict";

  function _el(tag, cls, txt) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  function _messagesEl() {
    if (typeof chatMessages !== "undefined" && chatMessages) return chatMessages;
    return document.getElementById("chat-messages");
  }

  function _scroll() {
    const el = _messagesEl();
    if (el) el.scrollTop = el.scrollHeight;
  }

  function _roleLabel(role) {
    const map = { research: "Recherche", knowledge: "Wissen", general: "Allgemein", code: "Code", browser: "Browser", planning: "Planung" };
    return map[role] || role || "Agent";
  }

  const _PHASES = [["plan", "Plan"], ["agents", "Agenten"], ["verify", "Verifikation"], ["synth", "Synthese"]];

  function buildOrchestratorPanel(task, mode) {
    const wrap = _el("div", "orchestrator-run");
    const head = _el("div", "orchestrator-head");
    head.appendChild(_el("span", "orchestrator-title", "Multi-Agenten-Lauf"));
    head.appendChild(_el("span", "orchestrator-mode", mode === "fast" ? "schnell" : "gruendlich"));
    const counts = _el("span", "orchestrator-counts", "");
    head.appendChild(counts);
    const status = _el("span", "orchestrator-status", "laeuft …");
    head.appendChild(status);
    wrap.appendChild(head);

    // Phasen-Leiste (wie Claude Code): Plan -> Agenten -> Verifikation -> Synthese.
    const phaseStrip = _el("div", "orchestrator-phases");
    const phases = {};
    _PHASES.forEach(([key, label]) => {
      const chip = _el("span", "orchestrator-phase", label);
      chip.setAttribute("data-phase", key);
      phaseStrip.appendChild(chip);
      phases[key] = chip;
    });
    wrap.appendChild(phaseStrip);

    const planBox = _el("div", "orchestrator-plan");
    const agentsBox = _el("div", "orchestrator-agents");
    const verifyBox = _el("div", "orchestrator-verify");
    wrap.appendChild(planBox);
    wrap.appendChild(agentsBox);
    wrap.appendChild(verifyBox);

    wrap._orch = { status, counts, phases, planBox, agentsBox, verifyBox, agents: {}, synthesis: "", stepCount: 0, mode };
    _setPhase(wrap, "plan", "active");
    return wrap;
  }

  function _setPhase(panel, key, state) {
    const refs = panel && panel._orch;
    if (!refs || !refs.phases || !refs.phases[key]) return;
    refs.phases[key].className = "orchestrator-phase " + state;  // pending|active|done|skip
  }

  function _updateCounts(panel) {
    const refs = panel && panel._orch;
    if (!refs) return;
    const n = Object.keys(refs.agents).length;
    refs.counts.textContent = n ? (n + " Agenten · " + refs.stepCount + " Schritte") : "";
  }

  function _setStatus(panel, text, kind) {
    const refs = panel._orch;
    if (!refs) return;
    refs.status.textContent = text;
    refs.status.className = "orchestrator-status" + (kind ? " " + kind : "");
  }

  function _renderPlan(panel, plan) {
    const refs = panel._orch;
    if (!refs || !plan) return;
    refs.planBox.replaceChildren();
    refs.planBox.appendChild(_el("div", "orchestrator-section-title", "Plan"));
    const list = _el("ol", "orchestrator-plan-list");
    (plan.subtasks || []).forEach((st) => {
      const li = _el("li");
      li.appendChild(_el("span", "orchestrator-plan-role", _roleLabel(st.role)));
      li.appendChild(_el("span", "orchestrator-plan-objective", " " + (st.objective || "")));
      list.appendChild(li);
    });
    refs.planBox.appendChild(list);
  }

  function _ensureAgentCard(panel, agentId, role, label, objective) {
    const refs = panel._orch;
    if (!refs) return null;
    if (refs.agents[agentId]) return refs.agents[agentId];
    const card = _el("div", "orchestrator-agent running");
    const header = _el("div", "orchestrator-agent-head");
    header.appendChild(_el("span", "orchestrator-agent-role", label || _roleLabel(role)));
    header.appendChild(_el("span", "orchestrator-agent-state", "laeuft"));
    card.appendChild(header);
    if (objective) card.appendChild(_el("div", "orchestrator-agent-objective", objective));
    // Schritte standardmaessig eingeklappt (aufgeraeumt statt Tool-Dump) — Klick toggelt.
    const stepsToggle = _el("button", "orchestrator-steps-toggle", "0 Schritte");
    stepsToggle.type = "button";
    const steps = _el("ul", "orchestrator-agent-steps collapsed");
    stepsToggle.addEventListener("click", () => {
      const open = steps.className.indexOf("collapsed") === -1;
      steps.className = open ? "orchestrator-agent-steps collapsed" : "orchestrator-agent-steps";
    });
    card.appendChild(stepsToggle);
    card.appendChild(steps);
    refs.agentsBox.appendChild(card);
    const entry = { card, header, steps, stepsToggle, state: header.lastChild, count: 0 };
    refs.agents[agentId] = entry;
    return entry;
  }

  function _addAgentStep(panel, agentId, step) {
    const entry = _ensureAgentCard(panel, agentId);
    if (!entry || !step) return;
    const li = _el("li", "orchestrator-step " + (step.status || ""));
    li.appendChild(_el("span", "orchestrator-step-tool", step.tool || "?"));
    if (step.summary) li.appendChild(_el("span", "orchestrator-step-summary", " — " + step.summary));
    entry.steps.appendChild(li);
    entry.count = (entry.count || 0) + 1;
    if (entry.stepsToggle) entry.stepsToggle.textContent = entry.count + (entry.count === 1 ? " Schritt" : " Schritte");
    if (panel._orch) { panel._orch.stepCount += 1; _updateCounts(panel); }
  }

  function _markAgentDone(panel, agentId, status, summary) {
    const entry = _ensureAgentCard(panel, agentId);
    if (!entry) return;
    entry.card.className = "orchestrator-agent " + (status === "done" ? "done" : "issue");
    if (entry.state) entry.state.textContent = status || "fertig";
    if (summary) {
      const sum = _el("div", "orchestrator-agent-summary", summary);
      entry.card.appendChild(sum);
    }
  }

  function _addVerification(panel, verdict) {
    const refs = panel._orch;
    if (!refs || !verdict) return;
    if (!refs.verifyShown) {
      refs.verifyBox.appendChild(_el("div", "orchestrator-section-title", "Verifikation"));
      refs.verifyShown = true;
    }
    const ok = verdict.passed;
    const line = _el("div", "orchestrator-verdict " + (ok ? "ok" : "doubt"));
    const tag = ok ? "✓" : "⚠";
    line.appendChild(_el("span", "orchestrator-verdict-tag", tag));
    line.appendChild(_el("span", "orchestrator-verdict-text",
      " " + (verdict.agent_id || "") + " — score " + (verdict.score != null ? verdict.score : "?")));
    refs.verifyBox.appendChild(line);
  }

  // Pure Event-Dispatch (test-bar): mutiert nur das Panel-DOM.
  function orchestratorHandleEvent(panel, event) {
    if (!panel || !event) return;
    switch (event.type) {
      case "plan":
        _renderPlan(panel, event.plan);
        _setPhase(panel, "plan", "done");
        _setPhase(panel, "agents", "active");
        break;
      case "subagent_start":
        _ensureAgentCard(panel, event.agent_id, event.role, event.label, event.objective);
        _setPhase(panel, "agents", "active");
        _updateCounts(panel);
        break;
      case "subagent_step": _addAgentStep(panel, event.agent_id, event.step); break;
      case "subagent_done": _markAgentDone(panel, event.agent_id, event.status, event.summary); break;
      case "verification":
        _setPhase(panel, "agents", "done");
        _setPhase(panel, "verify", "active");
        _addVerification(panel, event.verdict);
        break;
      case "synthesis":
        _setPhase(panel, "agents", "done");
        _setPhase(panel, "verify", (panel._orch && panel._orch.mode === "fast") ? "skip" : "done");
        _setPhase(panel, "synth", "active");
        if (panel._orch) panel._orch.synthesis = event.content || "";
        break;
      case "done":
        _setPhase(panel, "synth", "done");
        _setStatus(panel, "fertig", "done");
        if (panel._orch && event.run && event.run.partial) _setStatus(panel, "teilweise (Zeitlimit)", "issue");
        break;
      case "error": _setStatus(panel, event.message || "Fehler", "error"); break;
      default: break;
    }
  }

  // Inaktivitaets-Timeout pro Read: stallt der Backend-Stream, wird die Schleife verlassen
  // (sonst bliebe das Panel fuer immer auf "laeuft …" und die Connection wuerde leaken).
  const ORCH_STREAM_TIMEOUT_MS = 180000;

  function _readWithTimeout(reader, ms) {
    return new Promise((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (!settled) { settled = true; reject(new Error("orch_stream_timeout")); }
      }, ms);
      reader.read().then(
        (r) => { if (!settled) { settled = true; clearTimeout(timer); resolve(r); } },
        (e) => { if (!settled) { settled = true; clearTimeout(timer); reject(e); } },
      );
    });
  }

  async function _ensureConversation() {
    if (typeof LexaState === "undefined" || LexaState.get("currentConversationId")) return;
    try {
      const title = typeof t === "function" ? t("chat.newChatTitle") : "Neuer Chat";
      const c = await window.lexa.conversationCreate(title);
      if (c && c.id) {
        LexaState.set("currentConversationId", c.id);
        if (typeof chatSetActiveConversationId === "function") chatSetActiveConversationId(c.id);
        try {
          const d = await window.lexa.conversations();
          LexaState.set("conversationsList", (d && d.conversations) || []);
          if (typeof renderConversationList === "function") renderConversationList();
        } catch (_) { /* Liste optional */ }
      }
    } catch (_) { /* ohne Konversation laeuft es weiter, nur ohne Persistenz */ }
  }

  // Re-Entrancy-Guard: verhindert mehrere parallele Laeufe durch wiederholtes Absenden.
  let _running = false;

  async function sendOrchestratorMessage(task, options) {
    options = options || {};
    const taskText = String(task || "").trim();
    if (!taskText) return;
    if (_running) {
      if (typeof showToast === "function") showToast("Ein Agenten-Lauf laeuft bereits.", "warning");
      return;
    }
    _running = true;
    const displayText = String(options.displayText || taskText).trim();
    const mode = options.mode === "fast" ? "fast" : "thorough";

    try {
      await _ensureConversation();
      if (typeof addMessage === "function") addMessage(displayText, "user");
      if (typeof pushChatHistory === "function") pushChatHistory(displayText);
      // Eingabefeld + Draft leeren (sonst bleibt der /ultra-Text stehen -> versehentlicher Re-Run).
      if (typeof chatInput !== "undefined" && chatInput) {
        chatInput.value = "";
        if (typeof syncChatInputSize === "function") syncChatInputSize();
      }
      if (typeof clearChatDraft === "function") clearChatDraft();

      const container = _messagesEl();
      const panel = buildOrchestratorPanel(taskText, mode);
      if (container) { container.appendChild(panel); _scroll(); }

      let resp;
      try {
        resp = await window.lexa.orchestratorRun(taskText, { mode });
      } catch (e) {
        _setStatus(panel, "Start fehlgeschlagen", "error");
        return;
      }
      if (!resp || !resp.streamId) {
        _setStatus(panel, "Stream nicht verfuegbar", "error");
        if (typeof addMessage === "function") {
          addMessage((resp && resp.statusText) || "Orchestrator nicht erreichbar.", "system");
        }
        return;
      }

      let reader;
      try {
        reader = createAgentStreamReader(resp);
      } catch (e) {
        _setStatus(panel, "Stream nicht verfuegbar", "error");
        return;
      }
      const decoder = new TextDecoder();
      let buffer = "";
      try {
        while (true) {
          let chunk;
          try {
            chunk = await _readWithTimeout(reader, ORCH_STREAM_TIMEOUT_MS);
          } catch (e) {
            _setStatus(panel, e && e.message === "orch_stream_timeout" ? "Zeitlimit (keine Antwort)" : "Verbindungsfehler", "error");
            break;
          }
          const value = chunk && chunk.value;
          if (value && value.length) buffer += decoder.decode(value, { stream: true });
          let idx;
          while ((idx = buffer.indexOf("\n")) >= 0) {
            const line = buffer.slice(0, idx).trim();
            buffer = buffer.slice(idx + 1);
            if (!line || line.indexOf("data:") !== 0) continue;
            const payload = line.slice(5).trim();
            if (!payload) continue;
            let ev;
            try { ev = JSON.parse(payload); } catch (_) { continue; }
            orchestratorHandleEvent(panel, ev);
            _scroll();
          }
          if (chunk && chunk.done) break;
        }
      } finally {
        // Reader/HTTP-Connection in JEDEM Fall freigeben (nach done idempotent/no-op).
        try { if (reader && typeof reader.cancel === "function") await reader.cancel(); } catch (_) { /* idempotent */ }
      }

      const answer = panel._orch && panel._orch.synthesis;
      if (answer && typeof addMessage === "function") addMessage(answer, "system");
      _scroll();
      // Lauf (User-Prompt + Antwort) in der Konversation persistieren.
      if (typeof saveCurrentConversation === "function") {
        try { await saveCurrentConversation(); } catch (_) { /* Save best-effort */ }
      }
    } finally {
      _running = false;
    }
  }

  // ── Agenten-Aufwand (User-Regler, wie Claude Codes Schneller<->Intelligenter) ──
  // Steuert, OB komplexe Aufgaben automatisch (ohne /orchestrate) an die Agenten gehen
  // und WIE gruendlich. off = nur /orchestrate; fast = auto + schnell; thorough = auto +
  // adversarische Verifikation. Persistiert in localStorage.
  const _EFFORT_KEY = "lexa_agent_effort";
  const _EFFORT_LEVELS = ["off", "fast", "thorough"];
  const _EFFORT_LABEL = { off: "Aus", fast: "Schnell", thorough: "Gruendlich" };

  function getAgentEffort() {
    try {
      const v = localStorage.getItem(_EFFORT_KEY);
      if (_EFFORT_LEVELS.indexOf(v) !== -1) return v;
    } catch (_) { /* localStorage evtl. nicht verfuegbar */ }
    return "off";  // Default AUS: Auto-Agenten nur, wenn der Nutzer den Regler bewusst einschaltet
  }

  function setAgentEffort(level) {
    if (_EFFORT_LEVELS.indexOf(level) === -1) level = "fast";
    try { localStorage.setItem(_EFFORT_KEY, level); } catch (_) { /* noop */ }
    renderAgentEffortButton();
    return level;
  }

  function cycleAgentEffort() {
    const next = _EFFORT_LEVELS[(_EFFORT_LEVELS.indexOf(getAgentEffort()) + 1) % _EFFORT_LEVELS.length];
    setAgentEffort(next);
    if (typeof showToast === "function") {
      const hint = next === "off" ? "nur /orchestrate" : (next === "fast" ? "Agenten automatisch, schnell" : "Agenten automatisch, gruendlich");
      showToast("Agenten-Aufwand: " + _EFFORT_LABEL[next] + " (" + hint + ")", "info", 2000);
    }
  }

  function renderAgentEffortButton() {
    const level = getAgentEffort();
    const lbl = document.getElementById("agent-effort-label");
    const btn = document.getElementById("agent-effort-btn");
    if (lbl) lbl.textContent = _EFFORT_LABEL[level];
    if (btn) {
      btn.setAttribute("data-effort", level);
      btn.setAttribute("aria-label", "Agenten-Aufwand: " + _EFFORT_LABEL[level]);
    }
  }

  // Heuristik: lohnt sich der Multi-Agenten-Orchestrator (Vergleich/breite Recherche/
  // mehrteilige Aufgabe)? Bewusst KONSERVATIV — einfache Fragen bleiben normaler Chat.
  // Stamm-Praefixe (kein schliessendes \b, damit "vergleiche"/"recherchiere"/"analysiere"
  // mitmatchen). Fuehrendes \b verhindert Mid-Word-Treffer.
  const _ORCH_TRIGGER_RE = /\b(vergleich|gegen[uü]ber|pro und contra|recherchier|umfassend|ausf[uü]hrlich|tiefgehend|deep ?research|analysier|evaluier|bewerte|untersuch|welche optionen|verschiedene (optionen|ans[aä]tze|tools|wege))/i;

  function needsOrchestratorMode(text) {
    const s = String(text || "").trim();
    if (s.length < 25) return false;
    if (_ORCH_TRIGGER_RE.test(s)) return true;
    // Mehrteilige Aufgabe: mehrere "und"-Verknuepfungen in einer laengeren Anfrage.
    const ands = (s.match(/\bund\b/gi) || []).length;
    if (ands >= 2 && s.length > 60) return true;
    return false;
  }

  // Auto-Orchestrierung: fragt den LLM-Triage-Endpoint (Modell entscheidet wie ultracode,
  // OB Multi-Agent noetig) und startet ggf. den Lauf. Billiger Pre-Filter (Laenge) vermeidet
  // Triage-Calls fuer Smalltalk; bei nicht erreichbarem Triage faellt es auf die lokale
  // Heuristik zurueck. Gibt true zurueck, wenn der Orchestrator uebernommen hat.
  async function maybeAutoOrchestrate(text) {
    const s = String(text || "").trim();
    if (s.length < 25) return false;  // Smalltalk/kurze Fragen -> kein Triage-Call, kein Agent
    let decision = null;
    try {
      if (window.lexa && typeof window.lexa.orchestratorTriage === "function") {
        decision = await window.lexa.orchestratorTriage(s);
      }
    } catch (_) { decision = null; }
    const needs = decision && decision.source !== "error" && decision.source !== "disabled"
      ? !!decision.needs_agents
      : needsOrchestratorMode(s);  // Fallback: lokale Heuristik
    if (!needs) return false;
    const effort = typeof getAgentEffort === "function" ? getAgentEffort() : "fast";
    if (effort === "off") return false;
    sendOrchestratorMessage(s, { displayText: text, mode: effort === "thorough" ? "thorough" : "fast" });
    return true;
  }

  // Globals fuer chat.js (Routing) + Tests.
  window.sendOrchestratorMessage = sendOrchestratorMessage;
  window.maybeAutoOrchestrate = maybeAutoOrchestrate;
  window.buildOrchestratorPanel = buildOrchestratorPanel;
  window.orchestratorHandleEvent = orchestratorHandleEvent;
  window.getAgentEffort = getAgentEffort;
  window.setAgentEffort = setAgentEffort;
  window.cycleAgentEffort = cycleAgentEffort;
  window.renderAgentEffortButton = renderAgentEffortButton;
  window.needsOrchestratorMode = needsOrchestratorMode;

  // Button-Label initial setzen (Composer steht im DOM vor diesem Script).
  try { renderAgentEffortButton(); } catch (_) { /* noop */ }
})();
