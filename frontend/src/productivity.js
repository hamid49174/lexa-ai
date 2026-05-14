/* ════════════════════════════════════════════════
   LEXA AI — Productivity Module
   Todo, Pomodoro, Habits, Time Tracking, Focus Mode
   Extracted from app.js (Phase 19 functions)
   ════════════════════════════════════════════════ */

// ── PRODUCTIVITY VIEW ────────────────────────────

async function refreshProductivityView() {
  if (!LexaState.get("backendOnline")) return;
  // All sub-refreshes run in parallel for faster view loading
  await Promise.allSettled([
    refreshProdStats(),
    refreshTodos(),
    refreshPomodoro(),
    refreshHabits(),
    refreshTimeTracking(),
  ]);
}

async function refreshProdStats() {
  try {
    const stats = await window.lexa.productivityStats();
    const bar = document.getElementById("prod-stats-bar");
    if (!bar) return;
    bar.innerHTML = `
      <div class="prod-stat-card">
        <div class="prod-stat-value">${stats.open_todos || 0}</div>
        <div class="prod-stat-label">${t("productivity.statOpenTodos")}</div>
      </div>
      <div class="prod-stat-card">
        <div class="prod-stat-value">${stats.done_today || 0}</div>
        <div class="prod-stat-label">${t("productivity.statDoneToday")}</div>
      </div>
      <div class="prod-stat-card">
        <div class="prod-stat-value">${stats.pomodoros_today || 0}</div>
        <div class="prod-stat-label">${t("productivity.statPomodoros")}</div>
      </div>
      <div class="prod-stat-card">
        <div class="prod-stat-value">${stats.habits_done_today || 0}/${stats.habits_total || 0}</div>
        <div class="prod-stat-label">${t("productivity.statHabits")}</div>
      </div>
      <div class="prod-stat-card ${stats.focus_mode ? 'prod-stat-active' : ''}">
        <div class="prod-stat-value">${stats.focus_mode ? t("productivity.focusOn") : t("productivity.focusOff")}</div>
        <div class="prod-stat-label">${t("productivity.statFocusMode")}</div>
      </div>
    `;
  } catch (e) { console.warn("[Productivity] Failed to refresh stats:", e.message || e); }
}

// ── TODOS ──

