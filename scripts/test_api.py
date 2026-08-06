# -*- coding: utf-8 -*-
"""后端 API 自动化测试。跑在独立测试实例（17891 + 临时库），不污染用户数据。

用法: ./.venv/Scripts/python scripts/test_api.py
"""
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:17891"

PASS, FAIL = 0, 0
FAILURES = []


def req(method, path, data=None):
    url = BASE + path
    body = None
    headers = {"Content-Type": "application/json"}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        return e.code, (json.loads(raw) if raw else None)


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL  {name}  {detail}")


def section(title):
    print(f"\n=== {title} ===")


# ---------- 1. 健康检查 ----------
section("1. 健康检查")
s, d = req("GET", "/api/health")
check("health 返回 ok", s == 200 and d.get("service") == "workbench", str(d))

# ---------- 2. 任务 CRUD ----------
section("2. 任务创建（正常 + 边界）")
s, d = req("POST", "/api/tasks", {
    "title": "QA正常任务", "description": "描述文本", "priority": "high",
    "due_date": "2026-08-10", "tags": ["qa", "测试"], "source": "agent",
})
check("创建完整字段", s == 201 and d["title"] == "QA正常任务" and d["source"] == "agent"
      and d["tags"] == ["qa", "测试"] and d["priority"] == "high", str(d)[:120])
tid = d["id"] if d else None

s, d = req("POST", "/api/tasks", {"title": "QA最小字段"})
check("创建最小字段（默认值）", s == 201 and d["status"] == "todo"
      and d["priority"] == "medium" and d["source"] == "manual", str(d)[:120])

s, d = req("POST", "/api/tasks", {"title": "  "})
check("空 title 拒绝", s == 400 and "title" in str(d), str(d))

s, d = req("POST", "/api/tasks", {"title": "x", "status": "banana"})
check("非法 status 拒绝", s == 400, str(d))

s, d = req("POST", "/api/tasks", {"title": "x", "priority": "urgent"})
check("非法 priority 拒绝", s == 400, str(d))

s, d = req("POST", "/api/tasks", {"title": "x", "source": "robot"})
check("非法 source 拒绝", s == 400, str(d))

xss_title = '<script>alert(1)</script> "quotes" \'single\' & <b>粗</b> 😀 emoji'
s, d = req("POST", "/api/tasks", {"title": xss_title})
check("特殊字符/emoji 原样存储", s == 201 and d["title"] == xss_title, str(d)[:120])
xss_id = d["id"] if d else None

long_title = "长" * 500
s, d = req("POST", "/api/tasks", {"title": long_title})
check("超长 title(500字) 可创建", s == 201 and len(d["title"]) == 500, str(d)[:80])

sql_title = "'; DROP TABLE tasks; --"
s, d = req("POST", "/api/tasks", {"title": sql_title})
check("SQL 注入字符串安全存储", s == 201 and d["title"] == sql_title, str(d)[:80])

section("2b. 任务查询")
s, d = req("GET", "/api/tasks")
check("列表返回数组", s == 200 and isinstance(d, list) and len(d) >= 5, str(d)[:80])
s, d = req("GET", "/api/tasks?status=todo")
check("按状态过滤", s == 200 and all(t["status"] == "todo" for t in d))
s, d = req("GET", "/api/tasks?status=bad")
check("非法状态过滤拒绝", s == 400, str(d))
s, d = req("GET", f"/api/tasks/{tid}")
check("详情存在", s == 200 and d["id"] == tid, str(d)[:80])
s, d = req("GET", "/api/tasks/999999")
check("详情不存在 404", s == 404, str(d))

section("2c. 任务更新")
s, d = req("PATCH", f"/api/tasks/{tid}", {"title": "QA改名", "priority": "low"})
check("多字段更新", s == 200 and d["title"] == "QA改名" and d["priority"] == "low", str(d)[:100])
s, d = req("PATCH", f"/api/tasks/{tid}", {"status": "doing"})
check("状态 -> doing", s == 200 and d["status"] == "doing" and d["completed_at"] == "", str(d)[:100])
s, d = req("PATCH", f"/api/tasks/{tid}", {"status": "done"})
check("状态 -> done 打时间戳", s == 200 and d["status"] == "done" and d["completed_at"] != "", str(d)[:100])
s, d = req("PATCH", f"/api/tasks/{tid}", {"status": "todo"})
check("状态 -> todo 清时间戳", s == 200 and d["status"] == "todo" and d["completed_at"] == "", str(d)[:100])
s, d = req("PATCH", f"/api/tasks/{tid}", {"title": ""})
check("空 title 更新保留原标题", s == 200 and d["title"] == "QA改名", str(d)[:100])
s, d = req("PATCH", f"/api/tasks/{tid}", {"status": "nope"})
check("更新非法 status 拒绝", s == 400, str(d))
s, d = req("PATCH", "/api/tasks/999999", {"title": "x"})
check("更新不存在 404", s == 404, str(d))
s, d = req("PATCH", f"/api/tasks/{tid}", {})
check("空更新体（无字段）正常返回", s == 200, str(d)[:80])

