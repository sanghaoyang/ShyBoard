# -*- coding: utf-8 -*-
"""更新服务：从 GitHub Release 检查/下载新版本。

仓库公开后无需认证，GitHub API 匿名可读 latest release。
流程（借鉴 Clash Verge Rev 的更新模型——下载与安装解耦）：
  1. check()      -> 查 GitHub latest release，对比本地版本
  2. download()   -> 下载新版本 zip 到 data/updates/，写 pending 缓存
                     （pending_update.json：version + zip 名），不立即安装
  3. apply()      -> 启动独立 PowerShell helper（update.ps1），本进程退出；
                     helper 等主进程退出后解压替换 exe/_internal 并重启
  4. app.py 启动早期检查 pending 缓存，弹窗确认后走同样的 helper 安装
     （下次启动兜底：上次下载了但没重启的更新，这次启动时补装）
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPDATES_DIR = os.path.join(DATA_DIR, "updates")

# GitHub 仓库（公开）
REPO = "sanghaoyang/workbench"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"

TIMEOUT = 10


def _fetch(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "ShyBoard-Updater"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read() if binary else resp.read().decode("utf-8")


def _version_tuple(v):
    """'v1.2.3' / '1.2.3' -> (1,2,3)；解析失败返回 None。"""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", str(v))
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


CACHE_FILE = os.path.join(UPDATES_DIR, "check_cache.json")
CACHE_TTL = 300  # 5 分钟内不重复请求 GitHub API（防 403 限流）


def _load_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            c = json.load(f)
        if c.get("ts", 0) + CACHE_TTL >= time.time():
            return c.get("data")
    except Exception:
        pass
    return None


def _save_cache(data):
    try:
        os.makedirs(UPDATES_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "data": data}, f, ensure_ascii=False)
    except Exception:
        pass


def check(local_version):
    """查最新 release。返回 dict 或 None（无更新/网络失败）。

    带 5 分钟缓存防限流，但缓存只存 GitHub 远端数据（tag/notes/
    download_url/latest_tuple），has_update 与 current_tuple 永远用
    传入的 local_version 现场计算——否则更新到新版后 5 分钟内再查
    会命中旧缓存，误报"还有更新"（v1.3.3 修复的 bug）。
    """
    current = _version_tuple(local_version)
    cached = _load_cache()
    if cached is not None:
        # 命中缓存：用当前版本重新判定，不直接返回旧判断
        cached = dict(cached)
        latest = tuple(cached.get("latest_tuple") or ())
        cached["current_tuple"] = current
        cached["has_update"] = bool(latest) and bool(current) and latest > current
        cached["from_cache"] = True
        return cached
    try:
        data = json.loads(_fetch(LATEST_API))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 仓库还没有 release（或找不到 latest），视为无更新
            return {"tag": "", "has_update": False, "notes": "还没有发布版本"}
        if e.code == 403:
            # 限流：5 分钟后再试，提示用户
            return {"error": "GitHub 请求太频繁（403），请 5 分钟后再试"}
        return {"error": f"GitHub 返回错误（{e.code}），请稍后重试"}
    except Exception:
        return {"error": "网络无法访问 GitHub，请检查网络后重试"}
    tag = data.get("tag_name", "")
    assets = data.get("assets", [])
    if not assets:
        return {"error": f"最新版本 {tag} 没有发布包（等待维护者上传）"}
    # 取第一个 zip 资产
    asset = next((a for a in assets if a.get("name", "").endswith(".zip")), assets[0])
    latest = _version_tuple(tag)
    # 缓存只存远端数据，不存版本判断（避免更新后误报）
    remote = {
        "tag": tag,
        "name": data.get("name", ""),
        "notes": data.get("body", "")[:500],
        "download_url": asset.get("browser_download_url", ""),
        "asset_name": asset.get("name", ""),
        "latest_tuple": latest,
    }
    _save_cache(remote)
    remote["current_tuple"] = current
    remote["has_update"] = bool(latest) and bool(current) and latest > current
    return remote


def download(url, filename, version=""):
    """下载新版本 zip 到 data/updates/（流式写入，进度写 progress.json）。

    下载完成后写 pending 缓存（pending_update.json），不立即安装。
    返回本地路径。
    """
    os.makedirs(UPDATES_DIR, exist_ok=True)
    # 清理旧下载（保留进程信息/进度/缓存元数据）
    for f in os.listdir(UPDATES_DIR):
        if f in ("app.pid", "app.args", "check_cache.json", "progress.json", "pending_update.json"):
            continue
        try:
            os.remove(os.path.join(UPDATES_DIR, f))
        except OSError:
            pass
    dest = os.path.join(UPDATES_DIR, filename)
    PROGRESS = os.path.join(UPDATES_DIR, "progress.json")
    req = urllib.request.Request(url, headers={"User-Agent": "ShyBoard-Updater"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                try:
                    with open(PROGRESS, "w") as pf:
                        import json as _json
                        _json.dump({
                            "downloaded": downloaded,
                            "total": total,
                            "percent": round(downloaded / total * 100, 1) if total else -1,
                            "done": False,
                        }, pf)
                except OSError:
                    pass
    try:
        with open(PROGRESS, "w") as pf:
            _json = __import__("json")
            _json.dump({
                "downloaded": downloaded,
                "total": total,
                "percent": 100.0,
                "done": True,
            }, pf)
    except OSError:
        pass
    if version:
        _write_pending(version, filename)
    return dest


# ---------------- pending 缓存（下载完成但未安装） ----------------
# 借鉴 Clash Verge Rev：下载与安装解耦。下载完成只写缓存，
# 安装留到（a）用户点"重启安装"或（b）下次启动早期，由独立
# PowerShell helper 执行。这样替换 exe 时主程序已退出，无文件锁。

PENDING_FILE = os.path.join(UPDATES_DIR, "pending_update.json")


def _write_pending(version, filename):
    """写 pending 缓存：{version, zip, downloaded_at}。"""
    try:
        os.makedirs(UPDATES_DIR, exist_ok=True)
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "version": version,
                "zip": filename,
                "downloaded_at": time.time(),
            }, f, ensure_ascii=False)
    except OSError:
        pass


def pending_info():
    """读 pending 缓存。无缓存/损坏返回 None。"""
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def clear_pending():
    """删除 pending 缓存（安装完成后或版本已过期时调用）。"""
    try:
        os.remove(PENDING_FILE)
    except OSError:
        pass


def progress():
    """读取下载进度。无进度文件返回 None。"""
    p = os.path.join(UPDATES_DIR, "progress.json")
    try:
        with open(p, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _launch_helper(pid):
    """启动独立 PowerShell helper（update.ps1）执行替换并重启。

    helper 是独立进程，不继承 GUI 的无 stdin/stdout 句柄（上次 bat
    卡死的根因）。端口/版本通过 pending_update.json 与命令行参数传递，
    不用 set /p 读文件（上次卡死的第二根因）。
    """
    import subprocess
    ps1 = os.path.join(BASE_DIR, "update.ps1")
    if not os.path.exists(ps1):
        raise RuntimeError("update.ps1 不存在，无法自动更新")
    # PowerShell 5.1 默认编码问题：参数用纯 ASCII，路径用绝对路径
    powershell = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32", "WindowsPowerShell", "v1.0", "powershell.exe",
    )
    if not os.path.exists(powershell):
        powershell = "powershell.exe"
    cmd = [
        powershell,
        "-NoProfile", "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-File", ps1,
        "-OldPid", str(pid),
    ]
    # ⚠️ 不能带 DETACHED_PROCESS：实测 PowerShell 5.1 在 DETACHED 下
    # 会静默退出、-File 脚本完全不执行（exit 0 但零日志零改动）。
    # 用 CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW 组合（2026-08-07 对照实验确认）。
    flags = (subprocess.CREATE_NEW_PROCESS_GROUP
             | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    # 显式 DEVNULL：杜绝继承 GUI 无效句柄导致的阻塞
    subprocess.Popen(
        cmd, cwd=BASE_DIR, creationflags=flags, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def apply():
    """启动 PowerShell helper 执行替换，并安排本进程退出。

    必须在 exe/源码根目录存在 update.ps1（随发布包分发）。
    update.ps1 会等待本进程（OldPid）退出 → 解压 pending zip
    → 替换 exe/_internal → 按原端口重启。
    若还没有 pending 更新（未下载过），直接抛错。
    """
    import threading
    info = pending_info()
    if not info:
        raise RuntimeError("没有待安装的更新，请先下载")
    _launch_helper(os.getpid())
    # 给响应留时间，然后退出；helper 接管替换与重启
    threading.Timer(1.0, os._exit, args=(0,)).start()

