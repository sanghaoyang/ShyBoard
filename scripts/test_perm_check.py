# -*- coding: utf-8 -*-
"""验证可写性检测：盘根拒绝、正常目录通过。"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:\tools\workbench")
from installer import check_dest_safe, normalize_dest

print("=== 可写性检测测试 ===")
# 1. C:\ 盘根（normalize 后 C:\ShyBoard，父目录 C:\ 不可写）
d1, _ = normalize_dest("C:\\")
ok1, err1 = check_dest_safe(d1)
print(f"[{'PASS' if not ok1 else 'FAIL'}] C:\\ -> {d1}: safe={ok1} ({err1})")
# 2. 具体可写目录
ok2, err2 = check_dest_safe("C:\\tools\\ShyBoard")
print(f"[{'PASS' if ok2 else 'FAIL'}] C:\\tools\\ShyBoard: safe={ok2} ({err2})")
# 3. 系统目录（仍拒绝）
ok3, err3 = check_dest_safe("C:\\Program Files\\ShyBoard")
print(f"[{'PASS' if not ok3 else 'FAIL'}] C:\\Program Files\\ShyBoard: safe={ok3} ({err3})")
# 4. 桌面（可写）
desk = os.path.join(os.path.expanduser("~"), "Desktop", "ShyBoard")
ok4, err4 = check_dest_safe(desk)
print(f"[{'PASS' if ok4 else 'FAIL'}] 桌面: safe={ok4} ({err4})")

ok = (not ok1) and ok2 and (not ok3) and ok4
print()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
