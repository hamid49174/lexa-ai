/* Agenten-Ansicht (Phase 48 F): Status + Run-Historie + Replay.
 * CSP-sicher (createElement/textContent/addEventListener). Reuse des Orchestrator-Renderers
 * (buildOrchestratorPanel/orchestratorHandleEvent aus chat_orchestrator.js) fuer Replays.
 */
(function () {
  "use strict";

  function _el(tag, cls, txt) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (txt != null) n.textContent = txt;
    return n;
  }

  function _fmtTime(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);
      return d.toLocaleString((typeof t === "function" && t._locale) || "de-DE", {
        day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
      });
    } catch (_) { return String(iso); }
  }

  function _renderStatus(banner, status) {
    banner.replaceChildren();
    if (!status || status.enabled === false) {
      banner.appendChild(_el("span", "agents-status-pill off", "Orchestrator deaktiviert"));
      return;
    }
    banner.appendChild(_el("span", "agents-status-pill on", "bereit"));
    const modes = (status.modes || []).join(" · ");
    if (modes) banner.appendChild(_el("span", "agents-status-meta", "Modi: " + modes));
    if (typeof status.max_subagents === "number") {
      banner.appendChild(_el("span", "agents-status-meta", "max. " + status.max_subagents + " Agenten"));
    }
    const browser = status.browser;
    if (browser) {
      const pill = _el("span", "agents-status-pill " + (browser.available ? "on" : "off"),
        "Browser: " + (browser.available ? "bereit" : "aus"));
      if (browser.reason) pill.title = browser.reason;
      banner.appendChild(pill);
    }
  }

  function _renderRunsList(listEl, runs, onSelect) {
    listEl.replaceChildren();
    if (!runs || !runs.length) {
      listEl.appendChild(_el("div", "agents-empty", "Noch keine Laeufe. Starte einen mit /orchestrate im Chat."));
      return;
    }
    runs.forEach((run) => {
      const item = _el("button", "agents-run-item");
      item.type = "button";
      const top = _el("div", "agents-run-goal", run.goal || "(ohne Titel)");
      const meta = _el("div", "agents-run-meta");
      const statusKind = run.status === "completed" ? "ok" : (run.status === "partial" ? "warn" : "");
      meta.appendChild(_el("span", "agents-run-status " + statusKind, run.status || "?"));
      if (run.mode) meta.appendChild(_el("span", "agents-run-mode", run.mode === "fast" ? "schnell" : "gruendlich"));
      if (typeof run.subagent_count === "number") meta.appendChild(_el("span", "agents-run-count", run.subagent_count + " Agenten"));
      meta.appendChild(_el("span", "agents-run-time", _fmtTime(run.created_at)));
      item.appendChild(top);
      item.appendChild(meta);
      item.addEventListener("click", () => onSelect(run.run_id, item));
      listEl.appendChild(item);
    });
  }

  async function _renderDetail(detailEl, runId) {
    detailEl.replaceChildren(_el("div", "agents-detail-loading", "lade …"));
    let run = null;
    try {
      run = await window.lexa.orchestratorRunDetail(runId);
    } catch (_) { run = null; }
    detailEl.replaceChildren();
    if (!run) {
      detailEl.appendChild(_el("div", "agents-empty", "Lauf nicht gefunden."));
      return;
    }
    // Live-Baum aus gespeicherten Events rekonstruieren.
    if (typeof window.buildOrchestratorPanel === "function" && typeof window.orchestratorHandleEvent === "function") {
      const panel = window.buildOrchestratorPanel(run.goal || "", run.mode || "thorough");
      const events = Array.isArray(run.events) ? run.events : [];
      events.forEach((ev) => window.orchestratorHandleEvent(panel, ev));
      detailEl.appendChild(panel);
    }
    // Finale Antwort.
    if (run.answer) {
      const box = _el("div", "agents-answer");
      box.appendChild(_el("div", "orchestrator-section-title", "Antwort"));
      const body = _el("div", "agents-answer-body");
      if (typeof renderFormattedMessage === "function") {
        try { renderFormattedMessage(body, String(run.answer)); }
        catch (_) { body.textContent = String(run.answer); }
      } else {
        body.textContent = String(run.answer);
      }
      box.appendChild(body);
      detailEl.appendChild(box);
    }
  }

  async function refreshAgentsView() {
    const banner = document.getElementById("agents-status-banner");
    const listEl = document.getElementById("agents-runs-list");
    const detailEl = document.getElementById("agents-detail");
    if (!listEl) return;
    if (!window.lexa || typeof window.lexa.orchestratorRuns !== "function") {
      if (banner) banner.replaceChildren(_el("span", "agents-status-pill off", "nicht verfuegbar"));
      return;
    }

    if (banner) {
      try { _renderStatus(banner, await window.lexa.orchestratorStatus()); }
      catch (_) { banner.replaceChildren(); }
    }

    listEl.replaceChildren(_el("div", "agents-detail-loading", "lade …"));
    let runs = [];
    try {
      const data = await window.lexa.orchestratorRuns(50);
      runs = (data && data.runs) || [];
    } catch (_) { runs = []; }

    _renderRunsList(listEl, runs, (runId, item) => {
      listEl.querySelectorAll(".agents-run-item.active").forEach((b) => b.classList.remove("active"));
      if (item) item.classList.add("active");
      if (detailEl) _renderDetail(detailEl, runId);
    });

    // Ersten Lauf automatisch oeffnen.
    if (detailEl) {
      if (runs.length) {
        const first = listEl.querySelector(".agents-run-item");
        if (first) first.classList.add("active");
        _renderDetail(detailEl, runs[0].run_id);
      } else {
        detailEl.replaceChildren(_el("div", "agents-empty", "Waehle links einen Lauf oder starte einen mit /orchestrate."));
      }
    }
  }

  window.refreshAgentsView = refreshAgentsView;
})();
