# -*- coding: utf-8 -*-
"""ShyBoard 安装器：选择目录安装（解压内嵌 zip + 创建桌面快捷方式）。

独立 PyInstaller 打包（--onefile --windowed），不依赖源码与 Python 环境。
用法：
  python installer.py              # 源码调试
  python installer.py --silent <dir>  # 静默安装到指定目录（测试用）

打包：
  build_installer.bat  ->  dist/ShyBoardInstaller.exe
"""
import os
import shutil
import subprocess

# Windows 下子进程不创建控制台窗口（避免安装时闪现 cmd/PS 黑窗）
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import zipfile

APP_NAME = "ShyBoard"
APP_TITLE = "ShyBoard 安装程序"

# 主题色（与工作台 UI 一致：柔和粉色系）
C_BG = "#FBF7F8"
C_CARD = "#FFFFFF"
C_MAIN = "#C4A0A8"
C_TEXT = "#4E4450"
C_DIM = "#8A7B86"
C_OK = "#7FB69B"

# 内嵌 zip 文件名（发版时由 build_installer.bat 指定 --add-data 的 zip 名，此处保持默认）
ZIP_NAME = "ShyBoard-v1.0.0.zip"
# UI 显示的版本号：从内嵌 zip 名推导（ShyBoard-vX.Y.Z.zip -> X.Y.Z）
VERSION = ZIP_NAME.split("ShyBoard-v")[-1].replace(".zip", "")


def bundled_zip():
    """定位内嵌的 release zip（PyInstaller 打包后位于 _MEIPASS）。"""
    if getattr(sys, "_MEIPASS", ""):
        return os.path.join(sys._MEIPASS, ZIP_NAME)
    # 源码模式：从仓库 dist 找（installer.py 在仓库根）
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (
        os.path.join(here, "dist", ZIP_NAME),
        os.path.join(here, "..", "dist", ZIP_NAME),
        os.path.join(os.getcwd(), ZIP_NAME),
    ):
        if os.path.exists(cand):
            return cand
    return None


def normalize_dest(dest):
    """目录规范化：统一反斜杠 + 盘根目录自动追加 ShyBoard 子目录。

    返回 (normalized, changed)。如 C:\\ -> C:\\ShyBoard，D:/ -> D:\\ShyBoard。
    """
    dest = dest.strip().strip('"').strip()
    if not dest:
        return dest, False
    # 统一分隔符为反斜杠（Windows 风格），避免 / 与 \\ 混合
    dest = dest.replace("/", "\\")
    # 盘根目录：C:\ / C:/ / D:\
    if len(dest) == 3 and dest[1] == ":" and dest[2] == "\\":
        return os.path.join(dest, "ShyBoard"), True
    # 只有盘符没有斜杠：C: -> C:\ShyBoard
    if len(dest) == 2 and dest[1] == ":":
        return os.path.join(dest, "\\", "ShyBoard"), True
    return dest, False


# 系统目录黑名单（写这些位置需要管理员权限，或不该放应用数据）
SYSTEM_DIRS = {
    "windows", "winnt", "program files", "program files (x86)",
    "system32", "syswow64", "users", "perflogs", "recovery",
    "$recycle.bin", "system volume information", "boot",
    "programdata", "temp",
}


def check_dest_safe(dest):
    """校验目标目录是否安全。返回 (ok, error_msg, need_admin)。

    need_admin=True 表示：路径本身合法，但当前无写权限（如 C:\\ 盘根），
    需要管理员权限才能安装——不应拒绝，而应提示提权重试。
    """
    need_admin = False
    norm = dest.lower().rstrip("\\/")
    if not norm:
        return True, "", False
    # 取目标目录的第一级（在盘符之后的顶层目录名）
    parts = [p for p in norm.split("\\") if p]
    if len(parts) >= 2 and parts[1] in SYSTEM_DIRS:
        # 例外：用户自己的目录（C:\Users\<本用户名>）允许安装
        if parts[1] == "users" and len(parts) >= 3:
            if norm.startswith(os.environ.get("USERPROFILE", "C:\\Users\\x").lower()):
                pass  # 允许
            else:
                return False, "不能安装到其他用户的目录，请选择自己的目录", False
        else:
            return False, "不能安装到系统目录（Windows / Program Files 等），请选择其他目录", False
    # 直接命中系统目录（如 C:\Windows 本身）
    if len(parts) >= 1 and parts[0] in SYSTEM_DIRS and ":" not in parts[0]:
        return False, "不能安装到系统目录，请选择其他目录", False
    # 可写性检查：目标目录本身或父目录必须可写（盘根 C:\ 等普通权限不可写）
    if not _is_writable(dest):
        # 路径本身合法（C:\ShyBoard 没问题），只是需要管理员权限
        need_admin = True
        return False, f"该位置需要管理员权限（如 {dest[:3]} 盘根受系统保护）", True
    return True, "", False


