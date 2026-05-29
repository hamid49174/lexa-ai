/* ════════════════════════════════════════════════
   LEXA AI — Dashboard Module
   Dashboard rendering and weekly chart
   Extracted from app.js
   ════════════════════════════════════════════════ */

// ── DASHBOARD ───────────────────────────────────
function setDashboardAiStatusMessage(target, message, className = "") {
  if (!target) return;
  const span = document.createElement("span");
  if (className) span.className = className;
  span.textContent = message;
  target.replaceChildren(span);
}

function createDashboardAiRow(label, status, active = false) {
  const row = document.createElement("div");
  row.className = "dash-ai-row";
  const dot = document.createElement("span");
  dot.className = active ? "dash-dot active" : "dash-dot";
  const labelNode = document.createTextNode(` ${label} `);
  const tag = document.createElement("span");
  tag.className = "dash-ai-tag";
  tag.textContent = status;
  row.append(dot, labelNode, tag);
  return row;
}

function renderDashboardAiStatus(target, ai, hermes) {
  if (!target) return;
  const providers = [
    ["groq", "Groq"],
    ["openai", "OpenAI"],
    ["gemini", "Gemini"],
    ["anthropic", "Claude"],
  ];
  const activeProvider = String(ai?.active_provider || "");
  const activeLabel = providers.find(([key]) => key === activeProvider)?.[1] || activeProvider || t("dashboard.unknownProvider");
  const fragment = document.createDocumentFragment();

  providers.forEach(([key, label]) => {
    const ok = Boolean(ai?.[key]?.available);
    fragment.appendChild(createDashboardAiRow(label, ok ? t("dashboard.aiReady") : t("dashboard.aiOffline"), ok));
  });

  const fallbackCount = Array.isArray(ai?.fallback_available) ? ai.fallback_available.length : 0;
  if (ai?.fallback_enabled) {
    fragment.appendChild(createDashboardAiRow(
      t("dashboard.aiFallback"),
      fallbackCount ? t("dashboard.aiReady") : t("dashboard.aiOffline"),
      Boolean(fallbackCount),
    ));
  }

  if (hermes) {
    const hermesReady = Boolean(hermes.can_run_tasks);
    const hermesState = String(hermes.state || "unknown");
    const hermesLabel = hermesState === "ready"
      ? t("dashboard.aiReady")
      : hermesState === "attention" ? t("dashboard.needsAttention") : t("dashboard.aiOffline");
    fragment.appendChild(createDashboardAiRow("Hermes", hermesLabel, hermesReady));
  }

  const providerRow = document.createElement("div");
  providerRow.className = "dash-ai-provider";
  providerRow.append(document.createTextNode(`${t("dashboard.aiActive")}: `));
  const activeStrong = document.createElement("strong");
  activeStrong.textContent = activeLabel;
  providerRow.appendChild(activeStrong);
  fragment.appendChild(providerRow);

  target.replaceChildren(fragment);
}

function createDashboardRoutineItem(routine) {
  const item = document.createElement("div");
  item.className = "dash-routine-item";
  const dot = document.createElement("span");
  dot.className = routine?.enabled ? "dash-routine-dot active" : "dash-routine-dot";
  const nameEl = document.createElement("span");
  nameEl.className = "dash-routine-name";
  nameEl.textContent = String(routine?.name || "");
  const timeEl = document.createElement("span");
  timeEl.className = "dash-routine-time";
  timeEl.textContent = String(routine?.schedule || "");
  item.append(dot, nameEl, timeEl);
  return item;
}

function renderDashboardRoutines(target, routines) {
  if (!target) return;
  if (!Array.isArray(routines) || routines.length === 0) {
    const empty = document.createElement("div");
    empty.className = "dash-empty";
    empty.textContent = t("dashboard.noRoutines");
    target.replaceChildren(empty);
    return;
  }
  const fragment = document.createDocumentFragment();
  routines.forEach((routine) => {
    fragment.appendChild(createDashboardRoutineItem(routine));
  });
  target.replaceChildren(fragment);
}