async function refreshTodos() {
  try {
    const filter = document.getElementById("todo-filter")?.value || "";
    const data = await window.lexa.todos(filter);
    const list = document.getElementById("todo-list");
    if (!list) return;
    list.innerHTML = "";
    if (!data.todos || data.todos.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = t("empty.noTodos");
      list.appendChild(empty);
      return;
    }
    data.todos.forEach(td => {
      const priorityClass = td.priority === "urgent" ? "priority-urgent" :
        td.priority === "high" ? "priority-high" :
          td.priority === "low" ? "priority-low" : "";
      const statusIcon = td.status === "done" ? "\u2713" :
        td.status === "in_progress" ? "\u25b6" : "\u25cb";

      // Check if overdue
      let isOverdue = false;
      if (td.due_date && td.status !== "done") {
        const due = new Date(td.due_date);
        due.setHours(23, 59, 59, 999);
        isOverdue = due < new Date();
      }

      const item = document.createElement("div");
      item.className = `todo-item${td.status === "done" ? " todo-done" : ""}${priorityClass ? " " + priorityClass : ""}${isOverdue ? " todo-overdue" : ""}`;
      item.dataset.id = td.id;

      // Check/complete button
      const checkBtn = document.createElement("button");
      checkBtn.className = "todo-check";
      checkBtn.title = t("productivity.complete");
      checkBtn.textContent = statusIcon;
      checkBtn.addEventListener("click", () => completeTodo(td.id));
      item.appendChild(checkBtn);

      // Content area (double-click to inline edit)
      const content = document.createElement("div");
      content.className = "todo-content";

      const titleEl = document.createElement("div");
      titleEl.className = "todo-title";
      titleEl.textContent = td.title || "";
      titleEl.title = t("productivity.dblClickEdit");
      titleEl.addEventListener("dblclick", () => startTodoInlineEdit(td.id, titleEl, td.title));
      content.appendChild(titleEl);

      if (td.description) {
        const descEl = document.createElement("div");
        descEl.className = "todo-desc";
        descEl.textContent = td.description;
        content.appendChild(descEl);
      }

      const meta = document.createElement("div");
      meta.className = "todo-meta";
      const prioSpan = document.createElement("span");
      prioSpan.className = "todo-priority";
      prioSpan.textContent = td.priority || "normal";
      meta.appendChild(prioSpan);
      if (td.category) {
        const catSpan = document.createElement("span");
        catSpan.className = "todo-category";
        catSpan.textContent = td.category;
        meta.appendChild(catSpan);
      }
      if (td.due_date) {
        const dueSpan = document.createElement("span");
        dueSpan.className = `todo-due${isOverdue ? " todo-due-overdue" : ""}`;
        dueSpan.textContent = (isOverdue ? "\u26a0 " : "") + t("productivity.duePrefix") + td.due_date;
        meta.appendChild(dueSpan);
      }
      content.appendChild(meta);
      item.appendChild(content);

      // Action buttons
      const actions = document.createElement("div");
      actions.className = "todo-actions";
      if (td.status !== "done") {
        const progressBtn = document.createElement("button");
        progressBtn.className = "todo-action-btn";
        progressBtn.title = t("productivity.inProgress");
        progressBtn.textContent = "\u25b6";
        progressBtn.addEventListener("click", () => setTodoStatus(td.id, "in_progress"));
        actions.appendChild(progressBtn);
      }
      const delBtn = document.createElement("button");
      delBtn.className = "todo-action-btn todo-delete";
      delBtn.title = t("productivity.deleteBtn");
      delBtn.textContent = "\u2715";
      delBtn.addEventListener("click", () => deleteTodo(td.id));
      actions.appendChild(delBtn);
      item.appendChild(actions);

      list.appendChild(item);
    });
  } catch (e) { console.warn("[Productivity] Failed to refresh todos:", e.message || e); }
}

function filterTodosLocal(query) {
  const items = document.querySelectorAll("#todo-list .todo-item");
  const q = query.toLowerCase().trim();
  items.forEach(item => {
    const title = item.querySelector(".todo-title")?.textContent.toLowerCase() || "";
    const desc = item.querySelector(".todo-desc")?.textContent.toLowerCase() || "";
    item.classList.toggle("hidden", !(!q || title.includes(q) || desc.includes(q)));
  });
}

function startTodoInlineEdit(id, titleEl, currentTitle) {
  if (titleEl.querySelector("input")) return; // already editing
  const input = document.createElement("input");
  input.type = "text";
  input.value = currentTitle || "";
  input.className = "todo-inline-input";
  titleEl.textContent = "";
  titleEl.appendChild(input);
  input.focus();
  input.select();
  const save = async () => {
    const newTitle = input.value.trim();
    if (newTitle && newTitle !== currentTitle) {
      await window.lexa.todoUpdate(id, { title: newTitle });
      showToast(t("todo.updated"), "success");
    }
    refreshTodos();
  };
  input.addEventListener("blur", save);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); save(); }
    if (e.key === "Escape") { refreshTodos(); }
  });
}