section("2d. 任务删除")
s, d = req("DELETE", f"/api/tasks/{tid}")
check("删除存在", s == 200 and d.get("ok"), str(d))
s, d = req("GET", f"/api/tasks/{tid}")
check("删除后 404", s == 404, str(d))
s, d = req("DELETE", f"/api/tasks/{tid}")
check("删除不存在 404", s == 404, str(d))

# ---------- 3. 便签 ----------
section("3. 便签")
s, d = req("POST", "/api/notes", {"content": "QA便签内容"})
check("创建便签", s == 201 and d["content"] == "QA便签内容", str(d)[:80])
nid = d["id"] if d else None
s, d = req("POST", "/api/notes", {"content": ""})
check("空便签拒绝", s == 400, str(d))
s, d = req("POST", "/api/notes", {"content": "长" * 1000})
check("超长便签可创建", s == 201 and len(d["content"]) == 1000, str(d)[:80])
s, d = req("GET", "/api/notes")
check("便签列表", s == 200 and isinstance(d, list) and len(d) >= 2, str(d)[:80])
s, d = req("DELETE", f"/api/notes/{nid}")
check("删除便签", s == 200 and d.get("ok"), str(d))
s, d = req("DELETE", f"/api/notes/{nid}")
check("删除不存在便签 404", s == 404, str(d))

# ---------- 4. 快捷链接 ----------
section("4. 快捷链接")
s, d = req("POST", "/api/links", {"name": "QA站", "url": "example.com", "icon": "🔗"})
check("创建链接自动补 https", s == 201 and d["url"] == "https://example.com", str(d)[:100])
lid = d["id"] if d else None
s, d = req("POST", "/api/links", {"name": "", "url": "x.com"})
check("空 name 拒绝", s == 400, str(d))
s, d = req("POST", "/api/links", {"name": "x", "url": "ftp://weird"})
check("ftp:// 协议拒绝", s == 400, str(d))
s, d = req("POST", "/api/links", {"name": "x", "url": "javascript:alert(1)"})
check("javascript: 伪协议拒绝", s == 400, str(d))
s, d = req("POST", "/api/links", {"name": "x", "url": "sort_order", "sort_order": "abc"})
check("非数字 sort_order 不崩溃", s == 201, str(d))
s, d = req("GET", "/api/links")
check("链接列表", s == 200 and isinstance(d, list) and len(d) >= 1, str(d)[:80])
s, d = req("DELETE", f"/api/links/{lid}")
check("删除链接", s == 200 and d.get("ok"), str(d))
s, d = req("DELETE", f"/api/links/{lid}")
check("删除不存在链接 404", s == 404, str(d))

# ---------- 5. 天气 ----------
section("5. 天气")
s, d = req("GET", "/api/weather")
check("天气返回国内数据源", s == 200 and d.get("source") == "cn"
      and d.get("daily") and len(d["daily"]) >= 7, str(d)[:120])
check("天气含温度/湿度/风", s == 200 and d.get("temp") is not None
      and d.get("humidity") and d.get("wind"), str(d)[:120])
s, d = req("GET", "/api/weather/search?q=%E5%8D%97%E4%BA%AC")
check("城市搜索 南京", s == 200 and d and d[0]["n"] == "南京" and d[0]["c"], str(d)[:100])
s, d = req("GET", "/api/weather/search?q=")
check("空搜索返回空数组", s == 200 and d == [], str(d))
s, d = req("GET", "/api/weather/search?q=%E4%B8%8D%E5%AD%98%E5%9C%A8%E5%9F%8E%E5%B8%82xyz")
check("无结果返回空数组", s == 200 and d == [], str(d))

