# -*- coding: utf-8 -*-
"""打包 dist/Shyboard -> dist/Shyboard-<version>.zip（zipfile，兼容 extract_pyinstaller_zip.py）。
用法: python scripts/pack_release.py <version>  例如 python scripts/pack_release.py v1.3.3
路径基于本脚本位置推导，不硬编码本机路径。
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根
SRC = os.path.join(ROOT, "dist", "Shyboard")
version = sys.argv[1] if len(sys.argv) > 1 else "vX.Y.Z"
OUT = os.path.join(ROOT, "dist", f"Shyboard-{version}.zip")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(SRC):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, SRC).replace("\\", "/")
            z.write(full, rel)

print("zip written:", OUT, os.path.getsize(OUT), "bytes")