function createTodo(prefillTitle = "") {
  document.getElementById("todo-create-modal")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "todo-create-modal";
  overlay.className = "note-modal-overlay";

  const panel = document.createElement("div");
  panel.className = "note-modal-panel note-modal-panel-narrow";

  const header = document.createElement("div");
  header.className = "note-modal-header";
  const hTitle = document.createElement("div");
  hTitle.className = "note-modal-heading";
  hTitle.textContent = t("productivity.newTodoTitle");
  header.appendChild(hTitle);
  const closeBtn = document.createElement("button");
  closeBtn.className = "note-modal-close";
  closeBtn.textContent = "\u00d7";
  closeBtn.addEventListener("click", () => { overlay.remove(); document.removeEventListener("keydown", escHandler); });
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const form = document.createElement("div");
  form.className = "note-modal-form";

  const titleInput = document.createElement("input");
  titleInput.type = "text";
  titleInput.placeholder = t("productivity.titlePlaceholder");
  titleInput.className = "settings-input";
  titleInput.value = prefillTitle;
  form.appendChild(titleInput);

  const descInput = document.createElement("input");
  descInput.type = "text";
  descInput.placeholder = t("productivity.descPlaceholder");
  descInput.className = "settings-input";
  form.appendChild(descInput);

  const row = document.createElement("div");
  row.className = "note-modal-row";

  const prioSel = document.createElement("select");
  prioSel.className = "settings-select note-modal-flex";
  [["normal", t("productivity.priorityNormal")], ["low", t("productivity.priorityLow")], ["high", t("productivity.priorityHigh")], ["urgent", t("productivity.priorityUrgent")]].forEach(([val, label]) => {
    const opt = document.createElement("option");
    opt.value = val;
    opt.textContent = label;
    prioSel.appendChild(opt);
  });
  row.appendChild(prioSel);

  const dueInput = document.createElement("input");
  dueInput.type = "date";
  dueInput.className = "settings-input note-modal-flex";
  row.appendChild(dueInput);
  form.appendChild(row);

  const catInput = document.createElement("input");
  catInput.type = "text";
  catInput.placeholder = t("productivity.categoryPlaceholder");
  catInput.className = "settings-input";
  form.appendChild(catInput);
  panel.appendChild(form);

  const footer = document.createElement("div");
  footer.className = "note-modal-footer";
  const saveBtn = document.createElement("button");
  saveBtn.className = "action-btn";
  saveBtn.textContent = t("productivity.createBtn");
  saveBtn.addEventListener("click", async () => {
    const title = titleInput.value.trim();
    if (!title) { showToast(t("todo.titleEmpty"), "error"); return; }
    const todo = {
      title,
      priority: prioSel.value,
      description: descInput.value.trim() || undefined,
      due_date: dueInput.value || undefined,
      category: catInput.value.trim() || undefined,
    };
    await window.lexa.todoCreate(todo);
    showToast(t("todo.created"), "success");
    overlay.remove();
    document.removeEventListener("keydown", escHandler);
    if (LexaState.get("currentView") === "productivity") { refreshTodos(); refreshProdStats(); }
    // Update sidebar badge
    const pendingRes = await window.lexa.todos("open").catch(() => ({ todos: [] }));
    const pendingCount = (pendingRes.todos || []).length;
    const badge = document.getElementById("nav-todo-badge");
    if (badge) {
      badge.textContent = pendingCount > 99 ? "99+" : pendingCount;
      pendingCount > 0 ? badge.classList.remove("hidden") : badge.classList.add("hidden");
    }
  });
  footer.appendChild(saveBtn);
  const cancelBtn = document.createElement("button");
  cancelBtn.className = "action-btn action-btn-secondary";
  cancelBtn.textContent = t("common.cancel");
  cancelBtn.addEventListener("click", () => { overlay.remove(); document.removeEventListener("keydown", escHandler); });
  footer.appendChild(cancelBtn);
  panel.appendChild(footer);
  overlay.appendChild(panel);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) { overlay.remove(); document.removeEventListener("keydown", escHandler); } });
  const escHandler = (e) => { if (e.key === "Escape") { overlay.remove(); document.removeEventListener("keydown", escHandler); } };
  document.addEventListener("keydown", escHandler);
  document.body.appendChild(overlay);
  titleInput.focus();
}

async function completeTodo(id) {
  await window.lexa.todoComplete(id);
  showToast(t("todo.completed"), "success");
  refreshTodos();
  refreshProdStats();
}

async function setTodoStatus(id, status) {
  await window.lexa.todoUpdate(id, { status });
  refreshTodos();
}

async function deleteTodo(id) {
  await window.lexa.todoDelete(id);
  showToast(t("todo.deleted"), "info");
  refreshTodos();
  refreshProdStats();
}

