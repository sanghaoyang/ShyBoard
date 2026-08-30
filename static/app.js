/* ===== ShyBoard · 前端逻辑 ===== */
"use strict";

const $ = (sel) => document.querySelector(sel);
const PRIORITY_TEXT = { high: "高", medium: "中", low: "低" };
const STATUS_TEXT = { todo: "进行中", doing: "进行中", done: "已完成" };
const WEEK = ["日", "一", "二", "三", "四", "五", "六"];

const UI_ICON_PATHS = {
  link: '<path d="M9.5 14.5 14.5 9m-6.8 1.1 1.9-1.9a3.4 3.4 0 0 1 4.8 0l1.4 1.4a3.4 3.4 0 0 1 0 4.8l-1.9 1.9m-3.8-6.6-1.9 1.9a3.4 3.4 0 0 0 0 4.8l1.4 1.4a3.4 3.4 0 0 0 4.8 0l1.9-1.9"/>',
  note: '<path d="M6 3.5h9.5L19 7v13.5H6z"/><path d="M15.5 3.5V7H19M9 11h7m-7 3h7m-7 3h4"/>',
  calendar: '<rect x="4" y="5.5" width="16" height="14.5" rx="2"/><path d="M8 3v5m8-5v5M4 10h16"/>',
  edit: '<path d="m4 20 4.2-1 9.9-9.9a2.1 2.1 0 0 0-3-3L5.2 16zM13.8 7.4l3 3"/>',
  close: '<path d="m7 7 10 10M17 7 7 17"/>',
  history: '<path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.5"/><path d="M4 4v4.5h4.5M12 7.5V12l3 2"/>',
};
function uiIcon(name, cls = "") {
  return `<svg class="ui-icon ${cls}" viewBox="0 0 24 24" aria-hidden="true">${UI_ICON_PATHS[name] || ""}</svg>`;
}

/* ---------- API 封装 ---------- */
async function api(path, opts = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || `请求失败 (${resp.status})`);
  return data;
}

/* ---------- Toast ---------- */
let toastTimer = null;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2200);
}

/* ---------- 设置 ---------- */
let SETTINGS = {};  // 从 /api/settings 加载；确认开关存 "0"/"1"

const THEMES = ["pink", "dark", "light", "orange", "green", "purple", "ocean"];
const THEME_LABELS = {
  pink: "柔粉",
  dark: "暖夜",
  light: "雾蓝",
  orange: "暖杏",
  green: "鼠尾草",
  purple: "暮紫",
  ocean: "静海青",
};

/* 应用主题：body[data-theme] 驱动 CSS 变量切换；pink 是默认，去掉属性 */
function applyTheme(theme) {
  const t = THEMES.includes(theme) ? theme : "pink";
  if (t === "pink") delete document.body.dataset.theme;
  else document.body.dataset.theme = t;
  document.querySelectorAll("#theme-picker .theme-opt").forEach((el) => {
    el.classList.toggle("active", el.dataset.theme === t);
  });
}

function applyFontSize(size) {
  const value = size === "large" ? "large" : "normal";
  if (value === "large") document.body.dataset.fontSize = "large";
  else delete document.body.dataset.fontSize;
  document.querySelectorAll("#font-size-picker .font-size-opt").forEach((el) => {
    el.classList.toggle("active", el.dataset.fontSize === value);
    el.setAttribute("aria-pressed", String(el.dataset.fontSize === value));
  });
}

async function loadSettings() {
  try {
    const s = await api("/api/settings");
    SETTINGS = s;
    applyTheme(s.theme || "pink");
    applyFontSize(s.font_size || "normal");
    // 同步开关状态
    $("#set-autostart").checked = s.autostart === "1";
    $("#set-confirm-task").checked = s.confirm_delete_task !== "0";
    $("#set-confirm-link").checked = s.confirm_delete_link !== "0";
    $("#set-confirm-note").checked = s.confirm_delete_note !== "0";
    SETTINGS.confirm_task_status = s.confirm_task_status !== "0" ? "1" : "0";
    $("#set-confirm-status").checked = SETTINGS.confirm_task_status !== "0";
    // 开机自启以注册表为准（首次进入时刷新一次）
    const a = await api("/api/settings/autostart").catch(() => null);
    if (a && typeof a.enabled === "boolean") {
      SETTINGS.autostart = a.enabled ? "1" : "0";
      $("#set-autostart").checked = a.enabled;
    }
  } catch (e) { /* 设置加载失败不阻塞 */ }
}

function openSettings() {
  loadSettings().then(() => {
    if (typeof window.showSettingsPage === "function") window.showSettingsPage();
  });
}

function closeSettings() {
  if (typeof window.showWorkspacePage === "function") window.showWorkspacePage();
}

// 开关变化 → 立即保存
function bindSettingSwitch(id, key, isBool = true) {
  $(id).addEventListener("change", async () => {
    const val = $(id).checked;
    try {
      await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({ [key]: isBool ? (val ? 1 : 0) : val }),
      });
      SETTINGS[key] = val ? "1" : "0";
    } catch (e) {
      toast(e.message);
      $(id).checked = !val;
    }
  });
}

async function setAutostart(enabled) {
  const res = await api("/api/settings/autostart", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
  if (res.error) throw new Error(res.error);
  SETTINGS.autostart = enabled ? "1" : "0";
}

$("#btn-settings").addEventListener("click", openSettings);
// 主题切换：立即生效并保存
$("#theme-picker").addEventListener("click", async (e) => {
  const opt = e.target.closest(".theme-opt");
  if (!opt) return;
  const theme = opt.dataset.theme;
  if (!theme || theme === (SETTINGS.theme || "pink")) return;
  applyTheme(theme);
  try {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ theme }),
    });
    SETTINGS.theme = theme;
    toast(`已切换到${THEME_LABELS[theme] || "柔粉"}主题`);
  } catch (err) {
    toast(err.message);
    applyTheme(SETTINGS.theme || "pink");
  }
});
$("#font-size-picker").addEventListener("click", async (e) => {
  const opt = e.target.closest(".font-size-opt");
  if (!opt) return;
  const fontSize = opt.dataset.fontSize;
  if (!fontSize || fontSize === (SETTINGS.font_size || "normal")) return;
  applyFontSize(fontSize);
  try {
    await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ font_size: fontSize }),
    });
    SETTINGS.font_size = fontSize;
    toast(fontSize === "large" ? "已切换到大号字体" : "已切换到正常字体");
  } catch (err) {
    toast(err.message);
    applyFontSize(SETTINGS.font_size || "normal");
  }
});
bindSettingSwitch("#set-confirm-task", "confirm_delete_task");
bindSettingSwitch("#set-confirm-link", "confirm_delete_link");
bindSettingSwitch("#set-confirm-note", "confirm_delete_note");
bindSettingSwitch("#set-confirm-status", "confirm_task_status");
$("#set-autostart").addEventListener("change", async (e) => {
  const val = e.target.checked;
  try {
    await setAutostart(val);
    toast(val ? "已开启开机自启" : "已关闭开机自启");
  } catch (err) {
    toast(err.message);
    e.target.checked = !val;
  }
});

