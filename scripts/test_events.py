# -*- coding: utf-8 -*-
"""验证任务事件日志功能：创建/状态流转/字段更新 都要记录事件。"""
import json
import urllib.request

BASE = "http://127.0.0.1:17891"


def req(method, path, data=None):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    r = urllib.request.Request(BASE + path, data=body,
                               headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(r, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


# 1. 创建任务 → 应有 create 事件
s, t = req("POST", "/api/tasks", {"title": "事件日志测试", "priority": "high"})
tid = t["id"]
print(f"创建任务 id={tid}: status={s}")
s, d = req("GET", f"/api/tasks/{tid}")
ev = d["events"]
print("事件数:", len(ev), "| 类型:", [e["event_type"] for e in ev])
assert ev[0]["event_type"] == "create", "无 create 事件"
assert ev[0]["new_status"] == "todo"

# 2. 状态流转 todo→doing→done → 3 条 status 事件
req("PATCH", f"/api/tasks/{tid}", {"status": "doing"})
req("PATCH", f"/api/tasks/{tid}", {"status": "done"})
s, d = req("GET", f"/api/tasks/{tid}")
ev = d["events"]
print("流转后事件:", [(e["event_type"], e["old_status"], e["new_status"]) for e in ev])
status_events = [e for e in ev if e["event_type"] == "status"]
assert len(status_events) == 2, f"status 事件数不对: {len(status_events)}"
assert status_events[0]["new_status"] == "doing"
assert status_events[1]["old_status"] == "doing" and status_events[1]["new_status"] == "done"
# done 事件时间应等于 completed_at
assert status_events[1]["created_at"] == d["completed_at"], "完成事件时间与 completed_at 不一致"

# 3. 字段更新（不改状态）→ update 事件（note 是 JSON 详情）
req("PATCH", f"/api/tasks/{tid}", {"priority": "low", "title": "事件日志测试改"})
s, d = req("GET", f"/api/tasks/{tid}")
ev = d["events"]
update_events = [e for e in ev if e["event_type"] == "update"]
print("update 事件 note:", [e["note"] for e in update_events])
assert len(update_events) == 1, "应有 1 条 update 事件"
import json as _json
note = _json.loads(update_events[0]["note"])
assert "priority" in note and "title" in note, "note 应含 priority/title 详情"
assert note["priority"] == ["high", "low"], f"priority 旧新值不对: {note['priority']}"
assert note["title"] == ["事件日志测试", "事件日志测试改"], f"title 旧新值不对: {note['title']}"

# 4. 恢复到 todo 再 done → 时间线完整
req("PATCH", f"/api/tasks/{tid}", {"status": "todo"})
req("PATCH", f"/api/tasks/{tid}", {"status": "done"})
s, d = req("GET", f"/api/tasks/{tid}")
total = len(d["events"])
print("最终事件总数:", total)
assert total == 1 + 2 + 1 + 2, f"事件总数不对: {total}"

# 5. 列表接口不带 events（保持轻量）
s, tasks = req("GET", "/api/tasks")
assert "events" not in tasks[0], "列表接口不应带 events"

# 6. 删除任务 → 事件级联删除
req("DELETE", f"/api/tasks/{tid}")
import os
import sqlite3
conn = sqlite3.connect(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "qa_test.db"))
n = conn.execute("SELECT COUNT(*) FROM task_events WHERE task_id=?", (tid,)).fetchone()[0]
conn.close()
print("删除后残留事件:", n)
assert n == 0, "删除任务后事件未级联清理"

print("\n全部事件日志用例 PASS")