async function exportTodos() {
  try {
    const data = await window.lexa.todos("");
    const todos = data.todos || [];
    if (todos.length === 0) { showToast(t("todo.noTodosExport"), "warning"); return; }
    const statusIcon = s => s === "done" ? "[x]" : s === "in_progress" ? "[~]" : "[ ]";
    const lines = [
      `# ${t("productivity.todoExportTitle")}`,
      t("productivity.exportDate", {date: new Date().toLocaleDateString("de-DE")}),
      "",
    ];
    const byPriority = { urgent: [], high: [], normal: [], low: [] };
    todos.forEach(td => { (byPriority[td.priority] || byPriority.normal).push(td); });
    const order = ["urgent", "high", "normal", "low"];
    const labels = { urgent: t("productivity.priorityUrgent"), high: t("productivity.priorityHigh"), normal: t("productivity.priorityNormal"), low: t("productivity.priorityLow") };
    order.forEach(p => {
      if (byPriority[p].length === 0) return;
      lines.push(`## ${labels[p]}`);
      byPriority[p].forEach(td => {
        lines.push(`- ${statusIcon(td.status)} **${td.title}**${td.description ? " \u2014 " + td.description : ""}${td.due_date ? " _(" + t("productivity.exportDuePrefix") + td.due_date + ")_" : ""}`);
      });
      lines.push("");
    });
    const md = lines.join("\n");
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `todos_${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
    showToast(t("todo.exported", {count: todos.length}), "success");
  } catch (e) {
    showToast(t("todo.exportFailed", {error: e.message}), "error");
  }
}

// ── POMODORO ──

// Client-side pomodoro state to avoid 1 HTTP request/second
let _pomoLocal = { remaining: 0, total: 0, task: "", running: false, lastSync: 0 };
const _POMO_SYNC_INTERVAL = 15000; // sync with backend every 15s

function _renderPomodoroDisplay(remaining, total, task) {
  const display = document.getElementById("pomodoro-display");
  const controls = document.getElementById("pomodoro-controls");
  if (!display || !controls) return;
  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;
  const elapsed = total - remaining;
  const progress = Math.min(1, Math.max(0, total > 0 ? elapsed / total : 0));
  const circumference = 2 * Math.PI * 52;
  const dashoffset = circumference * (1 - progress);
  display.innerHTML = `
    <div class="pomodoro-timer">
      <div class="pomodoro-ring-wrap">
        <svg class="pomodoro-ring" width="130" height="130" viewBox="0 0 120 120">
          <circle class="pomo-ring-bg" cx="60" cy="60" r="52" fill="none" stroke-width="8"/>
          <circle class="pomo-ring-fill" cx="60" cy="60" r="52" fill="none" stroke-width="8"
            stroke-dasharray="${circumference.toFixed(1)}" stroke-dashoffset="${dashoffset.toFixed(1)}"
            transform="rotate(-90 60 60)"/>
        </svg>
        <div class="pomodoro-ring-text">
          <div class="pomodoro-time">${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}</div>
          <div class="pomodoro-pct">${Math.round(progress * 100)}%</div>
        </div>
      </div>
      <div class="pomodoro-task">${escapeHtml(String(task || t("productivity.noTask")))}</div>
    </div>
  `;
  controls.innerHTML = "";
  const stopBtn = document.createElement("button");
  stopBtn.className = "action-btn action-btn-danger";
  stopBtn.textContent = "Stop";
  stopBtn.addEventListener("click", stopPomodoro);
  controls.appendChild(stopBtn);
}

function _pomoClientTick() {
  if (!_pomoLocal.running) return;
  _pomoLocal.remaining = Math.max(0, _pomoLocal.remaining - 1);
  _renderPomodoroDisplay(_pomoLocal.remaining, _pomoLocal.total, _pomoLocal.task);
  // Sync with backend periodically (not every second)
  if (Date.now() - _pomoLocal.lastSync > _POMO_SYNC_INTERVAL) {
    _pomoLocal.lastSync = Date.now();
    refreshPomodoro(); // async, doesn't block the tick
  }
  if (_pomoLocal.remaining <= 0) {
    _pomoLocal.running = false;
    LexaState.clearInterval("pomodoro");
    playBeep("pomodoro");
    showToast(t("productivity.pomodoroFinished"), "success");
    refreshPomodoro();
  }
}

async function refreshPomodoro() {
  try {
    const status = await window.lexa.pomodoroStatus();
    const display = document.getElementById("pomodoro-display");
    const controls = document.getElementById("pomodoro-controls");
    if (!display || !controls) return;

    if (status.running) {
      // Sync local state from backend
      _pomoLocal.remaining = status.remaining_sec;
      _pomoLocal.total = status.duration_sec || (25 * 60);
      _pomoLocal.task = status.task || "";
      _pomoLocal.running = true;
      _pomoLocal.lastSync = Date.now();
      _renderPomodoroDisplay(_pomoLocal.remaining, _pomoLocal.total, _pomoLocal.task);
      // Client-side tick every second (no HTTP request)
      LexaState.setInterval("pomodoro", _pomoClientTick, 1000);
    } else {
      LexaState.clearInterval("pomodoro");
      display.innerHTML = `
        <div class="pomodoro-idle">
          <div class="pomodoro-stats">${t("productivity.pomodoroStats", {today: status.today_completed || 0, total: status.total_completed || 0})}</div>
        </div>
      `;
      controls.innerHTML = "";
      const startBtn = document.createElement("button");
      startBtn.className = "action-btn";
      startBtn.textContent = "Start";
      startBtn.addEventListener("click", startPomodoro);
      controls.appendChild(startBtn);
    }
  } catch (e) { console.warn("[Productivity] Failed to refresh pomodoro:", e.message || e); }
}

function startPomodoro() {
  document.getElementById("pomo-start-modal")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "pomo-start-modal";
  overlay.className = "note-modal-overlay";

  const panel = document.createElement("div");
  panel.className = "note-modal-panel note-modal-panel-compact";

  const header = document.createElement("div");
  header.className = "note-modal-header";
  const hTitle = document.createElement("div");
  hTitle.className = "note-modal-heading";
  hTitle.textContent = "\u23F3 " + t("productivity.startPomodoroTitle");
  header.appendChild(hTitle);
  const closeBtn = document.createElement("button");
  closeBtn.className = "note-modal-close";
  closeBtn.textContent = "\u00d7";
  closeBtn.addEventListener("click", () => { overlay.remove(); document.removeEventListener("keydown", escHandler); });
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const form = document.createElement("div");
  form.className = "note-modal-form";

  const taskInput = document.createElement("input");
  taskInput.type = "text";
  taskInput.placeholder = t("productivity.taskPlaceholder");
  taskInput.className = "settings-input";
  form.appendChild(taskInput);

  const durRow = document.createElement("div");
  durRow.className = "note-modal-row";
  const presets = [15, 25, 45, 60];
  presets.forEach(min => {
    const btn = document.createElement("button");
    btn.className = "action-btn action-btn-secondary note-modal-preset-btn";
    btn.textContent = min + " " + t("productivity.minutesSuffix");
    btn.dataset.min = min;
    btn.addEventListener("click", () => {
      durRow.querySelectorAll(".action-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      durInput.value = min;
    });
    durRow.appendChild(btn);
  });
  form.appendChild(durRow);

  const durInput = document.createElement("input");
  durInput.type = "number";
  durInput.value = "25";
  durInput.min = "1";
  durInput.max = "120";
  durInput.placeholder = t("productivity.customDuration");
  durInput.className = "settings-input";
  form.appendChild(durInput);
  // Highlight 25min preset by default
  durRow.querySelectorAll(".action-btn")[1].classList.add("active");
  panel.appendChild(form);

  const footer = document.createElement("div");
  footer.className = "note-modal-footer";
  const startBtn = document.createElement("button");
  startBtn.className = "action-btn";
  startBtn.textContent = t("productivity.startBtn");
  startBtn.addEventListener("click", async () => {
    const task = taskInput.value.trim();
    const dur = Math.max(1, Math.min(120, parseInt(durInput.value) || 25));
    overlay.remove();
    document.removeEventListener("keydown", escHandler);
    await window.lexa.pomodoroStart(task, dur);
    showToast(t("pomodoro.started", {dur}), "success");
    refreshPomodoro();
    refreshProdStats();
  });
  footer.appendChild(startBtn);
  const cancelBtn = document.createElement("button");
  cancelBtn.className = "action-btn action-btn-secondary";
  cancelBtn.textContent = t("common.cancel");
  cancelBtn.addEventListener("click", () => { overlay.remove(); document.removeEventListener("keydown", escHandler); });
  footer.appendChild(cancelBtn);
  panel.appendChild(footer);
  overlay.appendChild(panel);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) { overlay.remove(); document.removeEventListener("keydown", escHandler); } });
  const escHandler = (e) => { if (e.key === "Escape") { overlay.remove(); document.removeEventListener("keydown", escHandler); } };
  document.addEventListener("keydown", escHandler);
  document.body.appendChild(overlay);
  taskInput.focus();
}

async function stopPomodoro() {
  await window.lexa.pomodoroStop();
  showToast(t("pomodoro.stopped"), "info");
  refreshPomodoro();
}

// ── HABITS ──

async function refreshHabits() {
  try {
    const data = await window.lexa.habits();
    const list = document.getElementById("habits-list");
    if (!list) return;
    if (!data.habits || data.habits.length === 0) {
      list.innerHTML = '<div class="empty-state">' + escapeHtml(t("productivity.noHabits")) + '</div>';
      return;
    }
    // Build habit items using DOM (avoid inline-event + XSS issues with user-supplied names)
    list.innerHTML = "";
    data.habits.forEach(h => {
      const progress = Math.min(100, Math.round((h.today_count / (h.target || 1)) * 100));
      const safeName = escapeHtml(String(h.name || ""));
      const safeDesc = h.description ? escapeHtml(String(h.description)) : "";
      const streak = parseInt(h.streak) || 0;
      const todayCount = parseInt(h.today_count) || 0;
      const target = parseInt(h.target) || 1;

      const item = document.createElement("div");
      item.className = `habit-item${h.today_done ? " habit-done" : ""}`;
      // Build week dots (last 7 days)
      const weekDots = (h.week || [false,false,false,false,false,false,false]).map((done, i) => {
        const isToday = i === 6;
        return `<span class="habit-dot${done ? " habit-dot-done" : ""}${isToday ? " habit-dot-today" : ""}" title="${done ? t("productivity.habitDone") : t("productivity.habitPending")}"></span>`;
      }).join("");

      item.innerHTML = `
        <div class="habit-info">
          <div class="habit-name">${safeName}</div>
          ${safeDesc ? `<div class="habit-desc">${safeDesc}</div>` : ""}
          <div class="habit-meta">
            <span class="habit-streak">\uD83D\uDD25 ${t("productivity.streakDays", {streak})}</span>
            <span class="habit-progress">${t("productivity.todayProgress", {count: todayCount, target})}</span>
          </div>
          <div class="habit-week">${weekDots}</div>
        </div>
        <div class="habit-progress-bar">
          <div class="habit-progress-fill habit-progress-${Math.max(0, Math.min(100, Math.round(progress / 5) * 5))}"></div>
        </div>
        <div class="habit-actions">
          <button class="action-btn habit-log-btn ${h.today_done ? 'disabled-half' : ''}"${h.today_done ? ' disabled' : ""}>
            ${h.today_done ? "&#10003;" : "+1"}
          </button>
          <button class="todo-action-btn todo-delete habit-del-btn" title="${t("productivity.deleteBtn")}">&#10005;</button>
        </div>
      `;
      // Attach events with real name (no inline injection risk)
      item.querySelector(".habit-log-btn").addEventListener("click", () => logHabit(h.name));
      item.querySelector(".habit-del-btn").addEventListener("click", () => deleteHabit(h.name));
      list.appendChild(item);
    });
  } catch (e) { console.warn("[Productivity] Failed to refresh habits:", e.message || e); }
}

function createHabit() {
  document.getElementById("habit-create-modal")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "habit-create-modal";
  overlay.className = "note-modal-overlay";

  const panel = document.createElement("div");
  panel.className = "note-modal-panel note-modal-panel-medium";

  const header = document.createElement("div");
  header.className = "note-modal-header";
  const titleEl = document.createElement("div");
  titleEl.className = "note-modal-heading";
  titleEl.textContent = t("productivity.newHabitTitle");
  header.appendChild(titleEl);
  const closeBtn = document.createElement("button");
  closeBtn.className = "note-modal-close";
  closeBtn.textContent = "\u00d7";
  closeBtn.addEventListener("click", () => { overlay.remove(); document.removeEventListener("keydown", escHandler); });
  header.appendChild(closeBtn);
  panel.appendChild(header);

  const form = document.createElement("div");
  form.className = "note-modal-form note-modal-form-relaxed";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.placeholder = t("productivity.habitNamePlaceholder");
  nameInput.className = "settings-input";
  form.appendChild(nameInput);

  const descInput = document.createElement("input");
  descInput.type = "text";
  descInput.placeholder = t("productivity.descPlaceholder");
  descInput.className = "settings-input";
  form.appendChild(descInput);

  const row = document.createElement("div");
  row.className = "note-modal-row note-modal-row-center";
  const targetLabel = document.createElement("label");
  targetLabel.textContent = t("productivity.dailyGoalLabel");
  targetLabel.className = "note-modal-label";
  const targetInput = document.createElement("input");
  targetInput.type = "number";
  targetInput.value = "1";
  targetInput.min = "1";
  targetInput.max = "100";
  targetInput.className = "settings-input note-modal-number-input";
  row.appendChild(targetLabel);
  row.appendChild(targetInput);
  form.appendChild(row);
  panel.appendChild(form);

  const footer = document.createElement("div");
  footer.className = "note-modal-footer";
  const saveBtn = document.createElement("button");
  saveBtn.className = "action-btn";
  saveBtn.textContent = t("productivity.createBtn");
  saveBtn.addEventListener("click", async () => {
    const name = nameInput.value.trim();
    if (!name) { showToast(t("habits.nameEmpty"), "error"); return; }
    const target = Math.max(1, parseInt(targetInput.value) || 1);
    const desc = descInput.value.trim();
    await window.lexa.habitCreate({ name, target, description: desc || undefined });
    showToast(t("habits.created", {name}), "success");
    overlay.remove();
    document.removeEventListener("keydown", escHandler);
    refreshHabits();
  });
  footer.appendChild(saveBtn);
  const cancelBtn = document.createElement("button");
  cancelBtn.className = "action-btn action-btn-secondary";
  cancelBtn.textContent = t("common.cancel");
  cancelBtn.addEventListener("click", () => { overlay.remove(); document.removeEventListener("keydown", escHandler); });
  footer.appendChild(cancelBtn);
  panel.appendChild(footer);
  overlay.appendChild(panel);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) { overlay.remove(); document.removeEventListener("keydown", escHandler); } });
  const escHandler = (e) => { if (e.key === "Escape") { overlay.remove(); document.removeEventListener("keydown", escHandler); } };
  document.addEventListener("keydown", escHandler);
  document.body.appendChild(overlay);
  nameInput.focus();
}

async function logHabit(name) {
  await window.lexa.habitLog(name);
  showToast(t("habits.logged", {name}), "success");
  // Check for streak milestones
  try {
    const habitsData = await window.lexa.habits();
    const h = (habitsData.habits || []).find(x => x.name === name);
    if (h) {
      const streak = parseInt(h.streak) || 0;
      const milestones = [7, 14, 21, 30, 60, 100, 365];
      if (milestones.includes(streak)) {
        playBeep("pomodoro");
        showToast(t("habits.streakMilestone", {streak, name}), "success", 6000);
        sendNotification("Lexa \uD83C\uDF89", t("productivity.streakNotification", {streak, name}));
      }
    }
  } catch (e) { console.warn("[Productivity] Failed to check habit streak:", e.message || e); }
  refreshHabits();
  refreshProdStats();
}

async function deleteHabit(name) {
  await window.lexa.habitDelete(name);
  showToast(t("habits.deleted"), "info");
  refreshHabits();
  refreshProdStats();
}

// ── TIME TRACKING & FOCUS ──

async function refreshTimeTracking() {
  try {
    const [ttRes, focusRes, reportRes] = await Promise.allSettled([
      window.lexa.timeTracking(),
      window.lexa.focusStatus(),
      window.lexa.timeTrackingReport(1),
    ]);
    const ttStatus = ttRes.status === "fulfilled" ? ttRes.value : {};
    const focusStatus = focusRes.status === "fulfilled" ? focusRes.value : {};
    const report = reportRes.status === "fulfilled" ? reportRes.value : {};

    const ttBtn = document.getElementById("time-tracking-btn");
    const focusBtn = document.getElementById("focus-mode-btn");

    if (ttBtn) {
      ttBtn.textContent = ttStatus.running ? t("productivity.trackingStop") : t("productivity.trackingStart");
      ttBtn.classList.toggle("action-btn-danger", Boolean(ttStatus.running));
    }
    if (focusBtn) {
      focusBtn.textContent = focusStatus.active ? t("productivity.focusOff2") : t("productivity.focusModeBtn");
      focusBtn.classList.toggle("action-btn-danger", Boolean(focusStatus.active));
    }
    // Focus mode banner in chat view
    const focusBanner = document.getElementById("focus-mode-banner");
    if (focusBanner) focusStatus.active ? focusBanner.classList.remove("hidden") : focusBanner.classList.add("hidden");

    // Live tracking status display
    const liveEl = document.getElementById("time-tracking-live");
    if (liveEl) {
      if (ttStatus.running) {
        liveEl.classList.remove("hidden");
        const startTime = ttStatus.start_time ? new Date(ttStatus.start_time) : null;
        const elapsed = startTime ? Math.floor((Date.now() - startTime.getTime()) / 1000) : 0;
        const h = Math.floor(elapsed / 3600);
        const m = Math.floor((elapsed % 3600) / 60);
        const s = elapsed % 60;
        const timeStr = (h > 0 ? h + "h " : "") + String(m).padStart(2, "0") + "m " + String(s).padStart(2, "0") + "s";
        liveEl.innerHTML = `<span class="tt-live-dot"></span> ${t("productivity.trackingActive")} \u2014 ${timeStr}${ttStatus.current_app ? ` | ${escapeHtml(String(ttStatus.current_app))}` : ""}`;
      } else {
        liveEl.classList.add("hidden");
      }
    }

    // Render time report
    const reportDiv = document.getElementById("time-tracking-report");
    if (!reportDiv) return;

    if (!report.report || report.report.length === 0) {
      reportDiv.innerHTML = '<div class="empty-state">' + escapeHtml(t("productivity.noTimeData")) + '</div>';
      return;
    }
    reportDiv.innerHTML = `
      <div class="time-report-grid">
        ${report.report.slice(0, 10).map(r => `
          <div class="time-report-item">
            <div class="time-app-name">${escapeHtml(String(r.app || ""))}</div>
            <div class="time-duration">${escapeHtml(String(r.duration_display || ""))}</div>
          </div>
        `).join("")}
      </div>
    `;
  } catch (e) { console.warn("[Productivity] Failed to refresh time tracking:", e.message || e); }
}

async function toggleTimeTracking() {
  try {
    const status = await window.lexa.timeTracking();
    if (status.running) {
      await window.lexa.timeTrackingStop();
      showToast(t("timeTracking.stopped"), "info");
    } else {
      await window.lexa.timeTrackingStart();
      showToast(t("timeTracking.started"), "success");
    }
    refreshTimeTracking();
    refreshProdStats();
  } catch (e) { console.warn("[Productivity] Failed to toggle time tracking:", e.message || e); }
}

async function toggleFocusMode() {
  try {
    const status = await window.lexa.focusStatus();
    if (status.active) {
      await window.lexa.focusOff();
      showToast(t("focus.disabled"), "info");
    } else {
      await window.lexa.focusOn();
      showToast(t("focus.enabled"), "success");
    }
    refreshTimeTracking();
    refreshProdStats();
  } catch (e) { console.warn("[Productivity] Failed to toggle focus mode:", e.message || e); }
}
