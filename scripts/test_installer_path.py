# -*- coding: utf-8 -*-
"""验证：浏览对话框混合路径 + normalize 写回逻辑。"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:\tools\workbench")
from installer import normalize_dest

print("=== 模拟浏览对话框返回的路径（模拟 Windows 对话框可能返回正斜杠）===")
cases = [
    # (对话框返回, 期望输入框最终显示)
    ("C:/tools/workbench", "C:\\tools\\workbench\\Workbench"),
    ("C:\\tools", "C:\\tools\\Workbench"),
    ("D:/", "D:\\Workbench"),
    ("C:", "C:Workbench"),  # 理论场景：对话框不会返回裸盘符；C:Workbench 是相对盘符路径
    ("E:/Apps", "E:\\Apps\\Workbench"),
]
ok = True
for dlg, exp in cases:
    joined = os.path.normpath(os.path.join(dlg, "Workbench"))
    # 模拟 _refresh_detect 的写回判断
    norm, _ = normalize_dest(joined)
    final = norm if norm != joined else joined
    good = final == exp
    ok = ok and good
    print(f"[{'PASS' if good else 'FAIL'}] 对话框={dlg!r:22s} -> 最终={final!r:32s} (期望 {exp!r})")
print()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
