# -*- coding: utf-8 -*-
"""ShyBoard 入口。

用法:
  python app.py            # 打开桌面窗口
  python app.py --no-window  # 只起后台服务（供 agent / 无头测试）

端口策略: 默认 17890, 被占用时顺延。若 17890 已被本应用占用（health 通过），
直接复用并只开窗口（双击第二次只是再开一个窗口）。

启动优化（v2）:
  - WebView2 初始化与 Flask 启动并行：窗口先显示占位页（纯色背景），
    服务就绪后自动 load_url 导航，大幅缩短感知启动时间。
  - private_mode=False + storage_path=data/webview：持久 profile，
    二次启动复用字体/GPU/JS 缓存。
  - _is_workbench 先 socket 毫秒级探测端口，再 HTTP 确认，
    避免端口被其他程序占用时白等超时。
"""
import os
import socket
import sys
import threading
import time
import urllib.request

import paths as app_paths

BASE_DIR = str(app_paths.install_dir())
DATA_DIR = str(app_paths.get_data_dir(BASE_DIR))
PORT_FILE = os.path.join(DATA_DIR, "port.txt")
WEBVIEW_DIR = os.path.join(DATA_DIR, "webview")

PREFERRED_PORT = 17890
HEALTH_PATH = "/api/health"

# 全新版本线从 0.1.0 起步；发布时与对应安装包版本保持一致。
APP_VERSION = "0.1.1"

# 测试版标识：exe 名含 "Beta"（如 ShyBoardBeta.exe）即为测试版——
# 隐藏顶栏 ⬆ 自动更新按钮（测试版不走 GitHub release 更新），顶栏显示 Beta 徽标。
IS_BETA = "beta" in os.path.basename(sys.executable).lower()

# 占位页：窗口先显示纯色背景，避免导航前白屏
PLACEHOLDER_HTML = (
    "<body style='margin:0;background:#FBF7F8;"
    "display:flex;align-items:center;justify-content:center;"
    "font-family:Segoe UI,sans-serif;color:#C4A0A8;font-size:16px'>"
    "工作台</body>"
)


def _set_data_dir(path):
    """Refresh paths after a deferred data migration completes at startup."""
    global DATA_DIR, PORT_FILE, WEBVIEW_DIR
    DATA_DIR = os.path.abspath(str(path))
    PORT_FILE = os.path.join(DATA_DIR, "port.txt")
    WEBVIEW_DIR = os.path.join(DATA_DIR, "webview")


def _unblock_bundled_runtime(base_dir=None):
    """Remove Mark-of-the-Web streams before .NET/pythonnet loads assemblies.

    Windows can propagate a downloaded ZIP's Zone.Identifier stream to every
    extracted DLL. The CLR then treats Python.Runtime.dll as remote content and
    refuses to load it. Deleting only the alternate data stream preserves the
    file bytes and signatures while restoring normal local-assembly behavior.
    """
    if os.name != "nt":
        return {"checked": 0, "unblocked": 0}
    root = os.path.abspath(base_dir or BASE_DIR)
    candidates = []
    for name in ("ShyBoard.exe", "ShyBoard-MCP.exe"):
        path = os.path.join(root, name)
        if os.path.isfile(path):
            candidates.append(path)
    internal = os.path.join(root, "_internal")
    if os.path.isdir(internal):
        for folder, _, files in os.walk(internal):
            for name in files:
                if os.path.splitext(name)[1].lower() in {".dll", ".pyd", ".exe"}:
                    candidates.append(os.path.join(folder, name))
    try:
        import ctypes
        delete_file = ctypes.WinDLL("kernel32", use_last_error=True).DeleteFileW
        delete_file.argtypes = [ctypes.c_wchar_p]
        delete_file.restype = ctypes.c_int
    except Exception:
        return {"checked": len(candidates), "unblocked": 0}
    removed = 0
    for path in candidates:
        try:
            if delete_file(path + ":Zone.Identifier"):
                removed += 1
        except Exception:
            # A read-only installation may not allow ADS removal. Continue so
            # unaffected machines still launch; import webview will surface a
            # useful error if its managed assembly remains blocked.
            pass
    return {"checked": len(candidates), "unblocked": removed}


