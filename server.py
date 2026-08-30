# -*- coding: utf-8 -*-
"""Flask REST API + 静态页面服务。
所有接口绑定 127.0.0.1，仅供本机（应用窗口 / Hermes agent）调用。"""
import os
import re
import sqlite3
import sys
import uuid
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, request, send_from_directory

import db
from services import weather, favicon as favicon_service
from services import updater
from app import APP_VERSION, IS_BETA

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
if not os.path.isdir(STATIC_DIR) and hasattr(sys, "_MEIPASS"):
    STATIC_DIR = os.path.join(sys._MEIPASS, "static")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

VALID_STATUS = {"todo", "doing", "done"}
VALID_PRIORITY = {"low", "medium", "high"}


def _parse_tags(tags):
    if tags is None:
        return ""
    # 兼容网页标签编辑器、中文输入法和第三方 API：不再要求英文逗号。
    values = tags if isinstance(tags, list) else [tags]
    parts = [
        part.strip()
        for value in values
        for part in re.split(r"[,，、;；\n\r]+", str(value))
        if part.strip()
    ]
    return ",".join(dict.fromkeys(parts))


def _task_out(row):
    row["tags"] = [t for t in row.get("tags", "").split(",") if t]
    return row


# ---------------- 健康 / 统计 ----------------

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "workbench", "version": APP_VERSION,
                    "beta": bool(IS_BETA)})


@app.get("/api/integration")
def integration_info():
    """Return capabilities for the in-app Agent guide without exposing user paths."""
    if getattr(sys, "frozen", False):
        mcp_available = os.path.isfile(os.path.join(BASE_DIR, "ShyBoard-MCP.exe"))
    else:
        mcp_available = os.path.isfile(os.path.join(BASE_DIR, "run_mcp.bat"))
    return jsonify({
        "platform": "windows",
        "rest_available": True,
        "mcp_available": mcp_available,
    })


# ---------------- 更新 ----------------

@app.get("/api/update/check")
def update_check():
    """检查 GitHub 最新版本。返回 {tag, has_update, ...}"""
    force = request.args.get("force", "0") == "1"
    return jsonify(updater.check(APP_VERSION, force=force))


