/* ════════════════════════════════════════════════
   LEXA AI — Productivity Module
   Todo, Pomodoro, Habits, Time Tracking, Focus Mode
   Extracted from app.js (Phase 19 functions)
   ════════════════════════════════════════════════ */

// ── PRODUCTIVITY VIEW ────────────────────────────

const _todoMutationRunning = new Set();
const _habitMutationRunning = new Set();
let _pomodoroMutationRunning = false;
let _timeTrackingToggleRunning = false;
let _focusModeToggleRunning = false;

function productivityLocale() {
  try {
    if (typeof t === "function" && t._locale) return t._locale;
    if (typeof LexaI18n !== "undefined" && LexaI18n.getCurrentLanguage?.() === "en") return "en-US";
  } catch (_) { }
  return "de-DE";
}

function productivityFormatDate(value = new Date()) {
  return new Date(value).toLocaleDateString(productivityLocale());
}

function productivityDisplayCount(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num < 0) return "0";
  return String(Math.floor(num));
}

function createProductivityStatCard(value, label, active = false) {
  const card = document.createElement("div");
  card.className = active ? "prod-stat-card prod-stat-active" : "prod-stat-card";
  const valueEl = document.createElement("div");
  valueEl.className = "prod-stat-value";
  valueEl.textContent = String(value);
  const labelEl = document.createElement("div");
  labelEl.className = "prod-stat-label";
  labelEl.textContent = String(label);
  card.append(valueEl, labelEl);
  return card;
}

function createProductivityEmptyState(message) {
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = String(message || "");
  return empty;
}

function setTodoRowBusy(triggerBtn, busy) {
  const row = triggerBtn?.closest?.(".todo-item");
  if (row) row.setAttribute("aria-busy", busy ? "true" : "false");
  const buttons = row ? row.querySelectorAll("button") : (triggerBtn ? [triggerBtn] : []);
  buttons.forEach((button) => {
    button.disabled = Boolean(busy);
    if (busy) button.setAttribute("aria-busy", "true");
    else button.removeAttribute("aria-busy");
  });
}

function setHabitRowBusy(triggerBtn, busy) {
  const row = triggerBtn?.closest?.(".habit-item");
  if (row) row.setAttribute("aria-busy", busy ? "true" : "false");
  const buttons = row ? row.querySelectorAll("button") : (triggerBtn ? [triggerBtn] : []);
  buttons.forEach((button) => {
    if (busy) {
      button.dataset.lexaWasDisabled = button.disabled ? "true" : "false";
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      return;
    }
    button.disabled = button.dataset.lexaWasDisabled === "true";
    delete button.dataset.lexaWasDisabled;
    button.removeAttribute("aria-busy");
  });
}

function setPomodoroActionBusy(button, busy) {
  if (!button) return;
  button.disabled = Boolean(busy);
  if (busy) button.setAttribute("aria-busy", "true");
  else button.removeAttribute("aria-busy");
}

function setProductivityActionButtonsBusy(selector, busy) {
  document.querySelectorAll(selector).forEach((button) => {
    if (!(button instanceof HTMLButtonElement)) return;
    button.disabled = Boolean(busy);
    if (busy) button.setAttribute("aria-busy", "true");
    else button.removeAttribute("aria-busy");
  });
}

function renderTimeTrackingLiveStatus(target, label, timeText, currentApp) {
  const dot = document.createElement("span");
  dot.className = "tt-live-dot";
  const text = document.createTextNode(` ${label} \u2014 ${timeText}`);
  target.replaceChildren(dot, text);
  if (currentApp) {
    target.appendChild(document.createTextNode(` | ${String(currentApp)}`));
  }
}

function createTimeReportItem(entry) {
  const item = document.createElement("div");
  item.className = "time-report-item";
  const appName = document.createElement("div");
  appName.className = "time-app-name";
  appName.textContent = String(entry?.app || "");
  const duration = document.createElement("div");
  duration.className = "time-duration";
  duration.textContent = String(entry?.duration_display || "");
  item.append(appName, duration);
  return item;
}

function habitNumber(value, fallback = 0) {
  const num = Number(value);
  if (!Number.isFinite(num) || num < 0) return fallback;
  return Math.floor(num);
}

