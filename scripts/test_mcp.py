"""Smoke-test the local MCP bridge against an isolated SQLite database."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "mcp_server.py"


def result_json(result):
    if getattr(result, "isError", False):
        raise AssertionError(f"MCP tool error: {result}")
    structured = getattr(result, "structuredContent", None)
    if structured:
        return structured
    for block in getattr(result, "content", []):
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)
    raise AssertionError(f"MCP result had no JSON content: {result}")


async def run() -> None:
    with tempfile.TemporaryDirectory(prefix="shyboard-mcp-") as temp_path:
        temp_root = Path(temp_path)
        temp_db = temp_root / "workbench.db"
        project_dir = temp_root / "project"
        project_dir.mkdir()
        env = os.environ.copy()
        env["SHYBOARD_HOME"] = str(ROOT.parent)
        env["WORKBENCH_DB"] = str(temp_db)
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                expected = {
                    "shyboard_link_project", "shyboard_get_project_context",
                    "shyboard_create_task", "shyboard_append_progress",
                    "shyboard_edit_progress", "shyboard_delete_progress",
                }
                assert expected <= names, names
                linked = result_json(await session.call_tool("shyboard_link_project", {
                    "project_path": str(project_dir), "project_id": "smoke-project", "name": "Smoke Project"
                }))
                assert Path(linked["manifest"]).is_file()
                task = result_json(await session.call_tool("shyboard_create_task", {
                    "project_path": str(project_dir), "title": "MCP smoke task", "tags": ["smoke", "agent"]
                }))
                task_id = task["id"]
                first = result_json(await session.call_tool("shyboard_append_progress", {
                    "task_id": task_id, "content": "started", "record_id": "smoke-record"
                }))
                retry = result_json(await session.call_tool("shyboard_append_progress", {
                    "task_id": task_id, "content": "ignored retry", "record_id": "smoke-record"
                }))
                assert first["id"] == retry["id"]
                edited = result_json(await session.call_tool("shyboard_edit_progress", {
                    "progress_id": first["id"], "content": "finished"
                }))
                assert edited["content"] == "finished"
                context = result_json(await session.call_tool("shyboard_get_project_context", {
                    "project_path": str(project_dir), "include_completed": True
                }))
                assert context["tasks"][0]["project_id"] == "smoke-project"
                assert context["tasks"][0]["progress"][0]["content"] == "finished"
                result_json(await session.call_tool("shyboard_delete_progress", {"progress_id": first["id"]}))
                print("MCP smoke test passed")


if __name__ == "__main__":
    asyncio.run(run())
