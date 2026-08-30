# -*- coding: utf-8 -*-
"""后端 API 自动化测试。跑在独立测试实例（17891 + 临时库），不污染用户数据。

用法: ./.venv/Scripts/python scripts/test_api.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# 让测试脚本能 import 项目根目录的 db（闰月倒计时边界测试用）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402

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
s, d = req("GET", "/api/integration")
check("AI 接入信息不暴露本机路径", s == 200 and d.get("platform") == "windows"
      and d.get("rest_available") is True and "api_base" not in d
      and "mcp_available" in d and "port_file" not in d
      and "mcp_launcher" not in d, str(d))

# ---------- 2. 任务 CRUD ----------
section("2. 任务创建（正常 + 边界）")
s, d = req("POST", "/api/tasks", {
    "title": "QA正常任务", "description": "描述文本", "priority": "high",
    "due_date": "2026-08-10", "remind_days": 7, "tags": ["qa", "测试"], "source": "agent",
})
check("创建完整字段", s == 201 and d["title"] == "QA正常任务" and d["source"] == "agent"
      and d["tags"] == ["qa", "测试"] and d["priority"] == "high"
      and d["remind_days"] == 7, str(d)[:120])
tid = d["id"] if d else None

s, d = req("POST", "/api/tasks", {
    "title": "QA标签分隔", "tags": "工作， 本周、重要；复盘\n稍后",
})
check("标签兼容中文标点、分号和换行", s == 201 and d["tags"] == ["工作", "本周", "重要", "复盘", "稍后"], str(d)[:120])

s, d = req("POST", "/api/tasks", {"title": "QA最小字段"})
check("创建最小字段（默认值）", s == 201 and d["status"] == "todo"
      and d["priority"] == "medium" and d["source"] == "manual"
      and d["remind_days"] == 3, str(d)[:120])

s, d = req("POST", "/api/tasks", {"title": "  "})
check("空 title 拒绝", s == 400 and "title" in str(d), str(d))

s, d = req("POST", "/api/tasks", {"title": "x", "status": "banana"})
check("非法 status 拒绝", s == 400, str(d))

s, d = req("POST", "/api/tasks", {"title": "x", "priority": "urgent"})
check("非法 priority 拒绝", s == 400, str(d))

s, d = req("POST", "/api/tasks", {"title": "x", "source": "robot"})
check("非法 source 拒绝", s == 400, str(d))

s, d = req("POST", "/api/tasks", {"title": "x", "remind_days": 366})
check("非法提醒天数拒绝", s == 400 and "remind_days" in str(d), str(d))

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
s, d = req("PATCH", f"/api/tasks/{tid}", {"title": "QA改名", "priority": "low", "remind_days": 14})
check("多字段更新", s == 200 and d["title"] == "QA改名" and d["priority"] == "low"
      and d["remind_days"] == 14, str(d)[:100])
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
s, d = req("PATCH", f"/api/tasks/{tid}", {"remind_days": -2})
check("更新非法提醒天数拒绝", s == 400, str(d))
s, d = req("PATCH", "/api/tasks/999999", {"title": "x"})
check("更新不存在 404", s == 404, str(d))
s, d = req("PATCH", f"/api/tasks/{tid}", {})
check("空更新体（无字段）正常返回", s == 200, str(d)[:80])

section("2d. 任务进度记录")
s, d = req("POST", f"/api/tasks/{tid}/progress", {
    "content": "完成第一阶段", "source": "agent",
    "agent_id": "qa-agent", "run_id": "qa-run", "record_id": "qa-progress-1",
})
check("创建进度记录", s == 201 and d.get("content") == "完成第一阶段"
      and d.get("source") == "agent" and d.get("agent_id") == "qa-agent", str(d)[:120])
pid = d["id"] if d else None
s, d = req("POST", f"/api/tasks/{tid}/progress", {
    "content": "重复请求不重复写入", "source": "agent", "record_id": "qa-progress-1",
})
check("record_id 幂等", s == 200 and d.get("id") == pid and d.get("content") == "完成第一阶段", str(d)[:120])
s, d = req("GET", f"/api/tasks/{tid}/progress")
check("读取任务进度", s == 200 and len(d) == 1 and d[0].get("id") == pid, str(d)[:120])
s, d = req("PATCH", f"/api/progress/{pid}", {"content": "完成第二阶段"})
check("编辑进度记录", s == 200 and d.get("content") == "完成第二阶段", str(d)[:120])
s, d = req("PATCH", f"/api/progress/{pid}", {"content": ""})
check("空进度拒绝", s == 400, str(d))
s, d = req("DELETE", f"/api/progress/{pid}")
check("删除进度记录", s == 200 and d.get("ok"), str(d))
s, d = req("DELETE", f"/api/progress/{pid}")
check("重复删除进度返回 404", s == 404, str(d))

section("2e. 任务删除")
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
s, d = req("PATCH", f"/api/notes/{nid}", {"content": "QA便签已编辑"})
check("编辑便签", s == 200 and d.get("content") == "QA便签已编辑", str(d)[:80])
s, d = req("PATCH", f"/api/notes/{nid}", {"content": ""})
check("编辑便签空内容 400", s == 400, str(d))
s, d = req("PATCH", "/api/notes/999999", {"content": "x"})
check("编辑不存在便签 404", s == 404, str(d))
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
s, d = req("PATCH", f"/api/links/{lid}", {"name": "QA站改名", "icon": "🖥️"})
check("编辑链接", s == 200 and d.get("name") == "QA站改名" and d.get("icon") == "🖥️", str(d)[:80])
s, d = req("PATCH", "/api/links/999999", {"name": "x"})
check("编辑不存在链接 404", s == 404, str(d))
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
check("读取设置", s == 200 and d.get("city") == "上海" and d.get("font_size") == "normal", str(d)[:100])
s, d = req("PUT", "/api/settings", {"font_size": "large"})
check("切换大号字体", s == 200 and d.get("font_size") == "large", str(d)[:100])
s, d = req("PUT", "/api/settings", {"font_size": "normal"})
check("恢复正常字体", s == 200 and d.get("font_size") == "normal", str(d)[:100])
s, d = req("PUT", "/api/settings", {"pomodoro_focus_minutes": 45, "pomodoro_break_minutes": 10})
check("番茄钟时长进入可备份设置", s == 200
      and d.get("pomodoro_focus_minutes") == "45"
      and d.get("pomodoro_break_minutes") == "10", str(d)[:120])
req("PUT", "/api/settings", {"pomodoro_focus_minutes": 25, "pomodoro_break_minutes": 5})
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
s, d = req("PUT", "/api/settings", {"confirm_delete_ann": False})
check("关闭纪念日删除确认", s == 200 and d.get("confirm_delete_ann") == "0", str(d)[:100])
s, d = req("GET", "/api/settings")
check("读回纪念日确认关闭", s == 200 and d.get("confirm_delete_ann") == "0", str(d)[:100])
s, d = req("PUT", "/api/settings", {"confirm_delete_ann": True})
check("恢复纪念日删除确认", s == 200 and d.get("confirm_delete_ann") == "1", str(d)[:100])

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

for path, expect in [("/", 200), ("/style.css", 200), ("/premium.css", 200),
                     ("/app.js", 200), ("/redesign.js", 200),
                     ("/cities.json", 200), ("/nope.html", 404)]:
    s, body = req_raw("GET", path)
    check(f"GET {path} -> {expect}", s == expect, f"got {s}")
s, body = req_raw("GET", "/")
check("首页含 title", b"ShyBoard" in body, "body 无 ShyBoard")
page_text = body.decode("utf-8")
check("AI 接入明确二选一", "选择下面任意一种方式即可" in page_text
      and "agent-mcp-install" in page_text, page_text[:120])
check("截止提醒替代逾期入口", "id=\"deadline-reminder\"" in page_text
      and "id=\"nav-overdue\"" not in page_text, page_text[:120])
check("设置页字体档位替代返回按钮", 'id="font-size-picker"' in page_text
      and 'data-font-size="normal"' in page_text and 'data-font-size="large"' in page_text
      and 'id="settings-done"' not in page_text, page_text[:120])
check("番茄钟具备完整控制", all(x in page_text for x in [
      'id="focus-page-start"', 'id="focus-page-pause"', 'id="focus-page-stop"',
      'id="focus-page-break"', 'id="focus-duration"', 'id="break-duration"']), page_text[:120])
s, body = req_raw("GET", "/app.js")
script_text = body.decode("utf-8")
check("通用提示词自动发现端口", "Get-CimInstance Win32_Process" in script_text
      and "info.port_file" not in script_text and "info.mcp_launcher" not in script_text,
      script_text[:120])
check("便签列表不再显示编号", "note-index" not in script_text, script_text[:120])
check("便签时间精确到分钟", "created_at.slice(5, 16)" in script_text, script_text[:120])
check("番茄钟时长会保存", "POMO_FOCUS_KEY" in script_text
      and "pomoDurationChanged" in script_text and "pomoTogglePause" in script_text, script_text[:120])
check("字体档位会应用并保存", "applyFontSize" in script_text
      and 'JSON.stringify({ font_size: fontSize })' in script_text, script_text[:120])
check("日历记录使用后端主通道", "calendarApiRecord(d.logs, dateStr)" in script_text
      and "calendarApiRecord(cal.logs, _dayModalDate)" in script_text
      and 'api("/api/log"' in script_text, script_text[:120])
check("设置页提供完整数据迁移", "ensureDataTransferCard" in script_text
      and 'api("/api/backup")' in script_text
      and 'api("/api/backup/import"' in script_text, script_text[:120])
s, body = req_raw("GET", "/redesign.js")
redesign_text = body.decode("utf-8")
check("任务标签与日期分行", 'class="task-tags"' in redesign_text
      and 'class="task-facts"' in redesign_text and '"截止 · "' in redesign_text, redesign_text[:120])
s, body = req_raw("GET", "/premium.css")
premium_text = body.decode("utf-8")
check("雾蓝主题包含暖色层次", "--secondary: #C98A58" in premium_text
      and 'body:not([data-theme="dark"]) .focus-orbit' in premium_text, premium_text[:120])
check("主题色卡保持单色", '.theme-opt .th-swatch i:last-child { display: none; }' in premium_text
      and '.theme-opt[data-theme="dark"] .th-swatch i:first-child { background: #1B1917 !important; }' in premium_text, premium_text[-240:])
check("浅色主题辅助色各不相同", all(color in premium_text for color in [
      "--secondary: #71879A", "--secondary: #668D89", "--secondary: #9388A6",
      "--secondary: #B1788C", "--secondary: #93748D"]), premium_text[:120])
check("大号字体统一增大", '--font-bump: 1.5px' in premium_text
      and 'font-size: calc(' in premium_text, premium_text[:120])
check("日期选择入口清晰", '::-webkit-calendar-picker-indicator' in premium_text
      and 'border-color: rgba(var(--ink-rgb),.2)' in premium_text, premium_text[:120])
check("日历记录保留换行", ".cal-record" in premium_text
      and "white-space: pre-line" in premium_text
      and 'esc(record.replace(/\\s+/g, " "))' not in script_text, premium_text[:120])
s, body = req_raw("GET", "/cities.json")
check("cities.json 是合法 JSON", s == 200, f"got {s}")


# ---------- 10. 纪念日 + 日历 ----------
section("10. 纪念日与日历")
s, d = req("GET", "/api/anniversaries")
check("纪念日空列表", s == 200 and d == [], str(d)[:100])
s, d = req("POST", "/api/anniversaries", {"name": "QA测试生日", "month": 11, "day": 6})
check("新增纪念日", s == 201 and d.get("name") == "QA测试生日", str(d)[:100])
ann_id = d.get("id")
s, d = req("POST", "/api/anniversaries", {"name": "QA非法", "month": 2, "day": 30})
check("非法日期 400", s == 400, str(d)[:100])
s, d = req("POST", "/api/anniversaries", {"name": "", "month": 1, "day": 1})
check("空名称 400", s == 400, str(d)[:100])
s, d = req("GET", "/api/anniversaries")
qa_ann = [a for a in d if a["id"] == ann_id]
check("纪念日含倒计时字段",
      s == 200 and qa_ann and "days_left" in qa_ann[0] and qa_ann[0]["month"] == 11,
      str(d)[:150])
s, d = req("DELETE", f"/api/anniversaries/{ann_id}")
check("删除纪念日", s == 200, str(d)[:100])
s, d = req("DELETE", f"/api/anniversaries/{ann_id}")
check("删除不存在纪念日 404", s == 404, str(d)[:100])
# 日历接口：阳历纪念日 + 农历纪念日（中秋农历8/15 → 2026-09-25）+ 农历信息
s, ann = req("POST", "/api/anniversaries", {"name": "QA日历纪念", "month": 11, "day": 6})
s, ann_lunar = req("POST", "/api/anniversaries", {"name": "QA中秋", "month": 8, "day": 15, "calendar_type": "lunar"})
import datetime as _dt
_cur = _dt.date.today()
_nov = "2026-11" if _cur.year <= 2026 else f"{_cur.year}-11"
s, d = req("GET", f"/api/calendar?month={_nov}")
check("日历接口正常（含农历）", s == 200 and "anniversaries" in d and "lunar" in d, str(d)[:100])
_day6_anns = [x for x in d.get("anniversaries", {}).get("6", []) if x.get("name") == "QA日历纪念"]
check("阳历纪念日归位 11/6", len(_day6_anns) == 1, str(d.get("anniversaries"))[:150])
s, d = req("GET", "/api/calendar?month=2026-09")
_day25_anns = [x for x in d.get("anniversaries", {}).get("25", []) if x.get("name") == "QA中秋"]
check("农历纪念日归位 9/25（中秋）", len(_day25_anns) == 1, str(d.get("anniversaries"))[:150])
s, d = req("GET", "/api/calendar?month=2026-08")
check("日历含农历信息 8/11=六月廿九",
      d.get("lunar", {}).get("11", {}).get("month") == 6 and d.get("lunar", {}).get("11", {}).get("day") == 29,
      str(d.get("lunar", {}).get("11"))[:100])
s, d = req("GET", "/api/calendar?month=2026-13")
check("非法月份 400", s == 400, str(d)[:100])
# 农历纪念日倒计时（中秋 2026-09-25）
s, d = req("GET", "/api/anniversaries")
qa_mid = [a for a in d if a.get("name") == "QA中秋"]
check("农历纪念日含 calendar_type",
      s == 200 and qa_mid and qa_mid[0].get("calendar_type") == "lunar" and qa_mid[0]["next_date"] == "2026-09-25",
      str(qa_mid)[:150])
# 非法日历类型
s, d = req("POST", "/api/anniversaries", {"name": "QA火星", "month": 1, "day": 1, "calendar_type": "mars"})
check("非法日历类型 400", s == 400, str(d)[:100])
# 编辑纪念日（PATCH）
s, d = req("PATCH", f"/api/anniversaries/{ann['id']}", {"name": "QA生日改名", "month": 12, "day": 25, "calendar_type": "solar"})
check("编辑纪念日", s == 200 and d.get("name") == "QA生日改名" and d.get("month") == 12, str(d)[:100])
s, d = req("PATCH", f"/api/anniversaries/{ann['id']}", {"name": "", "month": 1, "day": 1})
check("编辑纪念日空名称 400", s == 400, str(d)[:100])
s, d = req("PATCH", "/api/anniversaries/999999", {"name": "x", "month": 1, "day": 1})
check("编辑不存在纪念日 404", s == 404, str(d)[:100])
# 编辑为农历闰月（month 负值）
s, d = req("PATCH", f"/api/anniversaries/{ann['id']}", {"name": "QA闰月纪念", "month": -6, "day": 15, "calendar_type": "lunar"})
check("编辑为农历闰月", s == 200 and d.get("month") == -6 and d.get("calendar_type") == "lunar", str(d)[:100])
req("DELETE", f"/api/anniversaries/{ann['id']}")
req("DELETE", f"/api/anniversaries/{ann_lunar['id']}")

# ---------- 11. 日记（日历每天记录） + 日历待办 DDL 标注 ----------
section("11. 日记与日历待办标注")
s, d = req("GET", "/api/log?date=2026-08-13")
check("空日记返回空内容", s == 200 and d.get("content") == "", str(d)[:100])
s, d = req("PUT", "/api/log", {"date": "2026-08-13", "content": "QA今天测试记录"})
check("保存日记", s == 200 and d.get("content") == "QA今天测试记录", str(d)[:100])
s, d = req("GET", "/api/log?date=2026-08-13")
check("读回日记", s == 200 and d.get("content") == "QA今天测试记录", str(d)[:100])
s, d = req("PUT", "/api/log", {"date": "2026-08-13", "content": "QA覆盖记录"})
check("覆盖日记", s == 200 and d.get("content") == "QA覆盖记录", str(d)[:100])
s, d = req("GET", "/api/calendar?month=2026-08")
check("日历 logs 含 13 日内容", s == 200 and d.get("logs", {}).get("13") == "QA覆盖记录", str(d.get("logs"))[:100])
s, d = req("PUT", "/api/log", {"date": "2026-08-13", "content": ""})
check("清空日记", s == 200 and d.get("content") == "", str(d)[:100])
s, d = req("PUT", "/api/log", {"date": "2026-8-1", "content": "x"})
check("非法日期格式 400", s == 400, str(d)[:100])
s, d = req("GET", "/api/log?date=2026-08")
check("非法 date 参数 400", s == 400, str(d)[:100])
# 日历待办 DDL 标注：todo 带 due_date 显示，done/doing 不显示
s, td = req("POST", "/api/tasks", {"title": "QA日历DDL任务", "due_date": "2026-08-15"})
check("创建带 DDL 的待办任务", s == 201, str(td)[:100])
s, td2 = req("POST", "/api/tasks", {"title": "QA日历进行中", "status": "doing", "due_date": "2026-08-15"})
check("创建进行中任务", s == 201, str(td2)[:100])
s, d = req("GET", "/api/calendar?month=2026-08")
q15 = d.get("todo_tasks", {}).get("15", [])
check("日历显示待办 DDL（含标题）",
      s == 200 and any(t["title"] == "QA日历DDL任务" for t in q15), str(q15)[:120])
check("日历不含进行中任务", not any(t["title"] == "QA日历进行中" for t in q15), str(q15)[:120])
s, d = req("GET", "/api/calendar?month=2026-09")
check("其他月无该 DDL", s == 200 and "15" not in d.get("todo_tasks", {}), str(d.get("todo_tasks"))[:80])
# 节日/节气（动态计算：清明/中秋/春节随年份变，农历节日要换算公历；国庆 10/1 公历固定）
import datetime as _dt
from lunar_python import Solar as _Solar, Lunar as _Lunar
_cur_year = _dt.date.today().year
_qm = None
for _d in range(1, 31):
    if _Solar.fromYmd(_cur_year, 4, _d).getLunar().getJieQi() == "清明":
        _qm = _d
        break
s, d = req("GET", f"/api/calendar?month={_cur_year}-04")
check("清明节气标识（动态）", s == 200 and _qm and "清明" in d.get("holidays", {}).get(str(_qm), []), f"qm={_qm} {str(d.get('holidays', {}).get(str(_qm)))[:60]}")
_mid = _Lunar.fromYmd(_cur_year, 8, 15).getSolar()
s, d = req("GET", f"/api/calendar?month={_mid.getYear()}-{_mid.getMonth():02d}")
check("中秋节标识（动态农历换算）", s == 200 and "中秋节" in d.get("holidays", {}).get(str(_mid.getDay()), []), f"mid={_mid.toYmd()} {str(d.get('holidays', {}).get(str(_mid.getDay())))[:60]}")
_cn = _Lunar.fromYmd(_cur_year, 1, 1).getSolar()
s, d = req("GET", f"/api/calendar?month={_cn.getYear()}-{_cn.getMonth():02d}")
check("春节标识（动态农历换算）", s == 200 and "春节" in d.get("holidays", {}).get(str(_cn.getDay()), []), f"cn={_cn.toYmd()} {str(d.get('holidays', {}).get(str(_cn.getDay())))[:60]}")
s, d = req("GET", f"/api/calendar?month={_cur_year}-10")
check("国庆节标识（公历固定）", s == 200 and "国庆节" in d.get("holidays", {}).get("1", []), str(d.get("holidays", {}).get("1"))[:80])
check("普通日无节日标识", s == 200 and "10" not in d.get("holidays", {}), str(d.get("holidays", {}).get("10"))[:80])

# ---------- 11b. 定时任务、提醒与完成历史 ----------
section("11b. 定时任务")
s, recurring = req("POST", "/api/recurring-tasks", {
    "title": "QA每月复盘", "description": "整理当月进展",
    "schedule_type": "monthly", "schedule_value": 15, "remind_days": 3,
})
check("创建月度定时任务", s == 201 and recurring.get("schedule_label") == "每月 15 日"
      and recurring.get("remind_days") == 3 and recurring.get("enabled") is True,
      str(recurring)[:150])
recurring_id = recurring.get("id") if recurring else None
s, d = req("GET", "/api/recurring-tasks")
check("读取定时任务列表", s == 200 and any(x.get("id") == recurring_id for x in d), str(d)[:150])
s, d = req("GET", "/api/calendar?month=2026-09")
cal_recurring = d.get("recurring_tasks", {}).get("15", [])
check("定时任务显示在日历", s == 200 and any(x.get("id") == recurring_id and not x.get("completed") for x in cal_recurring), str(cal_recurring)[:150])
check("日历星期从周日正确对齐", d.get("first_weekday") == 2, str(d.get("first_weekday")))
s, d = req("POST", f"/api/recurring-tasks/{recurring_id}/complete", {"scheduled_date": "2026-09-15"})
check("完成本次写入历史", s == 201 and d.get("completion", {}).get("scheduled_date") == "2026-09-15"
      and len(d.get("completions", [])) == 1, str(d)[:180])
completion_id = d.get("completion", {}).get("id")
s, d = req("POST", f"/api/recurring-tasks/{recurring_id}/complete", {"scheduled_date": "2026-09-15"})
check("重复完成保持幂等", s == 200 and d.get("already_completed") is True
      and len(d.get("completions", [])) == 1, str(d)[:180])
s, d = req("GET", "/api/calendar?month=2026-09")
cal_recurring = d.get("recurring_tasks", {}).get("15", [])
check("日历同步完成状态", s == 200 and any(x.get("id") == recurring_id and x.get("completed") for x in cal_recurring), str(cal_recurring)[:150])
s, d = req("PATCH", f"/api/recurring-tasks/{recurring_id}", {"enabled": False, "remind_days": -1})
check("暂停定时任务并关闭提醒", s == 200 and d.get("enabled") is False and d.get("remind_days") == -1, str(d)[:150])
s, d = req("GET", "/api/calendar?month=2026-09")
check("暂停后不再投射到日历", s == 200 and not any(x.get("id") == recurring_id for x in d.get("recurring_tasks", {}).get("15", [])), str(d.get("recurring_tasks"))[:150])
s, d = req("DELETE", f"/api/recurring-completions/{completion_id}")
check("撤销完成历史", s == 200 and d.get("ok"), str(d))
s, d = req("GET", f"/api/recurring-tasks/{recurring_id}")
check("撤销后历史为空", s == 200 and d.get("completions") == [], str(d)[:150])
s, d = req("POST", "/api/recurring-tasks", {"title": "QA坏规则", "schedule_type": "weekly", "schedule_value": 8})
check("非法星期拒绝", s == 400, str(d))
s, d = req("DELETE", f"/api/recurring-tasks/{recurring_id}")
check("删除定时任务", s == 200 and d.get("ok"), str(d))
s, d = req("GET", f"/api/recurring-tasks/{recurring_id}")
check("删除后返回 404", s == 404, str(d))

# ---------- 11c. 完整备份与恢复 ----------
section("11c. 完整备份与恢复")
s, backup_task = req("POST", "/api/tasks", {"title": "QA备份原始任务", "status": "doing"})
s2, backup_note = req("POST", "/api/notes", {"content": "QA备份便签"})
req("PUT", "/api/log", {"date": "2026-08-20", "content": "第一行\n第二行"})
check("准备备份数据", s == 201 and s2 == 201, f"task={s}, note={s2}")
s, backup = req("GET", "/api/backup")
check("导出包含全部数据表", s == 200 and backup.get("format") == "shyboard-backup"
      and backup.get("schema_version") == 1
      and all(name in backup.get("data", {}) for name in db.BACKUP_TABLES), str(backup)[:180])
req("PATCH", f"/api/tasks/{backup_task['id']}", {"title": "QA被修改"})
req("DELETE", f"/api/notes/{backup_note['id']}")
req("PUT", "/api/log", {"date": "2026-08-20", "content": "已覆盖"})
s, restored = req("POST", "/api/backup/import", backup)
check("完整备份可事务恢复", s == 200 and restored.get("ok")
      and restored.get("safety_backup", "").startswith("ShyBoard-before-import-"), str(restored)[:180])
s, restored_task = req("GET", f"/api/tasks/{backup_task['id']}")
s2, restored_notes = req("GET", "/api/notes")
s3, restored_log = req("GET", "/api/log?date=2026-08-20")
check("任务状态和历史恢复", s == 200 and restored_task.get("title") == "QA备份原始任务"
      and restored_task.get("status") == "doing"
      and len(restored_task.get("events", [])) >= 1, str(restored_task)[:120])
check("便签与多行日历记录恢复", s2 == 200
      and any(n.get("content") == "QA备份便签" for n in restored_notes)
      and s3 == 200 and restored_log.get("content") == "第一行\n第二行", str(restored_log))
s, invalid_backup = req("POST", "/api/backup/import", {"format": "other", "schema_version": 1, "data": {}})
check("拒绝非 ShyBoard 备份", s == 400, str(invalid_backup))
req("DELETE", f"/api/tasks/{backup_task['id']}")
req("DELETE", f"/api/notes/{backup_note['id']}")
req("PUT", "/api/log", {"date": "2026-08-20", "content": ""})

# ---------- 12. code-review v2.0.0 补盲用例（PATCH links 校验/due_date/闰月/theme/年份/日志日期） ----------
section("12. code-review 补盲")
# 12.1 PATCH /api/links URL 协议校验（🔴#1）
s, d = req("POST", "/api/links", {"name": "QA链接", "url": "https://example.com"})
lid2 = d.get("id")
s, d = req("PATCH", f"/api/links/{lid2}", {"url": "javascript:alert(1)"})
check("PATCH 拒绝 javascript: 协议", s == 400, str(d)[:100])
s, d = req("PATCH", f"/api/links/{lid2}", {"url": "example.com/abc"})
check("PATCH 无协议自动补 https", s == 200 and d.get("url") == "https://example.com/abc", str(d)[:100])
# 12.2 非法 due_date（🔴#2）
s, d = req("POST", "/api/tasks", {"title": "QA坏日期", "due_date": "2026-08-"})
check("残缺 due_date 拒绝 400", s == 400, str(d)[:100])
s, d = req("POST", "/api/tasks", {"title": "QA坏日期2", "due_date": "2026-13-99"})
check("非法 due_date 拒绝 400", s == 400, str(d)[:100])
s, d = req("GET", "/api/calendar?month=2026-08")
check("日历不受脏 due_date 影响", s == 200, f"status={s}")
# 12.3 闰月纪念日倒计时（🔴#3）
import datetime as _dt2
_t2 = _dt2.date(2026, 8, 12)
r = db.next_anniversary(-6, 15, "lunar", today=_t2)
check("2026-2027 无闰六月→None", r is None, str(r))
r2 = db.next_anniversary(8, 15, "lunar", today=_t2)
check("中秋 2026-09-25 倒计时 44", r2 == ("2026-09-25", 44), str(r2))
s, d = req("POST", "/api/anniversaries", {"name": "QA闰月", "month": -6, "day": 15, "calendar_type": "lunar"})
check("闰月纪念日可保存（负月）", s == 201, str(d)[:100])
s, d = req("PATCH", f"/api/anniversaries/{d.get('id')}", {"name": "QA闰月改", "month": -6})
check("PATCH 闰月负月边界", s == 200 and d.get("month") == -6, str(d)[:100])
# 12.4 非法 theme（白名单外忽略）
s, d = req("PUT", "/api/settings", {"theme": "hacker"})
check("非法 theme 忽略", s == 200 and d.get("theme") != "hacker", str(d)[:100])
# 12.5 年份边界（🔴#13）
s, d = req("GET", "/api/calendar?month=1900-01")
check("1900-01 边界 200", s == 200, f"status={s}")
s, d = req("GET", "/api/calendar?month=2100-12")
check("2100-12 边界 200", s == 200, f"status={s}")
s, d = req("GET", "/api/calendar?month=1899-12")
check("1899 拒绝 400", s == 400, str(d)[:80])
s, d = req("GET", "/api/calendar?month=2101-01")
check("2101 拒绝 400", s == 400, str(d)[:80])
# 12.6 日志日期格式（🔴#14）
s, d = req("GET", "/api/log?date=2026-08-99")
check("非法日志日期拒绝 400", s == 400, str(d)[:80])
s, d = req("PUT", "/api/log", {"date": "2026-8-1", "content": "x"})
check("短格式日志日期拒绝 400", s == 400, str(d)[:80])
# 12.7 city_code 白名单（🟡#12）
s, d = req("PUT", "/api/settings", {"city_code": "abc"})
check("未知 city_code 拒绝 400", s == 400, str(d)[:80])

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
s, d = req("GET", "/api/anniversaries")
for a in [x for x in d if str(x["name"]).startswith("QA")]:
    req("DELETE", f"/api/anniversaries/{a['id']}")
s, d = req("GET", "/api/recurring-tasks")
for task in [x for x in d if str(x["title"]).startswith("QA")]:
    req("DELETE", f"/api/recurring-tasks/{task['id']}")

print(f"\n{'='*50}")
print(f"RESULT: {PASS} passed, {FAIL} failed")
if FAILURES:
    print("FAILED:", FAILURES)
sys.exit(1 if FAIL else 0)
