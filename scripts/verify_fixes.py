# -*- coding: utf-8 -*-
"""验证 BUG-1 标签空格 / BUG-2 ftp 协议修复"""
import json
import urllib.request

BASE = "http://127.0.0.1:17891"


def req(method, path, data=None):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    r = urllib.request.Request(BASE + path, data=body,
                               headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(r, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


s, d = req("POST", "/api/tasks", {"title": "标签测试", "tags": "UI测试, 前端,中文 ,, 尾空格 "})
print("BUG-1 tags:", d.get("tags"), "| 期望无空格项:", d.get("tags") == ["UI测试", "前端", "中文", "尾空格"])

s, d = req("POST", "/api/links", {"name": "ftp测试", "url": "ftp://weird"})
print("BUG-2 ftp:", s, d)

s, d = req("POST", "/api/links", {"name": "B站", "url": "bilibili.com", "icon": "📺"})
print("正常补全:", s, d.get("url"), d.get("name"))

# 清理
for t in d if False else []:
    pass