def _is_writable(dest):
    """检测 dest（或其父目录）是否可写。返回 bool。"""
    # 目标目录已存在：直接测写
    probe_dir = dest if os.path.isdir(dest) else os.path.dirname(dest.rstrip("\\/")) or dest
    try:
        test_file = os.path.join(probe_dir, ".shyboard_perm_test")
        with open(test_file, "w") as f:
            f.write("x")
        os.remove(test_file)
        return True
    except Exception:
        return False


def is_admin():
    """当前进程是否有管理员权限。"""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(dest):
    """以管理员身份重启安装器（UAC 提权），传 --silent <dest> 直接安装。

    返回 True 表示已发起提权（新进程由 UAC 决定）。
    """
    try:
        exe = os.path.abspath(sys.executable)
        ps = (
            "Start-Process -Verb RunAs -FilePath "
            f"'{exe}' -ArgumentList '--silent','{dest}'"
        )
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                         creationflags=_NO_WINDOW)
        return True
    except Exception:
        return False


def detect_installed(dest):
    """检测 dest 是否已有 ShyBoard 安装。返回 (installed_bool, old_version)。"""
    exe = os.path.join(dest, "ShyBoard.exe")
    if not os.path.exists(exe):
        return False, None
    # 读上次安装/更新写入的版本标记（无则视为旧版）
    ver_file = os.path.join(dest, "data", "version.txt")
    old = None
    if os.path.exists(ver_file):
        try:
            with open(ver_file, "r", encoding="utf-8") as f:
                old = f.read().strip()
        except Exception:
            old = None
    return True, old


def kill_workbench():
    """结束正在运行的 ShyBoard.exe（更新时替换 exe 需要先释放文件锁）。"""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "ShyBoard.exe"],
                       capture_output=True, timeout=15, creationflags=_NO_WINDOW)
    except Exception:
        pass


def write_uninstall_reg(dest):
    """写入 HKCU 卸载注册表键，使 ShyBoard 出现在 设置→应用 中。

    HKCU（当前用户）无需管理员权限。UninstallString 指向卸载器。
    """
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ShyBoard"
        exe = os.path.join(dest, "ShyBoard.exe")
        uninstaller = os.path.join(dest, "ShyBoardUninstall.exe")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, "ShyBoard 小屋")
            winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, VERSION)
            winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, "sanghaoyang")
            winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, dest)
            winreg.SetValueEx(k, "DisplayIcon", 0, winreg.REG_SZ, exe)
            winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller}"')
            winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, 32000)
        return True
    except Exception:
        return False


def remove_uninstall_reg():
    """删除卸载注册表键（卸载时调用）。"""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\ShyBoard"
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        return True
    except Exception:
        return False


def create_startmenu_shortcut(dest):
    """开始菜单放快捷方式（左下角搜索可搜到 ShyBoard）。"""
    try:
        menu = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
        os.makedirs(menu, exist_ok=True)
        lnk = os.path.join(menu, "ShyBoard.lnk")
        create_shortcut(os.path.join(dest, "ShyBoard.exe"), dest, lnk, "ShyBoard 小屋")
        return True
    except Exception:
        return False


