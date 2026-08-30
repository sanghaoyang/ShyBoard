# -*- coding: utf-8 -*-
"""GitHub Release 更新服务。

下载、安装严格分离：主程序只负责检查、校验并保存发布包；独立的
PowerShell helper 在主程序退出后执行原子替换、启动验证与失败回滚。
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlparse

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPDATES_DIR = os.path.join(DATA_DIR, "updates")

REPO = os.environ.get("SHYBOARD_UPDATE_REPO", "sanghaoyang/ShyBoard")
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
EXPECTED_ASSET = "ShyBoard-Portable.zip"
CHECKSUM_ASSET = EXPECTED_ASSET + ".sha256"
TIMEOUT = 15
MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_EXTRACTED_BYTES = 1024 * 1024 * 1024

CACHE_FILE = os.path.join(UPDATES_DIR, "check_cache.json")
PENDING_FILE = os.path.join(UPDATES_DIR, "pending_update.json")
PROGRESS_FILE = os.path.join(UPDATES_DIR, "progress.json")
RESULT_FILE = os.path.join(UPDATES_DIR, "last_result.json")
CACHE_TTL = 300
_download_lock = threading.Lock()


def _atomic_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _fetch(url, binary=False, timeout=TIMEOUT, max_bytes=2 * 1024 * 1024):
    req = urllib.request.Request(url, headers={
        "User-Agent": "ShyBoard-Updater",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=timeout) as response:
        length = int(response.headers.get("Content-Length") or 0)
        if length and length > max_bytes:
            raise ValueError("更新响应体积异常")
        payload = response.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("更新响应体积异常")
        return payload if binary else payload.decode("utf-8")


def _version_tuple(version):
    """仅接受稳定版 vMAJOR.MINOR.PATCH。"""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(version or "").strip())
    return tuple(int(value) for value in match.groups()) if match else None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_sha256(value):
    value = str(value or "").strip().lower()
    if value.startswith("sha256:"):
        value = value[7:]
    return value if re.fullmatch(r"[0-9a-f]{64}", value) else ""


def _load_cache():
    try:
        cached = _read_json(CACHE_FILE)
        if float(cached.get("ts", 0)) + CACHE_TTL >= time.time():
            return cached.get("data")
    except Exception:
        pass
    return None


def _save_cache(data):
    try:
        _atomic_json(CACHE_FILE, {"ts": time.time(), "data": data})
    except OSError:
        pass


def _release_info(data):
    tag = str(data.get("tag_name") or "").strip()
    latest = _version_tuple(tag)
    if not latest:
        return {"error": "GitHub 最新版本号格式无效"}
    assets = data.get("assets") if isinstance(data.get("assets"), list) else []
    package = next((item for item in assets if item.get("name") == EXPECTED_ASSET), None)
    if not package:
        return {"error": f"最新版本 {tag} 缺少 {EXPECTED_ASSET}"}
    checksum = next((item for item in assets if item.get("name") == CHECKSUM_ASSET), None)
    expected_hash = _normalize_sha256(package.get("digest"))
    checksum_url = str(checksum.get("browser_download_url") or "") if checksum else ""
    if not expected_hash and not checksum_url:
        return {"error": f"最新版本 {tag} 缺少 SHA-256 校验信息"}
    return {
        "tag": tag,
        "name": str(data.get("name") or ""),
        "notes": str(data.get("body") or "")[:2000],
        "download_url": str(package.get("browser_download_url") or ""),
        "asset_name": EXPECTED_ASSET,
        "asset_size": int(package.get("size") or 0),
        "expected_sha256": expected_hash,
        "checksum_url": checksum_url,
        "latest_tuple": latest,
    }


def check(local_version, force=False):
    """查询 GitHub 最新稳定版，并在本地重新计算是否需要更新。"""
    current = _version_tuple(local_version)
    if not current:
        return {"error": "当前版本号格式无效"}
    remote = None if force else _load_cache()
    from_cache = remote is not None
    if remote is None:
        try:
            remote = _release_info(json.loads(_fetch(LATEST_API)))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return {"error": "无法访问 GitHub 更新源，请确认发布仓库允许公开读取"}
            if exc.code == 403:
                return {"error": "GitHub 请求受限，请稍后再试"}
            return {"error": f"GitHub 返回错误（{exc.code}）"}
        except (ValueError, json.JSONDecodeError) as exc:
            return {"error": f"GitHub 更新信息无效：{exc}"}
        except Exception:
            return {"error": "网络无法访问 GitHub，请检查网络后重试"}
        if "error" not in remote:
            _save_cache(remote)
    if "error" in remote:
        return remote
    result = dict(remote)
    latest = tuple(result.get("latest_tuple") or ())
    result["current_tuple"] = current
    result["has_update"] = bool(latest) and latest > current
    result["from_cache"] = from_cache
    return result


def _validate_release_url(url):
    parsed = urlparse(str(url or ""))
    prefix = f"/{REPO}/releases/download/"
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or not parsed.path.startswith(prefix):
        raise ValueError("发布包地址不属于配置的 GitHub 仓库")


def _checksum_from_release(info):
    expected = _normalize_sha256(info.get("expected_sha256"))
    if expected:
        return expected
    checksum_url = str(info.get("checksum_url") or "")
    _validate_release_url(checksum_url)
    text = _fetch(checksum_url, max_bytes=64 * 1024)
    for line in text.splitlines():
        parts = line.strip().split()
        if parts and _normalize_sha256(parts[0]):
            if len(parts) == 1 or parts[-1].lstrip("*") == EXPECTED_ASSET:
                return _normalize_sha256(parts[0])
    raise ValueError("SHA-256 校验文件格式无效")


def _validate_zip(path, expected_version=""):
    required = {"ShyBoard.exe", "ShyBoard-MCP.exe", "update.ps1", "release.json"}
    seen = set()
    extracted_size = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                normalized = item.filename.replace("\\", "/")
                member = PurePosixPath(normalized)
                if member.is_absolute() or ".." in member.parts or ":" in normalized:
                    raise ValueError("更新包包含不安全的文件路径")
                extracted_size += int(item.file_size)
                if extracted_size > MAX_EXTRACTED_BYTES:
                    raise ValueError("更新包解压体积异常")
                seen.add(normalized.rstrip("/"))
            if not required.issubset(seen) or not any(name.startswith("_internal/") for name in seen):
                raise ValueError("更新包结构不完整")
            try:
                manifest = json.loads(archive.read("release.json").decode("utf-8"))
            except Exception as exc:
                raise ValueError("更新包版本清单无效") from exc
            if manifest.get("format") != "shyboard-release" or not _version_tuple(manifest.get("version")):
                raise ValueError("更新包版本清单无效")
            if expected_version and _version_tuple(manifest.get("version")) != _version_tuple(expected_version):
                raise ValueError("更新包版本与 GitHub Release 不一致")
            bad_file = archive.testzip()
            if bad_file:
                raise ValueError(f"更新包文件损坏：{bad_file}")
    except zipfile.BadZipFile as exc:
        raise ValueError("下载的文件不是有效更新包") from exc


def _set_progress(**values):
    state = {"downloaded": 0, "total": 0, "percent": 0.0, "done": False, "error": ""}
    state.update(values)
    try:
        _atomic_json(PROGRESS_FILE, state)
    except OSError:
        pass


def _write_pending(version, filename, expected_sha256, size):
    _atomic_json(PENDING_FILE, {
        "version": version,
        "zip": filename,
        "sha256": expected_sha256,
        "size": int(size),
        "downloaded_at": time.time(),
    })


def download(url, filename, version, expected_sha256, expected_size=0):
    """流式下载到 .part，完成校验后原子落盘并写入待安装状态。"""
    if not _download_lock.acquire(blocking=False):
        raise RuntimeError("已有更新正在下载")
    part_path = ""
    try:
        filename = os.path.basename(str(filename or ""))
        if filename != EXPECTED_ASSET:
            raise ValueError("发布包名称无效")
        if not _version_tuple(version):
            raise ValueError("更新版本号无效")
        _validate_release_url(url)
        expected_hash = _normalize_sha256(expected_sha256)
        if not expected_hash:
            raise ValueError("缺少有效的 SHA-256 校验值")
        expected_size = int(expected_size or 0)
        if expected_size < 0 or expected_size > MAX_DOWNLOAD_BYTES:
            raise ValueError("发布包体积异常")
        os.makedirs(UPDATES_DIR, exist_ok=True)
        destination = os.path.join(UPDATES_DIR, filename)
        part_path = destination + ".part"
        try:
            os.remove(part_path)
        except FileNotFoundError:
            pass
        _set_progress()
        req = urllib.request.Request(url, headers={"User-Agent": "ShyBoard-Updater"})
        digest = hashlib.sha256()
        with urllib.request.urlopen(req, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or expected_size or 0)
            if total > MAX_DOWNLOAD_BYTES:
                raise ValueError("发布包体积超过安全限制")
            downloaded = 0
            with open(part_path, "wb") as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_BYTES:
                        raise ValueError("发布包体积超过安全限制")
                    handle.write(chunk)
                    digest.update(chunk)
                    _set_progress(
                        downloaded=downloaded,
                        total=total,
                        percent=round(downloaded / total * 100, 1) if total else -1,
                    )
                handle.flush()
                os.fsync(handle.fileno())
        if total and downloaded != total:
            raise ValueError("更新包下载不完整")
        if expected_size and downloaded != expected_size:
            raise ValueError("更新包大小与 GitHub 发布信息不一致")
        actual_hash = digest.hexdigest()
        if actual_hash != expected_hash:
            raise ValueError("更新包 SHA-256 校验失败")
        _validate_zip(part_path, version)
        os.replace(part_path, destination)
        _write_pending(version, filename, expected_hash, downloaded)
        _set_progress(downloaded=downloaded, total=downloaded, percent=100.0, done=True)
        return {"filename": filename, "version": version, "size": downloaded, "sha256": actual_hash}
    except Exception as exc:
        if part_path:
            try:
                os.remove(part_path)
            except OSError:
                pass
        _set_progress(error=str(exc))
        raise
    finally:
        _download_lock.release()


def download_release(local_version, requested_tag):
    info = check(local_version, force=True)
    if info.get("error"):
        raise RuntimeError(info["error"])
    if info.get("tag") != str(requested_tag or "").strip():
        raise ValueError("GitHub 最新版本已变化，请重新检查更新")
    if not info.get("has_update"):
        raise ValueError("当前已是最新版本")
    expected_hash = _checksum_from_release(info)
    return download(
        info["download_url"], info["asset_name"], info["tag"],
        expected_hash, info.get("asset_size", 0),
    )


def pending_info():
    try:
        info = _read_json(PENDING_FILE)
        return info if isinstance(info, dict) else None
    except Exception:
        return None


def validate_pending():
    info = pending_info()
    if not info:
        raise RuntimeError("没有待安装的更新，请先下载")
    version = str(info.get("version") or "")
    filename = os.path.basename(str(info.get("zip") or ""))
    expected_hash = _normalize_sha256(info.get("sha256"))
    if not _version_tuple(version) or filename != EXPECTED_ASSET or not expected_hash:
        raise RuntimeError("待安装更新信息无效")
    path = os.path.join(UPDATES_DIR, filename)
    if not os.path.isfile(path):
        raise RuntimeError("待安装更新包不存在")
    if int(info.get("size") or 0) != os.path.getsize(path):
        raise RuntimeError("待安装更新包大小不匹配")
    if _sha256(path) != expected_hash:
        raise RuntimeError("待安装更新包 SHA-256 校验失败")
    _validate_zip(path, version)
    return info


def clear_pending():
    try:
        os.remove(PENDING_FILE)
    except OSError:
        pass


def progress():
    try:
        return _read_json(PROGRESS_FILE)
    except Exception:
        return None


def record_result(status, version="", message=""):
    try:
        _atomic_json(RESULT_FILE, {
            "status": str(status), "version": str(version),
            "message": str(message)[:500], "timestamp": time.time(),
        })
    except OSError:
        pass


def consume_result():
    try:
        result = _read_json(RESULT_FILE)
        os.remove(RESULT_FILE)
        return result
    except Exception:
        return None


def _launch_helper(pid):
    ps1 = os.path.join(BASE_DIR, "update.ps1")
    if not os.path.exists(ps1):
        raise RuntimeError("update.ps1 不存在，无法自动更新")
    powershell = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32", "WindowsPowerShell", "v1.0", "powershell.exe",
    )
    if not os.path.exists(powershell):
        powershell = "powershell.exe"
    command = [
        powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", ps1, "-OldPid", str(pid),
    ]
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        command, cwd=BASE_DIR, creationflags=flags, close_fds=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def apply():
    """再次校验待安装包，启动独立 helper，并在响应返回后退出。"""
    validate_pending()
    _launch_helper(os.getpid())
    threading.Timer(3.0, os._exit, args=(0,)).start()