function createHabitWeekDots(week) {
  const values = Array.isArray(week) ? week.slice(-7) : [];
  while (values.length < 7) values.unshift(false);
  const wrap = document.createElement("div");
  wrap.className = "habit-week";
  values.forEach((done, index) => {
    const dot = document.createElement("span");
    dot.className = `habit-dot${done ? " habit-dot-done" : ""}${index === 6 ? " habit-dot-today" : ""}`;
    dot.title = done ? t("productivity.habitDone") : t("productivity.habitPending");
    wrap.appendChild(dot);
  });
  return wrap;
}

function createHabitItem(habit) {
  const name = String(habit?.name || "");
  const description = habit?.description ? String(habit.description) : "";
  const streak = habitNumber(habit?.streak);
  const todayCount = habitNumber(habit?.today_count);
  const target = Math.max(1, habitNumber(habit?.target, 1));
  const progress = Math.min(100, Math.round((todayCount / target) * 100));

  const item = document.createElement("div");
  item.className = `habit-item${habit?.today_done ? " habit-done" : ""}`;

  const info = document.createElement("div");
  info.className = "habit-info";
  const nameEl = document.createElement("div");
  nameEl.className = "habit-name";
  nameEl.textContent = name;
  info.appendChild(nameEl);
  if (description) {
    const descEl = document.createElement("div");
    descEl.className = "habit-desc";
    descEl.textContent = description;
    info.appendChild(descEl);
  }

  const meta = document.createElement("div");
  meta.className = "habit-meta";
  const streakEl = document.createElement("span");
  streakEl.className = "habit-streak";
  streakEl.textContent = `\uD83D\uDD25 ${t("productivity.streakDays", {streak})}`;
  const progressEl = document.createElement("span");
  progressEl.className = "habit-progress";
  progressEl.textContent = t("productivity.todayProgress", {count: todayCount, target});
  meta.append(streakEl, progressEl);
  info.append(meta, createHabitWeekDots(habit?.week));

  const progressBar = document.createElement("div");
  progressBar.className = "habit-progress-bar";
  const progressFill = document.createElement("div");
  progressFill.className = `habit-progress-fill habit-progress-${Math.max(0, Math.min(100, Math.round(progress / 5) * 5))}`;
  progressBar.appendChild(progressFill);

  const actions = document.createElement("div");
  actions.className = "habit-actions";
  const logBtn = document.createElement("button");
  logBtn.type = "button";
  logBtn.className = `action-btn habit-log-btn${habit?.today_done ? " disabled-half" : ""}`;
  logBtn.textContent = habit?.today_done ? "\u2713" : "+1";
  logBtn.disabled = Boolean(habit?.today_done);
  logBtn.title = t("productivity.logHabitLabel", { name });
  logBtn.setAttribute("aria-label", t("productivity.logHabitLabel", { name }));
  logBtn.addEventListener("click", () => logHabit(name, logBtn));

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "todo-action-btn todo-delete habit-del-btn";
  deleteBtn.textContent = "\u2715";
  deleteBtn.title = t("productivity.deleteHabitLabel", { name });
  deleteBtn.setAttribute("aria-label", t("productivity.deleteHabitLabel", { name }));
  deleteBtn.addEventListener("click", () => deleteHabit(name, deleteBtn));

  actions.append(logBtn, deleteBtn);
  item.append(info, progressBar, actions);
  return item;
}

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
    const habitsDone = productivityDisplayCount(stats.habits_done_today);
    const habitsTotal = productivityDisplayCount(stats.habits_total);
    bar.replaceChildren(
      createProductivityStatCard(productivityDisplayCount(stats.open_todos), t("productivity.statOpenTodos")),
      createProductivityStatCard(productivityDisplayCount(stats.done_today), t("productivity.statDoneToday")),
      createProductivityStatCard(productivityDisplayCount(stats.pomodoros_today), t("productivity.statPomodoros")),
      createProductivityStatCard(`${habitsDone}/${habitsTotal}`, t("productivity.statHabits")),
      createProductivityStatCard(stats.focus_mode ? t("productivity.focusOn") : t("productivity.focusOff"), t("productivity.statFocusMode"), Boolean(stats.focus_mode))
    );
  } catch (e) { console.warn("[Productivity] Failed to refresh stats:", e.message || e); }
}

