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
    "autostart": "0",
    "confirm_delete_task": "1",
    "confirm_delete_link": "1",
    "confirm_delete_note": "1",
}


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
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
                tags         TEXT DEFAULT '',
                source       TEXT DEFAULT 'manual' CHECK(source IN ('manual','agent')),
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
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )
        conn.commit()
    finally:
        conn.close()


# ---------------- 任务 ----------------

def create_task(title, description="", status="todo", priority="medium",
                due_date="", tags="", source="manual"):
    now = _now()
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO tasks (title, description, status, priority, due_date,
                                  tags, source, created_at, updated_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (title, description, status, priority, due_date, tags, source,
             now, now, now if status == "done" else ""),
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


def list_tasks(status=None, include_done=True, limit=200):
    conn = get_conn()
    try:
        sql = "SELECT * FROM tasks"
        args = []
        if status:
            sql += " WHERE status = ?"
            args.append(status)
        elif not include_done:
            sql += " WHERE status != 'done'"
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
    allowed = {"title", "description", "status", "priority", "due_date", "tags"}
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


# ---------------- 便签 ----------------

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
