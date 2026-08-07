# -*- coding: utf-8 -*-
"""验证：注册表写入/读取/删除 + 开始菜单快捷方式 + 卸载器完整链路。"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"C:\tools\workbench")
from installer import write_uninstall_reg, remove_uninstall_reg, create_startmenu_shortcut

dest = r"C:\tools\shy_test"
print("=== 1. 写注册表卸载信息 ===")
ok = write_uninstall_reg(dest)
print(f"[{'PASS' if ok else 'FAIL'}] write_uninstall_reg: {ok}")
assert ok

print("=== 2. 验证注册表可读（模拟设置→应用可见）===")
import winreg
key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ShyBoard"
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
    for name in ("DisplayName", "DisplayVersion", "InstallLocation", "UninstallString"):
        val, _ = winreg.QueryValueEx(k, name)
        print(f"   {name} = {val}")
        assert val
print("   [PASS] 注册表键完整")

print("=== 3. 开始菜单快捷方式（左下角搜索可见）===")
ok = create_startmenu_shortcut(dest)
menu = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
lnk = os.path.join(menu, "ShyBoard.lnk")
print(f"[{'PASS' if ok and os.path.exists(lnk) else 'FAIL'}] 开始菜单: {lnk}")

print("=== 4. 卸载器 --silent（删文件+快捷方式+注册表）===")
ret = os.system(r'"C:\tools\shy_test\ShyBoardUninstall.exe" --silent')
print(f"   uninstaller exit = {ret} (0=成功)")
try:
    winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
    print("   [FAIL] 注册表键还在")
except FileNotFoundError:
    print("   [PASS] 注册表键已删除")
print(f"   安装目录存在: {os.path.exists(dest)} (应 False)")

print()
print("全部验证完成")