/* ---------- 时钟 ---------- */
function tickClock() {
  const now = new Date();
  $("#date-line").textContent =
    `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 周${WEEK[now.getDay()]}`;
  $("#clock").textContent =
    `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
}
setInterval(tickClock, 1000);
tickClock();

/* ---------- 天气 ---------- */
let _weatherCache = null;

async function loadWeather() {
  try {
    const w = await api("/api/weather");
    _weatherCache = w;
    $("body").classList.add("has-weather");
    $("#w-icon").textContent = w.icon;
    $("#w-temp").textContent = `${Math.round(w.temp)}°C`;
    $("#w-city").textContent = `${w.city} · ${w.desc}`;
    $("#weather").title =
      `湿度 ${w.humidity} · 风 ${w.wind}` +
      (w.aqi ? ` · AQI ${w.aqi}` : "") +
      (w.sunrise ? `\n日出 ${w.sunrise} 日落 ${w.sunset}` : "") +
      `\n点击查看 7 天预报`;
  } catch (e) {
    $("body").classList.remove("has-weather");
    $("#w-temp").textContent = "--";
    $("#w-city").textContent = "天气不可用";
  }
}

const WEEK_SHORT = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

function openWeatherModal() {
  const w = _weatherCache;
  if (!w) { loadWeather().then(openWeatherModal); return; }
  $("#modal-title").textContent = `天气预报 · ${w.city}`;
  const today = new Date().toISOString().slice(0, 10);
  const days = (w.daily || []).map((d) => {
    const isToday = d.date === today;
    let week = d.week;
    if (!week && d.date) {
      week = WEEK_SHORT[new Date(d.date + "T00:00:00").getDay()];
    }
    return `
    <div class="forecast-day ${isToday ? "today" : ""}">
      <div class="f-day-week">${isToday ? "今天" : esc(week)}</div>
      <div class="f-day-date">${esc((d.date || "").slice(5))}</div>
      <div class="f-day-icon">${d.icon}</div>
      <div class="f-day-desc">${esc(d.desc)}</div>
      <div class="f-day-temp">${d.tmax != null ? d.tmax : "--"}° <span class="lo">${d.tmin != null ? d.tmin : "--"}°</span></div>
    </div>`;
  }).join("");
  const metaLines = [
    `湿度 ${w.humidity}`, `风 ${w.wind}`,
    w.aqi ? `AQI ${w.aqi}` : "",
    w.sunrise ? `日出 ${w.sunrise} · 日落 ${w.sunset}` : "",
  ].filter(Boolean);
  $("#modal-body").innerHTML = `
    <div class="weather-now">
      <span class="w-big-icon">${w.icon}</span>
      <div>
        <div class="w-temp-big">${Math.round(w.temp)}°C</div>
        <div class="w-desc">${esc(w.desc)}</div>
      </div>
      <div class="w-meta">${metaLines.join("<br>")}</div>
    </div>
    <div class="forecast-grid">${days || `<div class="lane-empty">暂无预报数据</div>`}</div>
    <div class="modal-actions" style="margin-top:14px">
      <button class="btn ghost" onclick="openCityModal()">修改城市</button>
      <button class="btn primary" onclick="closeModal()">关闭</button>
    </div>`;
  openModalWide();
}

/* ---------- 任务 ---------- */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function dueChip(due) {
  if (!due) return "";
  const today = new Date().toISOString().slice(0, 10);
  const cls = due < today ? "due-chip overdue" : "due-chip";
  return `<span class="${cls}">📅 ${due}</span>`;
}

function taskCard(t) {
  const isDone = t.status === "done";
  const check = isDone ? "checked" : "";
  const checkClick = isDone ? "restoreTask" : "completeTask";
  const agent = t.source === "agent"
    ? `<span class="tag-chip agent">🤖 agent</span>` : "";
  return `
  <div class="task-card p-${t.priority} ${isDone ? "done" : ""}" id="task-${t.id}">
    <div class="task-top">
      <div class="task-check ${check}" onclick="${checkClick}(${t.id})">✓</div>
      <div class="task-title">${esc(t.title)}</div>
    </div>
    ${t.description ? `<div class="task-meta" style="color:var(--text-dim);font-size:12px;margin-top:4px">${esc(t.description)}</div>` : ""}
    <div class="task-meta">
      ${t.tags.map((tag) => `<span class="tag-chip">${esc(tag)}</span>`).join("")}
      ${agent}
      ${dueChip(t.due_date)}
      <span class="due-chip">${PRIORITY_TEXT[t.priority]}优先级</span>
    </div>
    <div class="task-actions">
      <button class="mini-btn" onclick="editTask(${t.id})">✎ 编辑</button>
      <button class="mini-btn del" onclick="deleteTask(${t.id})">✕ 删除</button>
    </div>
  </div>`;
}

let _tasksSig = "";

async function loadTasks() {
  try {
    const tasks = await api("/api/tasks");
    const sig = JSON.stringify(tasks);
    if (sig === _tasksSig) return;  // 无变化不重绘，避免打断 hover/滚动
    _tasksSig = sig;
    renderTasks(tasks);
  } catch (e) { /* 轮询失败静默，不打扰 */ }
}

function renderTasks(tasks) {
  clearLanes();
  const lane = $("#lane-doing");
  if (!lane) return;
  const active = tasks.filter((task) => task.status !== "done");
  lane.innerHTML = active.length
    ? active.map(taskCard).join("")
    : `<div class="lane-empty">目前没有进行中的工作</div>`;
}

function clearLanes() {
  const lane = $("#lane-doing");
  if (lane) lane.innerHTML = "";
}

async function reloadAll() {
  loadTasks();
  // 日历视图可见 → 重绘日历（任务/纪念日标记变化）
  const calEl = document.getElementById("cal-view");
  if (calEl && !calEl.classList.contains("hidden")) loadCalendar();
  // 当天任务弹窗开着 → 刷新内容
  if (_dayModalDate && !document.getElementById("modal-mask").classList.contains("hidden")
      && document.getElementById("modal-title")?.textContent === dayTitle(_dayModalDate)) {
    loadDayModal();
  }
}

/* 刷新全部数据。auto=true 是后台轮询（只刷核心，轻量）；手动点击刷全部 */
async function refreshAll(auto = true) {
  loadTasks();
  api("/api/pomodoro").then((d) => {
    $("#pomo-count").textContent = `🍅 今日 ${d.count}`;
  }).catch(() => {});
  if (!auto) {
    loadNotes();
    loadLinks();
    loadWeather();
    loadAnns();
    if (!$("#cal-view").classList.contains("hidden")) loadCalendar();
  }
}

const TASK_REMINDER_OPTIONS = [
  [-1, "不提醒"], [0, "截止当天"], [1, "提前 1 天"], [3, "提前 3 天"],
  [7, "提前 7 天"], [14, "提前 14 天"], [30, "提前 30 天"],
];

function taskReminderOptions(selected = 3) {
  const value = Number.isFinite(Number(selected)) ? Number(selected) : 3;
  return TASK_REMINDER_OPTIONS.map(([days, label]) => `<option value="${days}" ${value === days ? "selected" : ""}>${label}</option>`).join("");
}

function syncTaskReminderControl(dueId, reminderId) {
  const due = document.getElementById(dueId);
  const reminder = document.getElementById(reminderId);
  if (!due || !reminder) return;
  const sync = () => {
    reminder.disabled = !due.value;
    reminder.title = due.value ? "选择何时显示截止提醒" : "设置截止日期后可选择提醒时间";
  };
  due.addEventListener("change", sync);
  sync();
}

function openCreateTaskModal() {
  $("#modal-title").textContent = "创建任务";
  $("#modal-body").innerHTML = `
    <div class="create-task-form">
      <label for="create-task-title">任务标题</label>
      <input id="create-task-title" type="text" maxlength="120" placeholder="现在最想完成什么？" autocomplete="off">
      <label for="create-task-desc">任务描述</label>
      <textarea id="create-task-desc" placeholder="补充背景、步骤或完成标准（可选）"></textarea>
      <div class="create-task-row deadline-row">
        <div><label for="create-task-priority">优先级</label><select id="create-task-priority"><option value="high">高优先级</option><option value="medium" selected>中优先级</option><option value="low">低优先级</option></select></div>
        <div><label for="create-task-due">截止日期</label><input id="create-task-due" type="date"></div>
        <div><label for="create-task-reminder">截止提醒</label><select id="create-task-reminder">${taskReminderOptions(3)}</select></div>
      </div>
      <label for="create-task-tags">标签</label>
      <div class="tag-editor">
        <div class="tag-editor-values" aria-live="polite"></div>
        <input id="create-task-tags" type="text" maxlength="24" placeholder="输入后按回车添加" autocomplete="off">
      </div>
      <div class="field-hint">支持回车、逗号、顿号或分号；点击标签可移除</div>
    </div>`;
  openModal();
  $("#modal").classList.add("create-task-modal");
  $("#modal-ok").textContent = "创建任务";
  setupTagEditor("create-task-tags");
  syncTaskReminderControl("create-task-due", "create-task-reminder");
  $("#create-task-title").addEventListener("keydown", (e) => {
    if (e.key === "Enter") createTask();
  });
  setTimeout(() => $("#create-task-title").focus(), 50);
}

async function createTask() {
  const title = $("#create-task-title")?.value.trim();
  if (!title) { toast("请输入任务标题"); return; }
  try {
    await api("/api/tasks", {
      method: "POST",
      body: JSON.stringify({
        title,
        status: "doing",
        priority: $("#create-task-priority").value,
        due_date: $("#create-task-due").value,
        remind_days: Number($("#create-task-reminder").value),
        tags: readTagEditor("create-task-tags"),
        description: $("#create-task-desc").value,
        source: "manual",
      }),
    });
    closeModal();
    toast("任务已创建");
    reloadAll();
  } catch (e) { toast(e.message); }
}

async function confirmTaskStatusChange(status) {
  if (SETTINGS.confirm_task_status === "0") return true;
  const completing = status === "done";
  return confirmDialog(
    completing ? "确定将这个任务标记为已完成吗？" : "确定将这个任务恢复为未完成吗？",
    {
      okText: completing ? "设为完成" : "恢复任务",
      title: completing ? "完成任务" : "恢复任务",
      icon: completing ? "✓" : "↻",
      tone: "primary",
    },
  );
}

async function completeTask(id) {
  if (!await confirmTaskStatusChange("done")) return;
  try { await api(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status: "done" }) }); }
  catch (e) { toast(e.message); }
  reloadAll();
}

async function restoreTask(id) {
  if (!await confirmTaskStatusChange("doing")) return;
  try { await api(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status: "doing" }) }); }
  catch (e) { toast(e.message); }
  reloadAll();
}

async function startTask(id) {
  try { await api(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status: "doing" }) }); }
  catch (e) { toast(e.message); }
  reloadAll();
}

async function deleteTask(id) {
  if (SETTINGS.confirm_delete_task !== "0") {
    if (!await confirmDialog("确定删除这个任务吗？", { okText: "删除", title: "删除任务" })) return;
  }
  try { await api(`/api/tasks/${id}`, { method: "DELETE" }); toast("已删除"); }
  catch (e) { toast(e.message); }
  reloadAll();
}

/* ---------- 编辑任务弹窗 ---------- */
let editingTask = null;

function splitTaskTags(value) {
  const raw = Array.isArray(value) ? value : String(value || "").split(/[,，、;；\n\r]+/);
  return [...new Set(raw.map((tag) => String(tag).trim()).filter(Boolean))].slice(0, 12);
}

function setupTagEditor(inputId, initialTags = []) {
  const input = document.getElementById(inputId);
  const editor = input?.closest(".tag-editor");
  const values = editor?.querySelector(".tag-editor-values");
  if (!input || !editor || !values) return;
  editor._tags = splitTaskTags(initialTags);
  const render = () => {
    values.innerHTML = editor._tags.map((tag, index) => `<button type="button" class="tag-editor-chip" data-tag-index="${index}" title="移除 ${esc(tag)}"><span>${esc(tag)}</span>${uiIcon("close")}</button>`).join("");
    values.hidden = editor._tags.length === 0;
  };
  const commit = () => {
    const additions = splitTaskTags(input.value);
    if (additions.length) editor._tags = splitTaskTags([...editor._tags, ...additions]);
    input.value = "";
    render();
  };
  editor._commitTags = commit;
  input.addEventListener("keydown", (event) => {
    if (event.isComposing) return;
    if (["Enter", ",", "，", "、", ";", "；"].includes(event.key)) {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && !input.value && editor._tags.length) {
      editor._tags.pop();
      render();
    }
  });
  input.addEventListener("input", () => {
    if (/[,，、;；\n\r]/.test(input.value)) commit();
  });
  input.addEventListener("blur", commit);
  values.addEventListener("click", (event) => {
    const chip = event.target.closest(".tag-editor-chip");
    if (!chip) return;
    editor._tags.splice(Number(chip.dataset.tagIndex), 1);
    render();
    input.focus();
  });
  render();
}

function readTagEditor(inputId) {
  const input = document.getElementById(inputId);
  const editor = input?.closest(".tag-editor");
  editor?._commitTags?.();
  return editor?._tags || [];
}

function editTask(id) {
  api(`/api/tasks/${id}`).then((t) => {
    editingTask = t;
    $("#modal-title").textContent = "编辑任务";
    $("#modal-body").innerHTML = `
      <label>标题</label>
      <input id="e-title" value="${esc(t.title)}">
      <label>描述</label>
      <textarea id="e-desc">${esc(t.description)}</textarea>
      <label>进度</label>
      <select id="e-status">
        <option value="doing" ${t.status !== "done" ? "selected" : ""}>进行中</option>
        <option value="done" ${t.status === "done" ? "selected" : ""}>已完成</option>
      </select>
      <div class="create-task-row deadline-row">
        <div>
          <label>优先级</label>
          <select id="e-priority">
            ${Object.entries(PRIORITY_TEXT).map(([k, v]) =>
              `<option value="${k}" ${t.priority === k ? "selected" : ""}>${v}优先级</option>`).join("")}
          </select>
        </div>
        <div>
          <label>截止日期</label>
          <input id="e-due" type="date" value="${esc(t.due_date)}">
        </div>
        <div>
          <label>截止提醒</label>
          <select id="e-reminder">${taskReminderOptions(t.remind_days)}</select>
        </div>
      </div>
      <label for="e-tags">标签</label>
      <div class="tag-editor">
        <div class="tag-editor-values" aria-live="polite"></div>
        <input id="e-tags" type="text" maxlength="24" placeholder="输入后按回车添加" autocomplete="off">
      </div>
      <div class="field-hint">支持回车、逗号、顿号或分号；点击标签可移除</div>`;
    openModal();
    setupTagEditor("e-tags", t.tags);
    syncTaskReminderControl("e-due", "e-reminder");
  });
}

async function saveTaskEdit() {
  if (!editingTask) return;
  const nextStatus = $("#e-status").value;
  const wasDone = editingTask.status === "done";
  const willBeDone = nextStatus === "done";
  if (wasDone !== willBeDone && !await confirmTaskStatusChange(nextStatus)) return;
  api(`/api/tasks/${editingTask.id}`, {
    method: "PATCH",
    body: JSON.stringify({
      title: $("#e-title").value,
      description: $("#e-desc").value,
      status: nextStatus,
      priority: $("#e-priority").value,
      due_date: $("#e-due").value,
      remind_days: Number($("#e-reminder").value),
      tags: readTagEditor("e-tags"),
    }),
  }).then(() => {
    closeModal();
    toast("已保存");
    reloadAll();
  }).catch((e) => toast(e.message));
}

/* ---------- 城市设置弹窗 ---------- */
async function openCityModal() {
  $("#modal-title").textContent = "修改城市";
  $("#modal-body").innerHTML = `
    <label>输入城市名（仅支持国内城市）</label>
    <input id="city-input" placeholder="例如：杭州 / 深圳">
    <div id="city-suggest"></div>`;
  openModal();
  const input = $("#city-input");
  let timer = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) { $("#city-suggest").innerHTML = ""; return; }
    timer = setTimeout(async () => {
      try {
        const list = await api(`/api/weather/search?q=${encodeURIComponent(q)}`);
        $("#city-suggest").innerHTML = list.map((c) =>
          `<button class="suggest-item" onclick="setCity('${c.c}', '${esc(c.n)}')">
            ${esc(c.n)} · ${esc(c.p)}</button>`).join("") ||
          `<div class="lane-empty">未找到城市，试试省会更名</div>`;
      } catch (e) { /* 忽略 */ }
    }, 200);
  });
  setTimeout(() => input.focus(), 50);
}

function setCity(code, name) {
  api("/api/settings", {
    method: "PUT",
    body: JSON.stringify({ city_code: code, city: name }),
  }).then(() => {
    closeModal();
    toast(`已切换城市：${name}`);
    loadWeather();
  }).catch((e) => toast(e.message));
}

/* ---------- 快捷方式 ---------- */
let _linksCache = [];
let editingLink = null;

/* 图标判断：/icons/ 开头的路径 → 用 img 显示；否则当 emoji 文本 */
function isIconUrl(icon) {
  return typeof icon === "string" && icon.startsWith("/icons/");
}
function iconHtml(icon) {
  if (isIconUrl(icon)) return `<img class="link-favicon" src="${esc(icon)}" alt="" onerror="this.style.display='none'">`;
  return icon ? esc(icon) : uiIcon("link");
}

async function loadLinks() {
  try {
    const links = await api("/api/links");
    _linksCache = links;
    $("body").classList.toggle("has-link-icons", links.some((l) => isIconUrl(l.icon)));
    $("#links").innerHTML = links.map((l) => `
      <div class="link-item" data-url="${esc(l.url)}" data-id="${l.id}" tabindex="0">
        <span class="link-icon">${iconHtml(l.icon)}</span>
        <span class="link-copy"><span class="link-name">${esc(l.name)}</span><small>${esc(String(l.url).replace(/^https?:\/\//, "").split("/")[0])}</small></span>
        <span class="link-arrow" aria-hidden="true">↗</span>
        <button class="link-edit" title="编辑" aria-label="编辑 ${esc(l.name)}">${uiIcon("edit")}</button>
        <button class="link-del" title="删除" aria-label="删除 ${esc(l.name)}">${uiIcon("close")}</button>
      </div>`).join("") || `<div class="lane-empty" style="padding:10px 0">暂无快捷方式</div>`;
    $("#links").onclick = (e) => {
      const item = e.target.closest(".link-item");
      if (!item) return;
      if (e.target.closest(".link-del")) {
        deleteLink(+item.dataset.id);
        return;
      }
      if (e.target.closest(".link-edit")) {
        openLinkModal(+item.dataset.id);
        return;
      }
      window.open(item.dataset.url, "_blank");
    };
    $("#links").onkeydown = (e) => {
      if (!["Enter", " "].includes(e.key) || e.target.closest(".link-del, .link-edit")) return;
      const item = e.target.closest(".link-item");
      if (!item) return;
      e.preventDefault();
      window.open(item.dataset.url, "_blank");
    };
  } catch (e) { /* 忽略 */ }
}

function openLinkModal(linkId = null) {
  if (typeof linkId !== "number") linkId = null;
  editingLink = linkId ? _linksCache.find((item) => item.id === linkId) || null : null;
  _fetchedIcon = "";
  $("#modal-title").textContent = editingLink ? "编辑快捷方式" : "添加快捷方式";
  $("#modal-body").innerHTML = `
    <label>名称</label>
    <input id="l-name" placeholder="例如：GitHub" value="${esc(editingLink?.name || "")}">
    <label>网址</label>
    <div style="display:flex;gap:8px">
      <input id="l-url" placeholder="https://github.com" value="${esc(editingLink?.url || "")}" style="flex:1">
      <button class="btn ghost sm" id="l-fetch" type="button" title="获取网站图标">自动获取图标</button>
    </div>
    <div id="l-preview" style="display:none;margin-top:10px">
      <img id="l-preview-img" class="link-favicon" style="width:28px;height:28px" alt="">
      <span id="l-preview-name" style="font-size:12px;color:var(--text-dim);margin-left:8px"></span>
    </div>
    <label>图标（可选）</label>
    <input id="l-icon" value="${esc(editingLink?.icon || "")}" placeholder="可填写一个 emoji，或自动获取">
    <div id="l-fetch-status" style="font-size:12px;color:var(--text-dim);margin-top:6px"></div>`;
  openModal();
  $("#l-fetch").addEventListener("click", fetchLinkIcon);
  // 输入网址后回车直接抓图标
  $("#l-url").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); fetchLinkIcon(); } });
}

let _fetchedIcon = "";  // 自动抓取到的图标路径（未保存前暂存）

async function fetchLinkIcon() {
  const url = $("#l-url").value.trim();
  if (!url) { toast("先输入网址"); return; }
  const btn = $("#l-fetch");
  const status = $("#l-fetch-status");
  btn.disabled = true;
  btn.textContent = "抓取中…";
  status.textContent = "正在抓取网站图标…";
  try {
    const r = await api(`/api/links/favicon?url=${encodeURIComponent(url)}`);
    if (r.icon) {
      _fetchedIcon = r.icon;
      $("#l-icon").value = r.icon;
      $("#l-preview-img").src = r.icon;
      $("#l-preview-name").textContent = "已获取网站图标";
      $("#l-preview").style.display = "flex";
      $("#l-preview").style.alignItems = "center";
      status.textContent = "";
    } else {
      status.textContent = "未找到该网站图标，可手动填 emoji";
    }
  } catch (e) {
    status.textContent = "抓取失败：" + (e.message || "网络问题");
  } finally {
    btn.disabled = false;
    btn.textContent = "自动获取图标";
  }
}

function saveLink() {
  const name = $("#l-name").value.trim();
  const url = $("#l-url").value.trim();
  if (!name || !url) { toast("名称和网址不能为空"); return; }
  // 优先用自动抓取到的图标；用户手动改了则用输入框内容
  const icon = $("#l-icon").value.trim();
  const editing = Boolean(editingLink);
  api(editing ? `/api/links/${editingLink.id}` : "/api/links", {
    method: editing ? "PATCH" : "POST",
    body: JSON.stringify({ name, url, icon }),
  }).then(() => {
    closeModal();
    _fetchedIcon = "";
    editingLink = null;
    loadLinks();
    toast(editing ? "快捷方式已更新" : "快捷方式已添加");
  }).catch((e) => toast(e.message));
}

async function deleteLink(id) {
  if (SETTINGS.confirm_delete_link !== "0") {
    if (!await confirmDialog("删除这个快捷方式？", { okText: "删除", title: "删除快捷方式" })) return;
  }
  try { await api(`/api/links/${id}`, { method: "DELETE" }); loadLinks(); }
  catch (e) { toast(e.message); }
}

/* ---------- 便签 ---------- */
let _notesCache = [];
let editingNote = null;

async function loadNotes() {
  try {
    const notes = await api("/api/notes");
    const visibleNotes = notes.filter((note) => !isCalendarRecordNote(note) && !isTaskProgressRecordNote(note));
    _notesCache = visibleNotes;
    $("#notes").innerHTML = visibleNotes.map((n) => `
      <div class="note-item">
        <div class="note-content" title="${esc(n.content)}">${esc(n.content)}</div>
        <time class="note-time">${esc(n.created_at.slice(5, 16))}</time>
        <div class="note-actions"><button class="note-edit" onclick="openNoteModal(${n.id})" aria-label="编辑便签">${uiIcon("edit")}</button><button class="note-del" onclick="deleteNote(${n.id})" aria-label="删除便签">${uiIcon("close")}</button></div>
      </div>`).join("") || `<div class="lane-empty" style="padding:10px 0">暂无便签</div>`;
  } catch (e) { /* 忽略 */ }
}

function openNoteModal(noteId = null) {
  if (typeof noteId !== "number") noteId = null;
  editingNote = noteId ? _notesCache.find((note) => note.id === noteId) || null : null;
  $("#modal-title").textContent = editingNote ? "编辑便签" : "新建便签";
  $("#modal-body").innerHTML = `<textarea id="n-content" placeholder="随手记点什么…">${esc(editingNote?.content || "")}</textarea>`;
  openModal();
  setTimeout(() => $("#n-content").focus(), 50);
}

function saveNote() {
  const content = $("#n-content").value.trim();
  if (!content) { toast("便签内容不能为空"); return; }
  const editing = Boolean(editingNote);
  api(editing ? `/api/notes/${editingNote.id}` : "/api/notes", {
    method: editing ? "PATCH" : "POST",
    body: JSON.stringify({ content }),
  }).then(() => {
    closeModal();
    editingNote = null;
    loadNotes();
    toast(editing ? "便签已更新" : "便签已保存");
  }).catch((e) => toast(e.message));
}

async function deleteNote(id) {
  if (SETTINGS.confirm_delete_note !== "0") {
    if (!await confirmDialog("删除这条便签？", { okText: "删除", title: "删除便签" })) return;
  }
  try { await api(`/api/notes/${id}`, { method: "DELETE" }); loadNotes(); }
  catch (e) { toast(e.message); }
}

/* ---------- AI 接入指南 ---------- */
let _aiGuideLoaded = false;

async function loadAiGuide() {
  if (_aiGuideLoaded) return;
  try {
    const info = await api("/api/integration");
    const restPrompt = `请接入并持续使用我正在运行的 ShyBoard。请使用下面的“直接连接”方式，不要配置或调用 MCP，也不要让我填写安装目录或端口。

自动发现连接信息（Windows）：
1. 在 PowerShell 中查找正在运行的 ShyBoard：
   $shyboard = Get-CimInstance Win32_Process -Filter "Name = 'ShyBoard.exe'" | Select-Object -First 1
2. 如果没有找到进程，提醒我先打开 ShyBoard，然后停止后续操作。
3. 自动从进程位置读取端口：
   $appDir = Split-Path -Parent $shyboard.ExecutablePath
   $portFile = Join-Path $appDir 'data\\port.txt'
   $port = (Get-Content -LiteralPath $portFile -Raw).Trim()
   $baseUrl = "http://127.0.0.1:$port"
4. 如果你运行在 WSL 中，请通过 powershell.exe 执行同样的发现步骤。不要猜测端口，也不要在电脑中大范围搜索文件。
5. 请求 $baseUrl/api/health；只有返回 ok=true 且 service=workbench 后再继续。连接失败时只需提醒我保持 ShyBoard 运行。

每次开始工作时：
- 先请求 GET $baseUrl/api/tasks，了解已有任务并避免重复创建。
- 将看板视为任务状态的唯一来源；不要只在聊天中声称已更新。

写入规则：
- 新建任务：POST $baseUrl/api/tasks，JSON 可包含 title、description、status、priority、due_date、remind_days、tags、source。
- status 使用 doing 或 done；priority 使用 low、medium 或 high；due_date 使用 YYYY-MM-DD；remind_days 使用 -1 到 365（-1 表示不提醒）；source 固定为 agent。
- 更新任务：PATCH $baseUrl/api/tasks/<任务ID>，只发送需要变化的字段。
- 记录进展：POST $baseUrl/api/tasks/<任务ID>/progress，JSON 为 {"content":"本次完成内容与下一步","source":"agent"}。
- 完成任务前，先写一条清晰的进展，再把 status 更新为 done。
- 创建前检查同名或同目标任务；不要生成重复项。
- 未经我明确同意，不要调用 DELETE 接口。

协作习惯：
- 开始一项已有工作前，先读取 GET $baseUrl/api/tasks/<任务ID>。
- 每完成一个有意义的阶段就追加进展，内容简洁、具体、可验证。
- 如果任务目标、截止时间或优先级不明确，先向我确认。
- 操作完成后告诉我更新了哪些任务，并给出任务 ID。

请现在先完成健康检查并读取现有任务，然后用一句话告诉我 ShyBoard 已连接；在我提出具体工作前不要自行创建或删除任务。`;

    const mcpInstallPrompt = `请帮我为你当前所在的 Agent 客户端接入 ShyBoard MCP。请只配置 MCP，不要同时尝试 REST 直接连接，也不要让我查找安装目录或端口。

请按顺序完成：
1. 先确认当前 Agent 客户端是否支持本地 stdio MCP 服务。如果不支持，明确告诉我改用 ShyBoard 文档中的“方式 A · 直接连接”，然后停止。
2. 使用 PowerShell 自动定位正在运行的 ShyBoard：
   $shyboard = Get-CimInstance Win32_Process -Filter "Name = 'ShyBoard.exe'" | Select-Object -First 1
   $appDir = Split-Path -Parent $shyboard.ExecutablePath
   $mcpCommand = Join-Path $appDir 'ShyBoard-MCP.exe'
   如果没有找到 ShyBoard 进程，请提醒我打开应用；如果组件不存在，请提醒我更新或重新下载完整安装包。不要在电脑中大范围搜索。
3. 按当前 Agent 客户端的配置规范，添加一个名为 shyboard 的本地 stdio MCP 服务。command 使用上一步得到的 ShyBoard-MCP.exe 绝对路径，args 使用空数组。等价配置结构如下，写入时将占位内容替换成你自动识别的真实路径：
   {"mcpServers":{"shyboard":{"command":"<自动识别的 ShyBoard-MCP.exe 路径>","args":[]}}}
4. 保留配置文件中已有的其他 MCP 服务，不要覆盖整个文件。若你没有权限自动修改，请告诉我当前产品中准确的设置入口、要填写的每个字段，以及是否需要重启；不要只说“添加 MCP 配置”。
5. 配置完成后验证 shyboard 服务能够列出工具。若当前会话必须重启才能加载，请明确告诉我重启或重新加载 Agent，然后停止，不要假装已经连接。
6. 验证成功时，告诉我“ShyBoard MCP 已连接”，并列出你看到的 ShyBoard 工具；此时不要创建或修改任务。`;

    const mcpPrompt = `ShyBoard MCP 已配置。请只通过名为 shyboard 的 MCP 服务维护看板，不要再使用 REST 直接连接，并遵守以下规则：

1. 先确认名为 shyboard 的 MCP 服务可用。
2. 如果当前项目还没有 .shyboard/project.json，调用 shyboard_link_project，project_path 使用当前项目绝对路径，name 使用清晰的项目名称；已有清单时不要重复关联。
3. 每次开始工作先调用 shyboard_get_project_context，读取当前项目的进行中任务和最近进展。
4. 创建任务前先用 shyboard_list_tasks 检查是否已有同一目标，避免重复。
5. 任务描述只写稳定目标；阶段成果、问题与下一步使用 shyboard_append_progress 记录。
6. 只有在交付物已完成并验证后，才调用 shyboard_set_task_status 将任务设为 done；可同时填写 progress_note。
7. 未经我明确同意，不删除任务或进度记录。
8. 每次写入后向我简要说明更新内容和任务 ID。

请现在读取当前项目上下文并确认连接成功；在我提出具体工作前不要自行创建任务。`;

    $("#agent-rest-prompt").textContent = restPrompt;
    $("#agent-mcp-install").textContent = info.mcp_available
      ? mcpInstallPrompt
      : "当前安装中未找到 MCP 组件。请更新或重新下载完整安装包，也可以直接使用上方的方式 A。";
    $("#agent-mcp-prompt").textContent = mcpPrompt;
    document.querySelectorAll("#ai-view .ai-code").forEach((element) => element.classList.remove("loading"));
    if (!info.mcp_available) {
      const button = document.querySelector('[data-copy-target="agent-mcp-install"]');
      if (button) button.disabled = true;
    }
    _aiGuideLoaded = true;
  } catch (error) {
    document.querySelectorAll("#ai-view .ai-code").forEach((element) => {
      element.textContent = "暂时无法读取本机接入信息，请确认 ShyBoard 已正常启动。";
      element.classList.remove("loading");
    });
  }
}

async function copyAiGuide(targetId, button) {
  const text = document.getElementById(targetId)?.textContent || "";
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  const old = button.textContent;
  button.textContent = "已复制";
  button.classList.add("copied");
  setTimeout(() => { button.textContent = old; button.classList.remove("copied"); }, 1600);
}

/* ---------- 纪念日 ---------- */
async function loadAnns() {
  try {
    const items = await api("/api/anniversaries");
    if (!items.length) {
      $("#anns").innerHTML = `<div class="ann-empty">暂无纪念日，点 ＋ 添加</div>`;
      return;
    }
    const today = new Date();
    $("#anns").innerHTML = items.map((a) => {
      const isToday = a.days_left === 0;
      const label = isToday ? "就是今天 🎉"
        : a.days_left === 1 ? "明天"
        : `还有 ${a.days_left} 天`;
      const typeTag = a.calendar_type === "lunar"
        ? `<span class="ann-type-tag">农历</span>` : "";
      const dateText = a.calendar_type === "lunar"
        ? `农历${Math.abs(a.month)}月${a.day}日${a.month < 0 ? "（闰）" : ""}`
        : `${a.month}/${a.day}`;
      return `
        <div class="ann-item ${isToday ? "ann-today" : ""}" data-id="${a.id}">
          <span class="ann-icon">${uiIcon("calendar")}</span>
          <span class="ann-info">
            <div class="ann-name">${esc(a.name)}${typeTag}</div>
            <div class="ann-days">${dateText} · ${label}</div>
          </span>
          <span class="ann-countdown">${isToday ? "TODAY" : String(a.days_left).padStart(2, "0")}</span>
          <button class="ann-del" title="删除" aria-label="删除 ${esc(a.name)}">${uiIcon("close")}</button>
        </div>`;
    }).join("");
    $("#anns").onclick = async (e) => {
      const del = e.target.closest(".ann-del");
      if (!del) return;
      const id = +del.closest(".ann-item").dataset.id;
      if (SETTINGS.confirm_delete_note !== "0") {
        if (!await confirmDialog("删除这个纪念日？", { okText: "删除", title: "删除纪念日" })) return;
      }
      try { await api(`/api/anniversaries/${id}`, { method: "DELETE" }); loadAnns(); loadCalendar(); }
      catch (err) { toast(err.message); }
    };
  } catch (e) { /* 忽略 */ }
}

function openAnnModal(fromDay = false) {
  // 非当天弹窗来源 → 清空来源标记（避免 saveAnn 误回弹窗）
  if (!fromDay) _dayModalDate = "";
  $("#modal-title").textContent = "添加纪念日";
  // 从某天进入：日期固定为那天，只需选农历/阳历 + 名称
  let datePart = `
    <label>日期（每年循环）</label>
    <div style="display:flex;gap:8px;align-items:center">
      <select id="a-month" style="flex:1">
        ${Array.from({length:12}, (_,i)=>`<option value="${i+1}">${i+1} 月</option>`).join("")}
      </select>
      <select id="a-day" style="flex:1">
        ${Array.from({length:31}, (_,i)=>`<option value="${i+1}">${i+1} 日</option>`).join("")}
      </select>
    </div>`;
  if (_dayModalDate) {
    const [y, m, d] = _dayModalDate.split("-").map(Number);
    datePart = `
      <label>日期（${y}年${m}月${d}日，每年循环）</label>
      <input type="hidden" id="a-month" value="${m}">
      <input type="hidden" id="a-day" value="${d}">`;
  }
  $("#modal-body").innerHTML = `
    <label>名称</label>
    <input id="a-name" placeholder="例如：老妈生日" maxlength="30">
    ${datePart}
    <label>日历类型</label>
    <div style="display:flex;gap:8px" id="a-type-row">
      <button type="button" class="btn ghost sm ann-type-btn active" data-type="solar">阳历</button>
      <button type="button" class="btn ghost sm ann-type-btn" data-type="lunar">农历</button>
    </div>
    <div style="font-size:12px;color:var(--text-dim);margin-top:6px" id="a-type-hint"></div>`;
  openModal();
  $("#a-name").focus();
  // 类型切换：农历时若从某天进入，把日期换算成农历月日
  const hint = $("#a-type-hint");
  const updateHint = async () => {
    const t = document.querySelector(".ann-type-btn.active").dataset.type;
    if (t === "lunar" && _dayModalDate) {
      const [y, m, d] = _dayModalDate.split("-").map(Number);
      try {
        const cal = await api(`/api/calendar?month=${calKey(y, m)}`);
        const lun = cal.lunar && cal.lunar[String(d)];
        if (lun && lun.month) {
          hint.textContent = `该日农历为 ${Math.abs(lun.month)}月${lun.day}日${lun.month < 0 ? "（闰月）" : ""}，将按每年农历这天循环`;
        }
      } catch (e) { hint.textContent = ""; }
    } else if (t === "solar" && _dayModalDate) {
      hint.textContent = "将按每年阳历这天循环";
    }
  };
  $("#a-type-row").onclick = (e) => {
    const btn = e.target.closest(".ann-type-btn");
    if (!btn) return;
    document.querySelectorAll(".ann-type-btn").forEach((b) => b.classList.toggle("active", b === btn));
    updateHint();
  };
  updateHint();
}

async function saveAnn() {
  const name = $("#a-name").value.trim();
  if (!name) { toast("请输入纪念日名称"); return; }
  const month = +$("#a-month").value, day = +$("#a-day").value;
  const ctype = document.querySelector(".ann-type-btn.active").dataset.type;
  // 农历 + 从某天进入：把阳历日期换算成农历月日存储（闰月为负）
  let storeMonth = month, storeDay = day;
  if (ctype === "lunar" && _dayModalDate) {
    const [y, m, d] = _dayModalDate.split("-").map(Number);
    try {
      const cal = await api(`/api/calendar?month=${calKey(y, m)}`);
      const lun = cal.lunar && cal.lunar[String(d)];
      if (lun && lun.month) {
        storeMonth = lun.month;
        storeDay = lun.day;
      }
    } catch (e) { /* 保持阳历值 */ }
  }
  try {
    await api("/api/anniversaries", {
      method: "POST",
      body: JSON.stringify({ name, month: storeMonth, day: storeDay, calendar_type: ctype }),
    });
    loadAnns();
    loadCalendar();
    // 从日历某天进入 → 保存后回到当天弹窗（能看到新纪念日）
    if (_dayModalDate) {
      loadDayModal();
    } else {
      closeModal();
    }
    toast("已添加纪念日");
  } catch (e) { toast(e.message); }
}

/* ---------- 日历视图 ---------- */
let _calYM = null;  // {year, month} 当前显示月份（null=跟随今天）

function todayYM() {
  const n = new Date();
  return { year: n.getFullYear(), month: n.getMonth() + 1 };
}

function calKey(y, m) { return `${y}-${String(m).padStart(2, "0")}`; }

const CALENDAR_RECORDS_KEY = "shyboard.calendar.records.v1";
const CALENDAR_RECORD_PREFIX = "[CALENDAR_RECORD:";
let _calendarRecords = null;
let _calendarRecordIds = {};

const SOLAR_FESTIVALS = {
  "01-01": [{ name: "元旦", type: "holiday" }],
  "02-14": [{ name: "情人节", type: "special" }],
  "03-08": [{ name: "妇女节", type: "special" }],
  "03-12": [{ name: "植树节", type: "special" }],
  "04-23": [{ name: "世界读书日", type: "special" }],
  "05-01": [{ name: "劳动节", type: "holiday" }],
  "05-04": [{ name: "青年节", type: "special" }],
  "06-01": [{ name: "儿童节", type: "special" }],
  "07-01": [{ name: "建党节", type: "special" }],
  "08-01": [{ name: "建军节", type: "special" }],
  "09-10": [{ name: "教师节", type: "special" }],
  "10-01": [{ name: "国庆节", type: "holiday" }],
  "12-24": [{ name: "平安夜", type: "special" }],
  "12-25": [{ name: "圣诞节", type: "special" }],
};

const LUNAR_FESTIVALS = {
  "1-1": { name: "春节", type: "holiday" },
  "1-15": { name: "元宵节", type: "special" },
  "5-5": { name: "端午节", type: "holiday" },
  "7-7": { name: "七夕", type: "special" },
  "8-15": { name: "中秋节", type: "holiday" },
  "9-9": { name: "重阳节", type: "special" },
  "12-8": { name: "腊八节", type: "special" },
};

function parseCalendarRecords(raw) {
  if (!raw) return {};
  try {
    const value = typeof raw === "string" ? JSON.parse(raw) : raw;
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch (_) { return {}; }
}

function parseCalendarRecordNote(note) {
  const match = String(note && note.content || "").match(/^\[CALENDAR_RECORD:(\d{4}-\d{2}-\d{2})\]\n?([\s\S]*)$/);
  return match ? { date: match[1], content: match[2], id: Number(note.id) } : null;
}

function isCalendarRecordNote(note) {
  return String(note && note.content || "").startsWith(CALENDAR_RECORD_PREFIX);
}

function isTaskProgressRecordNote(note) {
  return String(note && note.content || "").startsWith("[TASK_PROGRESS]\n");
}

async function ensureCalendarRecords() {
  if (_calendarRecords) return _calendarRecords;
  let localRecords = {};
  try { localRecords = parseCalendarRecords(localStorage.getItem(CALENDAR_RECORDS_KEY)); }
  catch (_) { /* WebView localStorage may be unavailable */ }
  try {
    const notes = await api("/api/notes");
    _calendarRecords = {};
    _calendarRecordIds = {};
    notes.forEach((note) => {
      const record = parseCalendarRecordNote(note);
      if (!record) return;
      (_calendarRecordIds[record.date] ||= []).push(record.id);
      if (!_calendarRecords[record.date] || record.id > _calendarRecords[record.date].id) {
        _calendarRecords[record.date] = { id: record.id, content: record.content };
      }
    });
    Object.keys(_calendarRecords).forEach((date) => {
      _calendarRecords[date] = _calendarRecords[date].content;
    });
    Object.entries(localRecords).forEach(([date, content]) => {
      if (!_calendarRecords[date]) _calendarRecords[date] = content;
    });
  } catch (_) { _calendarRecords = localRecords; }
  return _calendarRecords;
}

async function persistCalendarRecords(dateStr, content) {
  const raw = JSON.stringify(_calendarRecords || {});
  try { localStorage.setItem(CALENDAR_RECORDS_KEY, raw); }
  catch (_) { /* SQLite remains the primary store */ }
  try {
    const oldIds = [...(_calendarRecordIds[dateStr] || [])];
    if (content) {
      await api("/api/notes", {
        method: "POST",
        body: JSON.stringify({ content: `${CALENDAR_RECORD_PREFIX}${dateStr}]\n${content}` }),
      });
    }
    await Promise.all(oldIds.map((id) => api(`/api/notes/${id}`, { method: "DELETE" })));
    _calendarRecords = null;
    _calendarRecordIds = {};
    await ensureCalendarRecords();
    loadNotes();
    return true;
  } catch (_) { return false; }
}

function calendarRecord(dateStr) {
  return String((_calendarRecords && _calendarRecords[dateStr]) || "");
}

function qingmingDay(year) {
  const y = year % 100;
  const constant = year < 2000 ? 5.59 : 4.81;
  return Math.floor(y * 0.2422 + constant) - Math.floor((y - 1) / 4);
}

function isNthWeekday(year, month, day, weekday, nth) {
  if (new Date(year, month - 1, day).getDay() !== weekday) return false;
  return Math.floor((day - 1) / 7) + 1 === nth;
}

function festivalsForDay(year, month, day, lunar) {
  const key = `${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  const festivals = [...(SOLAR_FESTIVALS[key] || [])];
  if (month === 4 && day === qingmingDay(year)) festivals.push({ name: "清明节", type: "holiday" });
  if (month === 5 && isNthWeekday(year, month, day, 0, 2)) festivals.push({ name: "母亲节", type: "special" });
  if (month === 6 && isNthWeekday(year, month, day, 0, 3)) festivals.push({ name: "父亲节", type: "special" });
  if (month === 11 && isNthWeekday(year, month, day, 4, 4)) festivals.push({ name: "感恩节", type: "special" });
  if (lunar && lunar.month && lunar.day) {
    const lunarFestival = LUNAR_FESTIVALS[`${lunar.month}-${lunar.day}`];
    if (lunarFestival) festivals.push(lunarFestival);
  }
  return festivals;
}

async function loadCalendar() {
  const ym = _calYM || todayYM();
  try {
    await ensureCalendarRecords();
    const d = await api(`/api/calendar?month=${calKey(ym.year, ym.month)}`);
    $("#cal-title").textContent = `${d.year}年${d.month}月`;
    const cells = [];
    const pad = d.first_weekday;  // 0=周日
    for (let i = 0; i < pad; i++) cells.push(`<div class="cal-cell out"></div>`);
    for (let day = 1; day <= d.days; day++) {
      const dateStr = `${d.year}-${String(d.month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const isToday = dateStr === d.today;
      const anns = d.anniversaries[day] || [];
      const lun = d.lunar && d.lunar[day] || { month: 0, day: 0, month_name: "", day_name: "" };
      // 农历显示：初一显示"六月初一"（含月名），其余显示"廿九"
      const lunarText = lun.day === 1
        ? `${lun.month_name}月${lun.day_name}`
        : lun.day_name;
      const festivals = festivalsForDay(d.year, d.month, day, lun);
      const festivalHtml = festivals.map((festival) =>
        `<div class="cal-festival ${festival.type === "special" ? "special" : ""}" title="${esc(festival.name)}">${esc(festival.name)}</div>`
      ).join("");
      const annHtml = anns.map((a) => `<div class="cal-ann" title="${esc(a.name)}">🎂 ${esc(a.name)}</div>`).join("");
      const recurring = d.recurring_tasks && d.recurring_tasks[day] || [];
      const recurringHtml = recurring.map((task) => `<div class="cal-recurring ${task.completed ? "completed" : ""}" title="${esc(task.schedule_label)} · ${task.completed ? "已完成" : "待完成"}"><span aria-hidden="true">↻</span>${esc(task.title)}${task.completed ? " · 已完成" : ""}</div>`).join("");
      const record = calendarRecord(dateStr);
      const recordHtml = record
        ? `<div class="cal-record" title="${esc(record)}">📝 ${esc(record.replace(/\s+/g, " "))}</div>`
        : "";
      cells.push(`
        <div class="cal-cell ${isToday ? "today" : ""}" data-date="${dateStr}">
          <div class="cal-daynum">${day}<span class="cal-lunar">${lunarText}</span></div>
          ${festivalHtml}
          ${annHtml}
          ${recurringHtml}
          ${recordHtml}
        </div>`);
    }
    const total = pad + d.days;
    const rem = (7 - total % 7) % 7;
    for (let i = 0; i < rem; i++) cells.push(`<div class="cal-cell out"></div>`);
    $("#cal-grid").innerHTML = cells.join("");
    // 点击某天 → 当天任务管理弹窗（非 out 占位格）
    $("#cal-grid").onclick = (e) => {
      const cell = e.target.closest(".cal-cell");
      if (cell && cell.dataset.date) openDayModal(cell.dataset.date);
    };
  } catch (e) { toast(e.message); }
}

/* 当天任务管理弹窗：查看当天任务 + 添加当天任务 + 添加当天纪念日 */
let _dayModalDate = "";  // 当前弹窗日期 YYYY-MM-DD

function dayTitle(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return `${y}年${m}月${d}日`;
}

async function loadDayModal() {
  if (!_dayModalDate) return;
  const ym = { year: +_dayModalDate.slice(0, 4), month: +_dayModalDate.slice(5, 7) };
  try {
    await ensureCalendarRecords();
    const cal = await api(`/api/calendar?month=${calKey(ym.year, ym.month)}`);
    const day = String(+_dayModalDate.slice(8, 10));
    const anns = cal.anniversaries[day] || [];
    const recurring = cal.recurring_tasks && cal.recurring_tasks[day] || [];
    const lun = (cal.lunar && cal.lunar[day]) || { month: 0, day: 0, month_name: "", day_name: "" };
    const annHtml = anns.length ? anns.map((a) => `
      <div class="cal-day-ann">🎂 ${esc(a.name)}${a.calendar_type === "lunar" ? "（农历）" : ""}</div>`).join("")
      : "";
    const lunarLine = lun.day ? ` · 农历${lun.month_name}月${lun.day_name}` : "";
    const festivals = festivalsForDay(ym.year, ym.month, +day, lun);
    const festivalHtml = festivals.map((festival) =>
      `<span class="cal-day-festival ${festival.type === "special" ? "special" : ""}">${esc(festival.name)}</span>`
    ).join("");
    const record = calendarRecord(_dayModalDate);
    const recurringHtml = recurring.length ? recurring.map((task) => `
      <div class="cal-day-recurring ${task.completed ? "completed" : ""}"><span class="cal-day-recurring-mark">↻</span><div><strong>${esc(task.title)}</strong><small>${esc(task.schedule_label)} · ${task.completed ? "已完成" : "待完成"}</small></div></div>`).join("") : "";
    $("#modal-title").textContent = dayTitle(_dayModalDate);
    $("#modal-body").innerHTML = `
      <div class="cal-day-lunar">${lunarLine.replace(" · 农历", "")}</div>
      ${festivalHtml ? `<div class="cal-day-festivals">${festivalHtml}</div>` : ""}
      ${annHtml ? `<div class="cal-day-anns">${annHtml}</div>` : ""}
      ${recurringHtml ? `<section class="cal-day-recurring-list"><span class="cal-day-section-label">定时任务</span>${recurringHtml}</section>` : ""}
      <label class="cal-record-label" for="day-record">每日记录</label>
      <textarea id="day-record" maxlength="1000" placeholder="记录今天发生的事、想法或备忘…">${esc(record)}</textarea>
      <div style="margin-top:10px">
        <button class="btn primary sm" id="day-add-ann">🎂 设为纪念日</button>
      </div>`;
    openModal();
    $("#modal-ok").textContent = "保存记录";
    $("#day-add-ann").addEventListener("click", () => openAnnModalFromDay(_dayModalDate));
  } catch (e) { toast(e.message); }
}

async function saveDayRecord() {
  if (!_dayModalDate) return;
  await ensureCalendarRecords();
  const content = $("#day-record").value.trim();
  if (content) _calendarRecords[_dayModalDate] = content;
  else delete _calendarRecords[_dayModalDate];
  const synced = await persistCalendarRecords(_dayModalDate, content);
  closeModal();
  loadCalendar();
  toast(content ? (synced ? "每日记录已保存" : "每日记录已保存在本机") : "每日记录已清空");
}

function openDayModal(dateStr) {
  _dayModalDate = dateStr;
  loadDayModal();
}

/* 从日历某天打开纪念日弹窗：日期即当天（_dayModalDate 保留 → saveAnn 后回弹窗） */
function openAnnModalFromDay(dateStr) {
  _dayModalDate = dateStr;  // 确保来源标记正确
  openAnnModal(true);
}

async function calPrev() {
  _calYM = _calYM || todayYM();
  if (_calYM.month === 1) { _calYM = { year: _calYM.year - 1, month: 12 }; }
  else { _calYM = { year: _calYM.year, month: _calYM.month - 1 }; }
  loadCalendar();
}
async function calNext() {
  _calYM = _calYM || todayYM();
  if (_calYM.month === 12) { _calYM = { year: _calYM.year + 1, month: 1 }; }
  else { _calYM = { year: _calYM.year, month: _calYM.month + 1 }; }
  loadCalendar();
}
function calToday() { _calYM = null; loadCalendar(); }

function switchView(view) {
  const tasksView = view === "tasks";
  $("#lanes").style.display = tasksView ? "grid" : "none";
  $("#cal-view").classList.toggle("hidden", tasksView);
  $("#tab-tasks").classList.toggle("active", tasksView);
  $("#tab-calendar").classList.toggle("active", !tasksView);
  if (!tasksView) loadCalendar();
}

/* ---------- 弹窗 ---------- */
function openModal(showActions = true) {
  window.modalConfirmAction = null;
  $("#modal-mask").classList.remove("hidden");
  $("#modal").classList.remove("wide", "create-task-modal");
  $("#modal > .modal-actions").style.display = showActions ? "flex" : "none";
  $("#modal-ok").textContent = "确定";
  noAutofill();
}
function openModalWide() {
  window.modalConfirmAction = null;
  $("#modal-mask").classList.remove("hidden");
  $("#modal").classList.add("wide");
  $("#modal > .modal-actions").style.display = "none";
  noAutofill();
}
function closeModal() {
  $("#modal-mask").classList.add("hidden");
  $("#modal").classList.remove("create-task-modal");
  window.modalConfirmAction = null;
}

/* 自定义确认弹窗：替代原生 confirm()（原生对话框标题显示页面 URL，样式也与主题不符） */
function confirmDialog(message, opts = {}) {
  const { okText = "删除", title = "确认操作", icon = "🗑️", tone = "danger" } = opts;
  return new Promise((resolve) => {
    $("#confirm-title").textContent = title;
    $("#confirm-msg").textContent = message;
    $("#confirm-ok").textContent = okText;
    $("#confirm-ok").classList.toggle("danger", tone === "danger");
    $("#confirm-ok").classList.toggle("primary", tone === "primary");
    $(".confirm-icon").textContent = icon;
    $("#confirm-mask").classList.remove("hidden");
    const finish = (val) => {
      $("#confirm-mask").classList.add("hidden");
      $("#confirm-ok").onclick = null;
      $("#confirm-cancel").onclick = null;
      $("#confirm-mask").onclick = null;
      resolve(val);
    };
    $("#confirm-ok").onclick = () => finish(true);
    $("#confirm-cancel").onclick = () => finish(false);
    $("#confirm-mask").onclick = (e) => { if (e.target.id === "confirm-mask") finish(false); };
  });
}

/* 关闭 WebView2 自动填充：输入框不再显示历史输入记录下拉框 */
function noAutofill() {
  document.querySelectorAll("input, textarea").forEach((el) => {
    el.setAttribute("autocomplete", "off");
  });
}

/* ---------- 任务详情弹窗 ---------- */
const STATUS_TEXT2 = { todo: "进行中", doing: "进行中", done: "已完成" };
const FIELD_LABELS = { title: "标题", description: "描述", priority: "优先级",
                       due_date: "截止日期", remind_days: "截止提醒", tags: "标签" };
const PRIORITY_TEXT2 = { high: "高", medium: "中", low: "低" };

/* 变更详情弹窗的 changes 缓存（按时间线顺序索引） */
let _detailChanges = [];
/* 当前打开的任务详情（供描述历史使用） */
let _currentTaskDetail = null;

function fmtValue(field, v) {
  if (field === "priority") return (PRIORITY_TEXT2[v] || v) + "优先级";
  if (field === "tags") return v ? v.split(",").filter(Boolean).join("、") : "（无）";
  if (field === "due_date") return v || "（无）";
  if (field === "remind_days") return Number(v) < 0 ? "不提醒" : Number(v) === 0 ? "截止当天" : `提前 ${v} 天`;
  return v || "（空）";
}

function eventLine(ev) {
  if (ev.event_type === "create") {
    return { dot: "＋", cls: "create",
             text: `创建任务，状态 <b>${STATUS_TEXT2[ev.new_status] || ev.new_status}</b>`,
             tip: "", changes: null };
  }
  if (ev.event_type === "status") {
    const done = ev.new_status === "done";
    return {
      dot: done ? "✓" : "→",
      cls: "status " + (done ? "done" : ""),
      text: `进度更新：<b>${STATUS_TEXT2[ev.old_status] || ev.old_status}</b> → <b>${STATUS_TEXT2[ev.new_status] || ev.new_status}</b>`,
      tip: "", changes: null,
    };
  }
  // update 事件：note 存 JSON {"字段":[旧,新]}
  let tip = "", fields = "", changes = null;
  try {
    changes = JSON.parse(ev.note || "{}");
    const lines = Object.entries(changes).map(([k, [o, n]]) => {
      const label = FIELD_LABELS[k] || k;
      return `${label}：<span class="tl-old">${esc(fmtValue(k, o))}</span> → <span class="tl-new">${esc(fmtValue(k, n))}</span>`;
    });
    if (lines.length) {
      tip = lines.join("<br>");
      fields = Object.keys(changes).map((k) => FIELD_LABELS[k] || k).join("、");
    }
  } catch (e) { /* 解析失败视为无细节 */ }
  return { dot: "✎", cls: "update",
           text: `编辑任务${fields ? `（修改了 ${fields}）` : ""}`,
           tip, changes };
}

/* 变更详情弹窗：单击查看修改前/后完整内容（长描述可滚动） */
function showChangeDetail(idx) {
  const changes = _detailChanges[idx];
  if (!changes || !Object.keys(changes).length) return;
  $("#modal-title").textContent = "变更详情";
  $("#modal-body").innerHTML = Object.entries(changes).map(([k, [o, n]]) => `
    <div class="chg-block">
      <div class="chg-label">${esc(FIELD_LABELS[k] || k)}</div>
      <div class="chg-cols">
        <div class="chg-col">
          <div class="chg-col-head old">修改前</div>
          <div class="chg-col-body old">${esc(fmtValue(k, o)) || "（空）"}</div>
        </div>
        <div class="chg-col">
          <div class="chg-col-head new">修改后</div>
          <div class="chg-col-body new">${esc(fmtValue(k, n)) || "（空）"}</div>
        </div>
      </div>
    </div>`).join("");
  $("#modal-body").innerHTML += `
    <div class="modal-actions" style="margin-top:14px">
      <button class="btn primary" onclick="closeModal()">关闭</button>
    </div>`;
  openModalWide();
}

/* 描述历史弹窗：按日期回看任务描述的所有版本（最新在前） */
function showDescHistory() {
  const t = _currentTaskDetail;
  if (!t) return;
  // 从 events 重建版本链：当前描述 + 每次 description 变更的旧值（倒序）
  const versions = [];
  if (t.description) versions.push({ time: t.updated_at, desc: t.description });
  const evs = [...(t.events || [])].reverse();
  for (const ev of evs) {
    if (ev.event_type !== "update") continue;
    try {
      const changes = JSON.parse(ev.note || "{}");
      if (changes.description && changes.description[0] !== undefined) {
        versions.push({ time: ev.created_at, desc: changes.description[0] });
      }
    } catch (e) { /* 忽略解析失败 */ }
  }
  const total = versions.length;
  // 按日期分组
  const groups = {};
  versions.forEach((v, i) => {
    const date = (v.time || "").slice(0, 10) || "未知日期";
    (groups[date] = groups[date] || []).push({ ...v, ver: total - i });
  });
  $("#modal-title").textContent = "描述历史";
  if (!total) {
    $("#modal-body").innerHTML = `<div class="lane-empty">该任务暂无描述</div>
      <div class="modal-actions" style="margin-top:14px">
        <button class="btn primary" onclick="closeModal()">关闭</button>
      </div>`;
    openModalWide();
    return;
  }
  const body = Object.entries(groups).map(([date, items]) => `
    <div class="desc-group">
      <div class="desc-group-date">${esc(date)}</div>
      ${items.map((v) => `
        <div class="desc-ver">
          <div class="desc-ver-head">版本 ${v.ver} <span>${esc((v.time || "").slice(11, 19))}</span></div>
          <div class="desc-ver-body">${esc(v.desc) || "（空）"}</div>
        </div>`).join("")}
    </div>`).join("");
  $("#modal-body").innerHTML = `
    <div style="font-size:12px;color:var(--text-dim);margin-bottom:10px">共 ${total} 个版本，最新内容排在最前。</div>
    ${body}
    <div class="modal-actions" style="margin-top:14px">
      <button class="btn primary" onclick="closeModal()">关闭</button>
    </div>`;
  openModalWide();
}

function openTaskDetail(id) {
  _detailChanges = [];  // 每次打开重置索引
  api(`/api/tasks/${id}`).then((t) => {
    _currentTaskDetail = t;
    $("#modal-title").textContent = "任务详情";
    const overdue = t.due_date && t.due_date < new Date().toISOString().slice(0, 10)
      && t.status !== "done";
    const chips = [
      `<span class="detail-chip">${STATUS_TEXT2[t.status]}</span>`,
      `<span class="detail-chip">${PRIORITY_TEXT[t.priority]}优先级</span>`,
      ...t.tags.map((tag) => `<span class="detail-chip">${esc(tag)}</span>`),
      t.due_date ? `<span class="detail-chip ${overdue ? "overdue" : ""}">${esc(t.due_date)}${overdue ? " · 已逾期" : ""}</span>` : "",
      t.source === "agent" ? `<span class="detail-chip agent">Agent 创建</span>` : "",
      t.status === "done" ? `<span class="detail-chip done">✓ 已完成</span>` : "",
    ].filter(Boolean);
    const events = (t.events || []).map((ev) => {
      const l = eventLine(ev);
      const tipHtml = l.tip ? `<div class="tl-tip">${l.tip}</div>` : "";
      let viewBtn = "";
      if (l.changes && Object.keys(l.changes).length) {
        const idx = _detailChanges.length;
        _detailChanges.push(l.changes);
        viewBtn = `<button class="tl-view" title="查看修改前/后完整内容" onclick="showChangeDetail(${idx})">查看变更</button>`;
      }
      return `
      <div class="tl-item ${l.cls}">
        <div class="tl-dot">${l.dot}</div>
        <div class="tl-body">
          <div class="tl-text">${l.text} ${viewBtn}</div>
          <div class="tl-time">${esc(ev.created_at)}</div>
          ${tipHtml}
        </div>
      </div>`;
    }).join("") || `<div class="lane-empty">暂无记录</div>`;
    $("#modal-body").innerHTML = `
      <div class="task-detail-head">
        <div class="task-detail-title">${esc(t.title)}</div>
        ${t.description ? `<div class="task-detail-desc">${esc(t.description)}</div>` : ""}
        <div class="task-detail-meta">${chips.join("")}</div>
      </div>
      <div class="timeline">
        <div class="timeline-title">操作记录</div>
        ${events}
      </div>
      <div class="modal-actions" style="margin-top:14px">
        <button class="btn ghost" onclick="showDescHistory()">描述历史</button>
        <button class="btn ghost" onclick="editTask(${t.id})">✎ 编辑</button>
        <button class="btn primary" onclick="closeModal()">关闭</button>
      </div>`;
    openModalWide();
  }).catch((e) => toast(e.message));
}

/* ---------- 番茄钟 ---------- */
const POMO_FOCUS_KEY = "shyboard.pomodoro.focusMinutes";
const POMO_BREAK_KEY = "shyboard.pomodoro.breakMinutes";

function pomoStoredMinutes(key, fallback, allowed) {
  const value = Number(localStorage.getItem(key));
  return allowed.includes(value) ? value : fallback;
}

let pomo = {
  phase: "idle",
  focusMinutes: pomoStoredMinutes(POMO_FOCUS_KEY, 25, [15, 25, 45, 60]),
  breakMinutes: pomoStoredMinutes(POMO_BREAK_KEY, 5, [5, 10, 15]),
  remain: 0,
  endAt: 0,
  paused: false,
  _timer: null,
};
pomo.remain = pomo.focusMinutes * 60;

function pomoFmt(sec) {
  const total = Math.max(0, Math.ceil(sec));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function pomoRender() {
  const time = pomoFmt(Math.max(0, pomo.remain));
  const timeEl = $("#pomo-time");
  const pageTime = $("#focus-page-time");
  const phaseClass = pomo.phase === "focus" ? "focus" : pomo.phase === "break" ? "break" : "";
  if (timeEl) {
    timeEl.textContent = time;
    timeEl.className = `pomo-time ${phaseClass}`;
  }
  if (pageTime) pageTime.textContent = time;
  const phaseText = pomo.phase === "idle"
    ? "准备专注"
    : pomo.phase === "focus"
      ? (pomo.paused ? "专注已暂停" : `专注中 · ${pomo.focusMinutes} 分钟`)
      : (pomo.paused ? "休息已暂停" : `休息中 · ${pomo.breakMinutes} 分钟`);
  if ($("#pomo-phase")) $("#pomo-phase").textContent = pomo.phase === "idle" ? "就绪 · 点击开始专注" : phaseText;
  if ($("#focus-page-phase")) $("#focus-page-phase").textContent = phaseText;
  const orbit = $("#focus-orbit");
  if (orbit) {
    orbit.classList.toggle("is-focus", pomo.phase === "focus");
    orbit.classList.toggle("is-break", pomo.phase === "break");
    orbit.classList.toggle("is-paused", pomo.paused);
  }
  const startBtn = $("#pomo-start");
  const skipBtn = $("#pomo-skip");
  if (skipBtn) skipBtn.disabled = pomo.phase === "idle";
  if (startBtn) startBtn.textContent = pomo.phase === "idle" ? "开始" : pomo.paused ? "继续" : "暂停";
  const pageStart = $("#focus-page-start");
  const pagePause = $("#focus-page-pause");
  const pageStop = $("#focus-page-stop");
  const pageBreak = $("#focus-page-break");
  if (pageStart) {
    pageStart.disabled = pomo.phase !== "idle";
    pageStart.textContent = pomo.phase === "idle" ? "开始专注" : pomo.phase === "focus" ? "专注进行中" : "休息进行中";
  }
  if (pagePause) {
    pagePause.disabled = pomo.phase === "idle";
    pagePause.textContent = pomo.paused ? "继续" : "暂停";
  }
  if (pageStop) pageStop.disabled = pomo.phase === "idle";
  if (pageBreak) pageBreak.textContent = pomo.phase === "break" ? "结束休息" : "开始休息";
  const focusSelect = $("#focus-duration");
  const breakSelect = $("#break-duration");
  if (focusSelect) {
    focusSelect.value = String(pomo.focusMinutes);
    focusSelect.disabled = pomo.phase !== "idle";
  }
  if (breakSelect) {
    breakSelect.value = String(pomo.breakMinutes);
    breakSelect.disabled = pomo.phase !== "idle";
  }
}

function pomoTick() {
  pomo.remain = (pomo.endAt - Date.now()) / 1000;
  if (pomo.remain <= 0) {
    pomo.remain = 0;
    pomoPhaseDone();
  }
  pomoRender();
}

function pomoStartTimer() {
  clearInterval(pomo._timer);
  pomo._timer = setInterval(pomoTick, 500);
}

function pomoPhaseDone() {
  clearInterval(pomo._timer);
  if (pomo.phase === "focus") {
    api("/api/pomodoro/complete", { method: "POST" }).then((d) => {
      $("#pomo-count").textContent = `🍅 今日 ${d.count}`;
      if ($("#sum-pomo")) $("#sum-pomo").textContent = d.count;
    }).catch(() => {});
    beep(3);
    toast(`🍅 专注完成，休息 ${pomo.breakMinutes} 分钟`);
    pomo.phase = "break";
    pomo.remain = pomo.breakMinutes * 60;
    pomo.endAt = Date.now() + pomo.remain * 1000;
    pomo.paused = false;
    pomoStartTimer();
  } else {
    beep(2);
    toast("☕ 休息结束，可以开始下一轮专注了");
    pomo.phase = "idle";
    pomo.remain = pomo.focusMinutes * 60;
    pomo.paused = false;
  }
  pomoRender();
}

function pomoStartFocus() {
  if (pomo.phase !== "idle") return;
  pomo.phase = "focus";
  pomo.remain = pomo.focusMinutes * 60;
  pomo.paused = false;
  pomo.endAt = Date.now() + pomo.remain * 1000;
  pomoStartTimer();
  pomoRender();
}

function pomoTogglePause() {
  if (pomo.phase === "idle") return;
  if (pomo.paused) {
    pomo.paused = false;
    pomo.endAt = Date.now() + pomo.remain * 1000;
    pomoStartTimer();
  } else {
    pomo.paused = true;
    clearInterval(pomo._timer);
  }
  pomoRender();
}

function pomoStop() {
  clearInterval(pomo._timer);
  if (pomo.phase !== "idle") toast(pomo.phase === "break" ? "休息已结束" : "本轮专注已结束");
  pomo.phase = "idle";
  pomo.remain = pomo.focusMinutes * 60;
  pomo.paused = false;
  pomoRender();
}

function pomoBreakClick() {
  if (pomo.phase === "break") {
    pomoStop();
  } else {
    clearInterval(pomo._timer);
    pomo.phase = "break";
    pomo.remain = pomo.breakMinutes * 60;
    pomo.paused = false;
    pomo.endAt = Date.now() + pomo.remain * 1000;
    pomoStartTimer();
    toast(`开始休息 ${pomo.breakMinutes} 分钟`);
    pomoRender();
  }
}

function pomoStartClick() {
  if (pomo.phase === "idle") pomoStartFocus();
  else pomoTogglePause();
}

function pomoSkipClick() {
  if (pomo.phase === "focus") pomoBreakClick();
  else if (pomo.phase === "break") {
    pomo.phase = "idle";
    pomo.remain = pomo.focusMinutes * 60;
    pomo.paused = false;
    toast("已跳过休息");
    clearInterval(pomo._timer);
    pomoRender();
  }
}

function pomoDurationChanged(kind, value) {
  if (pomo.phase !== "idle") return;
  const minutes = Number(value);
  if (kind === "focus" && [15, 25, 45, 60].includes(minutes)) {
    pomo.focusMinutes = minutes;
    pomo.remain = minutes * 60;
    localStorage.setItem(POMO_FOCUS_KEY, String(minutes));
  }
  if (kind === "break" && [5, 10, 15].includes(minutes)) {
    pomo.breakMinutes = minutes;
    localStorage.setItem(POMO_BREAK_KEY, String(minutes));
  }
  pomoRender();
}

function beep(times = 1) {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    for (let i = 0; i < times; i++) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.value = 880;
      const t0 = ctx.currentTime + i * 0.7;
      gain.gain.setValueAtTime(0.25, t0);
      gain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.6);
      osc.start(t0);
      osc.stop(t0 + 0.6);
    }
  } catch (e) { /* 无音频环境忽略 */ }
}

/* ---------- 事件绑定 ---------- */
$("#btn-update").addEventListener("click", checkUpdate);
$("#weather").addEventListener("click", openWeatherModal);
$("#pomo-start").addEventListener("click", pomoStartClick);
$("#pomo-skip").addEventListener("click", pomoSkipClick);
$("#focus-page-start").addEventListener("click", pomoStartFocus);
$("#focus-page-pause").addEventListener("click", pomoTogglePause);
$("#focus-page-stop").addEventListener("click", pomoStop);
$("#focus-page-break").addEventListener("click", pomoBreakClick);
$("#focus-duration").addEventListener("change", (event) => pomoDurationChanged("focus", event.target.value));
$("#break-duration").addEventListener("change", (event) => pomoDurationChanged("break", event.target.value));
$(".add-link-btn").addEventListener("click", openLinkModal);
$(".add-note-btn").addEventListener("click", openNoteModal);
$(".add-ann-btn").addEventListener("click", openAnnModal);
$("#ai-view").addEventListener("click", (event) => {
  const button = event.target.closest(".ai-copy[data-copy-target]");
  if (button) copyAiGuide(button.dataset.copyTarget, button);
});
$("#cal-prev").addEventListener("click", calPrev);
$("#cal-next").addEventListener("click", calNext);
$("#cal-today-btn").addEventListener("click", calToday);
$("#tab-tasks").addEventListener("click", () => switchView("tasks"));
$("#tab-calendar").addEventListener("click", () => switchView("calendar"));
$("#modal-cancel").addEventListener("click", closeModal);
$("#modal-ok").addEventListener("click", () => {
  if (typeof window.modalConfirmAction === "function") {
    window.modalConfirmAction();
    return;
  }
  const title = $("#modal-title").textContent;
  if ($("#day-record")) saveDayRecord();
  else if (title === "创建任务") createTask();
  else if (title === "编辑任务") saveTaskEdit();
  else if (title === "添加快捷方式" || title === "编辑快捷方式") saveLink();
  else if (title === "新建便签" || title === "编辑便签") saveNote();
  else if (title === "添加纪念日") saveAnn();
  // 修改城市走 suggest-item 回调，确定按钮无操作
});
$("#modal-mask").addEventListener("click", (e) => {
  if (e.target.id === "modal-mask") closeModal();
});

/* 点任务卡片（非按钮/勾选框区域）打开详情 */
$("#lanes").addEventListener("click", (e) => {
  if (e.target.closest("button") || e.target.closest(".task-check")) return;
  const card = e.target.closest(".task-card");
  if (card) openTaskDetail(+card.id.replace("task-", ""));
});

/* ---------- 启动 ---------- */
noAutofill();  // 关闭 WebView2 历史输入下拉框
let APP_VERSION_TEXT = "?";  // 当前版本（从 health 接口获取）
api("/api/health").then((h) => {
  if (h && h.version) { APP_VERSION_TEXT = h.version; $("#btn-update").title = `检查更新（当前 v${h.version}）`; }
  // 测试版：隐藏 ⬆ 更新按钮，显示 Beta 徽标
  if (h && h.beta) {
    $("#btn-update").style.display = "none";
    $("#beta-badge").style.display = "inline-block";
  }
}).catch(() => {});
loadTasks();
loadSettings();
loadWeather();
loadLinks();
loadNotes();
loadAnns();
pomoRender();
api("/api/pomodoro").then((d) => {
  $("#pomo-count").textContent = `🍅 今日 ${d.count}`;
}).catch(() => {});

/* 自动刷新：本地数据 15 秒轮询（有变化才重绘），天气 15 分钟 */
setInterval(() => refreshAll(true), 15 * 1000);
setInterval(loadWeather, 15 * 60 * 1000);

/* 手动刷新按钮 */
$("#btn-refresh").addEventListener("click", () => {
  refreshAll(false);
  toast("已刷新");
});

/* ---------- 检查更新 ---------- */
let _updateInfo = null;

async function checkUpdate() {
  const btn = $("#btn-update");
  btn.disabled = true;
  btn.textContent = "…";
  try {
    const r = await api("/api/update/check");
    if (r.error) { toast(r.error); return; }
    if (!r.has_update) {
      toast(`已是最新版本 v${APP_VERSION_TEXT}（GitHub: ${r.tag || "?"}）`);
      return;
    }
    _updateInfo = r;
    $("#modal-title").textContent = "发现新版本";
    $("#modal-body").innerHTML = `
      <div style="font-size:14px;font-weight:600;margin-bottom:8px">
        当前 v${APP_VERSION_TEXT} → 最新 ${r.tag}
      </div>
      <div style="font-size:12px;color:var(--text-dim);margin-bottom:10px;white-space:pre-wrap">${esc(r.notes || "暂无更新说明")}</div>
      <div class="modal-actions" style="margin-top:8px">
        <button class="btn ghost" onclick="closeModal()">稍后</button>
        <button class="btn primary" onclick="downloadUpdate()">下载并更新</button>
      </div>`;
    openModal(false);  // body 已自带按钮，隐藏底部"取消/确定"
  } catch (e) {
    toast("检查更新失败：" + (e.message || "网络问题"));
  } finally {
    btn.disabled = false;
    btn.textContent = "⬆";
  }
}

async function downloadUpdate() {
  if (!_updateInfo) return;
  closeModal();
  // 打开下载进度弹窗（无底部按钮，遮罩点击可关闭）
  $("#modal-title").textContent = "正在下载更新";
  $("#modal-body").innerHTML = `
    <div style="font-size:13px;color:var(--text-dim);margin-bottom:10px">
      当前 v${APP_VERSION_TEXT} → 最新 ${_updateInfo.tag}
    </div>
    <div class="upd-bar"><div class="upd-bar-fill" id="upd-fill" style="width:0%"></div></div>
    <div class="upd-meta" id="upd-meta">准备下载…</div>`;
  openModal(false);
  let cancelled = false;
  let pollTimer = null;
  try {
    const d = await api("/api/update/download", {
      method: "POST",
      body: JSON.stringify({
        url: _updateInfo.download_url,
        filename: _updateInfo.asset_name,
        version: _updateInfo.tag,
      }),
    });
    if (d.error) { closeModal(); toast(d.error); return; }
    // 下载完成后轮询确认进度 100%（流式写盘可能略滞后）
    await new Promise((resolve) => {
      let tries = 0;
      pollTimer = setInterval(async () => {
        tries++;
        try {
          const p = await api("/api/update/progress");
          if (p.done || tries > 40) { clearInterval(pollTimer); resolve(); }
        } catch (e) { /* 继续等 */ }
      }, 250);
    });
    if (cancelled) return;
    $("#upd-fill").style.width = "100%";
    $("#upd-meta").textContent = "下载完成 ✓";
    // 用户已点过"下载并更新"，下载完直接应用（不再二次确认）
    await new Promise((r) => setTimeout(r, 600));  // 让"下载完成 ✓"停留一瞬
    closeModal();
    await api("/api/update/apply", { method: "POST" });
    toast("正在应用更新…");
  } catch (e) {
    closeModal();
    toast("下载失败：" + (e.message || "网络问题"));
  }
}

// 下载进度轮询（下载期间每秒刷新进度条）
setInterval(async () => {
  const fill = $("#upd-fill");
  const meta = $("#upd-meta");
  if (!fill || !meta || $("#modal-title").textContent !== "正在下载更新") return;
  try {
    const p = await api("/api/update/progress");
    if (p && p.percent > 0 && !p.done) {
      const pct = Math.min(100, Math.round(p.percent));
      fill.style.width = pct + "%";
      const mb = (n) => (n / 1048576).toFixed(1);
      meta.textContent = p.total ? `下载中 ${mb(p.downloaded)} / ${mb(p.total)} MB（${pct}%）` : `下载中 ${mb(p.downloaded)} MB…`;
    } else if (p && p.done && fill.style.width !== "100%") {
      fill.style.width = "100%";
      meta.textContent = "下载完成 ✓";
    }
  } catch (e) { /* 忽略 */ }
}, 1000);