// ── TODOS ──

async function refreshTodos() {
  try {
    const filter = document.getElementById("todo-filter")?.value || "";
    const data = await window.lexa.todos(filter);
    const list = document.getElementById("todo-list");
    if (!list) return;
    list.replaceChildren();
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
      checkBtn.type = "button";
      checkBtn.className = "todo-check";
      checkBtn.title = t("productivity.complete");
      checkBtn.setAttribute("aria-label", t("productivity.completeTodoLabel", { title: td.title || "" }));
      checkBtn.textContent = statusIcon;
      checkBtn.addEventListener("click", () => completeTodo(td.id, checkBtn));
      item.appendChild(checkBtn);

      // Content area (double-click to inline edit)
      const content = document.createElement("div");
      content.className = "todo-content";

      const titleEl = document.createElement("div");
      titleEl.className = "todo-title";
      titleEl.textContent = td.title || "";
      titleEl.title = t("productivity.dblClickEdit");
      titleEl.setAttribute("role", "button");
      titleEl.setAttribute("tabindex", "0");
      titleEl.setAttribute("aria-label", t("productivity.editTodoLabel", { title: td.title || "" }));
      titleEl.addEventListener("dblclick", () => startTodoInlineEdit(td.id, titleEl, td.title));
      titleEl.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          startTodoInlineEdit(td.id, titleEl, td.title);
        }
      });
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
        progressBtn.type = "button";
        progressBtn.className = "todo-action-btn";
        progressBtn.title = t("productivity.inProgress");
        progressBtn.setAttribute("aria-label", t("productivity.markTodoInProgressLabel", { title: td.title || "" }));
        progressBtn.textContent = "\u25b6";
        progressBtn.addEventListener("click", () => setTodoStatus(td.id, "in_progress", progressBtn));
        actions.appendChild(progressBtn);
      }
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "todo-action-btn todo-delete";
      delBtn.title = t("productivity.deleteBtn");
      delBtn.setAttribute("aria-label", t("productivity.deleteTodoLabel", { title: td.title || "" }));
      delBtn.textContent = "\u2715";
      delBtn.addEventListener("click", () => deleteTodo(td.id, delBtn));
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
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", t("productivity.newTodoTitle"));

  const header = document.createElement("div");
  header.className = "note-modal-header";
  const hTitle = document.createElement("div");
  hTitle.className = "note-modal-heading";
  hTitle.textContent = t("productivity.newTodoTitle");
  header.appendChild(hTitle);
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "note-modal-close";
  closeBtn.setAttribute("aria-label", t("common.close"));
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
  saveBtn.type = "button";
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
  cancelBtn.type = "button";
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

