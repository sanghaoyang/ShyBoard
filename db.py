# -*- coding: utf-8 -*-
"""SQLite 数据层：任务 / 便签 / 设置。每次操作短连接，线程安全。"""
import json
import os
import sqlite3
import sys
from datetime import datetime

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.environ.get("WORKBENCH_DB", os.path.join(DATA_DIR, "workbench.db"))

DEFAULT_SETTINGS = {
    "city": "上海",
    "city_code": "101020100",
    "lat": "31.2304",
    "lon": "121.4737",
    "theme": "pink",
    "font_size": "normal",
    "autostart": "0",
    "confirm_delete_task": "1",
    "confirm_delete_link": "1",
    "confirm_delete_note": "1",
    "confirm_task_status": "1",
}

TASK_PROGRESS_PREFIX = "[TASK_PROGRESS]\n"


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_conn():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")  # 极端写并发防 database is locked（code-review #24）
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT NOT NULL,
                description  TEXT DEFAULT '',
                status       TEXT DEFAULT 'todo' CHECK(status IN ('todo','doing','done')),
                priority     TEXT DEFAULT 'medium' CHECK(priority IN ('low','medium','high')),
                due_date     TEXT DEFAULT '',
                remind_days  INTEGER DEFAULT 3 CHECK(remind_days BETWEEN -1 AND 365),
                tags         TEXT DEFAULT '',
                source       TEXT DEFAULT 'manual' CHECK(source IN ('manual','agent')),
                project_id   TEXT DEFAULT '',
                external_key TEXT DEFAULT '',
                created_at   TEXT,
                updated_at   TEXT,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS notes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                content    TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS links (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                url        TEXT NOT NULL,
                icon       TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS task_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id    INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL CHECK(event_type IN ('create','status','update')),
                old_status TEXT DEFAULT '',
                new_status TEXT DEFAULT '',
                note       TEXT DEFAULT '',
                created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id, id);
            CREATE TABLE IF NOT EXISTS task_progress (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                record_id       TEXT NOT NULL UNIQUE,
                content         TEXT NOT NULL,
                source          TEXT DEFAULT 'manual' CHECK(source IN ('manual','agent')),
                agent_id        TEXT DEFAULT '',
                run_id          TEXT DEFAULT '',
                created_at      TEXT,
                updated_at      TEXT
            );
            CREATE TABLE IF NOT EXISTS projects (
                project_id   TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                root_path    TEXT DEFAULT '',
                created_at   TEXT,
                updated_at   TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_progress_task ON task_progress(task_id, id DESC);
            CREATE TABLE IF NOT EXISTS anniversaries (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                month         INTEGER NOT NULL CHECK(month BETWEEN -12 AND 12),
                day           INTEGER NOT NULL CHECK(day BETWEEN 1 AND 31),
                calendar_type TEXT DEFAULT 'solar' CHECK(calendar_type IN ('solar','lunar')),
                created_at    TEXT
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS daily_logs (
                date       TEXT PRIMARY KEY,
                content    TEXT NOT NULL,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS recurring_tasks (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                title          TEXT NOT NULL,
                description    TEXT DEFAULT '',
                schedule_type  TEXT NOT NULL CHECK(schedule_type IN ('weekly','monthly')),
                schedule_value INTEGER NOT NULL CHECK(schedule_value BETWEEN 1 AND 31),
                remind_days    INTEGER DEFAULT 1 CHECK(remind_days BETWEEN -1 AND 365),
                enabled        INTEGER DEFAULT 1 CHECK(enabled IN (0,1)),
                created_at     TEXT,
                updated_at     TEXT
            );
            CREATE TABLE IF NOT EXISTS recurring_completions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                recurring_task_id INTEGER NOT NULL REFERENCES recurring_tasks(id) ON DELETE CASCADE,
                scheduled_date    TEXT NOT NULL,
                completed_at      TEXT NOT NULL,
                UNIQUE(recurring_task_id, scheduled_date)
            );
            CREATE INDEX IF NOT EXISTS idx_recurring_completions_task
                ON recurring_completions(recurring_task_id, scheduled_date DESC);
            """
        )
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )
        conn.commit()
        _migrate_anniversaries(conn)
        _migrate_tasks(conn)
        _migrate_task_progress(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate_anniversaries(conn):
    """老库 anniversaries 表缺 calendar_type 列 / month CHECK 过严 → 重建表保留数据。

    2026-08-11 v1.0.2 日历功能升级：纪念日支持农历（lunar，闰月存负月如 -6）。
    旧表 CHECK(month BETWEEN 1 AND 12) 会拒绝负月，必须重建。
    """
    cols = [r[1] for r in conn.execute("PRAGMA table_info(anniversaries)").fetchall()]
    if "calendar_type" in cols:
        # 结构已新；但旧表 CHECK 仍可能限制 month 负值——SQLite 无法改 CHECK，
        # 若表定义是旧版（无 calendar_type 时已重建过）则无需处理。
        return
    # 旧表：建新表 + 复制数据（month/day 按原样，calendar_type 默认 solar）
    conn.execute(
        "CREATE TABLE anniversaries_new ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " name TEXT NOT NULL,"
        " month INTEGER NOT NULL CHECK(month BETWEEN -12 AND 12),"
        " day INTEGER NOT NULL CHECK(day BETWEEN 1 AND 31),"
        " calendar_type TEXT DEFAULT 'solar' CHECK(calendar_type IN ('solar','lunar')),"
        " created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO anniversaries_new (id, name, month, day, calendar_type, created_at)"
        " SELECT id, name, month, day, 'solar', created_at FROM anniversaries"
    )
    conn.execute("DROP TABLE anniversaries")
    conn.execute("ALTER TABLE anniversaries_new RENAME TO anniversaries")


def _migrate_task_progress(conn):
    """把 Beta 版隐藏便签中的进度复制到正式表，保留原便签便于降级。"""
    rows = conn.execute(
        "SELECT id, content, created_at, updated_at FROM notes "
        "WHERE content LIKE ? ORDER BY id DESC",
        (TASK_PROGRESS_PREFIX + "%",),
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["content"][len(TASK_PROGRESS_PREFIX):])
            task_id = int(payload.get("taskId"))
            record_id = str(payload.get("recordId") or "").strip()
            content = str(payload.get("content") or "").strip()
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not record_id or not content:
            continue
        if not conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone():
            continue
        conn.execute(
            """INSERT OR IGNORE INTO task_progress
               (task_id, record_id, content, source, agent_id, run_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                task_id,
                record_id,
                content,
                "manual",
                "",
                "",
                str(payload.get("createdAt") or row["created_at"] or _now()),
                str(payload.get("updatedAt") or row["updated_at"] or _now()),
            ),
        )


def _migrate_tasks(conn):
    """为旧任务表补充后续版本加入的字段。"""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
    if "project_id" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN project_id TEXT DEFAULT ''")
    if "external_key" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN external_key TEXT DEFAULT ''")
    if "remind_days" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN remind_days INTEGER DEFAULT 3")


# ---------------- 项目 ----------------

def upsert_project(project_id, name, root_path=""):
    now = _now()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO projects (project_id, name, root_path, created_at, updated_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(project_id) DO UPDATE SET
                 name = excluded.name, root_path = excluded.root_path, updated_at = excluded.updated_at""",
            (project_id, name, root_path, now, now),
        )
        conn.commit()
        return get_project(project_id)
    finally:
        conn.close()


def get_project(project_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------- 任务 ----------------

def create_task(title, description="", status="todo", priority="medium",
                due_date="", remind_days=3, tags="", source="manual", project_id="",
                external_key=""):
    now = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO tasks (title, description, status, priority, due_date,
                                  remind_days, tags, source, project_id, external_key,
                                  created_at, updated_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (title, description, status, priority, due_date, remind_days, tags, source,
             project_id, external_key, now, now, now if status == "done" else ""),
        )
        task_id = cur.lastrowid
        _add_event(conn, task_id, "create", old_status="", new_status=status)
        conn.commit()
        return get_task(task_id)
    finally:
        conn.close()


def _add_event(conn, task_id, event_type, old_status="", new_status="", note=""):
    conn.execute(
        """INSERT INTO task_events (task_id, event_type, old_status, new_status, note, created_at)
           VALUES (?,?,?,?,?,?)""",
        (task_id, event_type, old_status, new_status, note, _now()),
    )


def list_events(task_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM task_events WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_tasks(status=None, include_done=True, limit=200, project_id=None):
    conn = get_conn()
    try:
        sql = "SELECT * FROM tasks"
        args = []
        if status:
            sql += " WHERE status = ?"
            args.append(status)
        elif not include_done:
            sql += " WHERE status != 'done'"
        if project_id is not None:
            sql += " AND" if " WHERE " in sql else " WHERE"
            sql += " project_id = ?"
            args.append(project_id)
        sql += " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,"
        sql += " CASE WHEN due_date='' THEN 1 ELSE 0 END, due_date, id DESC LIMIT ?"
        args.append(limit)
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_task(task_id):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def update_task(task_id, **fields):
    allowed = {"title", "description", "status", "priority", "due_date", "remind_days", "tags", "project_id", "external_key"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_task(task_id)
    conn = get_conn()
    try:
        old = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not old:
            return None
        if "status" in updates:
            updates["completed_at"] = _now() if updates["status"] == "done" else ""
        updates["updated_at"] = _now()
        sets = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE tasks SET {sets} WHERE id = ?",
                     (*updates.values(), task_id))
        # 事件记录：状态变更记 old→new；字段编辑记 JSON 详情 {"字段":[旧,新]}
        if "status" in updates and updates["status"] != old["status"]:
            _add_event(conn, task_id, "status",
                       old_status=old["status"], new_status=updates["status"])
        else:
            changed = {}
            for k in updates:
                if k in ("updated_at", "completed_at"):
                    continue
                if updates[k] != old[k]:
                    changed[k] = [str(old[k]), str(updates[k])]
            if changed:
                _add_event(conn, task_id, "update",
                           note=json.dumps(changed, ensure_ascii=False))
        conn.commit()
        return get_task(task_id)
    finally:
        conn.close()


def delete_task(task_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------------- 定时任务 ----------------

def create_recurring_task(title, schedule_type, schedule_value, description="",
                          remind_days=1, enabled=True):
    now = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO recurring_tasks
               (title, description, schedule_type, schedule_value, remind_days,
                enabled, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (title, description, schedule_type, schedule_value, remind_days,
             1 if enabled else 0, now, now),
        )
        conn.commit()
        return get_recurring_task(cur.lastrowid)
    finally:
        conn.close()


def list_recurring_tasks(include_disabled=True):
    conn = get_conn()
    try:
        where = "" if include_disabled else "WHERE r.enabled = 1"
        rows = conn.execute(
            f"""SELECT r.*,
                       COUNT(c.id) AS completion_count,
                       MAX(c.completed_at) AS last_completed_at
                FROM recurring_tasks r
                LEFT JOIN recurring_completions c ON c.recurring_task_id = r.id
                {where}
                GROUP BY r.id
                ORDER BY r.enabled DESC, r.updated_at DESC, r.id DESC"""
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_recurring_task(recurring_task_id):
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT r.*,
                      COUNT(c.id) AS completion_count,
                      MAX(c.completed_at) AS last_completed_at
               FROM recurring_tasks r
               LEFT JOIN recurring_completions c ON c.recurring_task_id = r.id
               WHERE r.id = ? GROUP BY r.id""",
            (recurring_task_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_recurring_task(recurring_task_id, **fields):
    allowed = {"title", "description", "schedule_type", "schedule_value",
               "remind_days", "enabled"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return get_recurring_task(recurring_task_id)
    updates["updated_at"] = _now()
    conn = get_conn()
    try:
        exists = conn.execute(
            "SELECT id FROM recurring_tasks WHERE id = ?", (recurring_task_id,)
        ).fetchone()
        if not exists:
            return None
        sets = ", ".join(f"{key} = ?" for key in updates)
        conn.execute(
            f"UPDATE recurring_tasks SET {sets} WHERE id = ?",
            (*updates.values(), recurring_task_id),
        )
        conn.commit()
        return get_recurring_task(recurring_task_id)
    finally:
        conn.close()


def delete_recurring_task(recurring_task_id):
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM recurring_tasks WHERE id = ?", (recurring_task_id,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def complete_recurring_task(recurring_task_id, scheduled_date):
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT OR IGNORE INTO recurring_completions
               (recurring_task_id, scheduled_date, completed_at)
               VALUES (?,?,?)""",
            (recurring_task_id, scheduled_date, _now()),
        )
        conn.commit()
        row = conn.execute(
            """SELECT * FROM recurring_completions
               WHERE recurring_task_id = ? AND scheduled_date = ?""",
            (recurring_task_id, scheduled_date),
        ).fetchone()
        return dict(row) if row else None, cur.rowcount > 0
    finally:
        conn.close()


def list_recurring_completions(recurring_task_id, limit=100):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM recurring_completions
               WHERE recurring_task_id = ?
               ORDER BY scheduled_date DESC, id DESC LIMIT ?""",
            (recurring_task_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_recurring_completion(completion_id):
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM recurring_completions WHERE id = ?", (completion_id,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------- 任务进度 ----------------

def list_progress(task_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM task_progress WHERE task_id = ? ORDER BY id DESC",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_progress(progress_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM task_progress WHERE id = ?", (progress_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_progress_by_record_id(record_id):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM task_progress WHERE record_id = ?", (record_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_progress(task_id, record_id, content, source="manual", agent_id="", run_id=""):
    now = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO task_progress
               (task_id, record_id, content, source, agent_id, run_id, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (task_id, record_id, content, source, agent_id, run_id, now, now),
        )
        conn.commit()
        return get_progress(cur.lastrowid)
    finally:
        conn.close()


def update_progress(progress_id, content):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE task_progress SET content = ?, updated_at = ? WHERE id = ?",
            (content, _now(), progress_id),
        )
        conn.commit()
        return get_progress(progress_id)
    finally:
        conn.close()


def delete_progress(progress_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM task_progress WHERE id = ?", (progress_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------------- 便签 ----------------

def list_log_days(month_prefix):
    """当月写过日记的日期（prefix=YYYY-MM-），返回 {日: 内容}。"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT date, content FROM daily_logs WHERE date LIKE ?",
            (month_prefix + "%",),
        ).fetchall()
        return {str(int(r[0][8:10])): r[1] for r in rows}
    finally:
        conn.close()


def get_log(date):
    """某天的日记（date=YYYY-MM-DD），无则返回 None。"""
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT date, content, updated_at FROM daily_logs WHERE date = ?",
            (date,),
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def save_log(date, content):
    """写入/更新某天日记（upsert）。"""
    now = _now()
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO daily_logs (date, content, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(date) DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at",
            (date, content, now),
        )
        conn.commit()
        return get_log(date)
    finally:
        conn.close()

def create_note(content):
    now = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO notes (content, created_at, updated_at) VALUES (?,?,?)",
            (content, now, now),
        )
        conn.commit()
        return get_note(cur.lastrowid)
    finally:
        conn.close()


def list_notes(limit=50):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_note(note_id):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def delete_note(note_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def update_note(note_id, content):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE notes SET content = ?, updated_at = ? WHERE id = ?",
            (content, _now(), note_id),
        )
        conn.commit()
        return get_note(note_id)
    finally:
        conn.close()


# ---------------- 快捷链接 ----------------

def create_link(name, url, icon="", sort_order=0):
    now = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO links (name, url, icon, sort_order, created_at) "
            "VALUES (?,?,?,?,?)",
            (name, url, icon, sort_order, now),
        )
        conn.commit()
        return get_link(cur.lastrowid)
    finally:
        conn.close()


def list_links():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM links ORDER BY sort_order, id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_link(link_id):
    conn = get_conn()
    try:
        r = conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def update_link(link_id, name=None, url=None, icon=None, sort_order=None):
    conn = get_conn()
    try:
        fields = {}
        if name is not None:
            fields["name"] = name
        if url is not None:
            fields["url"] = url
        if icon is not None:
            fields["icon"] = icon
        if sort_order is not None:
            fields["sort_order"] = sort_order
        if not fields:
            return get_link(link_id)
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE links SET {sets} WHERE id = ?",
                     (*fields.values(), link_id))
        conn.commit()
        return get_link(link_id)
    finally:
        conn.close()


def delete_link(link_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM links WHERE id = ?", (link_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------------- 纪念日 ----------------


def create_anniversary(name, month, day, calendar_type="solar"):
    now = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO anniversaries (name, month, day, calendar_type, created_at)"
            " VALUES (?,?,?,?,?)",
            (name, int(month), int(day), calendar_type, now),
        )
        conn.commit()
        return get_anniversary(cur.lastrowid)
    finally:
        conn.close()


def list_anniversaries():
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM anniversaries ORDER BY month, day, id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_anniversary(ann_id):
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM anniversaries WHERE id = ?", (ann_id,)
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def delete_anniversary(ann_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM anniversaries WHERE id = ?", (ann_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def update_anniversary(ann_id, name, month, day, calendar_type="solar"):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE anniversaries SET name = ?, month = ?, day = ?, calendar_type = ? WHERE id = ?",
            (name, int(month), int(day), calendar_type, ann_id),
        )
        conn.commit()
        return get_anniversary(ann_id)
    finally:
        conn.close()


def next_anniversary(month, day, calendar_type="solar", today=None):
    """计算下次纪念日的阳历日期与剩余天数（每年循环）。

    - solar：month/day 是公历月日；2/29 平年顺延 2/28。
    - lunar：month/day 是农历月日（闰月 month 为负，如 -6=闰六月）；
      换算成"今天之后最近一次"对应的阳历日期。
    返回 (date_str, days_left)。若今天就是纪念日返回 days_left=0。
    """
    from datetime import date as _date
    today = today or _date.today()

    if calendar_type == "lunar":
        from lunar_python import Lunar
        # 闰月约 2-3 年一次：查 8 年足够覆盖；查不到（异常数据）返回 None 而非假日期
        for y in range(today.year, today.year + 8):
            try:
                lunar = Lunar.fromYmd(y, month, day)
                cand = lunar.getSolar()
                d = _date(cand.getYear(), cand.getMonth(), cand.getDay())
            except Exception:
                continue
            if d >= today:
                return d.isoformat(), (d - today).days
        return None

    # solar：公历每年循环
    try:
        cand = _date(today.year, month, day)
    except ValueError:
        cand = _date(today.year, month, min(day, 28))
    if cand < today:
        try:
            cand = _date(today.year + 1, month, day)
        except ValueError:
            cand = _date(today.year + 1, month, min(day, 28))
    return cand.isoformat(), (cand - today).days


# ---------------- 设置 ----------------

def get_setting(key, default=None):
    conn = get_conn()
    try:
        r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else default
    finally:
        conn.close()


def set_setting(key, value):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_all_settings():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


# ---------------- 番茄钟计数 ----------------

def pomodoro_state():
    """今日番茄计数（跨天自动归零）。"""
    today = datetime.now().strftime("%Y-%m-%d")
    if get_setting("pomodoro_date", "") != today:
        return {"date": today, "count": 0}
    return {"date": today, "count": int(get_setting("pomodoro_count", "0") or 0)}


def pomodoro_complete():
    """完成一个番茄，计数 +1（跨天自动归零）。"""
    today = datetime.now().strftime("%Y-%m-%d")
    count = 0 if get_setting("pomodoro_date", "") != today else int(
        get_setting("pomodoro_count", "0") or 0
    )
    count += 1
    set_setting("pomodoro_date", today)
    set_setting("pomodoro_count", str(count))
    return {"date": today, "count": count}
