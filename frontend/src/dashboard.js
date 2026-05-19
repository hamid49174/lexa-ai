/* ════════════════════════════════════════════════
   LEXA AI — Dashboard Module
   Dashboard rendering and weekly chart
   Extracted from app.js
   ════════════════════════════════════════════════ */

// ── DASHBOARD ───────────────────────────────────
async function refreshDashboard() {
  const versionLabel = `v${LexaState.get("backendVersion") || "1.0.0"}`;

  // Greeting based on time of day
  const hour = new Date().getHours();
  let greeting = t("dashboard.greetingDay");
  if (hour < 6) greeting = t("dashboard.greetingNight");
  else if (hour < 12) greeting = t("dashboard.greetingMorning");
  else if (hour < 18) greeting = t("dashboard.greetingDay");
  else greeting = t("dashboard.greetingEvening");

  const greetEl = document.getElementById("dash-greeting");
  if (greetEl) greetEl.textContent = `${greeting}${t("dashboard.greetingSuffix")}`;

  if (!LexaState.get("backendOnline")) {
    const aiStatusEl = document.getElementById("dash-ai-status");
    if (aiStatusEl) aiStatusEl.innerHTML = `<span class="text-error">${t("dashboard.backendOffline")}</span>`;
    const subEl = document.getElementById("dash-greeting-sub");
    if (subEl) subEl.textContent = `Lexa AI ${versionLabel} \u2014 ${t("dashboard.backendOffline")}`;
    return;
  }

  // Fetch all dashboard data in parallel (9 requests -> single round-trip)
  const systemInfo = typeof window.requestSystemInfoCached === "function"
    ? window.requestSystemInfoCached({ maxAgeMs: 12000 })
    : window.lexa.execute("system_info");
  const [sysRes, aiRes, healthRes, memRes, routRes, todosRes, pomoRes, focusRes, modelsRes, weeklyRes] = await Promise.allSettled([
    systemInfo,
    window.lexa.aiStatus(),
    window.lexa.health(),
    window.lexa.memoryStats(),
    window.lexa.routines(),
    window.lexa.todos("open"),
    window.lexa.pomodoroStatus(),
    window.lexa.focusStatus(),
    window.lexa.aiModels(),
    window.lexa.weeklyStats(7),
  ]);

  // Greeting subtitle with model name
  const subEl = document.getElementById("dash-greeting-sub");
  if (subEl) {
    const modelName = modelsRes.status === "fulfilled" ? modelsRes.value.current_name : null;
    subEl.textContent = `Lexa AI ${versionLabel} \u2014 ${modelName || t("dashboard.localAssistant")}`;
  }

  // System stats
  if (sysRes.status === "fulfilled") {
    const res = sysRes.value;
    if (res.success && res.data) {
      const d = res.data;
      const setDash = (id, val) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = val + "%";
        applyMetricTone(el, val);
        const bar = document.getElementById(id + "-bar");
        if (bar) applyMeterClass(bar, val, metricToneClass(val));
      };
      setDash("dash-cpu", d.cpu_percent);
      setDash("dash-ram", d.ram_percent);
      setDash("dash-disk", d.disk_percent);
      const battEl = document.getElementById("dash-battery");
      if (battEl) {
        const bv = d.battery_percent !== null ? d.battery_percent : "--";
        battEl.textContent = bv + "%";
        if (bv !== "--") applyMetricTone(battEl, bv <= 30 ? 90 : 20, "metric-success");
        const battBar = document.getElementById("dash-battery-bar");
        if (battBar && bv !== "--") applyMeterClass(battBar, bv, bv > 30 ? "meter-success" : "meter-error");
      }
    }
  }

  // AI status
  if (aiRes.status === "fulfilled") {
    const ai = aiRes.value;
    const aiEl = document.getElementById("dash-ai-status");
    if (aiEl) {
      const providers = [
        ["groq", "Groq"],
        ["openai", "OpenAI"],
        ["gemini", "Gemini"],
        ["anthropic", "Claude"],
      ];
      const activeLabel = providers.find(([key]) => key === ai.active_provider)?.[1] || escapeHtml(String(ai.active_provider || t("dashboard.unknownProvider")));
      const rows = providers.map(([key, label]) => {
        const ok = ai[key]?.available;
        const dot = ok ? '<span class="dash-dot active"></span>' : '<span class="dash-dot"></span>';
        return `<div class="dash-ai-row">${dot} ${label} <span class="dash-ai-tag">${ok ? t("dashboard.aiReady") : t("dashboard.aiOffline")}</span></div>`;
      }).join("");
      const fallbackCount = Array.isArray(ai.fallback_available) ? ai.fallback_available.length : 0;
      const fallbackRow = ai.fallback_enabled
        ? `<div class="dash-ai-row">${fallbackCount ? '<span class="dash-dot active"></span>' : '<span class="dash-dot"></span>'} ${escapeHtml(t("dashboard.aiFallback"))} <span class="dash-ai-tag">${fallbackCount ? escapeHtml(t("dashboard.aiReady")) : escapeHtml(t("dashboard.aiOffline"))}</span></div>`
        : "";
      const hermes = healthRes.status === "fulfilled" ? healthRes.value?.hermes : null;
      const hermesReady = Boolean(hermes?.can_run_tasks);
      const hermesState = hermes?.state || "unknown";
      const hermesRow = hermes
        ? `<div class="dash-ai-row">${hermesReady ? '<span class="dash-dot active"></span>' : '<span class="dash-dot"></span>'} Hermes <span class="dash-ai-tag">${escapeHtml(hermesState === "ready" ? t("dashboard.aiReady") : hermesState === "attention" ? t("dashboard.needsAttention") : t("dashboard.aiOffline"))}</span></div>`
        : "";
      aiEl.innerHTML = `
        ${rows}
        ${fallbackRow}
        ${hermesRow}
        <div class="dash-ai-provider">${t("dashboard.aiActive")}: <strong>${activeLabel}</strong></div>
      `;
    }
  }

  // Memory stats
  if (memRes.status === "fulfilled") {
    const mem = memRes.value;
    const memEl = document.getElementById("dash-memory-stats");
    if (memEl) {
      memEl.innerHTML = `
        <div class="dash-mem-grid">
          <div class="dash-mem-item"><span class="dash-mem-num">${mem.notes || 0}</span>${t("dashboard.memNotes")}</div>
          <div class="dash-mem-item"><span class="dash-mem-num">${mem.memories || 0}</span>${t("dashboard.memReminders")}</div>
          <div class="dash-mem-item"><span class="dash-mem-num">${mem.interactions || 0}</span>${t("dashboard.memChats")}</div>
          <div class="dash-mem-item"><span class="dash-mem-num">${mem.routines || 0}</span>${t("dashboard.memRoutines")}</div>
        </div>
      `;
    }
  }

  // Routines
  if (routRes.status === "fulfilled") {
    const routinesData = routRes.value;
    const routEl = document.getElementById("dash-routines-list");
    if (routEl) {
      if (routinesData.routines?.length > 0) {
        routEl.innerHTML = routinesData.routines.map(r => `
          <div class="dash-routine-item">
            <span class="dash-routine-dot ${r.enabled ? "active" : ""}"></span>
            <span class="dash-routine-name">${escapeHtml(String(r.name || ""))}</span>
            <span class="dash-routine-time">${escapeHtml(String(r.schedule || ""))}</span>
          </div>
        `).join("");
      } else {
        routEl.innerHTML = `<div class="dash-empty">${t("dashboard.noRoutines")}</div>`;
      }
    }
  }

  // Productivity stats
  {
    const prodEl = document.getElementById("dash-productivity-stats");
    if (prodEl) {
      const todos = todosRes.status === "fulfilled" ? todosRes.value : { todos: [] };
      const pomo = pomoRes.status === "fulfilled" ? pomoRes.value : { running: false };
      const focus = focusRes.status === "fulfilled" ? focusRes.value : { active: false };
      const pendingCount = todos.todos?.length ?? 0;
      const pomRunning = pomo.running;
      const focusOn = focus.active;

      let pomLabel = t("dashboard.noPomodoro");
      let pomClass = "off";
      if (pomRunning && pomo.remaining_sec != null) {
        const m = Math.floor(pomo.remaining_sec / 60);
        const s = pomo.remaining_sec % 60;
        pomLabel = t("dashboard.pomodoroRemaining", {time: `${m}:${String(s).padStart(2, "0")}`});
        pomClass = "ok";
      } else if (pomRunning) {
        pomLabel = t("dashboard.pomodoroRunning");
        pomClass = "ok";
      }

      prodEl.innerHTML = `
        <div class="dash-prod-row${pendingCount > 0 ? " warn" : ""}">
          <span class="dash-prod-label">&#9744; ${t("dashboard.openTasks")}</span>
          <span class="dash-prod-value${pendingCount > 5 ? " warn" : " ok"}">${pendingCount}</span>
        </div>
        <div class="dash-prod-row${pomRunning ? " active" : ""}">
          <span class="dash-prod-label">&#9203; Pomodoro</span>
          <span class="dash-prod-value ${pomClass}">${pomLabel}</span>
        </div>
        <div class="dash-prod-row${focusOn ? " active" : ""}">
          <span class="dash-prod-label">&#127919; ${t("focus.mode")}</span>
          <span class="dash-prod-value${focusOn ? " ok" : " off"}">${focusOn ? t("dashboard.focusActive") : t("dashboard.focusOff")}</span>
        </div>
      `;

      // Keep quick-action button in sync with pomodoro state
      const pomoBtn = document.getElementById("dash-btn-pomo");
      if (pomoBtn) pomoBtn.textContent = pomRunning ? "\u23F9 Stop" : "\u23F1 Pomodoro";

      // Update sidebar todo badge
      const todoBadge = document.getElementById("nav-todo-badge");
      if (todoBadge) {
        if (pendingCount > 0) {
          todoBadge.textContent = pendingCount > 99 ? "99+" : pendingCount;
          todoBadge.classList.remove("hidden");
        } else {
          todoBadge.classList.add("hidden");
        }
      }
    }
  }

  // Weekly chart
  {
    const chartEl = document.getElementById("dash-weekly-chart");
    if (chartEl && weeklyRes.status === "fulfilled") {
      const days = weeklyRes.value?.days || [];
      renderWeeklyChart(chartEl, days);
    }
  }
}

