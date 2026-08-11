# -*- coding: utf-8 -*-
"""创建演示数据（新库 / 重置后使用）。用法: ./.venv/Scripts/python scripts/seed_demo.py [--port <port>]

--port 可选：显式指定目标端口（如往桌面测试版 17894 注入）；缺省读项目 data/port.txt。
"""
import json
import os
import sys
import time
import urllib.request

PORT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "port.txt")


def get_port():
    if "--port" in sys.argv:
        return sys.argv[sys.argv.index("--port") + 1]
    try:
        with open(PORT_FILE) as f:
            return f.read().strip() or "17890"
    except Exception:
        return "17890"


BASE = f"http://127.0.0.1:{get_port()}"


def req(method, path, data=None):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    r = urllib.request.Request(BASE + path, data=body,
                               headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print("  !!", method, path, "->", e)
        return 0, {}


def task(**kw):
    s, d = req("POST", "/api/tasks", kw)
    print("  任务:", d.get("title", "?"), "->", s)
    return d


def patch(tid, **kw):
    s, d = req("PATCH", f"/api/tasks/{tid}", kw)
    return d


def wait(sec):
    """让事件时间戳有间隔，时间线更好读"""
    time.sleep(sec)


print("== 创建任务 ==")

# 待办 1：高优先级（用户心愿，继续挂着）
t1 = task(title="给工作台加个番茄钟", priority="high", tags=["功能规划"])

# 待办 2：中优先级 + 截止日期
t2 = task(title="整理周末爬山路线", priority="medium",
          due_date="2026-08-08", tags=["生活", "出行"],
          description="周六出发，找一条 2-3 小时的入门路线")

# 待办 3：低优先级
t3 = task(title="读完《深入理解计算机系统》第4章", priority="low", tags=["学习"])

# 进行中：带编辑历史的任务（演示 hover 变更细节）
t4 = task(title="写工作台使用手册", priority="medium", tags=["文档"])
wait(0.1)
patch(t4["id"], description="按模块分类：任务/天气/便签/快捷方式/Agent 接入")
wait(0.1)
patch(t4["id"], priority="high", due_date="2026-08-06")
wait(0.1)
patch(t4["id"], status="doing")

# 进行中：agent 来源（展示 🤖 标记）
t5 = task(title="调研：自托管个人仪表盘方案", priority="medium",
          tags=["Hermes", "调研"], source="agent",
          description="对比 Dashy / Glance / Hotpage，为工作台后续迭代参考")
wait(0.1)
patch(t5["id"], status="doing")

# 已完成：完整生命周期时间线
t6 = task(title="搭建工作台 v1", priority="high", tags=["项目"],
          description="任务三泳道 + 天气 + 便签 + 快捷方式 + Agent API")
wait(0.1)
patch(t6["id"], status="doing")
wait(0.1)
patch(t6["id"], status="done")

print("== 创建便签 ==")
req("POST", "/api/notes", {"content": "💡 想法：工作台可以加个番茄钟，放在侧栏"})
req("POST", "/api/notes", {"content": "周六 10:00 约了打球，记得提前订场"})

print("== 创建快捷方式 ==")
req("POST", "/api/links", {"name": "GitHub", "url": "github.com", "icon": "🐙"})
req("POST", "/api/links", {"name": "B站", "url": "bilibili.com", "icon": "📺"})
req("POST", "/api/links", {"name": "知乎", "url": "zhihu.com", "icon": "📚"})

print("== 创建纪念日 ==")
req("POST", "/api/anniversaries", {"name": "老妈生日", "month": 11, "day": 6, "calendar_type": "solar"})
req("POST", "/api/anniversaries", {"name": "老爸生日", "month": 12, "day": 2, "calendar_type": "solar"})
req("POST", "/api/anniversaries", {"name": "元旦", "month": 1, "day": 1, "calendar_type": "solar"})
req("POST", "/api/anniversaries", {"name": "中秋", "month": 8, "day": 15, "calendar_type": "lunar"})
req("POST", "/api/anniversaries", {"name": "除夕", "month": 12, "day": 30, "calendar_type": "lunar"})

s, stats = req("GET", "/api/stats")
print("\n== 完成 ==")
print("统计:", stats)