def install_to(dest, progress_cb=None, log_cb=None, mode="install"):
    """解压 zip 到 dest，返回 (ok, msg)。progress_cb(pct) 0-100。

    mode="install"：全新安装；mode="update"：更新（保留 data\\，只换程序文件）。
    """
    zip_path = bundled_zip()
    if not zip_path:
        return False, f"安装包内嵌资源缺失（未找到 {ZIP_NAME}）"
    if not os.path.exists(dest):
        os.makedirs(dest, exist_ok=True)
    try:
        if mode == "update":
            kill_workbench()
        z = zipfile.ZipFile(zip_path)
        total = len(z.namelist())
        for i, name in enumerate(z.namelist()):
            target = os.path.join(dest, name.replace("/", os.sep))
            if name.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(name) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            if progress_cb and i % 10 == 0:
                progress_cb(int((i + 1) / total * 100))
        if progress_cb:
            progress_cb(100)
        # 自愈：确保 update.ps1 存在（zip 里应有，防御性再拷一次）
        if not os.path.exists(os.path.join(dest, "update.ps1")):
            bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "update.ps1")
            if os.path.exists(bundled):
                shutil.copy2(bundled, os.path.join(dest, "update.ps1"))
        # 卸载器：从安装器资源复制到目标目录（注册表 UninstallString 指向它）
        uninstaller_src = os.path.join(getattr(sys, "_MEIPASS", ""), "ShyBoardUninstall.exe")
        if os.path.exists(uninstaller_src):
            shutil.copy2(uninstaller_src, os.path.join(dest, "ShyBoardUninstall.exe"))
        # 记录本次安装的版本（供下次检测更新）
        try:
            os.makedirs(os.path.join(dest, "data"), exist_ok=True)
            with open(os.path.join(dest, "data", "version.txt"), "w", encoding="utf-8") as f:
                f.write(VERSION)
        except Exception:
            pass
        action = "更新" if mode == "update" else "安装"
        return True, f"{action}完成到 {dest}"
    except Exception as e:
        return False, f"安装失败：{e}"