async function completeTodo(id, triggerBtn) {
  const key = String(id || "");
  if (!key || _todoMutationRunning.has(key)) return;
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  _todoMutationRunning.add(key);
  setTodoRowBusy(triggerBtn, true);
  try {
    await window.lexa.todoComplete(id);
    showToast(t("todo.completed"), "success");
    refreshTodos();
    refreshProdStats();
  } catch (e) {
    console.warn("[Productivity] Failed to complete todo:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _todoMutationRunning.delete(key);
    if (triggerBtn?.isConnected) setTodoRowBusy(triggerBtn, false);
  }
}

async function setTodoStatus(id, status, triggerBtn) {
  const key = String(id || "");
  if (!key || _todoMutationRunning.has(key)) return;
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  _todoMutationRunning.add(key);
  setTodoRowBusy(triggerBtn, true);
  try {
    await window.lexa.todoUpdate(id, { status });
    refreshTodos();
  } catch (e) {
    console.warn("[Productivity] Failed to update todo status:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _todoMutationRunning.delete(key);
    if (triggerBtn?.isConnected) setTodoRowBusy(triggerBtn, false);
  }
}

async function deleteTodo(id, triggerBtn) {
  const key = String(id || "");
  if (!key || _todoMutationRunning.has(key)) return;
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  _todoMutationRunning.add(key);
  setTodoRowBusy(triggerBtn, true);
  try {
    await window.lexa.todoDelete(id);
    showToast(t("todo.deleted"), "info");
    refreshTodos();
    refreshProdStats();
  } catch (e) {
    console.warn("[Productivity] Failed to delete todo:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _todoMutationRunning.delete(key);
    if (triggerBtn?.isConnected) setTodoRowBusy(triggerBtn, false);
  }
}

async function exportTodos() {
  try {
    const data = await window.lexa.todos("");
    const todos = data.todos || [];
    if (todos.length === 0) { showToast(t("todo.noTodosExport"), "warning"); return; }
    const statusIcon = s => s === "done" ? "[x]" : s === "in_progress" ? "[~]" : "[ ]";
    const lines = [
      `# ${t("productivity.todoExportTitle")}`,
      t("productivity.exportDate", {date: productivityFormatDate()}),
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

function pomodoroSeconds(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num < 0) return 0;
  return Math.floor(num);
}

function createPomodoroCircle(className) {
  const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  circle.setAttribute("class", className);
  circle.setAttribute("cx", "60");
  circle.setAttribute("cy", "60");
  circle.setAttribute("r", "52");
  circle.setAttribute("fill", "none");
  circle.setAttribute("stroke-width", "8");
  return circle;
}

function createPomodoroTimerDisplay(remaining, total, task) {
  const safeRemaining = pomodoroSeconds(remaining);
  const safeTotal = pomodoroSeconds(total);
  const mins = Math.floor(safeRemaining / 60);
  const secs = safeRemaining % 60;
  const elapsed = Math.max(0, safeTotal - safeRemaining);
  const progress = Math.min(1, Math.max(0, safeTotal > 0 ? elapsed / safeTotal : 0));
  const circumference = 2 * Math.PI * 52;
  const dashoffset = circumference * (1 - progress);

  const timer = document.createElement("div");
  timer.className = "pomodoro-timer";
  const wrap = document.createElement("div");
  wrap.className = "pomodoro-ring-wrap";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "pomodoro-ring");
  svg.setAttribute("width", "130");
  svg.setAttribute("height", "130");
  svg.setAttribute("viewBox", "0 0 120 120");
  const bg = createPomodoroCircle("pomo-ring-bg");
  const fill = createPomodoroCircle("pomo-ring-fill");
  fill.setAttribute("stroke-dasharray", circumference.toFixed(1));
  fill.setAttribute("stroke-dashoffset", dashoffset.toFixed(1));
  fill.setAttribute("transform", "rotate(-90 60 60)");
  svg.append(bg, fill);

  const ringText = document.createElement("div");
  ringText.className = "pomodoro-ring-text";
  const timeEl = document.createElement("div");
  timeEl.className = "pomodoro-time";
  timeEl.textContent = `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  const pctEl = document.createElement("div");
  pctEl.className = "pomodoro-pct";
  pctEl.textContent = `${Math.round(progress * 100)}%`;
  ringText.append(timeEl, pctEl);

  const taskEl = document.createElement("div");
  taskEl.className = "pomodoro-task";
  taskEl.textContent = String(task || t("productivity.noTask"));
  wrap.append(svg, ringText);
  timer.append(wrap, taskEl);
  return timer;
}

function createPomodoroIdleDisplay(status) {
  const idle = document.createElement("div");
  idle.className = "pomodoro-idle";
  const stats = document.createElement("div");
  stats.className = "pomodoro-stats";
  stats.textContent = t("productivity.pomodoroStats", {
    today: productivityDisplayCount(status?.today_completed),
    total: productivityDisplayCount(status?.total_completed),
  });
  idle.appendChild(stats);
  return idle;
}

function _renderPomodoroDisplay(remaining, total, task) {
  const display = document.getElementById("pomodoro-display");
  const controls = document.getElementById("pomodoro-controls");
  if (!display || !controls) return;
  display.replaceChildren(createPomodoroTimerDisplay(remaining, total, task));
  const stopBtn = document.createElement("button");
  stopBtn.type = "button";
  stopBtn.className = "action-btn action-btn-danger";
  stopBtn.textContent = t("productivity.stopBtn");
  stopBtn.title = t("productivity.stopBtn");
  stopBtn.setAttribute("aria-label", t("productivity.stopBtn"));
  setPomodoroActionBusy(stopBtn, _pomodoroMutationRunning);
  stopBtn.addEventListener("click", () => stopPomodoro(stopBtn));
  controls.replaceChildren(stopBtn);
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
      display.replaceChildren(createPomodoroIdleDisplay(status));
      const startBtn = document.createElement("button");
      startBtn.type = "button";
      startBtn.className = "action-btn";
      startBtn.textContent = t("productivity.startBtn");
      startBtn.title = t("productivity.startBtn");
      startBtn.setAttribute("aria-label", t("productivity.startBtn"));
      startBtn.addEventListener("click", startPomodoro);
      controls.replaceChildren(startBtn);
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
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", t("productivity.startPomodoroTitle"));

  const header = document.createElement("div");
  header.className = "note-modal-header";
  const hTitle = document.createElement("div");
  hTitle.className = "note-modal-heading";
  hTitle.textContent = "\u23F3 " + t("productivity.startPomodoroTitle");
  header.appendChild(hTitle);
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "note-modal-close";
  closeBtn.setAttribute("aria-label", t("common.close"));
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
    btn.type = "button";
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
  startBtn.type = "button";
  startBtn.className = "action-btn";
  startBtn.textContent = t("productivity.startBtn");
  startBtn.title = t("productivity.startBtn");
  startBtn.setAttribute("aria-label", t("productivity.startBtn"));
  startBtn.addEventListener("click", async () => {
    if (_pomodoroMutationRunning) return;
    if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
    const task = taskInput.value.trim();
    const dur = Math.max(1, Math.min(120, parseInt(durInput.value) || 25));
    _pomodoroMutationRunning = true;
    setPomodoroActionBusy(startBtn, true);
    try {
      await window.lexa.pomodoroStart(task, dur);
      showToast(t("pomodoro.started", {dur}), "success");
      overlay.remove();
      document.removeEventListener("keydown", escHandler);
      refreshPomodoro();
      refreshProdStats();
    } catch (e) {
      console.warn("[Productivity] Failed to start pomodoro:", e.message || e);
      showToast(t("toast.executionError"), "error", 2200);
    } finally {
      _pomodoroMutationRunning = false;
      if (startBtn?.isConnected) setPomodoroActionBusy(startBtn, false);
    }
  });
  footer.appendChild(startBtn);
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
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

async function stopPomodoro(triggerBtn) {
  if (_pomodoroMutationRunning) return;
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  _pomodoroMutationRunning = true;
  setPomodoroActionBusy(triggerBtn, true);
  try {
    await window.lexa.pomodoroStop();
    _pomoLocal.running = false;
    LexaState.clearInterval("pomodoro");
    showToast(t("pomodoro.stopped"), "info");
    refreshPomodoro();
    refreshProdStats();
  } catch (e) {
    console.warn("[Productivity] Failed to stop pomodoro:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _pomodoroMutationRunning = false;
    if (triggerBtn?.isConnected) setPomodoroActionBusy(triggerBtn, false);
  }
}

// ── HABITS ──

async function refreshHabits() {
  try {
    const data = await window.lexa.habits();
    const list = document.getElementById("habits-list");
    if (!list) return;
    const habits = Array.isArray(data.habits) ? data.habits : [];
    if (habits.length === 0) {
      list.replaceChildren(createProductivityEmptyState(t("productivity.noHabits")));
      return;
    }
    const fragment = document.createDocumentFragment();
    habits.forEach((habit) => {
      fragment.appendChild(createHabitItem(habit));
    });
    list.replaceChildren(fragment);
  } catch (e) { console.warn("[Productivity] Failed to refresh habits:", e.message || e); }
}

function createHabit() {
  document.getElementById("habit-create-modal")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "habit-create-modal";
  overlay.className = "note-modal-overlay";

  const panel = document.createElement("div");
  panel.className = "note-modal-panel note-modal-panel-medium";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", t("productivity.newHabitTitle"));

  const header = document.createElement("div");
  header.className = "note-modal-header";
  const titleEl = document.createElement("div");
  titleEl.className = "note-modal-heading";
  titleEl.textContent = t("productivity.newHabitTitle");
  header.appendChild(titleEl);
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "note-modal-close";
  closeBtn.setAttribute("aria-label", t("common.close"));
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
  saveBtn.type = "button";
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
  cancelBtn.type = "button";
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

async function logHabit(name, triggerBtn) {
  const key = String(name || "");
  if (!key || _habitMutationRunning.has(key)) return;
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  _habitMutationRunning.add(key);
  setHabitRowBusy(triggerBtn, true);
  try {
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
  } catch (e) {
    console.warn("[Productivity] Failed to log habit:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _habitMutationRunning.delete(key);
    if (triggerBtn?.isConnected) setHabitRowBusy(triggerBtn, false);
  }
}

async function deleteHabit(name, triggerBtn) {
  const key = String(name || "");
  if (!key || _habitMutationRunning.has(key)) return;
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  _habitMutationRunning.add(key);
  setHabitRowBusy(triggerBtn, true);
  try {
    await window.lexa.habitDelete(name);
    showToast(t("habits.deleted"), "info");
    refreshHabits();
    refreshProdStats();
  } catch (e) {
    console.warn("[Productivity] Failed to delete habit:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _habitMutationRunning.delete(key);
    if (triggerBtn?.isConnected) setHabitRowBusy(triggerBtn, false);
  }
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
      setProductivityActionButtonsBusy("#time-tracking-btn, button[data-action=\"toggleTimeTracking\"]", _timeTrackingToggleRunning);
    }
    if (focusBtn) {
      focusBtn.textContent = focusStatus.active ? t("productivity.focusOff2") : t("productivity.focusModeBtn");
      focusBtn.classList.toggle("action-btn-danger", Boolean(focusStatus.active));
      setProductivityActionButtonsBusy("#focus-mode-btn, button[data-action=\"toggleFocusMode\"]", _focusModeToggleRunning);
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
        renderTimeTrackingLiveStatus(liveEl, t("productivity.trackingActive"), timeStr, ttStatus.current_app);
      } else {
        liveEl.classList.add("hidden");
      }
    }

    // Render time report
    const reportDiv = document.getElementById("time-tracking-report");
    if (!reportDiv) return;

    if (!report.report || report.report.length === 0) {
      reportDiv.replaceChildren(createProductivityEmptyState(t("productivity.noTimeData")));
      return;
    }
    const grid = document.createElement("div");
    grid.className = "time-report-grid";
    report.report.slice(0, 10).forEach((entry) => {
      grid.appendChild(createTimeReportItem(entry));
    });
    reportDiv.replaceChildren(grid);
  } catch (e) { console.warn("[Productivity] Failed to refresh time tracking:", e.message || e); }
}

async function toggleTimeTracking() {
  if (_timeTrackingToggleRunning) return;
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  _timeTrackingToggleRunning = true;
  setProductivityActionButtonsBusy("#time-tracking-btn, button[data-action=\"toggleTimeTracking\"]", true);
  try {
    const status = await window.lexa.timeTracking();
    if (status.running) {
      await window.lexa.timeTrackingStop();
      showToast(t("timeTracking.stopped"), "info");
    } else {
      await window.lexa.timeTrackingStart();
      showToast(t("timeTracking.started"), "success");
    }
    await Promise.allSettled([refreshTimeTracking(), refreshProdStats()]);
  } catch (e) {
    console.warn("[Productivity] Failed to toggle time tracking:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _timeTrackingToggleRunning = false;
    setProductivityActionButtonsBusy("#time-tracking-btn, button[data-action=\"toggleTimeTracking\"]", false);
  }
}

async function toggleFocusMode() {
  if (_focusModeToggleRunning) return;
  if (!LexaState.get("backendOnline")) { showToast(t("common.backendOffline"), "error"); return; }
  _focusModeToggleRunning = true;
  setProductivityActionButtonsBusy("#focus-mode-btn, button[data-action=\"toggleFocusMode\"]", true);
  try {
    const status = await window.lexa.focusStatus();
    if (status.active) {
      await window.lexa.focusOff();
      showToast(t("focus.disabled"), "info");
    } else {
      await window.lexa.focusOn();
      showToast(t("focus.enabled"), "success");
    }
    await Promise.allSettled([refreshTimeTracking(), refreshProdStats()]);
  } catch (e) {
    console.warn("[Productivity] Failed to toggle focus mode:", e.message || e);
    showToast(t("toast.executionError"), "error", 2200);
  } finally {
    _focusModeToggleRunning = false;
    setProductivityActionButtonsBusy("#focus-mode-btn, button[data-action=\"toggleFocusMode\"]", false);
  }
}
