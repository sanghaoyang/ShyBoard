"""ShyBoard MCP bridge.

This is a stdio MCP server: an MCP host starts this process and talks to it
over stdin/stdout.  It talks directly to ShyBoard's SQLite data layer, so it
does not need to know the UI, Flask port, or packaged EXE layout.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any


SOURCE_DIR = Path(__file__).resolve().parent
DEFAULT_APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SOURCE_DIR.parent
APP_DIR = Path(os.environ.get("SHYBOARD_HOME", DEFAULT_APP_DIR)).resolve()
os.environ.setdefault("WORKBENCH_DB", str(APP_DIR / "data" / "workbench.db"))
sys.path.insert(0, str(SOURCE_DIR))

import db  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402


MANIFEST_DIR = ".shyboard"
MANIFEST_NAME = "project.json"
MAX_MANIFEST_BYTES = 16 * 1024

mcp = FastMCP(
    "ShyBoard",
    instructions=(
        "ShyBoard is a local task and progress ledger. "
        "Use shyboard_get_project_context once at the start of a project session, "
        "then record meaningful milestones with shyboard_append_progress. "
        "Keep task descriptions as goals; use progress records for updates."
    ),
)


def _find_manifest(project_path: str = "") -> Path | None:
    candidate = Path(project_path).expanduser() if project_path else Path.cwd()
    if candidate.is_file():
        candidate = candidate.parent
    candidate = candidate.resolve()
    for directory in (candidate, *candidate.parents):
        path = directory / MANIFEST_DIR / MANIFEST_NAME
        if path.is_file():
            return path
    return None


def _read_manifest(path: Path) -> dict[str, str]:
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("项目清单过大，拒绝读取")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"项目清单无效：{exc}") from exc
    project_id = str(data.get("project_id", "")).strip()
    name = str(data.get("name", "")).strip()
    if not project_id or not name:
        raise ValueError("项目清单必须包含 project_id 和 name")
    return {"project_id": project_id, "name": name}


def _project(project_path: str = "", project_id: str = "", name: str = "") -> dict[str, str]:
    manifest = _find_manifest(project_path)
    values = _read_manifest(manifest) if manifest else {}
    resolved_id = str(project_id or values.get("project_id", "")).strip()
    resolved_name = str(name or values.get("name", "")).strip()
    root_path = str(manifest.parent.parent) if manifest else ""
    if not resolved_id:
        raise ValueError("未找到项目清单，请先调用 shyboard_link_project")
    if not resolved_name:
        resolved_name = resolved_id
    project = db.upsert_project(resolved_id, resolved_name, root_path)
    return {"project_id": project["project_id"], "name": project["name"], "root_path": project.get("root_path", "")}


def _task_view(task: dict[str, Any]) -> dict[str, Any]:
    result = dict(task)
    raw_tags = task.get("tags", "")
    if isinstance(raw_tags, list):
        result["tags"] = [str(tag).strip() for tag in raw_tags if str(tag).strip()]
    else:
        result["tags"] = [tag.strip() for tag in str(raw_tags).split(",") if tag.strip()]
    return result


@mcp.tool()
def shyboard_link_project(project_path: str, project_id: str = "", name: str = "") -> dict[str, Any]:
    """Create or update the tiny .shyboard/project.json identity file for a project."""
    directory = Path(project_path).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError("project_path 必须是存在的目录")
    resolved_id = str(project_id).strip() or uuid.uuid4().hex[:12]
    resolved_name = str(name).strip() or directory.name or resolved_id
    manifest_dir = directory / MANIFEST_DIR
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / MANIFEST_NAME
    payload = {"schema": 1, "project_id": resolved_id, "name": resolved_name}
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    project = db.upsert_project(resolved_id, resolved_name, str(directory))
    return {"project": project, "manifest": str(manifest_path)}


@mcp.tool()
def shyboard_get_project_context(
    project_path: str = "",
    project_id: str = "",
    include_completed: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    """Return compact project context: active tasks and their three latest progress records."""
    project = _project(project_path, project_id)
    limit = max(1, min(50, int(limit)))
    tasks = db.list_tasks(project_id=project["project_id"], limit=limit)
    if not include_completed:
        tasks = [task for task in tasks if task["status"] != "done"]
    for task in tasks:
        task["progress"] = db.list_progress(task["id"])[:3]
    return {"project": project, "tasks": [_task_view(task) for task in tasks]}


@mcp.tool()
def shyboard_list_tasks(
    project_path: str = "",
    project_id: str = "",
    status: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List tasks for the resolved project, optionally filtered by todo/doing/done."""
    project = _project(project_path, project_id)
    if status and status not in {"todo", "doing", "done"}:
        raise ValueError("status 必须是 todo、doing 或 done")
    rows = db.list_tasks(status=status or None, project_id=project["project_id"], limit=max(1, min(100, int(limit))))
    return [_task_view(row) for row in rows]