@app.post("/api/update/download")
def update_download():
    """按 GitHub 最新 Release 下载、校验并保存待安装包。body: {tag}"""
    data = request.get_json(silent=True) or {}
    tag = str(data.get("tag", "")).strip()
    if not tag:
        return jsonify({"error": "缺少更新版本"}), 400
    try:
        result = updater.download_release(APP_VERSION, tag)
        return jsonify({"ok": True, "pending": True, **result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as e:
        return jsonify({"error": f"下载失败：{e}"}), 502


@app.get("/api/update/progress")
def update_progress():
    """查询下载进度（流式下载时前端轮询）。"""
    p = updater.progress()
    if p is None:
        return jsonify({"downloaded": 0, "total": 0, "percent": 0, "done": False, "active": False})
    p["active"] = True
    return jsonify(p)


@app.post("/api/update/apply")
def update_apply():
    """应用更新：启动 PowerShell helper（update.ps1）替换文件并重启。

    下载已完成（pending 缓存存在）→ helper 等本进程退出后
    解压替换 exe/_internal 并按原端口重启（本进程 1s 后退出）。
    """
    try:
        updater.apply()
        return jsonify({"ok": True, "message": "更新已开始，应用将自动重启"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/update/result")
def update_result():
    """新进程启动后读取一次安装结果，用于提示成功或已回滚。"""
    return jsonify(updater.consume_result() or {})


@app.get("/api/stats")
def stats():
    conn = db.get_conn()
    try:
        counts = {
            r["status"]: r["n"]
            for r in conn.execute(
                "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
            ).fetchall()
        }
        today = datetime.now().strftime("%Y-%m-%d")
        done_today = conn.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE completed_at LIKE ?",
            (today + "%",),
        ).fetchone()["n"]
    finally:
        conn.close()
    return jsonify({
        "total": sum(counts.values()),
        "todo": counts.get("todo", 0),
        "doing": counts.get("doing", 0),
        "done": counts.get("done", 0),
        "done_today": done_today,
    })


# ---------------- 任务 ----------------

@app.get("/api/tasks")
def tasks_list():
    status = request.args.get("status")
    if status and status not in VALID_STATUS:
        return jsonify({"error": f"status 必须是 {sorted(VALID_STATUS)}"}), 400
    project_id = request.args.get("project_id")
    rows = db.list_tasks(status=status, project_id=project_id if project_id else None)
    return jsonify([_task_out(r) for r in rows])


def _validate_due_date(value):
    """校验任务截止日期：空串=无 DDL；非真实 YYYY-MM-DD 返回 None（非法）。"""
    due = str(value or "").strip()
    if not due:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
        try:
            datetime.strptime(due, "%Y-%m-%d")
            return due
        except ValueError:
            return None
    return None


def _validate_remind_days(value):
    """-1 表示不提醒；其余值是截止日前的提醒天数。"""
    try:
        days = int(value)
    except (TypeError, ValueError):
        return None
    return days if -1 <= days <= 365 else None


@app.post("/api/tasks")
def tasks_create():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    if not title:
        return jsonify({"error": "title 不能为空"}), 400
    status = data.get("status", "todo")
    if status not in VALID_STATUS:
        return jsonify({"error": f"status 必须是 {sorted(VALID_STATUS)}"}), 400
    priority = data.get("priority", "medium")
    if priority not in VALID_PRIORITY:
        return jsonify({"error": f"priority 必须是 {sorted(VALID_PRIORITY)}"}), 400
    source = data.get("source", "manual")
    if source not in {"manual", "agent"}:
        return jsonify({"error": "source 必须是 manual 或 agent"}), 400
    due_date = _validate_due_date(data.get("due_date", ""))
    if due_date is None:
        return jsonify({"error": "due_date 格式应为 YYYY-MM-DD"}), 400
    remind_days = _validate_remind_days(data.get("remind_days", 3))
    if remind_days is None:
        return jsonify({"error": "remind_days 必须是 -1 到 365 之间的整数"}), 400
    project_id = str(data.get("project_id", "")).strip()
    external_key = str(data.get("external_key", "")).strip()

    row = db.create_task(
        title=title,
        description=str(data.get("description", "")).strip(),
        status=status,
        priority=priority,
        due_date=due_date,
        remind_days=remind_days,
        tags=_parse_tags(data.get("tags")),
        source=source,
        project_id=project_id,
        external_key=external_key,
    )
    return jsonify(_task_out(row)), 201


@app.get("/api/tasks/<int:task_id>")
def tasks_get(task_id):
    row = db.get_task(task_id)
    if not row:
        return jsonify({"error": "任务不存在"}), 404
    data = _task_out(row)
    data["events"] = db.list_events(task_id)
    data["progress"] = db.list_progress(task_id)
    return jsonify(data)


@app.patch("/api/tasks/<int:task_id>")
def tasks_update(task_id):
    row = db.get_task(task_id)
    if not row:
        return jsonify({"error": "任务不存在"}), 404
    data = request.get_json(silent=True) or {}
    fields = {}
    if "title" in data:
        fields["title"] = str(data["title"]).strip() or row["title"]
    if "description" in data:
        fields["description"] = str(data["description"]).strip()
    if "status" in data:
        if data["status"] not in VALID_STATUS:
            return jsonify({"error": f"status 必须是 {sorted(VALID_STATUS)}"}), 400
        fields["status"] = data["status"]
    if "priority" in data:
        if data["priority"] not in VALID_PRIORITY:
            return jsonify({"error": f"priority 必须是 {sorted(VALID_PRIORITY)}"}), 400
        fields["priority"] = data["priority"]
    if "due_date" in data:
        due = _validate_due_date(data["due_date"])
        if due is None:
            return jsonify({"error": "due_date 格式应为 YYYY-MM-DD"}), 400
        fields["due_date"] = due
    if "remind_days" in data:
        remind_days = _validate_remind_days(data["remind_days"])
        if remind_days is None:
            return jsonify({"error": "remind_days 必须是 -1 到 365 之间的整数"}), 400
        fields["remind_days"] = remind_days
    if "tags" in data:
        fields["tags"] = _parse_tags(data["tags"])
    if "project_id" in data:
        fields["project_id"] = str(data["project_id"] or "").strip()
    if "external_key" in data:
        fields["external_key"] = str(data["external_key"] or "").strip()
    updated = db.update_task(task_id, **fields)
    return jsonify(_task_out(updated))


@app.delete("/api/tasks/<int:task_id>")
def tasks_delete(task_id):
    if not db.get_task(task_id):
        return jsonify({"error": "任务不存在"}), 404
    db.delete_task(task_id)
    return jsonify({"ok": True})


# ---------------- 定时任务 ----------------

def _recurring_matches(task, value):
    if task["schedule_type"] == "weekly":
        return value.isoweekday() == int(task["schedule_value"])
    import calendar
    expected = min(int(task["schedule_value"]), calendar.monthrange(value.year, value.month)[1])
    return value.day == expected


def _recurring_schedule_label(task):
    if task["schedule_type"] == "weekly":
        labels = {1: "每周一", 2: "每周二", 3: "每周三", 4: "每周四", 5: "每周五", 6: "每周六", 7: "每周日"}
        return labels.get(int(task["schedule_value"]), "每周")
    day = int(task["schedule_value"])
    return "每月最后一天" if day == 31 else f"每月 {day} 日"


def _recurring_next_date(task, start=None):
    if not int(task.get("enabled", 1)):
        return ""
    cursor = start or date.today()
    completed = {
        item["scheduled_date"]
        for item in db.list_recurring_completions(task["id"], limit=500)
    }
    for offset in range(0, 370):
        candidate = cursor + timedelta(days=offset)
        key = candidate.isoformat()
        if _recurring_matches(task, candidate) and key not in completed:
            return key
    return ""


def _recurring_out(task, include_history=False):
    row = dict(task)
    row["enabled"] = bool(row.get("enabled", 1))
    row["schedule_label"] = _recurring_schedule_label(row)
    row["next_due_date"] = _recurring_next_date(row)
    if row["next_due_date"]:
        row["days_until"] = (date.fromisoformat(row["next_due_date"]) - date.today()).days
    else:
        row["days_until"] = None
    if include_history:
        row["completions"] = db.list_recurring_completions(row["id"], limit=100)
    return row


def _validate_recurring_payload(data, existing=None):
    fields = {}
    if existing is None or "title" in data:
        title = str(data.get("title", existing["title"] if existing else "")).strip()
        if not title:
            return None, "title 不能为空"
        fields["title"] = title
    if "description" in data:
        fields["description"] = str(data.get("description", "")).strip()
    schedule_type = str(data.get("schedule_type", existing["schedule_type"] if existing else "weekly")).strip()
    if schedule_type not in {"weekly", "monthly"}:
        return None, "schedule_type 必须是 weekly 或 monthly"
    if existing is None or "schedule_type" in data:
        fields["schedule_type"] = schedule_type
    if existing is None or "schedule_value" in data or "schedule_type" in data:
        try:
            value = int(data.get("schedule_value", existing["schedule_value"] if existing else 1))
        except (TypeError, ValueError):
            return None, "schedule_value 必须是整数"
        upper = 7 if schedule_type == "weekly" else 31
        if not 1 <= value <= upper:
            return None, f"schedule_value 必须是 1 到 {upper}"
        fields["schedule_value"] = value
    if existing is None or "remind_days" in data:
        remind_days = _validate_remind_days(data.get("remind_days", existing["remind_days"] if existing else 1))
        if remind_days is None:
            return None, "remind_days 必须是 -1 到 365 之间的整数"
        fields["remind_days"] = remind_days
    if "enabled" in data:
        raw = data["enabled"]
        fields["enabled"] = 0 if str(raw).strip().lower() in {"0", "false", "off", "no"} else 1
    return fields, None


@app.get("/api/recurring-tasks")
def recurring_tasks_list():
    return jsonify([_recurring_out(row) for row in db.list_recurring_tasks()])


@app.post("/api/recurring-tasks")
def recurring_tasks_create():
    data = request.get_json(silent=True) or {}
    fields, error = _validate_recurring_payload(data)
    if error:
        return jsonify({"error": error}), 400
    row = db.create_recurring_task(**fields)
    return jsonify(_recurring_out(row)), 201


@app.get("/api/recurring-tasks/<int:recurring_task_id>")
def recurring_tasks_get(recurring_task_id):
    row = db.get_recurring_task(recurring_task_id)
    if not row:
        return jsonify({"error": "定时任务不存在"}), 404
    return jsonify(_recurring_out(row, include_history=True))


@app.patch("/api/recurring-tasks/<int:recurring_task_id>")
def recurring_tasks_update(recurring_task_id):
    row = db.get_recurring_task(recurring_task_id)
    if not row:
        return jsonify({"error": "定时任务不存在"}), 404
    fields, error = _validate_recurring_payload(request.get_json(silent=True) or {}, existing=row)
    if error:
        return jsonify({"error": error}), 400
    updated = db.update_recurring_task(recurring_task_id, **fields)
    return jsonify(_recurring_out(updated))


@app.delete("/api/recurring-tasks/<int:recurring_task_id>")
def recurring_tasks_delete(recurring_task_id):
    if not db.delete_recurring_task(recurring_task_id):
        return jsonify({"error": "定时任务不存在"}), 404
    return jsonify({"ok": True})


@app.post("/api/recurring-tasks/<int:recurring_task_id>/complete")
def recurring_tasks_complete(recurring_task_id):
    row = db.get_recurring_task(recurring_task_id)
    if not row:
        return jsonify({"error": "定时任务不存在"}), 404
    data = request.get_json(silent=True) or {}
    scheduled_date = _validate_due_date(data.get("scheduled_date", ""))
    if scheduled_date is None:
        return jsonify({"error": "scheduled_date 格式应为 YYYY-MM-DD"}), 400
    if not scheduled_date:
        scheduled_date = _recurring_next_date(row)
    if not scheduled_date:
        return jsonify({"error": "当前没有可完成的周期"}), 400
    scheduled = date.fromisoformat(scheduled_date)
    if not _recurring_matches(row, scheduled):
        return jsonify({"error": "该日期不符合定时规则"}), 400
    completion, created = db.complete_recurring_task(recurring_task_id, scheduled_date)
    result = _recurring_out(db.get_recurring_task(recurring_task_id), include_history=True)
    result["completion"] = completion
    result["already_completed"] = not created
    return jsonify(result), 201 if created else 200


@app.delete("/api/recurring-completions/<int:completion_id>")
def recurring_completion_delete(completion_id):
    if not db.delete_recurring_completion(completion_id):
        return jsonify({"error": "完成记录不存在"}), 404
    return jsonify({"ok": True})


# ---------------- 任务进度 ----------------

@app.get("/api/tasks/<int:task_id>/progress")
def progress_list(task_id):
    if not db.get_task(task_id):
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(db.list_progress(task_id))


@app.post("/api/tasks/<int:task_id>/progress")
def progress_create(task_id):
    if not db.get_task(task_id):
        return jsonify({"error": "任务不存在"}), 404
    data = request.get_json(silent=True) or {}
    content = str(data.get("content", "")).strip()
    if not content:
        return jsonify({"error": "进度内容不能为空"}), 400
    source = str(data.get("source", "manual")).strip()
    if source not in {"manual", "agent"}:
        return jsonify({"error": "source 必须是 manual 或 agent"}), 400
    record_id = str(data.get("record_id") or uuid.uuid4()).strip()
    existing = db.get_progress_by_record_id(record_id)
    if existing:
        if existing["task_id"] != task_id:
            return jsonify({"error": "record_id 已被其它任务使用"}), 409
        return jsonify(existing)
    row = db.create_progress(
        task_id=task_id,
        record_id=record_id,
        content=content,
        source=source,
        agent_id=str(data.get("agent_id", "")).strip(),
        run_id=str(data.get("run_id", "")).strip(),
    )
    return jsonify(row), 201


@app.patch("/api/progress/<int:progress_id>")
def progress_update(progress_id):
    if not db.get_progress(progress_id):
        return jsonify({"error": "进度记录不存在"}), 404
    data = request.get_json(silent=True) or {}
    content = str(data.get("content", "")).strip()
    if not content:
        return jsonify({"error": "进度内容不能为空"}), 400
    return jsonify(db.update_progress(progress_id, content))


@app.delete("/api/progress/<int:progress_id>")
def progress_delete(progress_id):
    if not db.get_progress(progress_id):
        return jsonify({"error": "进度记录不存在"}), 404
    db.delete_progress(progress_id)
    return jsonify({"ok": True})


# ---------------- Agent 上下文 ----------------

@app.post("/api/v1/projects/link")
def project_link():
    data = request.get_json(silent=True) or {}
    project_id = str(data.get("project_id", "")).strip()
    name = str(data.get("name", "")).strip()
    root_path = str(data.get("root_path", "")).strip()
    if not project_id or not name:
        return jsonify({"error": "project_id 和 name 不能为空"}), 400
    return jsonify(db.upsert_project(project_id, name, root_path)), 200


@app.get("/api/v1/context")
def agent_context():
    project_id = str(request.args.get("project_id", "")).strip()
    if not project_id:
        return jsonify({"error": "project_id 不能为空"}), 400
    try:
        limit = max(1, min(50, int(request.args.get("limit", "10"))))
    except ValueError:
        return jsonify({"error": "limit 必须是整数"}), 400
    project = db.get_project(project_id)
    if not project:
        return jsonify({"error": "项目不存在，请先 link_project"}), 404
    tasks = db.list_tasks(project_id=project_id, limit=limit)
    for task in tasks:
        task["tags"] = [tag for tag in task.get("tags", "").split(",") if tag]
        task["progress"] = db.list_progress(task["id"])[:3]
    return jsonify({"project": project, "tasks": tasks})


# ---------------- 便签 ----------------

@app.get("/api/notes")
def notes_list():
    return jsonify(db.list_notes())


@app.post("/api/notes")
def notes_create():
    data = request.get_json(silent=True) or {}
    content = str(data.get("content", "")).strip()
    if not content:
        return jsonify({"error": "content 不能为空"}), 400
    return jsonify(db.create_note(content)), 201


@app.delete("/api/notes/<int:note_id>")
def notes_delete(note_id):
    if not db.get_note(note_id):
        return jsonify({"error": "便签不存在"}), 404
    db.delete_note(note_id)
    return jsonify({"ok": True})


@app.patch("/api/notes/<int:note_id>")
def notes_update(note_id):
    if not db.get_note(note_id):
        return jsonify({"error": "便签不存在"}), 404
    data = request.get_json(silent=True) or {}
    content = str(data.get("content", "")).strip()
    if not content:
        return jsonify({"error": "内容不能为空"}), 400
    return jsonify(db.update_note(note_id, content))


# ---------------- 天气 ----------------

@app.get("/api/weather")
def weather_now():
    code = db.get_setting("city_code", "101020100")
    lat = db.get_setting("lat", "31.2304")
    lon = db.get_setting("lon", "121.4737")
    city = db.get_setting("city", "上海")
    try:
        data = weather.forecast(code, lat=lat, lon=lon, city_name=city)
    except Exception:
        return jsonify({"error": "天气服务暂时不可用（网络问题）"}), 502
    return jsonify(data)


@app.get("/api/weather/search")
def weather_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    return jsonify(weather.geocode(q))


# ---------------- 快捷链接 ----------------

@app.get("/api/links")
def links_list():
    return jsonify(db.list_links())


def _validate_link_url(url):
    """校验并规范化快捷方式 URL：拒绝 javascript: 等非 http(s) 协议；无协议补 https://。"""
    url = str(url or "").strip()
    if not url:
        return None
    # 拒绝带协议前缀但不是 http/https/ftp 的（javascript: 等）
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+\-.]*:", url) and not url.startswith(("http://", "https://", "ftp://")):
        return None
    if not url.startswith(("http://", "https://", "ftp://")):
        url = "https://" + url
    if not (url.startswith("http://") or url.startswith("https://")):
        return None
    return url


@app.post("/api/links")
def links_create():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    url = _validate_link_url(str(data.get("url", "")))
    if not name or not url:
        return jsonify({"error": "name 和 url 不能为空，url 必须是 http(s) 地址"}), 400
    return jsonify(db.create_link(
        name=name,
        url=url,
        icon=str(data.get("icon", "")).strip(),
        sort_order=int(data.get("sort_order") or 0) if str(data.get("sort_order", "")).isdigit() else 0,
    )), 201


@app.patch("/api/links/<int:link_id>")
def links_update(link_id):
    if not db.get_link(link_id):
        return jsonify({"error": "链接不存在"}), 404
    data = request.get_json(silent=True) or {}
    fields = {}
    if "name" in data:
        fields["name"] = str(data["name"]).strip()
    if "url" in data:
        url = _validate_link_url(str(data["url"]))
        if not url:
            return jsonify({"error": "url 必须是 http(s) 地址"}), 400
        fields["url"] = url
    if "icon" in data:
        fields["icon"] = str(data["icon"]).strip()
    if not fields:
        return jsonify({"error": "没有可更新的字段"}), 400
    db.update_link(link_id, **fields)
    return jsonify(db.get_link(link_id))


@app.delete("/api/links/<int:link_id>")
def links_delete(link_id):
    if not db.get_link(link_id):
        return jsonify({"error": "链接不存在"}), 404
    db.delete_link(link_id)
    return jsonify({"ok": True})


# favicon 抓取：GET /api/links/favicon?url=https://github.com → {"icon": "/icons/github.com.png"}
# url 可省略协议（如 bing.com），自动补全 https://
@app.get("/api/links/favicon")
def links_favicon():
    url = str(request.args.get("url", "")).strip()
    if not url:
        return jsonify({"error": "url 不能为空"}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        icon = favicon_service.fetch_favicon(url)
    except Exception:
        icon = None
    if not icon:
        return jsonify({"icon": ""}), 404
    return jsonify({"icon": icon})


# 图标静态文件：data/icons/ 目录
@app.get("/icons/<path:filename>")
def icons_static(filename):
    icons_dir = os.path.join(BASE_DIR, "data", "icons")
    if os.path.isfile(os.path.join(icons_dir, filename)):
        return send_from_directory(icons_dir, filename)
    return jsonify({"error": "图标不存在"}), 404


# ---------------- 番茄钟 ----------------

@app.get("/api/pomodoro")
def pomodoro_get():
    return jsonify(db.pomodoro_state())


@app.post("/api/pomodoro/complete")
def pomodoro_complete():
    return jsonify(db.pomodoro_complete())


# ---------------- 纪念日 ----------------

@app.get("/api/anniversaries")
def anniversaries_list():
    """全部纪念日 + 计算下次阳历日期/剩余天数（solar 公历 / lunar 农历循环）。"""
    items = []
    for a in db.list_anniversaries():
        ret = db.next_anniversary(
            a["month"], a["day"], a.get("calendar_type", "solar"))
        if ret is None:
            # 8 年内无此农历闰月（异常数据）：返回提示而非假日期
            items.append({
                "id": a["id"], "name": a["name"],
                "month": a["month"], "day": a["day"],
                "calendar_type": a.get("calendar_type", "solar"),
                "next_date": "", "days_left": None, "note": "暂无此闰月",
            })
            continue
        date_str, days = ret
        items.append({
            "id": a["id"],
            "name": a["name"],
            "month": a["month"],
            "day": a["day"],
            "calendar_type": a.get("calendar_type", "solar"),
            "next_date": date_str,
            "days_left": days,
        })
    return jsonify(items)


@app.post("/api/anniversaries")
def anniversaries_create():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    ctype = str(data.get("calendar_type", "solar")).strip()
    if ctype not in ("solar", "lunar"):
        return jsonify({"error": "日历类型只能是 solar 或 lunar"}), 400
    try:
        month = int(data.get("month", 0))
        day = int(data.get("day", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "月份/日期必须是数字"}), 400
    if not name:
        return jsonify({"error": "请输入纪念日名称"}), 400
    if not (1 <= abs(month) <= 12 and 1 <= day <= 31):
        return jsonify({"error": "日期不合法"}), 400
    if ctype == "solar":
        # 校验该月确实有这一天（如 2/30 非法）
        import calendar as _cal
        if day > _cal.monthrange(2024, month)[1]:
            return jsonify({"error": "日期不合法"}), 400
    return jsonify(db.create_anniversary(name, month, day, ctype)), 201


@app.patch("/api/anniversaries/<int:ann_id>")
def anniversaries_update(ann_id):
    existing = db.get_anniversary(ann_id)
    if not existing:
        return jsonify({"error": "纪念日不存在"}), 404
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", existing["name"])).strip()
    ctype = str(data.get("calendar_type", existing.get("calendar_type", "solar"))).strip()
    if ctype not in ("solar", "lunar"):
        return jsonify({"error": "日历类型只能是 solar 或 lunar"}), 400
    try:
        month = int(data.get("month", existing["month"]))
        day = int(data.get("day", existing["day"]))
    except (TypeError, ValueError):
        return jsonify({"error": "月份/日期必须是数字"}), 400
    if not name:
        return jsonify({"error": "请输入纪念日名称"}), 400
    if not (1 <= abs(month) <= 12 and 1 <= day <= 31):
        return jsonify({"error": "日期不合法"}), 400
    if ctype == "solar":
        import calendar as _cal
        if day > _cal.monthrange(2024, month)[1]:
            return jsonify({"error": "日期不合法"}), 400
    db.update_anniversary(ann_id, name, month, day, ctype)
    return jsonify(db.get_anniversary(ann_id))


@app.delete("/api/anniversaries/<int:ann_id>")
def anniversaries_delete(ann_id):
    if not db.get_anniversary(ann_id):
        return jsonify({"error": "纪念日不存在"}), 404
    db.delete_anniversary(ann_id)
    return jsonify({"ok": True})


# ---------------- 日记（日历每天记录） ----------------

def _validate_log_date(date):
    """校验日记日期为真实 YYYY-MM-DD（2026-08-12 code-review #14）。"""
    date = str(date or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return None
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return None
    return date


@app.get("/api/log")
def log_get():
    date = _validate_log_date(request.args.get("date", ""))
    if not date:
        return jsonify({"error": "date 参数格式应为 YYYY-MM-DD"}), 400
    log = db.get_log(date)
    return jsonify(log if log else {"date": date, "content": ""})


@app.put("/api/log")
def log_save():
    data = request.get_json(silent=True) or {}
    date = _validate_log_date(data.get("date", ""))
    if not date:
        return jsonify({"error": "date 格式应为 YYYY-MM-DD"}), 400
    content = str(data.get("content", "")).strip()
    return jsonify(db.save_log(date, content))


# ---------------- 日历（月视图：任务 + 纪念日） ----------------

@app.get("/api/calendar")
def calendar_month():
    """返回某月每天的信息：农历 + 纪念日（solar 公历 / lunar 农历循环命中）。

    ?month=YYYY-MM（缺省当月）。anniversaries 返回 {日: [{id, name, calendar_type}]}；
    lunar 返回 {日: {month(负=闰月), day, month_name, day_name}}；today 返回今天日期。
    任务截止标记已移除（v1.0.2 日历回归纯纪念日，任务改由格子点击弹窗管理）。
    """
    from datetime import date, datetime as _dt
    import calendar as _cal
    now = _dt.now()
    m = request.args.get("month", "")
    try:
        if m:
            year, month = int(m[:4]), int(m[5:7])
        else:
            year, month = now.year, now.month
    except (ValueError, IndexError):
        return jsonify({"error": "月份格式应为 YYYY-MM"}), 400
    if not (1 <= month <= 12):
        return jsonify({"error": "月份不合法"}), 400
    # 与前端年月跳转范围一致（2026-08-12 code-review #13）
    if not (1900 <= year <= 2100):
        return jsonify({"error": "年份范围应为 1900-2100"}), 400

    days_in_month = _cal.monthrange(year, month)[1]
    # 节日表：公历固定 + 农历固定（闰月不匹配）
    SOLAR_HOLIDAYS = {
        (1, 1): "元旦", (2, 14): "情人节", (3, 8): "妇女节", (3, 12): "植树节",
        (4, 1): "愚人节", (5, 1): "劳动节", (5, 4): "青年节", (6, 1): "儿童节",
        (7, 1): "建党节", (8, 1): "建军节", (9, 10): "教师节", (10, 1): "国庆节",
        (12, 24): "平安夜", (12, 25): "圣诞节",
    }
    LUNAR_HOLIDAYS = {
        (1, 1): "春节", (1, 15): "元宵节", (2, 2): "龙抬头", (5, 5): "端午节",
        (7, 7): "七夕", (8, 15): "中秋节", (9, 9): "重阳节", (12, 8): "腊八节",
    }
    # 每日农历（阳历日期 → 农历月/日；闰月 month 为负）。key 为字符串日（"1"~"31"）
    from lunar_python import Solar
    lunar_by_day = {}
    holidays_by_day = {}
    for day in range(1, days_in_month + 1):
        try:
            s = Solar.fromYmd(year, month, day)
            lunar = s.getLunar()
            lunar_by_day[str(day)] = {
                "month": lunar.getMonth(),       # 负值=闰月
                "day": lunar.getDay(),
                "month_name": lunar.getMonthInChinese(),
                "day_name": lunar.getDayInChinese(),
            }
            # 节日/节气：节气（清明等）+ 公历节日 + 农历节日（闰月不匹配）
            tags = []
            jq = (lunar.getJieQi() or "").strip()
            if jq:
                tags.append(jq)
            if (month, day) in SOLAR_HOLIDAYS:
                tags.append(SOLAR_HOLIDAYS[(month, day)])
            if lunar.getMonth() > 0 and (lunar.getMonth(), lunar.getDay()) in LUNAR_HOLIDAYS:
                tags.append(LUNAR_HOLIDAYS[(lunar.getMonth(), lunar.getDay())])
            if tags:
                holidays_by_day[str(day)] = tags
        except Exception:
            lunar_by_day[str(day)] = {"month": 0, "day": 0, "month_name": "", "day_name": ""}
    # 纪念日归位：solar 直接按公历月日；lunar 换算当年阳历日期（落在本月才显示）
    anns_by_day = {}
    for a in db.list_anniversaries():
        if a.get("calendar_type", "solar") == "solar":
            if a["month"] == month and 1 <= a["day"] <= days_in_month:
                anns_by_day.setdefault(str(a["day"]), []).append(
                    {"id": a["id"], "name": a["name"], "calendar_type": "solar"})
        else:
            # 农历：当年该农历月日 → 阳历
            try:
                from lunar_python import Lunar
                l = Lunar.fromYmd(year, a["month"], a["day"])
                s = l.getSolar()
                if s.getYear() == year and s.getMonth() == month:
                    anns_by_day.setdefault(str(s.getDay()), []).append(
                        {"id": a["id"], "name": a["name"], "calendar_type": "lunar"})
            except Exception:
                pass
    # 待办任务 DDL 标注（v1.0.3 用户要求：只标待办任务的截止日期，进行中/已完成不标）
    prefix = f"{year}-{month:02d}-"
    todo_tasks = db.list_tasks(status="todo", include_done=False)
    tasks_by_day = {}
    for t in todo_tasks:
        dd = str(t.get("due_date") or "")
        # 防御历史脏数据：残缺/非法 due_date 跳过（201 修复：写入端已校验 YYYY-MM-DD）
        if dd.startswith(prefix) and len(dd) >= 10 and dd[8:10].isdigit():
            day = int(dd[8:10])
            if 1 <= day <= 31:
                tasks_by_day.setdefault(str(day), []).append({"id": t["id"], "title": t["title"]})
    # 定时任务按规则投射到本月；完成记录只标记当次，不会终止后续周期。
    recurring_by_day = {}
    for recurring in db.list_recurring_tasks(include_disabled=False):
        completed_dates = {
            item["scheduled_date"]
            for item in db.list_recurring_completions(recurring["id"], limit=500)
            if str(item.get("scheduled_date", "")).startswith(prefix)
        }
        for day in range(1, days_in_month + 1):
            current = date(year, month, day)
            if not _recurring_matches(recurring, current):
                continue
            key = current.isoformat()
            recurring_by_day.setdefault(str(day), []).append({
                "id": recurring["id"],
                "title": recurring["title"],
                "schedule_label": _recurring_schedule_label(recurring),
                "completed": key in completed_dates,
                "remind_days": recurring["remind_days"],
            })
    # 当月写过日记的日期（v1.0.3：保存后日历格子显示 📝 标记）
    log_days = db.list_log_days(prefix)
    return jsonify({
        "year": year, "month": month, "days": days_in_month,
        # calendar.monthrange uses Monday=0; the UI grid starts on Sunday.
        "first_weekday": (_cal.monthrange(year, month)[0] + 1) % 7,
        "today": now.strftime("%Y-%m-%d"),
        "lunar": lunar_by_day,
        "anniversaries": anns_by_day,
        "todo_tasks": tasks_by_day,
        "recurring_tasks": recurring_by_day,
        "holidays": holidays_by_day,
        "logs": log_days,
    })


# ---------------- 数据备份与恢复 ----------------

@app.get("/api/backup")
def backup_export():
    data = db.export_all_data()
    return jsonify({
        "format": "shyboard-backup",
        "schema_version": 1,
        "app_version": APP_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data": data,
    })


@app.post("/api/backup/import")
def backup_import():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or payload.get("format") != "shyboard-backup":
        return jsonify({"error": "这不是有效的 ShyBoard 备份文件"}), 400
    try:
        schema_version = int(payload.get("schema_version", 0))
    except (TypeError, ValueError):
        schema_version = 0
    if schema_version != 1:
        return jsonify({"error": "暂不支持这个备份版本，请先升级 ShyBoard"}), 400
    try:
        restored = db.import_all_data(payload.get("data"))
        return jsonify({"ok": True, **restored})
    except (ValueError, sqlite3.Error) as exc:
        return jsonify({"error": f"无法导入备份：{exc}"}), 400


# ---------------- 设置 ----------------

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ShyBoard"


def _autostart_command():
    """生成开机自启命令：打包版直接指向 exe；源码版用 pythonw 跑 app.py。
    若进程是 --port 启动（如测试版 17891），自启命令带上该参数，避免 find_port 复用他人服务。"""
    extra = ""
    if "--port" in sys.argv:
        try:
            extra = f" --port {int(sys.argv[sys.argv.index('--port') + 1])}"
        except (ValueError, IndexError):
            pass
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"{extra}'
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    app_py = os.path.join(BASE_DIR, "app.py")
    return f'"{pyw}" "{app_py}"{extra}'


@app.get("/api/settings/autostart")
def autostart_get():
    """查询开机自启状态：读注册表为准（settings 仅作界面记忆）。"""
    enabled = False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
            enabled = True
    except FileNotFoundError:
        enabled = False
    except OSError:
        pass
    db.set_setting("autostart", "1" if enabled else "0")
    return jsonify({"enabled": enabled})


@app.post("/api/settings/autostart")
def autostart_set():
    data = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled"))
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enabled:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, _autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
        db.set_setting("autostart", "1" if enabled else "0")
        return jsonify({"ok": True, "enabled": enabled})
    except OSError as e:
        return jsonify({"error": f"设置开机自启失败：{e}"}), 500


@app.get("/api/settings")
def settings_get():
    s = db.get_all_settings()
    # 兜底：老库缺少新键时补默认值
    for k, v in db.DEFAULT_SETTINGS.items():
        s.setdefault(k, v)
    return jsonify(s)


@app.put("/api/settings")
def settings_update():
    data = request.get_json(silent=True) or {}
    # 通用设置项（布尔开关等）：confirm_delete_*；autostart 不走这里（统一 POST /api/settings/autostart 双写注册表+DB，2026-08-12 code-review #10）
    SIMPLE_KEYS = {
        "confirm_delete_task", "confirm_delete_link", "confirm_delete_note",
        "confirm_delete_ann", "confirm_task_status",
    }
    for k in SIMPLE_KEYS:
        if k in data:
            db.set_setting(k, "1" if data[k] else "0")
    # 主题色系（pink / dark / light / orange / green）
    if "theme" in data and str(data["theme"]).strip() in {
        "pink", "dark", "light", "orange", "green", "purple", "ocean",
        "teal", "terracotta", "navy", "graphite", "plum",
    }:
        db.set_setting("theme", str(data["theme"]).strip())
    if "font_size" in data and str(data["font_size"]).strip() in {"normal", "large"}:
        db.set_setting("font_size", str(data["font_size"]).strip())
    duration_options = {
        "pomodoro_focus_minutes": {15, 25, 45, 60},
        "pomodoro_break_minutes": {5, 10, 15},
    }
    for key, allowed in duration_options.items():
        if key not in data:
            continue
        try:
            minutes = int(data[key])
        except (TypeError, ValueError):
            return jsonify({"error": "番茄钟时长无效"}), 400
        if minutes not in allowed:
            return jsonify({"error": "番茄钟时长无效"}), 400
        db.set_setting(key, str(minutes))
    # 直接给城市代码（前端从搜索结果选定）：city + city_code 一起存
    if "city_code" in data and str(data.get("city_code", "")).strip():
        code = str(data["city_code"]).strip()
        hit = weather.city_by_code(code)
        if not hit:
            return jsonify({"error": "未知城市代码"}), 400
        city = str(data.get("city", "")).strip() or hit["n"]
        db.set_setting("city_code", code)
        db.set_setting("city", city)
        return jsonify(db.get_all_settings())
    # 按城市名查表（向后兼容）
    if "city" in data and str(data["city"]).strip():
        found = weather.geocode(str(data["city"]).strip())
        if found:
            db.set_setting("city", found[0]["n"])
            db.set_setting("city_code", found[0]["c"])
            return jsonify(db.get_all_settings())
        # 城市名查表失败：契约要求 404（test_api.py:193），勿删
        return jsonify({"error": f"未知城市：{data['city']}"}), 404
    return jsonify(db.get_all_settings())


# ---------------- 页面 ----------------

@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename):
    return send_from_directory(STATIC_DIR, filename)


def run_server(port):
    db.init_db()
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)
