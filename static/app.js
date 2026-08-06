/* ===== 工作台 Workbench · 前端逻辑 ===== */
"use strict";

const $ = (sel) => document.querySelector(sel);
const PRIORITY_TEXT = { high: "高", medium: "中", low: "低" };
const STATUS_TEXT = { todo: "待办", doing: "进行中", done: "已完成" };
const WEEK = ["日", "一", "二", "三", "四", "五", "六"];

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
let SETTINGS = {};  // 从 /api/settings 加载；confirm_delete_* 存 "0"/"1"

async function loadSettings() {
  try {
    const s = await api("/api/settings");
    SETTINGS = s;
    // 同步开关状态
    $("#set-autostart").checked = s.autostart === "1";
    $("#set-confirm-task").checked = s.confirm_delete_task !== "0";
    $("#set-confirm-link").checked = s.confirm_delete_link !== "0";
    $("#set-confirm-note").checked = s.confirm_delete_note !== "0";
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
    $("#settings-mask").classList.remove("hidden");
  });
}

function closeSettings() {
  $("#settings-mask").classList.add("hidden");
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
$("#settings-done").addEventListener("click", closeSettings);
$("#settings-mask").addEventListener("click", (e) => {
  if (e.target.id === "settings-mask") closeSettings();
});
bindSettingSwitch("#set-confirm-task", "confirm_delete_task");
bindSettingSwitch("#set-confirm-link", "confirm_delete_link");
bindSettingSwitch("#set-confirm-note", "confirm_delete_note");
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

/* ---------- 统计 ---------- */
async function loadStats() {
  try {
    const s = await api("/api/stats");
    $("#stats").innerHTML = `
      <div class="stat-cell"><div class="stat-num">${s.todo}</div><div class="stat-label">待办</div></div>
      <div class="stat-cell"><div class="stat-num">${s.doing}</div><div class="stat-label">进行中</div></div>
      <div class="stat-cell done"><div class="stat-num">${s.done}</div><div class="stat-label">已完成</div></div>
      <div class="stat-cell done"><div class="stat-num">${s.done_today}</div><div class="stat-label">今日完成</div></div>`;
  } catch (e) { /* 忽略 */ }
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
  const isDoing = t.status === "doing";
  const check = isDone ? "checked" : "";
  const checkClick = isDone ? "restoreTask" : "completeTask";
  const startBtn = (!isDone && !isDoing)
    ? `<button class="mini-btn" onclick="startTask(${t.id})">开始 →</button>` : "";
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
      ${startBtn}
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
  const lanes = { todo: $("#lane-todo"), doing: $("#lane-doing"), done: $("#lane-done") };
  const counts = { todo: 0, doing: 0, done: 0 };
  tasks.forEach((t) => {
    counts[t.status] += 1;
    lanes[t.status].insertAdjacentHTML("beforeend", taskCard(t));
  });
  for (const s of ["todo", "doing", "done"]) {
    if (counts[s] === 0) {
      lanes[s].innerHTML = `<div class="lane-empty">暂无任务</div>`;
    }
    $(`#cnt-${s}`).textContent = counts[s];
  }
}

function clearLanes() {
  ["todo", "doing", "done"].forEach((s) => {
    $(`#lane-${s}`).innerHTML = "";
  });
}

async function reloadAll() {
  loadTasks();
  loadStats();
}

/* 刷新全部数据。auto=true 是后台轮询（只刷核心，轻量）；手动点击刷全部 */
async function refreshAll(auto = true) {
  loadTasks();
  loadStats();
  api("/api/pomodoro").then((d) => {
    $("#pomo-count").textContent = `🍅 今日 ${d.count}`;
  }).catch(() => {});
  if (!auto) {
    loadNotes();
    loadLinks();
    loadWeather();
  }
}

async function createTask() {
  const title = $("#nt-title").value.trim();
  if (!title) return;
  try {
    await api("/api/tasks", {
      method: "POST",
      body: JSON.stringify({
        title,
        priority: $("#nt-priority").value,
        due_date: $("#nt-due").value,
        tags: $("#nt-tags").value,
        description: $("#nt-desc").value,
        source: "manual",
      }),
    });
    $("#nt-title").value = "";
    $("#nt-due").value = "";
    $("#nt-tags").value = "";
    $("#nt-desc").value = "";
    toast("任务已创建");
    reloadAll();
  } catch (e) { toast(e.message); }
}

async function completeTask(id) {
  try { await api(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status: "done" }) }); }
  catch (e) { toast(e.message); }
  reloadAll();
}

async function restoreTask(id) {
  try { await api(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status: "todo" }) }); }
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

