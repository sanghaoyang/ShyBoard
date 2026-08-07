# -*- coding: utf-8 -*-
"""用 Flask test client 验证设置/天气逻辑（不经过网络服务）"""
import os
import sys
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import server
import db

client = server.app.test_client()

# 1. 先确认当前设置
r = client.get("/api/settings")
print("当前设置:", r.get_json())

# 2. PUT city_code 切杭州
r = client.put("/api/settings", json={"city_code": "101210101", "city": "杭州"})
print("PUT 杭州 ->", r.status_code, r.get_json())

# 3. 天气应该变成杭州
r = client.get("/api/weather")
d = r.get_json()
print("天气:", d.get("city"), d.get("temp"), d.get("desc"))

# 4. 切回上海
r = client.put("/api/settings", json={"city_code": "101020100", "city": "上海"})
print("PUT 上海 ->", r.status_code, r.get_json())

