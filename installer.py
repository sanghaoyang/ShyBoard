# -*- coding: utf-8 -*-
"""Workbench 安装器：选择目录安装（解压内嵌 zip + 创建桌面快捷方式）。

独立 PyInstaller 打包（--onefile --windowed），不依赖源码与 Python 环境。
用法：
  python installer.py              # 源码调试
  python installer.py --silent <dir>  # 静默安装到指定目录（测试用）

打包：
  build_installer.bat  ->  dist/WorkbenchInstaller.exe
"""
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import zipfile

APP_NAME = "工作台 Workbench"
APP_TITLE = "Workbench 安装程序"

# 主题色（与工作台 UI 一致：柔和粉色系）
C_BG = "#FBF7F8"
C_CARD = "#FFFFFF"
C_MAIN = "#C4A0A8"
C_TEXT = "#4E4450"
C_DIM = "#8A7B86"
C_OK = "#7FB69B"

# 内嵌 zip 文件名（发版时由 build_installer.bat 指定 --add-data 的 zip 名，此处保持默认）
ZIP_NAME = "Workbench-v1.0.0.zip"
# UI 显示的版本号：从内嵌 zip 名推导（Workbench-vX.Y.Z.zip -> X.Y.Z）
VERSION = ZIP_NAME.split("Workbench-v")[-1].replace(".zip", "")


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
    """目录规范化：统一反斜杠 + 盘根目录自动追加 Workbench 子目录。

    返回 (normalized, changed)。如 C:\\ -> C:\\Workbench，D:/ -> D:\\Workbench。
    """
    dest = dest.strip().strip('"').strip()
    if not dest:
        return dest, False
    # 统一分隔符为反斜杠（Windows 风格），避免 / 与 \\ 混合
    dest = dest.replace("/", "\\")
    # 盘根目录：C:\ / C:/ / D:\
    if len(dest) == 3 and dest[1] == ":" and dest[2] == "\\":
        return os.path.join(dest, "Workbench"), True
    # 只有盘符没有斜杠：C: -> C:\Workbench
    if len(dest) == 2 and dest[1] == ":":
        return os.path.join(dest, "\\", "Workbench"), True
    return dest, False


# 系统目录黑名单（写这些位置需要管理员权限，或不该放应用数据）
SYSTEM_DIRS = {
    "windows", "winnt", "program files", "program files (x86)",
    "system32", "syswow64", "users", "perflogs", "recovery",
    "$recycle.bin", "system volume information", "boot",
    "programdata", "temp",
}


def check_dest_safe(dest):
    """校验目标目录是否安全。返回 (ok, error_msg)。

    规则：盘根目录自动修正（由 normalize_dest 处理，这里不再拦截）；
    系统目录（Windows/Program Files/Users 等）拒绝安装。
    """
    norm = dest.lower().rstrip("\\/")
    if not norm:
        return True, ""
    # 取目标目录的第一级（在盘符之后的顶层目录名）
    parts = [p for p in norm.split("\\") if p]
    if len(parts) >= 2 and parts[1] in SYSTEM_DIRS:
        return False, "不能安装到系统目录（Windows / Program Files / Users 等），请选择其他目录"
    # 直接命中系统目录（如 C:\Windows 本身）
    if len(parts) >= 1 and parts[0] in SYSTEM_DIRS and ":" not in parts[0]:
        return False, "不能安装到系统目录，请选择其他目录"
    return True, ""