function renderWeeklyChart(container, days) {
  if (!days.length) { container.textContent = t("empty.noData"); return; }

  // Find max value across all metrics for scaling
  const maxVal = Math.max(1, ...days.map(d => Math.max(d.todos_done, d.pomodoros, d.habits_done)));

  container.innerHTML = "";

  // Legend
  const legend = document.createElement("div");
  legend.className = "weekly-legend";
  [["weekly-bar-todos", t("dashboard.chartTodos")], ["weekly-bar-pomo", t("dashboard.chartPomodoros")], ["weekly-bar-habits", t("dashboard.chartHabits")]].forEach(([cls, label]) => {
    const item = document.createElement("span");
    item.className = "weekly-legend-item";
    const dot = document.createElement("span");
    dot.className = "weekly-legend-dot " + cls;
    item.appendChild(dot);
    item.appendChild(document.createTextNode(label));
    legend.appendChild(item);
  });
  container.appendChild(legend);

  // Chart
  const chart = document.createElement("div");
  chart.className = "weekly-chart-bars";

  days.forEach(day => {
    const col = document.createElement("div");
    col.className = "weekly-col";

    // Three bars per day
    const barsWrap = document.createElement("div");
    barsWrap.className = "weekly-bars-group";

    [
      { val: day.todos_done, cls: "weekly-bar-todos", title: t("dashboard.chartTodosDone", {count: day.todos_done}) },
      { val: day.pomodoros, cls: "weekly-bar-pomo", title: t("dashboard.chartPomodorosCount", {count: day.pomodoros}) },
      { val: day.habits_done, cls: "weekly-bar-habits", title: t("dashboard.chartHabitsCount", {count: day.habits_done}) },
    ].forEach(({ val, cls, title }) => {
      const barWrap = document.createElement("div");
      barWrap.className = "weekly-bar-wrap";
      const bar = document.createElement("div");
      bar.className = "weekly-bar " + cls;
      const pct = maxVal > 0 ? Math.round((val / maxVal) * 100) : 0;
      applyChartHeightClass(bar, Math.max(pct, val > 0 ? 8 : 0));
      bar.title = title;
      if (val > 0) {
        const num = document.createElement("span");
        num.className = "weekly-bar-num";
        num.textContent = val;
        bar.appendChild(num);
      }
      barWrap.appendChild(bar);
      barsWrap.appendChild(barWrap);
    });

    col.appendChild(barsWrap);

    const lbl = document.createElement("div");
    lbl.className = "weekly-label";
    lbl.textContent = day.label;
    col.appendChild(lbl);

    chart.appendChild(col);
  });

  container.appendChild(chart);
}

