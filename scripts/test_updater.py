# -*- coding: utf-8 -*-
"""Offline updater tests: download integrity, ZIP safety, pending state and cache."""
import hashlib
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import updater  # noqa: E402


class FakeResponse(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def make_zip(extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ShyBoard.exe", b"desktop-binary")
        archive.writestr("ShyBoard-MCP.exe", b"mcp-binary")
        archive.writestr("update.ps1", b"# updater")
        archive.writestr("release.json", json.dumps({"format": "shyboard-release", "version": "0.2.0"}))
        archive.writestr("_internal/runtime.dat", b"runtime")
        if extra:
            archive.writestr(extra[0], extra[1])
    return output.getvalue()


def configure(root):
    updater.BASE_DIR = str(root)
    updater.DATA_DIR = str(root / "data")
    updater.UPDATES_DIR = str(root / "data" / "updates")
    updater.CACHE_FILE = str(root / "data" / "updates" / "check_cache.json")
    updater.PENDING_FILE = str(root / "data" / "updates" / "pending_update.json")
    updater.PROGRESS_FILE = str(root / "data" / "updates" / "progress.json")
    updater.RESULT_FILE = str(root / "data" / "updates" / "last_result.json")
    updater.REPO = "owner/repo"
    updater.LATEST_API = "https://api.github.com/repos/owner/repo/releases/latest"


def main():
    checks = 0
    original_urlopen = updater.urllib.request.urlopen
    with tempfile.TemporaryDirectory(prefix="shyboard-updater-") as temp:
        root = Path(temp)
        configure(root)
        payload = make_zip()
        digest = hashlib.sha256(payload).hexdigest()
        url = "https://github.com/owner/repo/releases/download/v0.2.0/ShyBoard-Portable.zip"
        updater.urllib.request.urlopen = lambda *_args, **_kwargs: FakeResponse(payload)

        assert updater._version_tuple("v0.2.0") == (0, 2, 0)
        assert updater._version_tuple("0.2") is None
        checks += 2

        result = updater.download(url, updater.EXPECTED_ASSET, "v0.2.0", digest, len(payload))
        assert result["sha256"] == digest
        assert updater.validate_pending()["version"] == "v0.2.0"
        assert not Path(updater.UPDATES_DIR, updater.EXPECTED_ASSET + ".part").exists()
        checks += 3

        installed_zip = Path(updater.UPDATES_DIR, updater.EXPECTED_ASSET)
        before = installed_zip.read_bytes()
        updater.urllib.request.urlopen = lambda *_args, **_kwargs: FakeResponse(payload + b"corrupt")
        try:
            updater.download(url, updater.EXPECTED_ASSET, "v0.2.0", digest, len(payload) + 7)
            raise AssertionError("hash mismatch should fail")
        except ValueError as exc:
            assert "SHA-256" in str(exc)
        assert installed_zip.read_bytes() == before
        checks += 2

        unsafe = make_zip(("../escape.txt", b"escape"))
        updater.urllib.request.urlopen = lambda *_args, **_kwargs: FakeResponse(unsafe)
        try:
            updater.download(
                url, updater.EXPECTED_ASSET, "v0.2.0",
                hashlib.sha256(unsafe).hexdigest(), len(unsafe),
            )
            raise AssertionError("unsafe ZIP should fail")
        except ValueError as exc:
            assert "不安全" in str(exc)
        assert not (root / "escape.txt").exists()
        checks += 2

        remote = {
            "tag": "v0.2.0", "name": "", "notes": "", "download_url": url,
            "asset_name": updater.EXPECTED_ASSET, "asset_size": len(payload),
            "expected_sha256": digest, "checksum_url": "", "latest_tuple": [0, 2, 0],
        }
        updater._save_cache(remote)
        assert updater.check("0.1.0")["has_update"] is True
        assert updater.check("0.2.0")["has_update"] is False
        checks += 2

        updater.record_result("success", "v0.2.0", "ok")
        assert updater.consume_result()["status"] == "success"
        assert updater.consume_result() is None
        checks += 2

    updater.urllib.request.urlopen = original_urlopen
    print(f"RESULT: {checks} updater checks passed")


if __name__ == "__main__":
    main()
