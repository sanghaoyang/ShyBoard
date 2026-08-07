# -*- coding: utf-8 -*-
"""防护逻辑单元测试：normalize_dest + check_dest_safe。"""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:\tools\workbench")
from installer import normalize_dest, check_dest_safe

cases = [
    ("C:\\", "盘根应自动修正"),
    ("D:/", "盘根斜杠也应修正"),
    ("C:", "裸盘符应修正"),
    ("C:\\ShyBoard", "正常路径不修正"),
    ("C:\\Windows", "系统目录应拒绝"),
    ("C:\\Program Files", "系统目录应拒绝"),
    ("C:\\Users\\me", "Users 应拒绝"),
    ("D:\\Tools\\WB", "正常路径应通过"),
    ("C:\\Program Files (x86)\\x", "Program Files (x86) 应拒绝"),
    ("C:\\System32", "system32 大小写也应拒绝"),
]
all_ok = True
for dest, desc in cases:
    norm, changed = normalize_dest(dest)
    ok, err = check_dest_safe(norm)
    flag = "OK " if ok or "拒绝" in desc or "修正" in desc else "??"
    # 期望判断：带"修正"的应 changed=True；带"拒绝"的应 not ok
    exp_change = "修正" in desc
    exp_safe = "拒绝" not in desc
    good = (changed == exp_change) and (ok == exp_safe)
    # 正常路径：不修正且安全
    if "正常" in desc:
        good = (changed is False) and ok
    all_ok = all_ok and good
    print(f"[{'PASS' if good else 'FAIL'}] {desc:16s} | {dest!r:22s} -> {norm!r:26s} changed={changed} safe={ok}")

# 源码目录检测（目录存在 + 有特征文件）
print()
print("=== 源码目录检测（真实存在目录 + 特征文件）===")
import tempfile, os
with tempfile.TemporaryDirectory() as td:
    # 有 app.py
    d1 = os.path.join(td, "src_app")
    os.makedirs(d1)
    with open(os.path.join(d1, "app.py"), "w") as f:
        f.write("x")
    ok1, _ = check_dest_safe(d1)
    print(f"[{'PASS' if not ok1 else 'FAIL'}] 含 app.py: {d1} -> safe={ok1} (应 False)")
    # 有 server.py
    d2 = os.path.join(td, "src_server")
    os.makedirs(d2)
    with open(os.path.join(d2, "server.py"), "w") as f:
        f.write("x")
    ok2, _ = check_dest_safe(d2)
    print(f"[{'PASS' if not ok2 else 'FAIL'}] 含 server.py: {d2} -> safe={ok2} (应 False)")
    # 空目录
    d3 = os.path.join(td, "empty")
    os.makedirs(d3)
    ok3, _ = check_dest_safe(d3)
    print(f"[{'PASS' if ok3 else 'FAIL'}] 空目录: {d3} -> safe={ok3} (应 True)")
    all_ok = all_ok and (not ok1) and (not ok2) and ok3
print()
print("ALL PASS" if all_ok else "SOME FAILED")
sys.exit(0 if all_ok else 1)