function clampPercent(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return 0;
  return Math.max(0, Math.min(100, Math.round(num)));
}

function percentBucket(value) {
  return Math.round(clampPercent(value) / 5) * 5;
}

function metricToneClass(value) {
  const pct = clampPercent(value);
  if (pct > 80) return "meter-error";
  if (pct > 60) return "meter-warning";
  return "meter-accent";
}

function applyMetricTone(el, value, successClass = "") {
  el.classList.remove("stat-danger", "stat-warn", "metric-success");
  const pct = clampPercent(value);
  if (successClass) {
    el.classList.add(successClass);
  } else if (pct > 80) {
    el.classList.add("stat-danger");
  } else if (pct > 60) {
    el.classList.add("stat-warn");
  }
}

function applyMeterClass(el, value, toneClass = "meter-accent") {
  const classes = Array.from(el.classList).filter((cls) => cls.startsWith("meter-width-") || cls.startsWith("meter-"));
  if (classes.length) el.classList.remove(...classes);
  el.classList.add(`meter-width-${percentBucket(value)}`, toneClass);
}

function applyChartHeightClass(el, value) {
  const classes = Array.from(el.classList).filter((cls) => cls.startsWith("chart-height-"));
  if (classes.length) el.classList.remove(...classes);
  el.classList.add(`chart-height-${percentBucket(value)}`);
}
