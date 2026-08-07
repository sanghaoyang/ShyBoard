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

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PORT_FILE = os.path.join(DATA_DIR, "port.txt")
WEBVIEW_DIR = os.path.join(DATA_DIR, "webview")

PREFERRED_PORT = 17890
HEALTH_PATH = "/api/health"

# 应用版本：发布时手动递增，与 GitHub Release tag 对应（如 v1.1.0）
APP_VERSION = "1.0.0"

# 占位页：窗口先显示纯色背景，避免导航前白屏
PLACEHOLDER_HTML = (
    "<body style='margin:0;background:#FBF7F8;"
    "display:flex;align-items:center;justify-content:center;"
    "font-family:Segoe UI,sans-serif;color:#C4A0A8;font-size:16px'>"
    "工作台</body>"
)


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
    for _ in range(50):
        try:
            window.load_url(f"http://127.0.0.1:{port}/")
            return
        except Exception:
            time.sleep(0.1)


def _run_window(port):
    import webview

    window = webview.create_window(
        "ShyBoard",
        html=PLACEHOLDER_HTML,
        width=1180,
        height=780,
        min_size=(960, 640),
        background_color="#FBF7F8",
    )

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
    """自愈：确保安装目录存在 update.ps1（更新机制依赖它）。

    打包后 update.ps1 在 _internal（sys._MEIPASS）里。若安装目录缺失
    （旧版升级上来，旧 update.bat 只替换 exe/_internal 不带 ps1），
    启动时从打包资源复制一份，保证下一次自动更新可用。
    """
    target = os.path.join(BASE_DIR, "update.ps1")
    if os.path.exists(target):
        return
    try:
        bundled = os.path.join(getattr(sys, "_MEIPASS", ""), "update.ps1")
        if os.path.exists(bundled):
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
    except Exception:
        # helper 启动失败不阻塞正常启动（pending 保留，可下次再试）
        return False


def main():
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