@mcp.tool()
def shyboard_create_task(
    title: str,
    project_path: str = "",
    project_id: str = "",
    description: str = "",
    status: str = "todo",
    priority: str = "medium",
    due_date: str = "",
    remind_days: int = 3,
    tags: list[str] | str = "",
    external_key: str = "",
) -> dict[str, Any]:
    """Create an agent-owned task and associate it with a project."""
    project = _project(project_path, project_id)
    if not title.strip():
        raise ValueError("title 不能为空")
    if status not in {"todo", "doing", "done"}:
        raise ValueError("status 必须是 todo、doing 或 done")
    if priority not in {"low", "medium", "high"}:
        raise ValueError("priority 必须是 low、medium 或 high")
    due = due_date.strip()
    if due:
        try:
            from datetime import datetime
            datetime.strptime(due, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("due_date 格式应为 YYYY-MM-DD") from exc
    try:
        reminder = int(remind_days)
    except (TypeError, ValueError) as exc:
        raise ValueError("remind_days 必须是 -1 到 365 之间的整数") from exc
    if not -1 <= reminder <= 365:
        raise ValueError("remind_days 必须是 -1 到 365 之间的整数")
    row = db.create_task(
        title=title.strip(),
        description=description.strip(),
        status=status,
        priority=priority,
        due_date=due,
        remind_days=reminder,
        tags=(",".join(str(tag).strip() for tag in tags if str(tag).strip())
              if isinstance(tags, list) else tags.strip()),
        source="agent",
        project_id=project["project_id"],
        external_key=external_key.strip(),
    )
    return _task_view(row)


@mcp.tool()
def shyboard_update_task(task_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    """Update task fields such as title, description, status, priority, due_date, remind_days, tags, or external_key."""
    allowed = {"title", "description", "status", "priority", "due_date", "remind_days", "tags", "project_id", "external_key"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"不支持的字段：{', '.join(sorted(unknown))}")
    if "status" in fields and fields["status"] not in {"todo", "doing", "done"}:
        raise ValueError("status 必须是 todo、doing 或 done")
    if "priority" in fields and fields["priority"] not in {"low", "medium", "high"}:
        raise ValueError("priority 必须是 low、medium 或 high")
    if "due_date" in fields and fields["due_date"]:
        try:
            from datetime import datetime
            datetime.strptime(str(fields["due_date"]), "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("due_date 格式应为 YYYY-MM-DD") from exc
    if "remind_days" in fields:
        try:
            fields["remind_days"] = int(fields["remind_days"])
        except (TypeError, ValueError) as exc:
            raise ValueError("remind_days 必须是 -1 到 365 之间的整数") from exc
        if not -1 <= fields["remind_days"] <= 365:
            raise ValueError("remind_days 必须是 -1 到 365 之间的整数")
    if "tags" in fields and isinstance(fields["tags"], list):
        fields = {**fields, "tags": ",".join(str(tag).strip() for tag in fields["tags"] if str(tag).strip())}
    row = db.update_task(task_id, **fields)
    if not row:
        raise ValueError("任务不存在")
    return _task_view(row)


@mcp.tool()
def shyboard_append_progress(
    task_id: int,
    content: str,
    agent_id: str = "",
    run_id: str = "",
    record_id: str = "",
) -> dict[str, Any]:
    """Append a progress record; record_id makes retries idempotent."""
    if not db.get_task(task_id):
        raise ValueError("任务不存在")
    text = content.strip()
    if not text:
        raise ValueError("进度内容不能为空")
    stable_id = record_id.strip() or uuid.uuid4().hex
    existing = db.get_progress_by_record_id(stable_id)
    if existing:
        if existing["task_id"] != task_id:
            raise ValueError("record_id 已被其它任务使用")
        return existing
    return db.create_progress(task_id, stable_id, text, "agent", agent_id.strip(), run_id.strip())


@mcp.tool()
def shyboard_edit_progress(progress_id: int, content: str) -> dict[str, Any]:
    """Edit one existing progress record."""
    if not content.strip():
        raise ValueError("进度内容不能为空")
    row = db.update_progress(progress_id, content.strip())
    if not row:
        raise ValueError("进度记录不存在")
    return row


@mcp.tool()
def shyboard_delete_progress(progress_id: int) -> dict[str, bool]:
    """Delete one progress record."""
    if not db.get_progress(progress_id):
        raise ValueError("进度记录不存在")
    db.delete_progress(progress_id)
    return {"ok": True}


@mcp.tool()
def shyboard_set_task_status(
    task_id: int,
    status: str,
    progress_note: str = "",
    agent_id: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    """Set a task status and optionally append a progress note in the same tool call."""
    if status not in {"todo", "doing", "done"}:
        raise ValueError("status 必须是 todo、doing 或 done")
    task = db.update_task(task_id, status=status)
    if not task:
        raise ValueError("任务不存在")
    result: dict[str, Any] = {"task": _task_view(task)}
    if progress_note.strip():
        result["progress"] = shyboard_append_progress(task_id, progress_note, agent_id, run_id)
    return result


def main() -> None:
    db.init_db()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