def _is_workbench(port):
    """快速探测：先 socket 确认端口在听（毫秒级），再 HTTP 确认是本应用。"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            pass
    except Exception:
        return False
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}{HEALTH_PATH}", timeout=1
        ) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("service") == "workbench"
    except Exception:
        return False


def find_port():
    """优先 17890；已运行则返回它；否则顺延找空闲端口。"""
    if _is_workbench(PREFERRED_PORT):
        return PREFERRED_PORT
    for port in range(PREFERRED_PORT, PREFERRED_PORT + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return PREFERRED_PORT


def start_server(port):
    from server import run_server
    t = threading.Thread(target=run_server, args=(port,), daemon=True)
    t.start()
    for _ in range(50):
        if _is_workbench(port):
            break
        time.sleep(0.1)


def _write_port_file(port):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PORT_FILE, "w") as f:
        f.write(str(port))


def _hide_console():
    """隐藏控制台窗口。

    uv venv 的 pythonw.exe 是 stub（与 python.exe 同为控制台子系统），
    启动后仍会创建控制台窗口。这里在应用启动瞬间把它藏掉，
    用户就看不到终端，也无法通过关终端影响工作台。
    """
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def _detach_if_console():
    """如果以 python.exe（带控制台）启动，自动切换为 pythonw.exe 后台运行。

    这样从终端运行 `python app.py` 也会立即返回，关终端不影响工作台。
    --no-window 模式（无头服务/测试）保持前台，方便看输出。
    """
    if "--no-window" in sys.argv:
        return
    if getattr(sys, "frozen", False):
        return
    if not sys.executable.lower().endswith("python.exe"):
        return  # 已经是 pythonw
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw):
        return
    import subprocess
    flags = (subprocess.DETACHED_PROCESS
             | subprocess.CREATE_NEW_PROCESS_GROUP
             | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    subprocess.Popen(
        [pythonw, os.path.abspath(__file__)] + sys.argv[1:],
        creationflags=flags,
        close_fds=True,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    sys.exit(0)


def _parse_port():
    if "--port" not in sys.argv:
        return None
    try:
        return int(sys.argv[sys.argv.index("--port") + 1])
    except (ValueError, IndexError):
        print("usage: --port <number>")
        sys.exit(1)


def _run_headless(port):
    """--no-window：只起服务，前台常驻（供 agent / 无头测试）。"""
    if not _is_workbench(port):
        start_server(port)
        _write_port_file(port)
    print(f"workbench server running at http://127.0.0.1:{port}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return


def _boot_and_goto(window, port):
    """后台线程：确保服务就绪，然后导航真实页面（WebView2 未就绪时重试）。"""
    if not _is_workbench(port):
        start_server(port)
        _write_port_file(port)
    for _ in range(100):
        if _is_workbench(port):
            break
        time.sleep(0.1)
    # WebView2 初始化与 Flask 并行，load_url 可能早于浏览器就绪，重试兜底
    # 加 ?v=版本号：WebView2 持久缓存（data/webview）可能缓存旧 HTML/JS，
    # 版本变化时换 URL 强制拉新页面，避免"改完代码还是旧行为"的假象
    for _ in range(50):
        try:
            window.load_url(f"http://127.0.0.1:{port}/?v={APP_VERSION}")
            return
        except Exception:
            time.sleep(0.1)


def _run_window(port):
    import webview

    class DesktopApi:
        def __init__(self):
            self.window = None

        def get_data_location(self):
            return app_paths.data_location_info(BASE_DIR)

        def choose_data_directory(self):
            try:
                current = app_paths.get_data_dir(BASE_DIR)
                chosen = self.window.create_file_dialog(
                    webview.FOLDER_DIALOG,
                    directory=str(current.parent),
                )
                if not chosen:
                    return {"ok": False, "cancelled": True}
                info = app_paths.prepare_data_directory(chosen[0], BASE_DIR)
                return {"ok": True, **info}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

    desktop_api = DesktopApi()

    window = webview.create_window(
        "ShyBoard",
        html=PLACEHOLDER_HTML,
        width=1180,
        height=780,
        min_size=(960, 640),
        background_color="#FBF7F8",
        js_api=desktop_api,
    )
    desktop_api.window = window

    # 立即并行启动服务（如未运行），与 WebView2 初始化同时进行；
    # 就绪后自动导航真实页面。不等窗口回调，缩短内容出现时间。
    threading.Thread(
        target=_boot_and_goto, args=(window, port), daemon=True
    ).start()

    webview.start(
        private_mode=False,
        storage_path=WEBVIEW_DIR,
    )
    # 窗口关闭后如果本进程是唯一实例（端口是我们起的），退出进程
    os._exit(0)


def _ensure_update_ps1():
    """自愈：确保安装目录使用当前包内的 update.ps1。

    旧版 helper 只替换 exe/_internal，不会更新外置 update.ps1。新版首次
    启动时比较内容并覆盖旧 helper，保证后续更新具备校验和回滚能力。
    """
    target = os.path.join(BASE_DIR, "update.ps1")
    try:
        bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "update.ps1")
        if not os.path.exists(bundled):
            return
        import filecmp
        if not os.path.exists(target) or not filecmp.cmp(bundled, target, shallow=False):
            import shutil
            shutil.copy2(bundled, target)
    except Exception:
        pass


def _try_pending_update():
    """启动早期检查：有已下载未安装的更新则弹窗确认并安装。

    借鉴 Clash Verge Rev 的 try_install_on_startup：
    - 下载完成只写 pending 缓存，不立即替换（运行中替换 exe 会锁文件）
    - 下次启动到这里：版本更新 → 弹窗询问 → 确认则启动 PowerShell
      helper 并退出本进程，由 helper 等本进程退出后替换重启
    - 用户拒绝/无头模式 → 保留 pending，下次启动再问（Clash 同款行为）
    - 返回 True 表示已启动安装流程，调用方应立即退出进程
    """
    try:
        from services import updater
    except Exception:
        return False
    info = updater.pending_info()
    if not info:
        return False
    version = str(info.get("version", ""))
    current = updater._version_tuple(APP_VERSION)
    latest = updater._version_tuple(version)
    if not latest or not current or latest <= current:
        # pending 版本不新（或解析失败）：清理残留，正常启动
        updater.clear_pending()
        return False
    # 无头模式 / QA 隔离环境：不弹窗，跳过（pending 保留，下次窗口模式再装）
    if "--no-window" in sys.argv or os.environ.get("WORKBENCH_DB"):
        return False
    try:
        import ctypes
        MB_YESNO = 0x00000004
        MB_ICONQUESTION = 0x00000020
        MB_DEFBUTTON2 = 0x00000100  # 默认光标在"否"，防止误回车直接更新
        res = ctypes.windll.user32.MessageBoxW(
            0,
            f"发现已下载的更新 {version}（当前 {APP_VERSION}）。\n\n"
            "是否现在重启并完成更新？",
            "ShyBoard 更新",
            MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2,
        )
        if res != 6:  # IDYES
            return False
    except Exception:
        return False
    try:
        updater.apply()
        return True
    except Exception as exc:
        # 校验或 helper 启动失败时取消待安装状态，避免每次启动重复弹窗。
        updater.record_result("failed", version, f"更新未开始：{exc}")
        updater.clear_pending()
        return False


def main():
    # Must run before importing webview/pythonnet in _run_window.
    _unblock_bundled_runtime()
    # A directory chosen in Settings is activated only after the previous
    # process has closed, so SQLite and WebView profile files can be copied.
    _set_data_dir(app_paths.activate_pending_data_directory(BASE_DIR))
    _hide_console()
    _detach_if_console()
    # 自愈：确保 update.ps1 存在（旧版升级上来时补装）
    _ensure_update_ps1()
    # 启动早期：检查已下载未安装的更新（在 GUI/服务启动之前）
    if _try_pending_update():
        os._exit(0)

    no_window = "--no-window" in sys.argv
    explicit_port = _parse_port()

    if explicit_port:
        port = explicit_port
    else:
        port = find_port()

    if no_window:
        _run_headless(port)
    else:
        _run_window(port)


if __name__ == "__main__":
    main()
