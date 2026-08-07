# -*- coding: utf-8 -*-
"""ShyBoard 卸载器：从 设置→应用 的卸载入口调用。

流程：结束 ShyBoard 进程 → 删除桌面/开始菜单快捷方式 → 删除注册表
卸载键 → 删除整个安装目录（含 data 数据）。默认带确认提示，--silent 静默。
"""
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox

APP_TITLE = "ShyBoard 卸载程序"

# 与 installer.py 相同的主题色
C_BG = "#FBF7F8"
C_MAIN = "#C4A0A8"
C_TEXT = "#4E4450"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def get_install_dir():
    """从注册表读安装位置（卸载入口所在目录）。"""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ShyBoard"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            val, _ = winreg.QueryValueEx(k, "InstallLocation")
            return val
    except Exception:
        return None


def uninstall(dest):
    """执行卸载。返回 (ok, msg)。"""
    errors = []
    # 1. 杀进程
    try:
        subprocess.run(["taskkill", "/F", "/IM", "ShyBoard.exe"],
                       capture_output=True, timeout=15, creationflags=_NO_WINDOW)
    except Exception:
        pass
    # 2. 删桌面快捷方式
    for lnk_name in ("ShyBoard.lnk", "ShyBoard.lnk"):
        lnk = os.path.join(os.path.expanduser("~"), "Desktop", lnk_name)
        if os.path.exists(lnk):
            try:
                os.remove(lnk)
            except Exception as e:
                errors.append(f"桌面快捷方式：{e}")
    # 3. 删开始菜单快捷方式
    menu = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
    for lnk_name in ("ShyBoard.lnk", "ShyBoard.lnk"):
        lnk = os.path.join(menu, lnk_name)
        if os.path.exists(lnk):
            try:
                os.remove(lnk)
            except Exception as e:
                errors.append(f"开始菜单快捷方式：{e}")
    # 4. 删注册表卸载键
    try:
        import winreg
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ShyBoard")
    except Exception as e:
        errors.append(f"注册表键：{e}")
    # 5. 删安装目录（含 data），用延迟删除处理"正在运行的文件"
    if dest and os.path.exists(dest):
        try:
            # 先删除了自身以外的所有文件
            for name in os.listdir(dest):
                p = os.path.join(dest, name)
                if os.path.basename(sys.executable) == name:
                    continue  # 自己稍后延迟删除
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
        except Exception as e:
            errors.append(f"安装目录清理：{e}")
    # 6. 延迟删除卸载器自身 + 目录（cmd /c 用 start 脱离当前进程）
    self_path = os.path.abspath(sys.executable)
    cmd = (
        'start /B cmd /c "ping 127.0.0.1 -n 2 >nul & '
        f'rmdir /s /q "{dest}" 2>nul & '
        f'del /f /q "{self_path}" 2>nul"'
    )
    try:
        subprocess.Popen(cmd, shell=True, creationflags=_NO_WINDOW)
    except Exception as e:
        errors.append(f"延迟清理：{e}")
    if errors:
        return False, "部分内容删除失败：\n" + "\n".join(errors)
    return True, "ShyBoard 已完全卸载"


def main():
    dest = get_install_dir()
    if "--silent" in sys.argv:
        ok, msg = uninstall(dest)
        print(msg)
        sys.exit(0 if ok else 1)

    root = tk.Tk()
    root.title(APP_TITLE)
    root.configure(bg=C_BG)
    root.resizable(False, False)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"380x200+{(sw-380)//2}+{(sh-200)//2}")

    tk.Label(root, text="ShyBoard 卸载", font=("Microsoft YaHei UI", 14, "bold"),
             bg=C_BG, fg=C_MAIN).pack(pady=(24, 4))
    tk.Label(root, text="将删除程序文件与数据（含任务/便签/设置），不可恢复。",
             font=("Microsoft YaHei UI", 9), bg=C_BG, fg=C_TEXT).pack(pady=8)

    def do_uninstall():
        ok, msg = uninstall(dest)
        if ok:
            messagebox.showinfo(APP_TITLE, msg, parent=root)
            root.destroy()
        else:
            messagebox.showerror(APP_TITLE, msg, parent=root)

    tk.Button(root, text="卸载", command=do_uninstall, bg=C_MAIN, fg="#FFFFFF",
              activebackground="#B08E96", activeforeground="#FFFFFF", relief="flat",
              font=("Microsoft YaHei UI", 11, "bold"), padx=24, pady=3).pack(pady=10)
    tk.Button(root, text="取消", command=root.destroy, bg="#FFFFFF", fg=C_TEXT,
              relief="flat", font=("Microsoft YaHei UI", 10)).pack()
    root.mainloop()


if __name__ == "__main__":
    main()