function editTask(id) {
  api(`/api/tasks/${id}`).then((t) => {
    editingTask = t;
    $("#modal-title").textContent = "编辑任务";
    $("#modal-body").innerHTML = `
      <label>标题</label>
      <input id="e-title" value="${esc(t.title)}">
      <label>描述</label>
      <textarea id="e-desc">${esc(t.description)}</textarea>
      <label>状态</label>
      <select id="e-status">
        ${Object.entries(STATUS_TEXT).map(([k, v]) =>
          `<option value="${k}" ${t.status === k ? "selected" : ""}>${v}</option>`).join("")}
      </select>
      <div style="display:flex;gap:10px">
        <div style="flex:1">
          <label>优先级</label>
          <select id="e-priority">
            ${Object.entries(PRIORITY_TEXT).map(([k, v]) =>
              `<option value="${k}" ${t.priority === k ? "selected" : ""}>${v}优先级</option>`).join("")}
          </select>
        </div>
        <div style="flex:1">
          <label>截止日期</label>
          <input id="e-due" type="date" value="${esc(t.due_date)}">
        </div>
      </div>
      <label>标签（逗号分隔）</label>
      <input id="e-tags" value="${esc(t.tags.join(", "))}">`;
    openModal();
  });
}

function saveTaskEdit() {
  if (!editingTask) return;
  api(`/api/tasks/${editingTask.id}`, {
    method: "PATCH",
    body: JSON.stringify({
      title: $("#e-title").value,
      description: $("#e-desc").value,
      status: $("#e-status").value,
      priority: $("#e-priority").value,
      due_date: $("#e-due").value,
      tags: $("#e-tags").value,
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
/* 图标判断：/icons/ 开头的路径 → 用 img 显示；否则当 emoji 文本 */
function isIconUrl(icon) {
  return typeof icon === "string" && icon.startsWith("/icons/");
}
function iconHtml(icon) {
  if (isIconUrl(icon)) return `<img class="link-favicon" src="${esc(icon)}" alt="" onerror="this.style.display='none'">`;
  return esc(icon || "🔗");
}

async function loadLinks() {
  try {
    const links = await api("/api/links");
    $("body").classList.toggle("has-link-icons", links.some((l) => isIconUrl(l.icon)));
    $("#links").innerHTML = links.map((l) => `
      <div class="link-item" data-url="${esc(l.url)}" data-id="${l.id}">
        <span class="link-icon">${iconHtml(l.icon)}</span>
        <span class="link-name">${esc(l.name)}</span>
        <button class="link-del" title="删除">✕</button>
      </div>`).join("") || `<div class="lane-empty" style="padding:10px 0">暂无快捷方式</div>`;
    $("#links").onclick = (e) => {
      const item = e.target.closest(".link-item");
      if (!item) return;
      if (e.target.closest(".link-del")) {
        deleteLink(+item.dataset.id);
        return;
      }
      window.open(item.dataset.url, "_blank");
    };
  } catch (e) { /* 忽略 */ }
}

function openLinkModal() {
  $("#modal-title").textContent = "添加快捷方式";
  $("#modal-body").innerHTML = `
    <label>名称</label>
    <input id="l-name" placeholder="例如：GitHub">
    <label>网址</label>
    <div style="display:flex;gap:8px">
      <input id="l-url" placeholder="https://github.com" style="flex:1">
      <button class="btn ghost sm" id="l-fetch" type="button" title="抓取该网站自己的图标">✨ 自动图标</button>
    </div>
    <div id="l-preview" style="display:none;margin-top:10px">
      <img id="l-preview-img" class="link-favicon" style="width:28px;height:28px" alt="">
      <span id="l-preview-name" style="font-size:12px;color:var(--text-dim);margin-left:8px"></span>
    </div>
    <label>图标（emoji 或自动抓取，可选）</label>
    <input id="l-icon" placeholder="🐙">
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
    btn.textContent = "✨ 自动图标";
  }
}

function saveLink() {
  const name = $("#l-name").value.trim();
  const url = $("#l-url").value.trim();
  if (!name || !url) { toast("名称和网址不能为空"); return; }
  // 优先用自动抓取到的图标；用户手动改了则用输入框内容
  const icon = $("#l-icon").value.trim();
  api("/api/links", {
    method: "POST",
    body: JSON.stringify({ name, url, icon }),
  }).then(() => {
    closeModal();
    _fetchedIcon = "";
    loadLinks();
    toast("已添加");
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
async function loadNotes() {
  try {
    const notes = await api("/api/notes");
    $("#notes").innerHTML = notes.map((n) => `
      <div class="note-item">${esc(n.content)}
        <button class="note-del" onclick="deleteNote(${n.id})">✕</button>
        <span class="note-time">${esc(n.created_at.slice(5, 16))}</span>
      </div>`).join("") || `<div class="lane-empty" style="padding:10px 0">暂无便签</div>`;
  } catch (e) { /* 忽略 */ }
}

function openNoteModal() {
  $("#modal-title").textContent = "新建便签";
  $("#modal-body").innerHTML = `<textarea id="n-content" placeholder="随手记点什么…"></textarea>`;
  openModal();
  setTimeout(() => $("#n-content").focus(), 50);
}

function saveNote() {
  const content = $("#n-content").value.trim();
  if (!content) { toast("便签内容不能为空"); return; }
  api("/api/notes", {
    method: "POST",
    body: JSON.stringify({ content }),
  }).then(() => {
    closeModal();
    loadNotes();
    toast("已保存便签");
  }).catch((e) => toast(e.message));
}

async function deleteNote(id) {
  if (SETTINGS.confirm_delete_note !== "0") {
    if (!await confirmDialog("删除这条便签？", { okText: "删除", title: "删除便签" })) return;
  }
  try { await api(`/api/notes/${id}`, { method: "DELETE" }); loadNotes(); }
  catch (e) { toast(e.message); }
}

/* ---------- 弹窗 ---------- */
function openModal() {
  $("#modal-mask").classList.remove("hidden");
  $("#modal").classList.remove("wide");
  $("#modal > .modal-actions").style.display = "flex";
  noAutofill();
}
function openModalWide() {
  $("#modal-mask").classList.remove("hidden");
  $("#modal").classList.add("wide");
  $("#modal > .modal-actions").style.display = "none";
  noAutofill();
}
function closeModal() { $("#modal-mask").classList.add("hidden"); }

/* 自定义确认弹窗：替代原生 confirm()（原生对话框标题显示页面 URL，样式也与主题不符） */
function confirmDialog(message, opts = {}) {
  const { okText = "删除", title = "确认操作", icon = "🗑️" } = opts;
  return new Promise((resolve) => {
    $("#confirm-title").textContent = title;
    $("#confirm-msg").textContent = message;
    $("#confirm-ok").textContent = okText;
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
const STATUS_TEXT2 = { todo: "待办", doing: "进行中", done: "已完成" };
const FIELD_LABELS = { title: "标题", description: "描述", priority: "优先级",
                       due_date: "截止日期", tags: "标签" };
const PRIORITY_TEXT2 = { high: "高", medium: "中", low: "低" };

/* 变更详情弹窗的 changes 缓存（按时间线顺序索引） */
let _detailChanges = [];
/* 当前打开的任务详情（供描述历史使用） */
let _currentTaskDetail = null;

function fmtValue(field, v) {
  if (field === "priority") return (PRIORITY_TEXT2[v] || v) + "优先级";
  if (field === "tags") return v ? v.split(",").filter(Boolean).join("、") : "（无）";
  if (field === "due_date") return v || "（无）";
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
      <div class="desc-group-date">📅 ${esc(date)}</div>
      ${items.map((v) => `
        <div class="desc-ver">
          <div class="desc-ver-head">版本 ${v.ver} <span>${esc((v.time || "").slice(11, 19))}</span></div>
          <div class="desc-ver-body">${esc(v.desc) || "（空）"}</div>
        </div>`).join("")}
    </div>`).join("");
  $("#modal-body").innerHTML = `
    <div style="font-size:12px;color:var(--text-dim);margin-bottom:10px">共 ${total} 个版本，最新在前；每次编辑自动记录，点「查看变更」看相邻版本差异</div>
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
      t.due_date ? `<span class="detail-chip ${overdue ? "overdue" : ""}">📅 ${esc(t.due_date)}${overdue ? " 已过期" : ""}</span>` : "",
      t.source === "agent" ? `<span class="detail-chip agent">🤖 agent 创建</span>` : "",
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
        <div class="timeline-title">时间线<span style="color:var(--text-dim);font-weight:400;font-size:11px;margin-left:8px">悬停看变更 · 点「查看变更」看完整前后对比</span></div>
        ${events}
      </div>
      <div class="modal-actions" style="margin-top:14px">
        <button class="btn ghost" onclick="showDescHistory()">📜 描述历史</button>
        <button class="btn ghost" onclick="editTask(${t.id})">✎ 编辑</button>
        <button class="btn primary" onclick="closeModal()">关闭</button>
      </div>`;
    openModalWide();
  }).catch((e) => toast(e.message));
}

/* ---------- 番茄钟 ---------- */
const POMO_FOCUS = 25 * 60;
const POMO_BREAK = 5 * 60;
let pomo = { phase: "idle", remain: POMO_FOCUS, endAt: 0, paused: false, _timer: null };

function pomoFmt(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function pomoRender() {
  const timeEl = $("#pomo-time");
  timeEl.textContent = pomoFmt(pomo.remain);
  timeEl.className = "pomo-time " +
    (pomo.phase === "focus" ? "focus" : pomo.phase === "break" ? "break" : "");
  const startBtn = $("#pomo-start");
  const skipBtn = $("#pomo-skip");
  skipBtn.disabled = pomo.phase === "idle";
  if (pomo.phase === "idle") {
    $("#pomo-phase").textContent = "就绪 · 点击开始专注";
    startBtn.textContent = "开始";
  } else if (pomo.phase === "focus") {
    $("#pomo-phase").textContent = pomo.paused ? "专注已暂停" : "专注中 · 25 分钟";
    startBtn.textContent = pomo.paused ? "继续" : "暂停";
  } else {
    $("#pomo-phase").textContent = pomo.paused ? "休息已暂停" : "休息中 · 5 分钟";
    startBtn.textContent = pomo.paused ? "继续" : "暂停";
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
    }).catch(() => {});
    beep(3);
    toast("🍅 专注完成，休息 5 分钟");
    pomo.phase = "break";
    pomo.remain = POMO_BREAK;
  } else {
    beep(2);
    toast("☕ 休息结束，开始下一个番茄");
    pomo.phase = "idle";
    pomo.remain = POMO_FOCUS;
  }
  pomo.paused = false;
  pomoRender();
}

function pomoStartClick() {
  if (pomo.phase === "idle") {
    pomo.phase = "focus";
    pomo.remain = POMO_FOCUS;
    pomo.paused = false;
    pomo.endAt = Date.now() + pomo.remain * 1000;
    pomoStartTimer();
  } else if (pomo.paused) {
    pomo.paused = false;
    pomo.endAt = Date.now() + pomo.remain * 1000;
    pomoStartTimer();
  } else {
    pomo.paused = true;
    clearInterval(pomo._timer);
  }
  pomoRender();
}

function pomoSkipClick() {
  clearInterval(pomo._timer);
  if (pomo.phase === "focus") {
    pomo.phase = "break";
    pomo.remain = POMO_BREAK;
    pomo.paused = false;
    pomo.endAt = Date.now() + pomo.remain * 1000;
    pomoStartTimer();
    toast("已跳过专注，进入休息");
  } else if (pomo.phase === "break") {
    pomo.phase = "idle";
    pomo.remain = POMO_FOCUS;
    pomo.paused = false;
    toast("已跳过休息");
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
$("#nt-add").addEventListener("click", createTask);
$("#nt-title").addEventListener("keydown", (e) => { if (e.key === "Enter") createTask(); });
$("#nt-more").addEventListener("click", () => $("#nt-detail").classList.toggle("hidden"));
$("#weather").addEventListener("click", openWeatherModal);
$("#pomo-start").addEventListener("click", pomoStartClick);
$("#pomo-skip").addEventListener("click", pomoSkipClick);
$(".add-link-btn").addEventListener("click", openLinkModal);
$(".add-note-btn").addEventListener("click", openNoteModal);
$("#modal-cancel").addEventListener("click", closeModal);
$("#modal-ok").addEventListener("click", () => {
  const title = $("#modal-title").textContent;
  if (title === "编辑任务") saveTaskEdit();
  else if (title === "添加快捷方式") saveLink();
  else if (title === "新建便签") saveNote();
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
}).catch(() => {});
loadTasks();
loadStats();
loadSettings();
loadWeather();
loadLinks();
loadNotes();
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
    openModal();
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
  // 打开下载进度弹窗
  $("#modal-title").textContent = "正在下载更新";
  $("#modal-body").innerHTML = `
    <div style="font-size:13px;color:var(--text-dim);margin-bottom:10px">
      当前 v${APP_VERSION_TEXT} → 最新 ${_updateInfo.tag}
    </div>
    <div class="upd-bar"><div class="upd-bar-fill" id="upd-fill" style="width:0%"></div></div>
    <div class="upd-meta" id="upd-meta">准备下载…</div>`;
  openModal();
  let cancelled = false;
  let pollTimer = null;
  try {
    const d = await api("/api/update/download", {
      method: "POST",
      body: JSON.stringify({
        url: _updateInfo.download_url,
        filename: _updateInfo.asset_name,
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
    const ok = await confirmDialog("更新已下载完成，将自动重启应用完成更新。确定？", { okText: "更新", title: "确认更新", icon: "⬆️" });
    if (!ok) return;
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