def detect_installed(dest):
    """检测 dest 是否已有 Workbench 安装。返回 (installed_bool, old_version)。"""
    exe = os.path.join(dest, "Workbench.exe")
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
    """结束正在运行的 Workbench.exe（更新时替换 exe 需要先释放文件锁）。"""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "Workbench.exe"],
                       capture_output=True, timeout=15)
    except Exception:
        pass


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
                   check=True, capture_output=True, timeout=30)


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
        tk.Label(self.root, text="工作台 Workbench", font=("Microsoft YaHei UI", 16, "bold"),
                 bg=C_BG, fg=C_MAIN).pack(pady=(24, 2))
        tk.Label(self.root, text=f"安装程序 v{VERSION} · 本地个人工作台",
                 font=("Microsoft YaHei UI", 9), bg=C_BG, fg=C_DIM).pack()

        # 卡片：功能简介
        card = tk.Frame(self.root, bg=C_CARD, highlightbackground=C_MAIN, highlightthickness=1)
        card.pack(fill="x", padx=24, pady=12)
        features = "任务三泳道 · 番茄钟 · 天气 · 便签 · 快捷方式\nAI Agent 接入 · GitHub 自动更新"
        tk.Label(card, text=features, font=("Microsoft YaHei UI", 9),
                 bg=C_CARD, fg=C_TEXT, justify="left").pack(padx=16, pady=10)

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
        tk.Button(row, text="浏览…", command=self._browse, bg=C_MAIN, fg="#FFFFFF",
                  activebackground="#B08E96", activeforeground="#FFFFFF", relief="flat",
                  font=("Microsoft YaHei UI", 9), cursor="hand2", padx=10).pack(side="left", padx=(8, 0))
        # 已安装检测提示（目录变化时自动刷新）
        self.detect_var = tk.StringVar(value="")
        self.detect_label = tk.Label(loc, textvariable=self.detect_var, font=("Microsoft YaHei UI", 9),
                                     bg=C_CARD, fg=C_OK)
        self.detect_label.pack(anchor="w", padx=16, pady=(0, 8))
        self.dest_var.trace_add("write", lambda *_: self._refresh_detect())

        # 选项
        opts = tk.Frame(self.root, bg=C_BG)
        opts.pack(fill="x", padx=30, pady=4)
        tk.Checkbutton(opts, text="创建桌面快捷方式「工作台」", variable=self.make_shortcut_var,
                       bg=C_BG, fg=C_TEXT, activebackground=C_BG, activeforeground=C_TEXT,
                       font=("Microsoft YaHei UI", 9), selectcolor="#FFFFFF").pack(anchor="w")
        tk.Checkbutton(opts, text="安装完成后启动工作台", variable=self.launch_var,
                       bg=C_BG, fg=C_TEXT, activebackground=C_BG, activeforeground=C_TEXT,
                       font=("Microsoft YaHei UI", 9), selectcolor="#FFFFFF").pack(anchor="w")

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
        # 盘根目录自动追加 Workbench（同步回输入框让用户看到）
        dest, changed = normalize_dest(raw)
        if changed:
            self.dest_var.set(dest)
            return  # trace 会再次触发本函数
        # 系统目录拒绝
        ok, err = check_dest_safe(dest)
        if not ok:
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
            self.dest_var.set(os.path.join(d, "Workbench"))

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
        ok, err = check_dest_safe(dest)
        if not ok:
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
                        lnk = os.path.join(os.path.expanduser("~"), "Desktop", "工作台.lnk")
                        create_shortcut(os.path.join(dest, "Workbench.exe"), dest, lnk, "工作台正式版（自动更新）")
                    except Exception as e:
                        msg += f"（快捷方式创建失败：{e}）"
                done = "更新完成 ✓" if mode == "update" else "安装完成 ✓"
                self.status_var.set(done)
                self._set_progress(100)
                if self.launch_var.get():
                    subprocess.Popen([os.path.join(dest, "Workbench.exe")], cwd=dest)
                messagebox.showinfo(APP_TITLE, msg, parent=self.root)
            else:
                self.status_var.set("操作失败")
                messagebox.showerror(APP_TITLE, msg, parent=self.root)
            self.btn.config(state="normal")

        threading.Thread(target=work, daemon=True).start()


def main():
    # 静默模式（自动化测试用）：python installer.py --silent <dir>
    if "--silent" in sys.argv:
        idx = sys.argv.index("--silent")
        if idx + 1 < len(sys.argv):
            dest, _ = normalize_dest(sys.argv[idx + 1])
            ok_safe, err = check_dest_safe(dest)
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
