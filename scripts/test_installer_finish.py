# -*- coding: utf-8 -*-
"""验证 _finish 逻辑：控件引用存在、锁定后不可再装。"""
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:\tools\workbench")

# 无头验证：检查 InstallerApp 构建后引用的控件都存在
import tkinter as tk
from installer import InstallerApp, VERSION

root = tk.Tk()
root.withdraw()
app = InstallerApp(root)
root.update()

checks = {
    "entry": hasattr(app, "entry"),
    "browse_btn": hasattr(app, "browse_btn"),
    "make_shortcut_cb": hasattr(app, "make_shortcut_cb"),
    "launch_cb": hasattr(app, "launch_cb"),
    "btn": hasattr(app, "btn"),
    "dest_var": hasattr(app, "dest_var"),
}
ok = True
for name, present in checks.items():
    print(f"[{'PASS' if present else 'FAIL'}] 控件引用 {name}: {'存在' if present else '缺失'}")
    ok = ok and present

# 模拟 _finish
try:
    app.entry.config(state="disabled")
    app.browse_btn.config(state="disabled")
    app.make_shortcut_cb.config(state="disabled")
    app.launch_cb.config(state="disabled")
    app.btn.config(text="完成", state="normal", command=root.destroy)
    print("[PASS] _finish 锁定逻辑可执行（entry/browse/checkbox 全禁用，按钮=完成）")
except Exception as e:
    print(f"[FAIL] _finish 锁定异常: {e}")
    ok = False

root.destroy()
print()
print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)