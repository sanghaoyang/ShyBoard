# -*- coding: utf-8 -*-
"""favicon 抓取服务：按网址抓取网站自己的图标，本地缓存到 data/icons/。

策略（按优先级）：
  1. 直接抓 {scheme}://{host}/favicon.ico（多数网站标准路径）
  2. 抓网页 HTML，解析 <link rel="icon"> 标签里的真实图标 URL
  3. 兜底 Google favicon 服务（s2/favicons，按域名给 64px 图标）

所有请求先直连，失败后走 WB_PROXY 环境变量指定的代理（可选）。
结果缓存为 data/icons/{host}.{ext}，命中缓存直接返回，不重复下载。
"""
import os
import re
import sys
import urllib.request
from urllib.parse import urljoin, urlparse

if getattr(sys, "frozen", False):
    # 打包版：数据目录在 exe 旁边（可写、随用户数据走）
    DATA_BASE = os.path.dirname(sys.executable)
else:
    DATA_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS_DIR = os.path.join(DATA_BASE, "data", "icons")

PROXY = os.environ.get("WB_PROXY", "")
TIMEOUT = 6

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 常见图片后缀 → 扩展名（用于保存时确定类型）
_EXT_BY_CT = {
    "image/png": ".png",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/gif": ".gif",
}


def _fetch(url):
    """直连一次，失败后走 WB_PROXY 代理（若配置）再试一次。返回 bytes 或抛异常。"""
    headers = {"User-Agent": _UA}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except Exception:
        if not PROXY:
            raise
        proxy_handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
        opener = urllib.request.build_opener(proxy_handler)
        req = urllib.request.Request(url, headers=headers)
        with opener.open(req, timeout=TIMEOUT) as resp:
            return resp.read()


def _ext_from_url(url, content_type=""):
    """根据 URL 后缀或 Content-Type 推断扩展名。"""
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext in (".png", ".ico", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
        return ".jpg" if ext == ".jpeg" else ext
    for ct, e in _EXT_BY_CT.items():
        if ct in content_type:
            return e
    return ".png"


def _looks_like_image(data):
    """简单判断是否为图片（文件头魔数）。"""
    if not data:
        return False
    sig = data[:12]
    return (sig.startswith(b"\x89PNG") or sig.startswith(b"\xff\xd8")
            or sig.startswith(b"\x00\x00\x01\x00")  # ico
            or sig.startswith(b"RIFF")  # webp
            or sig.startswith(b"<svg") or sig.startswith(b"<?xml"))


def _cache_path(host, ext):
    os.makedirs(ICONS_DIR, exist_ok=True)
    # host 可能含端口，替换为安全文件名
    safe = re.sub(r"[^a-zA-Z0-9.-]", "_", host)
    return os.path.join(ICONS_DIR, f"{safe}{ext}")


def _save(data, host, ext):
    path = _cache_path(host, ext)
    with open(path, "wb") as f:
        f.write(data)
    return f"/icons/{os.path.basename(path)}"


def fetch_favicon(url):
    """抓取网站图标，返回本地路径（如 /icons/github.com.png）；失败返回 None。"""
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    scheme = parsed.scheme or "https"
    host = parsed.netloc
    # 已缓存直接返回
    for existing in os.listdir(ICONS_DIR) if os.path.isdir(ICONS_DIR) else []:
        safe = re.sub(r"[^a-zA-Z0-9.-]", "_", host)
        if existing.startswith(safe + "."):
            return f"/icons/{existing}"

    # 1. 标准路径 /favicon.ico
    for fav_url in (f"{scheme}://{host}/favicon.ico", f"https://{host}/favicon.ico"):
        try:
            data = _fetch(fav_url)
            if _looks_like_image(data):
                return _save(data, host, _ext_from_url(fav_url))
        except Exception:
            continue

    # 2. 解析 HTML 的 <link rel="icon">
    try:
        html = _fetch(f"{scheme}://{host}/").decode("utf-8", "ignore")
        hrefs = re.findall(
            r"<link[^>]+rel=[\"']?(?:shortcut\s+)?icon[\"']?[^>]*href=[\"']([^\"'>]+)[\"']",
            html, re.IGNORECASE,
        )
        if not hrefs:
            hrefs = re.findall(
                r"href=[\"']([^\"'>]+)[\"'][^>]*rel=[\"']?(?:shortcut\s+)?icon[\"']?",
                html, re.IGNORECASE,
            )
        for href in hrefs:
            full = urljoin(f"{scheme}://{host}/", href.strip())
            try:
                data = _fetch(full)
                if _looks_like_image(data):
                    return _save(data, host, _ext_from_url(full))
            except Exception:
                continue
    except Exception:
        pass

    # 3. 兜底 Google favicon 服务
    try:
        gurl = f"https://www.google.com/s2/favicons?domain={host}&sz=64"
        data = _fetch(gurl)
        if _looks_like_image(data):
            return _save(data, host, ".png")
    except Exception:
        pass

    return None