function dashboardTodoCount(todos) {
  return Array.isArray(todos?.todos) ? todos.todos.length : 0;
}

function dashboardPomodoroState(pomo) {
  const running = Boolean(pomo?.running);
  if (!running) return { running: false, label: t("dashboard.noPomodoro"), valueClass: "off" };
  const remaining = Number(pomo?.remaining_sec);
  if (Number.isFinite(remaining) && remaining >= 0) {
    const totalSeconds = Math.floor(remaining);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return {
      running: true,
      label: t("dashboard.pomodoroRemaining", {time: `${minutes}:${String(seconds).padStart(2, "0")}`}),
      valueClass: "ok",
    };
  }
  return { running: true, label: t("dashboard.pomodoroRunning"), valueClass: "ok" };
}

function createDashboardProductivityRow(label, value, rowClass = "", valueClass = "") {
  const row = document.createElement("div");
  row.className = rowClass ? `dash-prod-row ${rowClass}` : "dash-prod-row";
  const labelEl = document.createElement("span");
  labelEl.className = "dash-prod-label";
  labelEl.textContent = label;
  const valueEl = document.createElement("span");
  valueEl.className = valueClass ? `dash-prod-value ${valueClass}` : "dash-prod-value";
  valueEl.textContent = value;
  row.append(labelEl, valueEl);
  return row;
}

function renderDashboardProductivityStats(target, todos, pomo, focus) {
  const pendingCount = dashboardTodoCount(todos);
  const pomodoro = dashboardPomodoroState(pomo);
  const focusOn = Boolean(focus?.active);
  if (!target) return { pendingCount, pomRunning: pomodoro.running };

  const fragment = document.createDocumentFragment();
  fragment.appendChild(createDashboardProductivityRow(
    `\u2610 ${t("dashboard.openTasks")}`,
    String(pendingCount),
    pendingCount > 0 ? "warn" : "",
    pendingCount > 5 ? "warn" : "ok",
  ));
  fragment.appendChild(createDashboardProductivityRow(
    "\u23F3 Pomodoro",
    pomodoro.label,
    pomodoro.running ? "active" : "",
    pomodoro.valueClass,
  ));
  fragment.appendChild(createDashboardProductivityRow(
    `\u{1F3AF} ${t("focus.mode")}`,
    focusOn ? t("dashboard.focusActive") : t("dashboard.focusOff"),
    focusOn ? "active" : "",
    focusOn ? "ok" : "off",
  ));
  target.replaceChildren(fragment);
  return { pendingCount, pomRunning: pomodoro.running };
}

function createDashboardMemoryItem(count, label) {
  const item = document.createElement("div");
  item.className = "dash-mem-item";
  const countEl = document.createElement("span");
  countEl.className = "dash-mem-num";
  countEl.textContent = count;
  item.append(countEl, document.createTextNode(label));
  return item;
}

