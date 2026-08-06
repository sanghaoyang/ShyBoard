# -*- coding: utf-8 -*-
"""更新服务：从 GitHub Release 检查/下载新版本。

仓库公开后无需认证，GitHub API 匿名可读 latest release。
流程（由前端按钮触发）：
  1. check()      -> 查 GitHub latest release，对比本地版本
  2. download()   -> 下载新版本 zip 到 data/updates/（返回 zip 路径）
  3. 前端提示用户重启；app.py 检测到待更新 zip 后自动替换并重启
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
    req = urllib.request.Request(url, headers={"User-Agent": "Workbench-Updater"})
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
    """查最新 release。返回 dict 或 None（无更新/网络失败）。带 5 分钟缓存防限流。"""
    cached = _load_cache()
    if cached is not None:
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
    current = _version_tuple(local_version)
    result = {
        "tag": tag,
        "name": data.get("name", ""),
        "notes": data.get("body", "")[:500],
        "download_url": asset.get("browser_download_url", ""),
        "asset_name": asset.get("name", ""),
        "latest_tuple": latest,
        "current_tuple": current,
        "has_update": bool(latest) and bool(current) and latest > current,
    }
    _save_cache(result)
    return result


def download(url, filename):
    """下载新版本 zip 到 data/updates/（流式写入，进度写 progress.json）。返回本地路径。"""
    os.makedirs(UPDATES_DIR, exist_ok=True)
    # 清理旧下载
    for f in os.listdir(UPDATES_DIR):
        if f in ("app.pid", "app.args", "check_cache.json", "progress.json"):
            continue
        try:
            os.remove(os.path.join(UPDATES_DIR, f))
        except OSError:
            pass
    dest = os.path.join(UPDATES_DIR, filename)
    PROGRESS = os.path.join(UPDATES_DIR, "progress.json")
    req = urllib.request.Request(url, headers={"User-Agent": "Workbench-Updater"})
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
    return dest


def progress():
    """读取下载进度。无进度文件返回 None。"""
    p = os.path.join(UPDATES_DIR, "progress.json")
    try:
        with open(p, "r") as f:
            return json.load(f)
    except Exception:
        return None


def apply():
    """启动 update.bat 执行替换，并安排本进程退出。

    必须在 exe/源码根目录存在 update.bat（随发布包分发）。
    update.bat 会等待本进程（PID 写入 data/updates/app.pid）退出
    → 解压 zip → 替换 exe/_internal → 按原端口重启。
    """
    import subprocess
    import threading
    bat = os.path.join(BASE_DIR, "update.bat")
    if not os.path.exists(bat):
        raise RuntimeError("update.bat 不存在，无法自动更新")
    # 记录本进程 PID + 启动端口，供 update.bat 精确等待与重启
    try:
        os.makedirs(UPDATES_DIR, exist_ok=True)
        with open(os.path.join(UPDATES_DIR, "app.pid"), "w") as f:
            f.write(str(os.getpid()))
        with open(os.path.join(UPDATES_DIR, "app.args"), "w") as f:
            port = ""
            if "--port" in sys.argv:
                try:
                    port = str(int(sys.argv[sys.argv.index("--port") + 1]))
                except (ValueError, IndexError):
                    pass
            f.write(port)
    except OSError:
        pass
    flags = (subprocess.DETACHED_PROCESS
             | subprocess.CREATE_NEW_PROCESS_GROUP
             | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    subprocess.Popen([bat], cwd=BASE_DIR, creationflags=flags, close_fds=True)
    # 给响应留时间，然后退出
    threading.Timer(1.0, os._exit, args=(0,)).start()
