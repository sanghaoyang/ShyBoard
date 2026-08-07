# -*- coding: utf-8 -*-
"""验证：路径规范化统一反斜杠 + PowerShell 创建快捷方式（完整安装→快捷方式链路）。"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:\tools\workbench")

from installer import normalize_dest, create_shortcut

print("=== 1. 路径规范化测试 ===")
cases = [
    ("D:/", "D:\\Workbench"),
    ("D:/Tools", "D:\\Tools"),
    ("C:\\", "C:\\Workbench"),
    ("C:\\Workbench", "C:\\Workbench"),
    ("D:/Tools/WB", "D:\\Tools\\WB"),
    ("C:Workbench", "C:Workbench"),  # C:Workbench 是相对盘符路径（当前目录下），不修正
]
ok = True
for inp, exp in cases:
    got, changed = normalize_dest(inp)
    good = got == exp
    ok = ok and good
    print(f"[{'PASS' if good else 'FAIL'}] {inp!r} -> {got!r} (期望 {exp!r})")
print()

print("=== 2. PowerShell 创建快捷方式测试（真实桌面）===")
try:
    test_dir = r"C:\tools\inst_test"
    os.makedirs(test_dir, exist_ok=True)
    exe = os.path.join(test_dir, "Workbench.exe")
    with open(exe, "w") as f:
        f.write("test")
    lnk = os.path.join(os.path.expanduser("~"), "Desktop", "__inst_test_workbench.lnk")
    create_shortcut(exe, test_dir, lnk, "测试快捷方式")
    print("[PASS] 快捷方式创建成功:", lnk)
    print("       存在:", os.path.exists(lnk))
    os.remove(lnk)
except Exception as e:
    print(f"[FAIL] {e}")
    ok = False
print()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
