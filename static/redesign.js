/* ShyBoard workspace layer.
 * The product has two task states: active work and completed archive.
 * Legacy `todo` rows remain compatible and are presented as active work.
 */
(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const statusText = { todo: "进行中", doing: "进行中", done: "已完成" };
  const priorityText = { high: "高", medium: "中", low: "低" };
  const priorityRank = { high: 0, medium: 1, low: 2 };
  const weekText = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
  const state = { tasks: [], recurring: [], view: "board", mode: "active", query: "", priority: "all", due: "all", sort: "updated", editingProgressId: null };
  const taskProgressPrefix = "[TASK_PROGRESS]\n";
  const eventFieldText = { title: "标题", description: "描述", status: "状态", priority: "优先级", due_date: "截止日期", remind_days: "截止提醒", tags: "标签" };

  function dateKey(date = new Date()) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function addDays(dateString, amount) {
    const date = new Date(`${dateString}T12:00:00`);
    date.setDate(date.getDate() + amount);
    return dateKey(date);
  }

  function formatDetailTime(value) {
    if (!value) return "";
    const date = new Date(String(value).replace(" ", "T"));
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  function formatProgressTime(value) {
    if (!value) return { date: "日期未知", time: "" };
    const date = new Date(String(value).replace(" ", "T"));
    if (Number.isNaN(date.getTime())) return { date: String(value), time: "" };
    return {
      date: date.toLocaleDateString("zh-CN", { month: "long", day: "numeric" }),
      time: date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })
    };
  }

  function formatEventValue(field, value) {
    if (field === "status") return statusText[value] || value || "未设置";
    if (field === "priority") return `${priorityText[value] || value || "未设置"}优先级`;
    if (field === "tags") return Array.isArray(value) ? value.join("、") : String(value || "无标签").replace(/,/g, "、");
    if (field === "due_date") return value || "未设置";
    if (field === "remind_days") return Number(value) < 0 ? "不提醒" : Number(value) === 0 ? "截止当天" : `提前 ${value} 天`;
    return value || "空";
  }

  function renderTaskEvent(event) {
    if (event.event_type === "create") {
      return `<div class="detail-event create"><span class="detail-event-dot"></span><div><strong>创建任务</strong><p>初始状态：${escapeHtml(statusText[event.new_status] || "进行中")}</p><small>${escapeHtml(formatDetailTime(event.created_at))}</small></div></div>`;
    }
    if (event.event_type === "status") {
      return `<div class="detail-event status"><span class="detail-event-dot"></span><div><strong>调整任务状态</strong><p>${escapeHtml(statusText[event.old_status] || event.old_status || "未设置")} → ${escapeHtml(statusText[event.new_status] || event.new_status || "未设置")}</p><small>${escapeHtml(formatDetailTime(event.created_at))}</small></div></div>`;
    }
    let changes = {};
    try { changes = JSON.parse(event.note || "{}"); }
    catch (_) { changes = {}; }
    const rows = Object.entries(changes).map(([field, values]) => {
      const pair = Array.isArray(values) ? values : ["", values];
      return `<div class="detail-event-change"><span>${escapeHtml(eventFieldText[field] || field)}</span><p><del>${escapeHtml(formatEventValue(field, pair[0]))}</del><i>→</i><ins>${escapeHtml(formatEventValue(field, pair[1]))}</ins></p></div>`;
    }).join("");
    const label = Object.keys(changes).map((field) => eventFieldText[field] || field).join("、");
    return `<div class="detail-event update"><span class="detail-event-dot"></span><div><strong>${label ? `修改了${escapeHtml(label)}` : "更新任务信息"}</strong>${rows ? `<div class="detail-event-changes">${rows}</div>` : ""}<small>${escapeHtml(formatDetailTime(event.created_at))}</small></div></div>`;
  }

  function parseTaskProgressNote(note) {
    const raw = String(note && note.content || "");
    if (!raw.startsWith(taskProgressPrefix)) return null;
    try {
      const record = JSON.parse(raw.slice(taskProgressPrefix.length));
      if (!record || !record.taskId || !record.recordId || typeof record.content !== "string") return null;
      return { ...record, taskId: Number(record.taskId), noteId: Number(note.id) };
    } catch (_) { return null; }
  }

  async function loadTaskProgressRecords(taskId) {
    try {
      const records = await api(`/api/tasks/${taskId}/progress`);
      return records.map((record) => ({
        ...record,
        progressId: Number(record.id),
        taskId: Number(record.task_id),
        recordId: record.record_id,
        createdAt: record.created_at,
        updatedAt: record.updated_at
      }));
    } catch (_) { /* 兼容未升级后端，回退到旧版隐藏便签 */ }
    const notes = await api("/api/notes");
    const records = new Map();
    notes.forEach((note) => {
      const record = parseTaskProgressNote(note);
      if (!record || record.taskId !== taskId) return;
      const current = records.get(record.recordId);
      if (!current || record.noteId > current.noteId) records.set(record.recordId, record);
    });
    return [...records.values()].sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
  }

  async function saveTaskProgressRecord(taskId, content, existing = null) {
    const text = content.trim();
    if (!text) { toast("请先填写进度记录"); return false; }
    if (existing?.progressId) {
      await api(`/api/progress/${existing.progressId}`, {
        method: "PATCH",
        body: JSON.stringify({ content: text })
      });
      return true;
    }
    if (!existing) {
      await api(`/api/tasks/${taskId}/progress`, {
        method: "POST",
        body: JSON.stringify({ content: text, source: "manual" })
      });
      return true;
    }
    const now = new Date().toISOString();
    const record = existing
      ? { ...existing, content: text, updatedAt: now }
      : { taskId, recordId: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`, createdAt: now, updatedAt: now, content: text };
    const stored = { taskId: record.taskId, recordId: record.recordId, createdAt: record.createdAt, updatedAt: record.updatedAt, content: record.content };
    await api("/api/notes", { method: "POST", body: JSON.stringify({ content: taskProgressPrefix + JSON.stringify(stored) }) });
    if (existing?.noteId) await api(`/api/notes/${existing.noteId}`, { method: "DELETE" });
    if (typeof loadNotes === "function") loadNotes();
    return true;
  }

  function isActive(task) { return task.status !== "done"; }
  function isOverdue(task) { return Boolean(task.due_date && task.due_date < dateKey() && isActive(task)); }
  function isDueToday(task) { return task.due_date === dateKey() && isActive(task); }

  function daysUntil(dateString) {
    if (!dateString) return Number.POSITIVE_INFINITY;
    const today = new Date(`${dateKey()}T12:00:00`);
    const target = new Date(`${dateString}T12:00:00`);
    return Math.round((target.getTime() - today.getTime()) / 86400000);
  }

  function renderDeadlineReminder(tasks) {
    const button = $("#deadline-reminder");
    if (!button) return;
    const taskCandidates = tasks.filter((task) => {
      const days = daysUntil(task.due_date);
      const windowDays = Number.isFinite(Number(task.remind_days)) ? Number(task.remind_days) : 3;
      return isActive(task) && windowDays >= 0 && days >= 0 && days <= windowDays;
    }).map((task) => ({ ...task, reminderKind: "task" }));
    const recurringCandidates = state.recurring.filter((task) => {
      const days = daysUntil(task.next_due_date);
      return task.enabled && Number(task.remind_days) >= 0 && days >= 0 && days <= Number(task.remind_days);
    }).map((task) => ({ ...task, due_date: task.next_due_date, priority: "low", reminderKind: "recurring" }));
    const candidates = [...taskCandidates, ...recurringCandidates]
      .sort((a, b) => daysUntil(a.due_date) - daysUntil(b.due_date) || (priorityRank[a.priority] ?? 9) - (priorityRank[b.priority] ?? 9));
    button.classList.toggle("has-reminder", candidates.length > 0);
    button.classList.toggle("due-today", candidates.length > 0 && daysUntil(candidates[0].due_date) === 0);
    if (!candidates.length) {
      $("#deadline-reminder-text").textContent = "近期没有截止提醒";
      $("#deadline-reminder-meta").textContent = "本地数据已保存";
      button.dataset.target = "today";
      button.title = "打开计划";
      return;
    }
    const next = candidates[0];
    const days = daysUntil(next.due_date);
    const recurring = next.reminderKind === "recurring";
    $("#deadline-reminder-text").textContent = days === 0 ? (recurring ? "今天有定时任务" : "今天到期") : days === 1 ? (recurring ? "明天有定时任务" : "还有 1 天到期") : `还有 ${days} 天${recurring ? "执行" : "到期"}`;
    $("#deadline-reminder-meta").textContent = `${recurring ? "定时 · " : ""}${next.title}${candidates.length > 1 ? ` · 另有 ${candidates.length - 1} 项` : ""}`;
    button.dataset.target = recurring ? "recurring" : "today";
    button.title = `${next.title} · ${humanDate(next.due_date)}，点击查看`;
  }

  function matchesSearchAndPriority(task) {
    const query = state.query.trim().toLowerCase();
    if (query && ![task.title, task.description, ...(task.tags || [])].join(" ").toLowerCase().includes(query)) return false;
    if (state.priority !== "all" && task.priority !== state.priority) return false;
    return true;
  }

  function taskMatches(task) {
    if (state.mode === "archive" ? task.status !== "done" : !isActive(task)) return false;
    if (!matchesSearchAndPriority(task)) return false;
    if (state.mode === "archive") return true;
    if (state.due === "today" && !isDueToday(task)) return false;
    if (state.due === "none" && task.due_date) return false;
    return true;
  }

  function sortTasks(tasks) {
    return [...tasks].sort((a, b) => {
      if (state.sort === "priority") return (priorityRank[a.priority] ?? 9) - (priorityRank[b.priority] ?? 9);
      if (state.sort === "due") return (a.due_date || "9999-99-99").localeCompare(b.due_date || "9999-99-99");
      if (state.sort === "created") return String(b.created_at || "").localeCompare(String(a.created_at || ""));
      return String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""));
    });
  }

  function humanDate(dateString) {
    if (!dateString) return "未安排日期";
    if (dateString === dateKey()) return "今天";
    const date = new Date(`${dateString}T12:00:00`);
    return `${date.getMonth() + 1}月${date.getDate()}日 · ${weekText[date.getDay()]}`;
  }

  function planTask(task) {
    const overdue = isOverdue(task);
    const due = overdue ? `已逾期 · ${humanDate(task.due_date)}` : humanDate(task.due_date);
    return `<article class="plan-task ${overdue ? "overdue" : ""}" data-id="${task.id}">
      <button class="plan-task-check" data-plan-action="complete" aria-label="完成任务"></button>
      <div class="plan-task-copy"><strong>${escapeHtml(task.title)}</strong><span>${escapeHtml(due)}</span></div>
      <span class="plan-priority p-${task.priority}">${priorityText[task.priority]}优先级</span>
      <span class="plan-open" aria-hidden="true">›</span>
    </article>`;
  }

  function renderPlan(tasks) {
    const active = tasks.filter((task) => isActive(task) && matchesSearchAndPriority(task));
    const todayValue = dateKey();
    const weekEnd = addDays(todayValue, 7);
    const overdue = sortTasks(active.filter(isOverdue));
    const todayTasks = sortTasks(active.filter(isDueToday));
    const reminders = sortTasks(active.filter((task) => {
      const days = daysUntil(task.due_date);
      const windowDays = Number.isFinite(Number(task.remind_days)) ? Number(task.remind_days) : 3;
      return windowDays >= 0 && days > 0 && days <= windowDays;
    }));
    const upcoming = sortTasks(active.filter((task) => task.due_date > todayValue && task.due_date <= weekEnd));
    const later = sortTasks(active.filter((task) => task.due_date > weekEnd));
    const unscheduled = sortTasks(active.filter((task) => !task.due_date));
    const now = new Date();
    const groups = [
      ["需要重新安排", "截止日期已过", overdue, "urgent"],
      ["今天", weekText[now.getDay()], todayTasks, "today"],
      ["接下来 7 天", `${now.getMonth() + 1}月${now.getDate()}日 — ${new Date(`${weekEnd}T12:00:00`).getMonth() + 1}月${new Date(`${weekEnd}T12:00:00`).getDate()}日`, upcoming, "full upcoming"],
      ["之后", "7 天以后", later, "full later"],
      ["尚未安排", "没有截止日期", unscheduled, "full unscheduled"],
    ];
    const sections = groups.map(([title, hint, list, className]) => `<section class="today-section plan-section ${className}">
      <div class="today-section-head"><div><h3>${title}</h3><span class="plan-section-hint">${hint}</span></div><span class="today-section-count">${list.length} 件</span></div>
      <div class="today-task-list">${list.length ? list.map(planTask).join("") : `<div class="today-empty">这里暂时是空的。</div>`}</div>
    </section>`).join("");
    $("#today-sections").innerHTML = `<section class="plan-overview">
      <div class="plan-date"><span>今天</span><strong>${now.getMonth() + 1}月${now.getDate()}日</strong><small>${weekText[now.getDay()]}</small></div>
      <div class="plan-overview-copy"><span class="eyebrow">TIME PLAN</span><h2>${todayTasks.length ? `今天有 ${todayTasks.length} 件工作到期` : reminders.length ? `${reminders.length} 件工作临近截止` : "今天没有必须赶完的事"}</h2><p>轻重缓急，一眼就有数。</p></div>
      <div class="plan-metrics"><span><strong>${todayTasks.length}</strong>今天</span><span><strong>${reminders.length}</strong>临近</span><span><strong>${upcoming.length}</strong>未来 7 天</span></div>
    </section>${sections}`;
  }

  function renderSummary(tasks) {
    const active = tasks.filter(isActive).length;
    const dueToday = tasks.filter(isDueToday).length;
    const doneToday = tasks.filter((task) => task.status === "done" && String(task.completed_at || task.updated_at || "").slice(0, 10) === dateKey()).length;
    $("#sum-active").textContent = active;
    $("#sum-due-today").textContent = dueToday;
    $("#sum-done-today").textContent = doneToday;
    renderDeadlineReminder(tasks);
    const count = $("#pomo-count")?.textContent.match(/\d+/)?.[0] || "0";
    $("#sum-pomo").textContent = count;
  }

  function taskCard(task) {
    const done = task.status === "done";
    const due = task.due_date ? `<span class="due-chip ${isOverdue(task) ? "overdue" : ""}">${isOverdue(task) ? "已逾期 · " : "截止 · "}${escapeHtml(task.due_date)}</span>` : `<span class="due-chip unset">未设置截止日期</span>`;
    const tags = (task.tags || []).slice(0, 3).map((tag) => `<span class="tag-chip">${escapeHtml(tag)}</span>`).join("");
    const tagLine = `${tags}${task.source === "agent" ? `<span class="tag-chip agent">agent</span>` : ""}`;
    return `<article class="task-card p-${task.priority} ${done ? "done" : ""}" id="task-${task.id}" data-id="${task.id}" tabindex="0">
      <div class="task-top"><div class="task-check ${done ? "checked" : ""}" data-action="toggle" role="checkbox" aria-checked="${done}">${done ? "✓" : ""}</div><div class="task-title">${escapeHtml(task.title)}</div><button class="task-more" data-action="detail" aria-label="打开任务详情">···</button></div>
      ${task.description ? `<div class="task-description">${escapeHtml(task.description)}</div>` : ""}
      <div class="task-card-bottom">${tagLine ? `<div class="task-tags">${tagLine}</div>` : ""}<div class="task-facts">${due}<span class="priority-label p-${task.priority}">${priorityText[task.priority]}优先级</span></div></div>
      <div class="task-actions"><button class="mini-btn" data-action="edit">编辑</button><button class="mini-btn del" data-action="delete">删除</button></div>
    </article>`;
  }

  function renderWorkspace(tasks) {
    state.tasks = Array.isArray(tasks) ? tasks : [];
    renderSummary(state.tasks);
    renderPlan(state.tasks);
    const visible = sortTasks(state.tasks.filter(taskMatches));
    const lane = $("#lane-doing");
    $("#lanes").classList.toggle("archive", state.mode === "archive");
    lane.innerHTML = visible.length ? visible.map(taskCard).join("") : `<div class="lane-empty workspace-empty"><span>${state.mode === "archive" ? "✓" : "○"}</span><strong>${state.mode === "archive" ? "还没有完成记录" : "当前没有进行中的工作"}</strong><small>${state.query || state.priority !== "all" || state.due !== "all" ? "可以清除筛选查看全部内容" : state.mode === "archive" ? "完成的任务会安静地收在这里" : "可以给自己留一点空间，或者创建一件新工作"}</small></div>`;
    $("#workspace-mode-title").textContent = state.mode === "archive" ? "整理完成记录" : "筛选与排序";
    $("#workspace-mode-hint").textContent = state.mode === "archive" ? `共 ${visible.length} 条记录` : "按优先级、日期或更新时间";
    updateFilterUi();
  }

  function recurringReminderText(value) {
    const days = Number(value);
    if (days < 0) return "不提醒";
    if (days === 0) return "当天提醒";
    return `提前 ${days} 天提醒`;
  }

  function recurringNextText(task) {
    if (!task.enabled) return "已暂停，不再提醒";
    if (!task.next_due_date) return "暂无下一次安排";
    const days = Number(task.days_until);
    const prefix = days === 0 ? "今天" : days === 1 ? "明天" : humanDate(task.next_due_date);
    return `下次 · ${prefix}`;
  }

  function renderRecurringTasks(items = state.recurring) {
    const list = $("#recurring-list");
    if (!list) return;
    const ordered = [...items].sort((a, b) => Number(b.enabled) - Number(a.enabled) || String(a.next_due_date || "9999").localeCompare(String(b.next_due_date || "9999")));
    list.innerHTML = ordered.length ? ordered.map((task) => `<article class="recurring-card ${task.enabled ? "" : "paused"}" data-recurring-id="${task.id}">
      <button class="recurring-open" data-recurring-action="detail" type="button">
        <span class="recurring-glyph" aria-hidden="true">↻</span>
        <span class="recurring-copy"><strong>${escapeHtml(task.title)}</strong><small>${escapeHtml(task.schedule_label)} · ${escapeHtml(recurringNextText(task))}</small></span>
      </button>
      <div class="recurring-meta"><span>${escapeHtml(recurringReminderText(task.remind_days))}</span><span>${Number(task.completion_count || 0)} 次完成</span></div>
      <div class="recurring-actions"><button class="btn primary sm" data-recurring-action="complete" type="button" ${task.enabled ? "" : "disabled"}>完成本次</button><button class="recurring-more" data-recurring-action="detail" type="button" aria-label="查看定时任务详情">···</button></div>
    </article>`).join("") : `<div class="recurring-empty"><span>↻</span><strong>还没有定时任务</strong><small>把每周、每月重复发生的事情安排在这里。</small></div>`;
    renderDeadlineReminder(state.tasks);
  }

  async function loadRecurringTasks() {
    try {
      state.recurring = await api("/api/recurring-tasks");
      renderRecurringTasks();
    } catch (error) {
      const list = $("#recurring-list");
      if (list) list.innerHTML = `<div class="recurring-empty"><strong>定时任务暂时无法读取</strong><small>${escapeHtml(error.message || "请稍后重试")}</small></div>`;
    }
  }

  function recurringScheduleOptions(type, selected) {
    if (type === "monthly") {
      return Array.from({ length: 31 }, (_, index) => {
        const value = index + 1;
        const label = value === 31 ? "最后一天" : `${value} 日`;
        return `<option value="${value}" ${Number(selected) === value ? "selected" : ""}>${label}</option>`;
      }).join("");
    }
    return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map((label, index) => `<option value="${index + 1}" ${Number(selected) === index + 1 ? "selected" : ""}>${label}</option>`).join("");
  }

  function openRecurringEditor(task = null) {
    const editing = Boolean(task);
    $("#modal-title").textContent = editing ? "编辑定时任务" : "新建定时任务";
    $("#modal-body").innerHTML = `<div class="recurring-form">
      <label><span>任务名称</span><input id="recurring-title" maxlength="200" placeholder="例如：整理本周账目" value="${escapeHtml(task?.title || "")}"></label>
      <label><span>补充说明</span><textarea id="recurring-description" maxlength="1000" placeholder="可选，写下需要注意的事项">${escapeHtml(task?.description || "")}</textarea></label>
      <div class="recurring-form-grid">
        <label><span>重复方式</span><select id="recurring-type"><option value="weekly" ${task?.schedule_type !== "monthly" ? "selected" : ""}>每周</option><option value="monthly" ${task?.schedule_type === "monthly" ? "selected" : ""}>每月</option></select></label>
        <label><span id="recurring-value-label">${task?.schedule_type === "monthly" ? "每月日期" : "每周日期"}</span><select id="recurring-value"></select></label>
        <label><span>提醒时间</span><select id="recurring-reminder"><option value="0">当天提醒</option><option value="1">提前 1 天</option><option value="2">提前 2 天</option><option value="3">提前 3 天</option><option value="7">提前 7 天</option><option value="-1">不提醒</option></select></label>
      </div>
      <p class="recurring-form-hint">选择“每月最后一天”时，会自动适配二月和只有 30 天的月份。</p>
    </div>`;
    openModal();
    $("#modal-ok").textContent = editing ? "保存修改" : "创建任务";
    const typeInput = $("#recurring-type");
    const valueInput = $("#recurring-value");
    const updateValues = (selected) => {
      valueInput.innerHTML = recurringScheduleOptions(typeInput.value, selected || 1);
      $("#recurring-value-label").textContent = typeInput.value === "monthly" ? "每月日期" : "每周日期";
    };
    updateValues(task?.schedule_value || 1);
    $("#recurring-reminder").value = String(task?.remind_days ?? 1);
    typeInput.addEventListener("change", () => updateValues(1));
    $("#recurring-title").focus();
    window.modalConfirmAction = async () => {
      const title = $("#recurring-title").value.trim();
      if (!title) { toast("请填写任务名称"); return; }
      const payload = {
        title,
        description: $("#recurring-description").value.trim(),
        schedule_type: typeInput.value,
        schedule_value: Number(valueInput.value),
        remind_days: Number($("#recurring-reminder").value)
      };
      const button = $("#modal-ok");
      button.disabled = true;
      try {
        await api(editing ? `/api/recurring-tasks/${task.id}` : "/api/recurring-tasks", { method: editing ? "PATCH" : "POST", body: JSON.stringify(payload) });
        closeModal();
        toast(editing ? "定时任务已更新" : "定时任务已创建");
        await loadRecurringTasks();
        if (state.view === "calendar" && typeof loadCalendar === "function") loadCalendar();
      } catch (error) { toast(error.message || "保存失败"); }
      finally { button.disabled = false; }
    };
  }

  async function completeRecurringTask(id, keepDetail = false) {
    try {
      const result = await api(`/api/recurring-tasks/${id}/complete`, { method: "POST", body: "{}" });
      toast(result.already_completed ? "这一期已经完成" : "已记录本次完成");
      await loadRecurringTasks();
      if (state.view === "calendar" && typeof loadCalendar === "function") loadCalendar();
      if (keepDetail) openRecurringDetail(id);
    } catch (error) { toast(error.message || "记录失败"); }
  }

  async function openRecurringDetail(id) {
    let task;
    try { task = await api(`/api/recurring-tasks/${id}`); }
    catch (error) { toast(error.message || "无法打开定时任务"); return; }
    const history = task.completions || [];
    const historyHtml = history.length ? history.map((item) => `<div class="recurring-history-item" data-completion-id="${item.id}"><span class="recurring-history-check">✓</span><div><strong>${escapeHtml(humanDate(item.scheduled_date))}</strong><small>完成于 ${escapeHtml(formatDetailTime(item.completed_at))}</small></div><button data-recurring-detail-action="undo" type="button">撤销</button></div>`).join("") : `<div class="recurring-history-empty">完成一次后，记录会按时间出现在这里。</div>`;
    $("#modal-title").textContent = "定时任务";
    $("#modal-body").innerHTML = `<div class="recurring-detail">
      <div class="recurring-detail-hero"><span class="recurring-detail-glyph">↻</span><div><span>${escapeHtml(task.schedule_label)}</span><h3>${escapeHtml(task.title)}</h3><p>${escapeHtml(task.description || "保持节奏，每次完成都会自动留下记录。")}</p></div></div>
      <div class="recurring-detail-facts"><span><small>下一次</small><strong>${escapeHtml(task.enabled ? humanDate(task.next_due_date) : "已暂停")}</strong></span><span><small>提醒</small><strong>${escapeHtml(recurringReminderText(task.remind_days))}</strong></span><span><small>累计完成</small><strong>${Number(task.completion_count || 0)} 次</strong></span></div>
      <div class="recurring-detail-actions"><button class="btn primary sm" data-recurring-detail-action="complete" type="button" ${task.enabled ? "" : "disabled"}>完成本次</button><button class="btn ghost sm" data-recurring-detail-action="edit" type="button">编辑</button><button class="btn ghost sm" data-recurring-detail-action="toggle" type="button">${task.enabled ? "暂停" : "恢复"}</button><button class="btn ghost sm recurring-delete" data-recurring-detail-action="delete" type="button">删除</button><button class="btn ghost sm" data-recurring-detail-action="close" type="button">关闭</button></div>
      <section class="recurring-history"><div class="recurring-history-heading"><div><span class="eyebrow">HISTORY</span><h4>完成历史</h4></div><small>${history.length} 条记录</small></div>${historyHtml}</section>
    </div>`;
    openModalWide();
    $("#modal-body").onclick = async (event) => {
      const button = event.target.closest("[data-recurring-detail-action]");
      if (!button) return;
      const action = button.dataset.recurringDetailAction;
      if (action === "close") { closeModal(); return; }
      if (action === "edit") { openRecurringEditor(task); return; }
      if (action === "complete") { await completeRecurringTask(id, true); return; }
      if (action === "toggle") {
        try {
          await api(`/api/recurring-tasks/${id}`, { method: "PATCH", body: JSON.stringify({ enabled: !task.enabled }) });
          toast(task.enabled ? "定时任务已暂停" : "定时任务已恢复");
          await loadRecurringTasks();
          openRecurringDetail(id);
        } catch (error) { toast(error.message || "更新失败"); }
        return;
      }
      if (action === "delete") {
        const allowed = await confirmDialog("删除后，相关完成历史也会一并移除。", { title: "删除定时任务", okText: "删除" });
        if (!allowed) return;
        try {
          await api(`/api/recurring-tasks/${id}`, { method: "DELETE" });
          closeModal();
          toast("定时任务已删除");
          await loadRecurringTasks();
          if (state.view === "calendar" && typeof loadCalendar === "function") loadCalendar();
        } catch (error) { toast(error.message || "删除失败"); }
        return;
      }
      if (action === "undo") {
        const item = button.closest("[data-completion-id]");
        if (!item) return;
        try {
          await api(`/api/recurring-completions/${item.dataset.completionId}`, { method: "DELETE" });
          toast("完成记录已撤销");
          await loadRecurringTasks();
          if (state.view === "calendar" && typeof loadCalendar === "function") loadCalendar();
          openRecurringDetail(id);
        } catch (error) { toast(error.message || "撤销失败"); }
      }
    };
  }

  function updateFilterUi() {
    $("#filter-priority").value = state.priority;
    $("#filter-due").value = state.due;
    $("#sort-tasks").value = state.sort;
    $("#filter-due").hidden = state.mode === "archive";
    const active = state.query || state.priority !== "all" || (state.mode === "active" && state.due !== "all");
    $("#clear-filters").hidden = !active || state.view !== "board";
  }

  function setFilter(key, value) {
    state[key] = value;
    renderWorkspace(state.tasks);
  }

  async function openDetailDrawer(id, options = {}) {
    const fallback = state.tasks.find((task) => task.id === id);
    if (!fallback) return;
    if (!options.keepEditing) state.editingProgressId = null;
    $("#detail-drawer").dataset.id = String(id);
    $("#detail-drawer").classList.add("open");
    $("#detail-drawer").setAttribute("aria-hidden", "false");
    $("#detail-content").innerHTML = `<div class="detail-loading">正在打开任务…</div>`;
    const task = await api(`/api/tasks/${id}`).catch(() => fallback);
    const records = await loadTaskProgressRecords(id).catch(() => []);
    const events = [...(task.events || [])].reverse().map(renderTaskEvent).join("") || `<div class="detail-empty">暂无操作记录</div>`;
    const active = task.status !== "done";
    const recordHtml = records.map((record, index) => {
      const editing = state.editingProgressId === record.recordId;
      if (editing) {
        return `<article class="progress-record editing" data-record-id="${escapeHtml(record.recordId)}"><div class="progress-record-rail"><span>${String(records.length - index).padStart(2, "0")}</span></div><div class="progress-record-main"><textarea class="progress-edit-input" maxlength="2000">${escapeHtml(record.content)}</textarea><div class="progress-edit-actions"><button class="btn ghost sm" data-detail-action="cancel-progress">取消</button><button class="btn primary sm" data-detail-action="save-progress">保存修改</button></div></div></article>`;
      }
      const changed = record.updatedAt && record.updatedAt !== record.createdAt;
      const stamp = formatProgressTime(record.createdAt);
      const source = record.source === "agent" ? "AGENT" : "NOTE";
      return `<article class="progress-record" data-record-id="${escapeHtml(record.recordId)}"><div class="progress-record-rail"><span>${String(records.length - index).padStart(2, "0")}</span></div><div class="progress-record-main"><div class="progress-record-head"><div class="progress-record-meta"><time><strong>${escapeHtml(stamp.date)}</strong><span>${escapeHtml(stamp.time)}</span></time><span class="progress-source">${source}</span>${changed ? `<span class="progress-edited">已编辑</span>` : ""}</div><div class="progress-record-actions"><button data-detail-action="edit-progress" aria-label="编辑进度">${uiIcon("edit")}<span>编辑</span></button><button class="danger" data-detail-action="delete-progress" aria-label="删除进度">${uiIcon("close")}<span>删除</span></button></div></div><p>${escapeHtml(record.content)}</p></div></article>`;
    }).join("") || `<div class="detail-empty">还没有进度记录，可以从上方添加第一条。</div>`;
    const reminderText = task.due_date && Number(task.remind_days) >= 0
      ? Number(task.remind_days) === 0 ? "当天提醒" : `提前 ${task.remind_days} 天提醒`
      : "";
    $("#detail-content").innerHTML = `<div class="detail-status-line"><span class="detail-status">${statusText[task.status]}</span><span class="priority-label p-${task.priority}">${priorityText[task.priority]}优先级</span></div><h2 class="detail-title">${escapeHtml(task.title)}</h2><div class="detail-chips">${(task.tags || []).map((tag) => `<span class="tag-chip">${escapeHtml(tag)}</span>`).join("")}${task.due_date ? `<span class="detail-date ${isOverdue(task) ? "overdue" : ""}">${isOverdue(task) ? "已逾期 · " : "截止 · "}${escapeHtml(task.due_date)}</span>` : ""}${reminderText ? `<span class="detail-reminder">${escapeHtml(reminderText)}</span>` : ""}</div><section class="progress-composer"><div class="progress-composer-head"><span class="detail-section-label">写一条进展</span><small>把重要节点留在这里</small></div><textarea id="task-progress-new" maxlength="2000" placeholder="完成了什么、遇到什么问题，或下一步准备做什么…"></textarea><button class="btn primary sm" data-detail-action="add-progress">添加记录</button></section><section class="progress-history"><div class="detail-section-heading"><span class="detail-section-title">${uiIcon("history")}进度历史</span><small>${records.length} 条记录</small></div><div class="progress-record-list">${recordHtml}</div></section><div class="detail-actions">${active ? `<button class="btn primary sm" data-detail-action="complete">标记完成</button>` : `<button class="btn ghost sm" data-detail-action="restore">重新进行</button>`}<button class="btn ghost sm" data-detail-action="edit">编辑任务信息</button><button class="btn ghost sm" data-detail-action="delete">删除</button></div><div class="detail-timeline"><div class="detail-section-heading"><span class="detail-section-label">操作记录</span><small>自动保存</small></div>${events}</div>`;
  }

  function closeDetailDrawer() {
    $("#detail-drawer").classList.remove("open");
    $("#detail-drawer").setAttribute("aria-hidden", "true");
  }

  async function setTaskStatus(id, status) {
    try {
      if (typeof confirmTaskStatusChange === "function" && !await confirmTaskStatusChange(status)) return;
    } catch (_) { /* confirmation preference is optional */ }
    try {
      await api(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
      closeDetailDrawer();
      if (typeof reloadAll === "function") reloadAll();
    } catch (error) { toast(error.message || "更新失败"); }
  }

  async function redesignedDeleteTask(id) {
    let allowed = true;
    try { if (typeof SETTINGS !== "undefined" && SETTINGS.confirm_delete_task !== "0") allowed = await confirmDialog("确定删除这个任务吗？删除后无法撤销。", { okText: "删除", title: "删除任务" }); }
    catch (_) { /* settings are optional */ }
    if (!allowed) return;
    closeDetailDrawer();
    try {
      const progressRecords = await loadTaskProgressRecords(id).catch(() => []);
      await api(`/api/tasks/${id}`, { method: "DELETE" });
      await Promise.all(progressRecords.filter((record) => record.noteId).map((record) => api(`/api/notes/${record.noteId}`, { method: "DELETE" }).catch(() => null)));
      if (typeof loadNotes === "function") loadNotes();
      toast("已删除");
      reloadAll();
    } catch (error) { toast(error.message || "删除失败"); }
  }

  function syncNavigation() {
    $$(".nav-item").forEach((button) => button.classList.remove("active"));
    if (state.view === "board" && state.mode === "archive") $("#nav-done").classList.add("active");
    else $(`#nav-${state.view}`)?.classList.add("active");
  }

  function setView(view) {
    closeDetailDrawer();
    state.view = view;
    document.body.classList.toggle("archive-view", view === "board" && state.mode === "archive");
    syncNavigation();
    $("#board-view").classList.toggle("hidden", view !== "board");
    $("#today-view").classList.toggle("hidden", view !== "today");
    $("#cal-view").classList.toggle("hidden", view !== "calendar");
    $("#focus-view").classList.toggle("hidden", view !== "focus");
    $("#ai-view").classList.toggle("hidden", view !== "ai");
    $("#settings-view").classList.toggle("hidden", view !== "settings");
    const boardMeta = state.mode === "archive"
      ? ["ARCHIVE", "已完成", "完成的工作，安静地收在这里。"]
      : ["ACTIVE WORK", "正在进行", "把此刻最重要的事情放在眼前。"];
    const meta = { board: boardMeta, today: ["TIME PLAN", "计划", "今天先做什么，接下来做什么。"], calendar: ["PLANNING", "日历", "重要日期与每日记录，一目了然。"], focus: ["DEEP WORK", "专注", "留一点完整的时间，给真正重要的事。"], ai: ["AGENT CONNECTION", "AI 接入", "让你的 Agent 与 ShyBoard 保持同步。"], settings: ["PREFERENCES", "设置", "按你的习惯调整 ShyBoard。"] }[view];
    $("#view-eyebrow").textContent = meta[0];
    $("#view-title").textContent = meta[1];
    $("#view-subtitle").textContent = meta[2];
    $("#board-toolbar").classList.toggle("hidden", view !== "board");
    const showCreate = view === "board" && state.mode === "active";
    $("#focus-quick-add").classList.toggle("hidden", !showCreate);
    $("#summary-strip").classList.toggle("hidden", view !== "board" || state.mode === "archive");
    $("#recurring-section").classList.toggle("hidden", view !== "board" || state.mode === "archive");
    updateFilterUi();
    if (view === "calendar" && typeof loadCalendar === "function") loadCalendar();
    if (view === "focus") updateFocusPage();
    if (view === "ai" && typeof loadAiGuide === "function") loadAiGuide();
    if (view === "settings" && typeof loadSettings === "function") loadSettings();
  }

  function openActiveBoard() {
    state.mode = "active";
    state.due = "all";
    setView("board");
    renderWorkspace(state.tasks);
  }

  function openArchive() {
    state.mode = "archive";
    state.due = "all";
    setView("board");
    renderWorkspace(state.tasks);
  }

  function updateFocusPage() {
    if (typeof pomoRender === "function") pomoRender();
  }

  function bindInteractions() {
    $("#nav-board").addEventListener("click", () => openActiveBoard());
    $("#nav-today").addEventListener("click", () => setView("today"));
    $("#nav-calendar").addEventListener("click", () => setView("calendar"));
    $("#nav-focus").addEventListener("click", () => setView("focus"));
    $("#nav-ai").addEventListener("click", () => setView("ai"));
    $("#nav-settings").addEventListener("click", () => setView("settings"));
    $$(".panel-link[data-view]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
    $("#nav-done").addEventListener("click", openArchive);
    $("#deadline-reminder").addEventListener("click", () => {
      if ($("#deadline-reminder").dataset.target === "recurring") {
        openActiveBoard();
        $("#recurring-section").scrollIntoView({ behavior: "smooth", block: "start" });
      } else setView("today");
    });
    $("#task-search").addEventListener("input", (event) => setFilter("query", event.target.value));
    $("#filter-priority").addEventListener("change", (event) => setFilter("priority", event.target.value));
    $("#filter-due").addEventListener("change", (event) => setFilter("due", event.target.value));
    $("#sort-tasks").addEventListener("change", (event) => setFilter("sort", event.target.value));
    $("#clear-filters").addEventListener("click", () => { Object.assign(state, { query: "", priority: "all", due: "all" }); $("#task-search").value = ""; renderWorkspace(state.tasks); });
    $("#focus-quick-add").addEventListener("click", () => { if (typeof openCreateTaskModal === "function") openCreateTaskModal(); });
    $("#add-recurring-task").addEventListener("click", () => openRecurringEditor());
    $("#recurring-list").addEventListener("click", (event) => {
      const card = event.target.closest("[data-recurring-id]");
      if (!card) return;
      const id = Number(card.dataset.recurringId);
      const action = event.target.closest("[data-recurring-action]")?.dataset.recurringAction || "detail";
      if (action === "complete") completeRecurringTask(id);
      else openRecurringDetail(id);
    });
    $("#toggle-sidebar").addEventListener("click", () => { if (window.matchMedia("(max-width: 1100px)").matches) document.body.classList.toggle("sidebar-open"); else document.body.classList.toggle("sidebar-collapsed"); });
    $("#close-sidebar").addEventListener("click", () => { if (window.matchMedia("(max-width: 1100px)").matches) document.body.classList.remove("sidebar-open"); else document.body.classList.add("sidebar-collapsed"); });
    $("#close-detail").addEventListener("click", closeDetailDrawer);
    $("#lanes").addEventListener("click", (event) => {
      const card = event.target.closest(".task-card");
      if (!card) return;
      event.stopImmediatePropagation();
      const id = Number(card.dataset.id);
      const action = event.target.closest("[data-action]")?.dataset.action;
      if (action === "toggle") setTaskStatus(id, card.classList.contains("done") ? "doing" : "done");
      else if (action === "edit" && typeof editTask === "function") editTask(id);
      else if (action === "delete") redesignedDeleteTask(id);
      else openDetailDrawer(id);
    }, true);

    $("#today-sections").addEventListener("click", (event) => {
      const task = event.target.closest(".plan-task");
      if (!task) return;
      if (event.target.closest("[data-plan-action='complete']")) setTaskStatus(Number(task.dataset.id), "done");
      else openDetailDrawer(Number(task.dataset.id));
    });

    $("#detail-content").addEventListener("click", async (event) => {
      const button = event.target.closest("[data-detail-action]");
      if (!button) return;
      const id = Number($("#detail-drawer").dataset.id || 0);
      const task = state.tasks.find((item) => item.id === id);
      if (!task) return;
      const action = button.dataset.detailAction;
      if (action === "add-progress") {
        const content = $("#task-progress-new")?.value || "";
        try {
          if (await saveTaskProgressRecord(id, content)) {
            toast("进度记录已添加");
            openDetailDrawer(id);
          }
        } catch (error) { toast(error.message || "记录保存失败"); }
        return;
      }
      if (action === "edit-progress") {
        state.editingProgressId = event.target.closest(".progress-record")?.dataset.recordId || null;
        openDetailDrawer(id, { keepEditing: true });
        return;
      }
      if (action === "cancel-progress") {
        state.editingProgressId = null;
        openDetailDrawer(id, { keepEditing: true });
        return;
      }
      if (action === "delete-progress") {
        const recordId = event.target.closest(".progress-record")?.dataset.recordId;
        try {
          const records = await loadTaskProgressRecords(id);
          const record = records.find((item) => item.recordId === recordId);
          if (!record) return;
          const allowed = await confirmDialog("确定删除这条进度记录吗？删除后无法恢复。", {
            title: "删除进度记录",
            okText: "删除"
          });
          if (!allowed) return;
          if (record.progressId) await api(`/api/progress/${record.progressId}`, { method: "DELETE" });
          else await api(`/api/notes/${record.noteId}`, { method: "DELETE" });
          if (!record.progressId && typeof loadNotes === "function") loadNotes();
          state.editingProgressId = null;
          toast("进度记录已删除");
          openDetailDrawer(id);
        } catch (error) { toast(error.message || "记录删除失败"); }
        return;
      }
      if (action === "save-progress") {
        const card = event.target.closest(".progress-record");
        const recordId = card?.dataset.recordId;
        const content = card?.querySelector(".progress-edit-input")?.value || "";
        try {
          const records = await loadTaskProgressRecords(id);
          const record = records.find((item) => item.recordId === recordId);
          if (record && await saveTaskProgressRecord(id, content, record)) {
            state.editingProgressId = null;
            toast("进度记录已更新");
            openDetailDrawer(id);
          }
        } catch (error) { toast(error.message || "记录更新失败"); }
        return;
      }
      if (action === "complete") setTaskStatus(id, "done");
      if (action === "restore") setTaskStatus(id, "doing");
      if (action === "edit" && typeof editTask === "function") editTask(id);
      if (action === "delete") redesignedDeleteTask(id);
    });

    document.addEventListener("keydown", (event) => {
      const tag = document.activeElement?.tagName;
      const editing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); $("#task-search").focus(); return; }
      if (!editing && event.key === "/") { event.preventDefault(); $("#task-search").focus(); return; }
      if (!editing && event.key.toLowerCase() === "n" && state.view === "board" && state.mode === "active") { event.preventDefault(); if (typeof openCreateTaskModal === "function") openCreateTaskModal(); return; }
      if (!editing && /^[1-4]$/.test(event.key)) { const target = Number(event.key); if (target === 1) openActiveBoard(); else setView([null, null, "today", "calendar", "focus"][target]); return; }
      if (event.key === "Escape") closeDetailDrawer();
    });
  }

  function patchRenderer() {
    try { renderTasks = renderWorkspace; _tasksSig = ""; } catch (_) { window.renderTasks = renderWorkspace; }
    try { deleteTask = redesignedDeleteTask; } catch (_) { window.deleteTask = redesignedDeleteTask; }
  }

  patchRenderer();
  bindInteractions();
  window.showSettingsPage = () => setView("settings");
  window.showWorkspacePage = () => openActiveBoard();
  window.loadRecurringTasks = loadRecurringTasks;
  try { _tasksSig = ""; loadTasks(); } catch (_) { /* startup race is harmless */ }
  loadRecurringTasks();
  setInterval(updateFocusPage, 500);
  setInterval(loadRecurringTasks, 30000);
})();