# ---------- 6. 设置 ----------
section("6. 设置")
s, d = req("GET", "/api/settings")
check("读取设置", s == 200 and d.get("city") == "上海", str(d)[:100])
s, d = req("PUT", "/api/settings", {"city_code": "101210101", "city": "杭州"})
check("切城市（代码）", s == 200 and d.get("city_code") == "101210101" and d.get("city") == "杭州", str(d)[:100])
s, d = req("GET", "/api/weather")
check("切城市后天气跟随", s == 200 and "杭州" in str(d.get("city", "")), str(d)[:100])
s, d = req("PUT", "/api/settings", {"city": "深圳"})
check("按城市名切（兼容）", s == 200 and d.get("city_code") == "101280601", str(d)[:100])
s, d = req("PUT", "/api/settings", {"city": "亚特兰蒂斯"})
check("未知城市 404", s == 404, str(d))
s, d = req("PUT", "/api/settings", {"city_code": "101020100", "city": "上海"})
check("切回上海", s == 200 and d.get("city") == "上海", str(d)[:100])

# ---------- 7. 统计一致性 ----------
section("7. 统计")
s, before = req("GET", "/api/stats")
check("统计接口正常", s == 200 and "total" in before, str(before)[:100])
s, t1 = req("POST", "/api/tasks", {"title": "QA统计1", "status": "done"})
s, t2 = req("POST", "/api/tasks", {"title": "QA统计2", "status": "doing"})
s, after = req("GET", "/api/stats")
check("统计 +2", s == 200 and after["total"] == before["total"] + 2
      and after["done"] == before["done"] + 1 and after["doing"] == before["doing"] + 1,
      f"before={before} after={after}")
req("DELETE", f"/api/tasks/{t1['id']}")
req("DELETE", f"/api/tasks/{t2['id']}")
s, back = req("GET", "/api/stats")
check("删除后统计还原", back["total"] == before["total"], f"{before} -> {back}")

# ---------- 8. 并发 ----------
section("8. 并发（30 线程同时创建）")
def create_one(i):
    return req("POST", "/api/tasks", {"title": f"QA并发{i}", "source": "agent"})

with ThreadPoolExecutor(max_workers=10) as ex:
    results = list(ex.map(create_one, range(30)))
ok = all(s == 201 for s, _ in results)
check("30 并发创建全部成功", ok, f"fail_count={sum(1 for s, _ in results if s != 201)}")
s, d = req("GET", "/api/tasks")
qa_conc = [t for t in d if t["title"].startswith("QA并发")]
check("并发任务全部落库", len(qa_conc) == 30, f"got={len(qa_conc)}")
for t in qa_conc:
    req("DELETE", f"/api/tasks/{t['id']}")
s, d = req("GET", "/api/tasks")
qa_conc = [t for t in d if t["title"].startswith("QA并发")]
check("并发任务清理干净", len(qa_conc) == 0, f"got={len(qa_conc)}")

# ---------- 9. 静态文件 ----------
section("9. 静态文件")
def req_raw(method, path):
    url = BASE + path
    r = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

for path, expect in [("/", 200), ("/style.css", 200), ("/app.js", 200),
                     ("/cities.json", 200), ("/nope.html", 404)]:
    s, body = req_raw("GET", path)
    check(f"GET {path} -> {expect}", s == expect, f"got {s}")
s, body = req_raw("GET", "/")
check("首页含 title", b"Workbench" in body, "body 无 Workbench")
s, body = req_raw("GET", "/cities.json")
check("cities.json 是合法 JSON", s == 200, f"got {s}")

# ---------- 清理测试数据 ----------
section("清理")
s, d = req("GET", "/api/tasks")
for t in [x for x in d if str(x["title"]).startswith("QA")]:
    req("DELETE", f"/api/tasks/{t['id']}")
s, d = req("GET", "/api/notes")
for n in [x for x in d if str(x["content"]).startswith("QA")]:
    req("DELETE", f"/api/notes/{n['id']}")
s, d = req("GET", "/api/links")
for l in [x for x in d if str(x["name"]).startswith("QA")]:
    req("DELETE", f"/api/links/{l['id']}")

print(f"\n{'='*50}")
print(f"RESULT: {PASS} passed, {FAIL} failed")
if FAILURES:
    print("FAILED:", FAILURES)
sys.exit(1 if FAIL else 0)
