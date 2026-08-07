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


def uninstall(dest, keep_data=False):
    """执行卸载。返回 (ok, msg)。

    keep_data=True：保留 data\\ 目录（任务/便签/设置），只删程序文件。
    keep_data=False：完全卸载（连数据一起删）。
    """
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
    # 5. 删安装目录（keep_data=True 时保留 data\\）
    if dest and os.path.exists(dest):
        try:
            for name in os.listdir(dest):
                p = os.path.join(dest, name)
                if os.path.basename(sys.executable) == name:
                    continue  # 自己稍后延迟删除
                if keep_data and name == "data":
                    continue  # 保留数据
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
        except Exception as e:
            errors.append(f"安装目录清理：{e}")
    # 6. 延迟删除卸载器自身（cmd /c 用 start 脱离当前进程）
    self_path = os.path.abspath(sys.executable)
    if keep_data and dest and os.path.exists(dest):
        # 保留数据：卸载器复制到 data 里（延迟自删），程序文件已在第5步删完
        try:
            import shutil as _sh
            moved = os.path.join(dest, "data", "_uninstaller_tmp.exe")
            _sh.copy2(self_path, moved)
            self_path = moved
        except Exception:
            pass
    if keep_data and dest and os.path.exists(dest):
        # 保留数据：只自删卸载器副本（data 目录保留）
        cmd = (
            'start /B cmd /c "ping 127.0.0.1 -n 2 >nul & '
            f'del /f /q "{self_path}" 2>nul"'
        )
    else:
        # 完全删除：先删卸载器副本，等进程退出后再 rmdir 整个目录
        cmd = (
            'start /B cmd /c "ping 127.0.0.1 -n 2 >nul & '
            f'del /f /q "{self_path}" 2>nul & '
            'ping 127.0.0.1 -n 2 >nul & '
            f'rmdir /s /q "{dest}" 2>nul"'
        )
    try:
        subprocess.Popen(cmd, shell=True, creationflags=_NO_WINDOW)
    except Exception as e:
        errors.append(f"延迟清理：{e}")
    if errors:
        return False, "部分内容删除失败：\n" + "\n".join(errors)
    return True, "ShyBoard 已卸载（数据已保留）" if keep_data else "ShyBoard 已完全卸载"


def main():
    dest = get_install_dir()
    if "--silent" in sys.argv:
        keep = "--keep-data" in sys.argv
        ok, msg = uninstall(dest, keep_data=keep)
        print(msg)
        sys.exit(0 if ok else 1)

    root = tk.Tk()
    root.title(APP_TITLE)
    root.configure(bg=C_BG)
    root.resizable(False, False)
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"400x240+{(sw-400)//2}+{(sh-240)//2}")

    tk.Label(root, text="卸载 ShyBoard", font=("Microsoft YaHei UI", 14, "bold"),
             bg=C_BG, fg=C_MAIN).pack(pady=(22, 4))
    tk.Label(root, text="将删除程序文件与快捷方式。",
             font=("Microsoft YaHei UI", 9), bg=C_BG, fg=C_TEXT).pack()

    keep_var = tk.BooleanVar(value=True)

    def do_uninstall():
        ok, msg = uninstall(dest, keep_data=keep_var.get())
        if ok:
            messagebox.showinfo(APP_TITLE, msg, parent=root)
            root.destroy()
        else:
            messagebox.showerror(APP_TITLE, msg, parent=root)

    def toggle_keep():
        if keep_var.get():
            tip_label.config(text="保留 data 目录：任务/便签/设置不删除，下次安装可恢复")
        else:
            tip_label.config(text="完全删除：任务/便签/设置将一并清除，不可恢复！")

    tk.Checkbutton(root, text="保留我的数据（任务/便签/设置）", variable=keep_var,
                   command=toggle_keep, bg=C_BG, fg=C_TEXT,
                   activebackground=C_BG, activeforeground=C_TEXT,
                   font=("Microsoft YaHei UI", 10)).pack(pady=(12, 2))
    tip_label = tk.Label(root, text="保留 data 目录：任务/便签/设置不删除，下次安装可恢复",
                         font=("Microsoft YaHei UI", 8), bg=C_BG, fg="#8A7B86")
    tip_label.pack(pady=(0, 8))

    tk.Button(root, text="卸载", command=do_uninstall, bg=C_MAIN, fg="#FFFFFF",
              activebackground="#B08E96", activeforeground="#FFFFFF", relief="flat",
              font=("Microsoft YaHei UI", 11, "bold"), padx=24, pady=3).pack(pady=4)
    tk.Button(root, text="取消", command=root.destroy, bg="#FFFFFF", fg=C_TEXT,
              relief="flat", font=("Microsoft YaHei UI", 10)).pack()
    root.mainloop()


if __name__ == "__main__":
    main()