def create_shortcut(exe_path, working_dir, lnk_path, desc):
    """创建 .lnk 桌面快捷方式（PowerShell + WScript.Shell，无 pywin32 依赖）。

    PyInstaller onefile 里 pythoncom/win32com 常不可用，直接用 PowerShell
    最稳。路径统一转义为 PowerShell 单引号字符串。
    """
    def ps_str(s):
        # PowerShell 单引号字符串：把内部的 ' 翻倍转义
        return "'" + s.replace("'", "''") + "'"

    ps = (
        "$ws = New-Object -ComObject WScript.Shell;"
        f"$l = $ws.CreateShortcut({ps_str(lnk_path)});"
        f"$l.TargetPath = {ps_str(exe_path)};"
        f"$l.WorkingDirectory = {ps_str(working_dir)};"
        f"$l.Description = {ps_str(desc)};"
        "$l.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   check=True, capture_output=True, timeout=30, creationflags=_NO_WINDOW)


class InstallerApp:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.configure(bg=C_BG)
        root.resizable(False, False)
        self._center(460, 520)

        self.dest_var = tk.StringVar()
        self.status_var = tk.StringVar(value="准备安装")
        self.make_shortcut_var = tk.BooleanVar(value=True)
        self.launch_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._check_zip_present()

    def _center(self, w, h):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        pad = {"padx": 24, "pady": 8}
        # 标题
        tk.Label(self.root, text="ShyBoard", font=("Microsoft YaHei UI", 16, "bold"),
                 bg=C_BG, fg=C_MAIN).pack(pady=(24, 2))
        tk.Label(self.root, text=f"安装程序 v{VERSION} · 本地个人工作台",
                 font=("Microsoft YaHei UI", 9), bg=C_BG, fg=C_DIM).pack()

        # 卡片：安装位置
        loc = tk.Frame(self.root, bg=C_CARD, highlightbackground=C_MAIN, highlightthickness=1)
        loc.pack(fill="x", padx=24, pady=6)
        tk.Label(loc, text="安装位置", font=("Microsoft YaHei UI", 10, "bold"),
                 bg=C_CARD, fg=C_TEXT).pack(anchor="w", padx=16, pady=(10, 2))
        row = tk.Frame(loc, bg=C_CARD)
        row.pack(fill="x", padx=16, pady=(2, 10))
        self.entry = tk.Entry(row, textvariable=self.dest_var, font=("Microsoft YaHei UI", 9),
                              bg="#FFFFFF", fg=C_TEXT, relief="solid", bd=1)
        self.entry.pack(side="left", fill="x", expand=True, ipady=3)
        self.browse_btn = tk.Button(row, text="浏览…", command=self._browse, bg=C_MAIN, fg="#FFFFFF",
                  activebackground="#B08E96", activeforeground="#FFFFFF", relief="flat",
                  font=("Microsoft YaHei UI", 9), cursor="hand2", padx=10)
        self.browse_btn.pack(side="left", padx=(8, 0))
        # 已安装检测提示（目录变化时自动刷新）
        self.detect_var = tk.StringVar(value="")
        self.detect_label = tk.Label(loc, textvariable=self.detect_var, font=("Microsoft YaHei UI", 9),
                                     bg=C_CARD, fg=C_OK)
        self.detect_label.pack(anchor="w", padx=16, pady=(0, 8))
        self.dest_var.trace_add("write", lambda *_: self._refresh_detect())

        # 选项
        opts = tk.Frame(self.root, bg=C_BG)
        opts.pack(fill="x", padx=30, pady=4)
        self.make_shortcut_cb = tk.Checkbutton(opts, text="创建桌面快捷方式「ShyBoard」", variable=self.make_shortcut_var,
                       bg=C_BG, fg=C_TEXT, activebackground=C_BG, activeforeground=C_TEXT,
                       font=("Microsoft YaHei UI", 9), selectcolor="#FFFFFF")
        self.make_shortcut_cb.pack(anchor="w")
        self.launch_cb = tk.Checkbutton(opts, text="安装完成后启动 ShyBoard", variable=self.launch_var,
                       bg=C_BG, fg=C_TEXT, activebackground=C_BG, activeforeground=C_TEXT,
                       font=("Microsoft YaHei UI", 9), selectcolor="#FFFFFF")
        self.launch_cb.pack(anchor="w")

        # 进度条
        self.prog = tk.Canvas(self.root, height=10, bg=C_CARD, highlightthickness=0)
        self.prog.pack(fill="x", padx=24, pady=(12, 4))
        self.prog.create_rectangle(0, 0, 0, 10, fill=C_MAIN, width=0, tags="bar")

        # 状态
        tk.Label(self.root, textvariable=self.status_var, font=("Microsoft YaHei UI", 9),
                 bg=C_BG, fg=C_DIM).pack()

        # 安装按钮
        self.btn = tk.Button(self.root, text="安装", command=self._install,
                             bg=C_MAIN, fg="#FFFFFF", activebackground="#B08E96",
                             activeforeground="#FFFFFF", relief="flat", cursor="hand2",
                             font=("Microsoft YaHei UI", 12, "bold"), padx=30, pady=4)
        self.btn.pack(pady=16)

    def _check_zip_present(self):
        if not bundled_zip():
            self.status_var.set("错误：未找到内嵌安装包，无法安装")
            self.btn.config(state="disabled")

    def _refresh_detect(self):
        """目录变化时规范化路径 + 检测已安装 + 安全校验，动态更新提示。"""
        raw = self.dest_var.get().strip()
        if not raw:
            self.detect_var.set("")
            self.btn.config(text="安装")
            self.btn.config(state="normal")
            return
        # 规范化（盘根追加 + 分隔符统一），只要变了就写回输入框
        dest, changed = normalize_dest(raw)
        if dest != raw:
            self.dest_var.set(dest)
            return  # trace 会再次触发本函数
        # 系统目录拒绝
        ok, err, need_admin = check_dest_safe(dest)
        if not ok:
            if need_admin:
                # 路径合法但需要管理员权限：允许点安装，安装时提权
                self.detect_var.set(err + "（点击「安装」将以管理员身份重试）")
                self.detect_label.config(fg="#C05A5A")
                self.btn.config(text="安装", state="normal")
            else:
                self.detect_var.set(err)
                self.detect_label.config(fg="#C05A5A")
                self.btn.config(text="安装", state="disabled")
            return
        self.detect_label.config(fg=C_OK)
        installed, old = detect_installed(dest)
        if installed:
            if old and old != VERSION:
                self.detect_var.set(f"检测到已安装 v{old}，将更新到 v{VERSION}（数据保留）")
            elif old == VERSION:
                self.detect_var.set(f"已安装 v{VERSION}，重新覆盖（数据保留）")
            else:
                self.detect_var.set(f"检测到已有安装，将更新到 v{VERSION}（数据保留）")
            self.btn.config(text="更新")
        else:
            self.detect_var.set("")
            self.btn.config(text="安装")
        self.btn.config(state="normal")

    def _browse(self):
        d = filedialog.askdirectory(title="选择安装目录", mustexist=True)
        if d:
            # normpath 统一分隔符，避免 join 产生 C:/a\b 混合路径
            self.dest_var.set(os.path.normpath(os.path.join(d, "ShyBoard")))

    def _set_progress(self, pct):
        self.prog.coords("bar", 0, 0, int(self.prog.winfo_width() * pct / 100), 10)
        self.prog.update_idletasks()

    def _install(self):
        raw = self.dest_var.get().strip()
        if not raw:
            messagebox.showwarning(APP_TITLE, "请先选择安装目录", parent=self.root)
            return
        # 规范化（盘根自动追加）+ 安全校验（最终拦截，防绕过 UI）
        dest, changed = normalize_dest(raw)
        if changed:
            self.dest_var.set(dest)
            self.status_var.set(f"已自动选择 {dest}")
            return  # trace 触发 _refresh_detect 后用户再点一次
        ok, err, need_admin = check_dest_safe(dest)
        if not ok:
            if need_admin:
                # 路径合法但需要管理员权限：弹窗确认后提权安装
                if messagebox.askyesno(
                    APP_TITLE,
                    f"{err}\n\n是否以管理员身份重新运行安装器完成安装？",
                    parent=self.root,
                ):
                    if relaunch_as_admin(dest):
                        self.status_var.set("已请求管理员权限，请在 UAC 弹窗中确认…")
                        self.btn.config(state="disabled")
                    else:
                        messagebox.showerror(APP_TITLE, "提权失败，请右键安装器选择「以管理员身份运行」", parent=self.root)
                return
            messagebox.showwarning(APP_TITLE, err, parent=self.root)
            return
        installed, old = detect_installed(dest)
        mode = "update" if installed else "install"
        if installed:
            if old == VERSION:
                confirm = "目标目录已安装同版本工作台，重新覆盖？\n（数据 data\\ 目录保留）"
            else:
                confirm = f"检测到已安装 v{old or '未知'}，将更新到 v{VERSION}？\n（数据 data\\ 目录保留）"
            if not messagebox.askyesno(APP_TITLE, confirm, parent=self.root):
                return
        self.btn.config(state="disabled")
        self.status_var.set("正在更新…" if mode == "update" else "正在安装…")

        def work():
            ok, msg = install_to(dest, progress_cb=self._set_progress, mode=mode)
            if ok:
                if self.make_shortcut_var.get():
                    try:
                        lnk = os.path.join(os.path.expanduser("~"), "Desktop", "ShyBoard.lnk")
                        create_shortcut(os.path.join(dest, "ShyBoard.exe"), dest, lnk, "ShyBoard 小屋（自动更新）")
                    except Exception as e:
                        msg += f"（快捷方式创建失败：{e}）"
                # 注册表卸载信息（设置→应用 可见）+ 开始菜单（搜索可见）
                if write_uninstall_reg(dest):
                    create_startmenu_shortcut(dest)
                done = "更新完成 ✓" if mode == "update" else "安装完成 ✓"
                self.status_var.set(done)
                self._set_progress(100)
                self.root.after(0, self._finish, msg)
            else:
                self.status_var.set("操作失败")
                messagebox.showerror(APP_TITLE, msg, parent=self.root)
                self.btn.config(state="normal")

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, msg):
        """安装/更新成功后的收尾：锁定全部输入，按钮变「完成」，点击后启动并关闭。"""
        self.dest_installed = self.dest_var.get().strip()
        self.entry.config(state="disabled")
        if hasattr(self, "browse_btn"):
            self.browse_btn.config(state="disabled")
        if hasattr(self, "make_shortcut_cb"):
            self.make_shortcut_cb.config(state="disabled")
        if hasattr(self, "launch_cb"):
            self.launch_cb.config(state="disabled")
        self.btn.config(text="完成", state="normal", command=self._on_finish_click)
        self.status_var.set("点击「完成」关闭并启动 ShyBoard" if self.launch_var.get()
                            else "点击「完成」关闭窗口")
        messagebox.showinfo(APP_TITLE, msg, parent=self.root)

    def _on_finish_click(self):
        """点「完成」：若勾选了启动则打开工作台，然后关闭安装器。"""
        dest = getattr(self, "dest_installed", "")
        if self.launch_var.get() and dest:
            try:
                subprocess.Popen([os.path.join(dest, "ShyBoard.exe")], cwd=dest,
                                 creationflags=_NO_WINDOW)
            except Exception:
                pass
        self.root.destroy()


def main():
    # 静默模式（自动化测试用）：python installer.py --silent <dir>
    if "--silent" in sys.argv:
        idx = sys.argv.index("--silent")
        if idx + 1 < len(sys.argv):
            dest, _ = normalize_dest(sys.argv[idx + 1])
            ok_safe, err, need_admin = check_dest_safe(dest)
            if not ok_safe:
                print(f"拒绝安装：{err}")
                sys.exit(2)
            installed, _ = detect_installed(dest)
            mode = "update" if installed else "install"
            ok, msg = install_to(dest, mode=mode)
            print(msg)
            sys.exit(0 if ok else 1)
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
