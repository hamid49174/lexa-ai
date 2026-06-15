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

  function buildOrchestratorPanel(task, mode) {
    const wrap = _el("div", "orchestrator-run");
    const head = _el("div", "orchestrator-head");
    head.appendChild(_el("span", "orchestrator-title", "Multi-Agenten-Lauf"));
    head.appendChild(_el("span", "orchestrator-mode", mode === "fast" ? "schnell" : "gruendlich"));
    const status = _el("span", "orchestrator-status", "laeuft …");
    head.appendChild(status);
    wrap.appendChild(head);

    const planBox = _el("div", "orchestrator-plan");
    const agentsBox = _el("div", "orchestrator-agents");
    const verifyBox = _el("div", "orchestrator-verify");
    wrap.appendChild(planBox);
    wrap.appendChild(agentsBox);
    wrap.appendChild(verifyBox);

    wrap._orch = { status, planBox, agentsBox, verifyBox, agents: {}, synthesis: "" };
    return wrap;
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
    const steps = _el("ul", "orchestrator-agent-steps");
    card.appendChild(steps);
    refs.agentsBox.appendChild(card);
    const entry = { card, header, steps, state: header.lastChild };
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
      case "plan": _renderPlan(panel, event.plan); break;
      case "subagent_start": _ensureAgentCard(panel, event.agent_id, event.role, event.label, event.objective); break;
      case "subagent_step": _addAgentStep(panel, event.agent_id, event.step); break;
      case "subagent_done": _markAgentDone(panel, event.agent_id, event.status, event.summary); break;
      case "verification": _addVerification(panel, event.verdict); break;
      case "synthesis": if (panel._orch) panel._orch.synthesis = event.content || ""; break;
      case "done":
        _setStatus(panel, "fertig", "done");
        if (panel._orch && event.run && event.run.partial) _setStatus(panel, "teilweise (Zeitlimit)", "issue");
        break;
      case "error": _setStatus(panel, event.message || "Fehler", "error"); break;
      default: break;
    }
  }

  async function sendOrchestratorMessage(task, options) {
    options = options || {};
    const taskText = String(task || "").trim();
    if (!taskText) return;
    const displayText = String(options.displayText || taskText).trim();
    const mode = options.mode === "fast" ? "fast" : "thorough";

    if (typeof addMessage === "function") addMessage(displayText, "user");
    if (typeof pushChatHistory === "function") pushChatHistory(displayText);

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
        const chunk = await reader.read();
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
    } catch (e) {
      _setStatus(panel, "Verbindungsfehler", "error");
    }

    const answer = panel._orch && panel._orch.synthesis;
    if (answer && typeof addMessage === "function") {
      addMessage(answer, "system");
    }
    _scroll();
  }

  // Globals fuer chat.js (Routing) + Tests.
  window.sendOrchestratorMessage = sendOrchestratorMessage;
  window.buildOrchestratorPanel = buildOrchestratorPanel;
  window.orchestratorHandleEvent = orchestratorHandleEvent;
})();
