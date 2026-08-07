# -*- coding: utf-8 -*-
"""验证：check_dest_safe 新签名 + 提权场景 + 管理员权限检测。"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:\tools\workbench")
from installer import check_dest_safe, normalize_dest, is_admin, _is_writable

ROOT_DRIVE = "C:\\\\"
print(f"当前管理员权限: {is_admin()}")
print(f"C盘根可写: {_is_writable(ROOT_DRIVE)}")
print()

print("=== check_dest_safe 场景 ===")
cases = [
    ("C:\\", "盘根 -> 需提权 need_admin=True"),
    ("C:\\tools\\ShyBoard", "正常目录 -> 允许"),
    ("C:\\Program Files\\ShyBoard", "系统目录 -> 拒绝"),
    ("C:\\Windows", "系统目录 -> 拒绝"),
]
all_ok = True
for dest_in, desc in cases:
    d, _ = normalize_dest(dest_in)
    ok, err, need_admin = check_dest_safe(d)
    if "盘根" in desc:
        good = (not ok) and need_admin
    elif "正常" in desc:
        good = ok
    else:
        good = (not ok) and (not need_admin)
    all_ok = all_ok and good
    print(f"[{'PASS' if good else 'FAIL'}] {desc:24s} | {d} ok={ok} need_admin={need_admin}")

print()
print("ALL PASS" if all_ok else "SOME FAILED")
sys.exit(0 if all_ok else 1)