function renderDashboardMemoryStats(target, mem) {
  if (!target) return;
  const grid = document.createElement("div");
  grid.className = "dash-mem-grid";
  grid.append(
    createDashboardMemoryItem(dashCount(mem?.notes), t("dashboard.memNotes")),
    createDashboardMemoryItem(dashCount(mem?.memories), t("dashboard.memReminders")),
    createDashboardMemoryItem(dashCount(mem?.interactions), t("dashboard.memChats")),
    createDashboardMemoryItem(dashCount(mem?.routines), t("dashboard.memRoutines")),
  );
  target.replaceChildren(grid);
}

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
    setDashboardAiStatusMessage(aiStatusEl, t("dashboard.backendOffline"), "text-error");
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
        const pct = dashPercent(val);
        el.textContent = pct + "%";
        applyMetricTone(el, pct);
        const bar = document.getElementById(id + "-bar");
        if (bar) applyMeterClass(bar, pct, metricToneClass(pct));
      };
      setDash("dash-cpu", d.cpu_percent);
      setDash("dash-ram", d.ram_percent);
      setDash("dash-disk", d.disk_percent);
      const battEl = document.getElementById("dash-battery");
      if (battEl) {
        const bv = dashBatteryPercent(d.battery_percent);
        battEl.textContent = bv !== null ? bv + "%" : "--";
        if (bv !== null) applyMetricTone(battEl, bv <= 30 ? 90 : 20, "metric-success");
        const battBar = document.getElementById("dash-battery-bar");
        if (battBar && bv !== null) applyMeterClass(battBar, bv, bv > 30 ? "meter-success" : "meter-error");
      }
    }
  }

  // AI status
  if (aiRes.status === "fulfilled") {
    const ai = aiRes.value;
    const aiEl = document.getElementById("dash-ai-status");
    if (aiEl) {
      const hermes = healthRes.status === "fulfilled" ? healthRes.value?.hermes : null;
      renderDashboardAiStatus(aiEl, ai, hermes);
    }
  }

  // Memory stats
  if (memRes.status === "fulfilled") {
    const mem = memRes.value;
    const memEl = document.getElementById("dash-memory-stats");
    renderDashboardMemoryStats(memEl, mem);
  }

  // Routines
  if (routRes.status === "fulfilled") {
    const routinesData = routRes.value;
    const routEl = document.getElementById("dash-routines-list");
    renderDashboardRoutines(routEl, routinesData.routines);
  }

  // Productivity stats
  {
    const prodEl = document.getElementById("dash-productivity-stats");
    if (prodEl) {
      const todos = todosRes.status === "fulfilled" ? todosRes.value : { todos: [] };
      const pomo = pomoRes.status === "fulfilled" ? pomoRes.value : { running: false };
      const focus = focusRes.status === "fulfilled" ? focusRes.value : { active: false };
      const { pendingCount, pomRunning } = renderDashboardProductivityStats(prodEl, todos, pomo, focus);

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

function dashCount(value) {
  const count = Number(value);
  if (!Number.isFinite(count) || count < 0) return "0";
  return String(Math.floor(count));
}

function dashChartCount(value) {
  const count = Number(value);
  if (!Number.isFinite(count) || count < 0) return 0;
  return Math.floor(count);
}

function dashPercent(value) {
  return clampPercent(value);
}

function dashBatteryPercent(value) {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return clampPercent(num);
}

function renderWeeklyChart(container, days) {
  const safeDays = Array.isArray(days) ? days.map((day) => ({
    label: String(day?.label || ""),
    todosDone: dashChartCount(day?.todos_done),
    pomodoros: dashChartCount(day?.pomodoros),
    habitsDone: dashChartCount(day?.habits_done),
  })) : [];
  if (!safeDays.length) { container.textContent = t("empty.noData"); return; }

  // Find max value across all metrics for scaling
  const maxVal = Math.max(1, ...safeDays.map(d => Math.max(d.todosDone, d.pomodoros, d.habitsDone)));

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
  // Chart
  const chart = document.createElement("div");
  chart.className = "weekly-chart-bars";

  safeDays.forEach(day => {
    const col = document.createElement("div");
    col.className = "weekly-col";

    // Three bars per day
    const barsWrap = document.createElement("div");
    barsWrap.className = "weekly-bars-group";

    [
      { val: day.todosDone, cls: "weekly-bar-todos", title: t("dashboard.chartTodosDone", {count: day.todosDone}) },
      { val: day.pomodoros, cls: "weekly-bar-pomo", title: t("dashboard.chartPomodorosCount", {count: day.pomodoros}) },
      { val: day.habitsDone, cls: "weekly-bar-habits", title: t("dashboard.chartHabitsCount", {count: day.habitsDone}) },
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

  container.replaceChildren(legend, chart);
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
