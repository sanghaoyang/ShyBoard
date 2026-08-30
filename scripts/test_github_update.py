# -*- coding: utf-8 -*-
"""Real GitHub Release -> local transactional install integration test."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
import zipfile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from services import updater  # noqa: E402

APP_SOURCE = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
VERSION_MATCH = re.search(r'APP_VERSION\s*=\s*"(\d+\.\d+\.\d+)"', APP_SOURCE)
if not VERSION_MATCH:
    raise RuntimeError("Cannot read APP_VERSION")
APP_VERSION = VERSION_MATCH.group(1)

TEST_PARENT = PROJECT_ROOT / "data" / "github-update-tests"
TEST_ROOT = TEST_PARENT / uuid.uuid4().hex
DOWNLOAD_DATA = TEST_ROOT / "download-data"
INSTALL_DIR = TEST_ROOT / "install"
CHECKS = 0
ALL_PASSED = False


def check(condition, message):
    global CHECKS
    if not condition:
        raise AssertionError(message)
    CHECKS += 1


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop_test_app():
    exe = str((INSTALL_DIR / "ShyBoard.exe").resolve())
    env = os.environ.copy()
    env["SHYBOARD_TEST_EXE"] = exe
    command = (
        "$target=[IO.Path]::GetFullPath($env:SHYBOARD_TEST_EXE);"
        "Get-CimInstance Win32_Process | Where-Object {"
        "$_.Name -eq 'ShyBoard.exe' -and $_.ExecutablePath -and "
        "([IO.Path]::GetFullPath($_.ExecutablePath) -eq $target)"
        "} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        env=env, capture_output=True, check=False,
    )


def wait_health(port, expected_version):
    url = f"http://127.0.0.1:{port}/api/health"
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                health = json.loads(response.read().decode("utf-8"))
            if health.get("service") == "workbench" and health.get("version") == expected_version:
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


TEST_ROOT.mkdir(parents=True)
try:
    updates_dir = DOWNLOAD_DATA / "updates"
    updater.DATA_DIR = str(DOWNLOAD_DATA)
    updater.UPDATES_DIR = str(updates_dir)
    updater.CACHE_FILE = str(updates_dir / "check_cache.json")
    updater.PENDING_FILE = str(updates_dir / "pending_update.json")
    updater.PROGRESS_FILE = str(updates_dir / "progress.json")
    updater.RESULT_FILE = str(updates_dir / "last_result.json")

    print("[1/3] Reading the public GitHub Release anonymously...")
    release = updater.check("0.1.0", force=True)
    check(not release.get("error"), f"GitHub check failed: {release.get('error')}")
    check(release.get("tag") == f"v{APP_VERSION}", "latest public tag does not match APP_VERSION")
    check(release.get("has_update") is True, "0.1.0 should see the public release as an update")
    check(release.get("asset_name") == updater.EXPECTED_ASSET, "release asset name is invalid")
    expected_hash = updater._checksum_from_release(release)
    check(bool(expected_hash), "release must provide a valid SHA-256 digest")

    print("[2/3] Downloading and validating the official release asset...")
    downloaded = updater.download_release("0.1.0", release["tag"])
    package = updates_dir / updater.EXPECTED_ASSET
    check(package.is_file(), "release package was not written locally")
    check(sha256(package) == expected_hash == downloaded["sha256"], "downloaded SHA-256 mismatch")
    pending = updater.validate_pending()
    check(pending["version"] == f"v{APP_VERSION}", "pending version is invalid")

    print("[3/3] Installing the downloaded package in an isolated local directory...")
    with zipfile.ZipFile(package) as archive:
        archive.extractall(INSTALL_DIR)
    install_updates = INSTALL_DIR / "data" / "updates"
    install_updates.mkdir(parents=True)
    shutil.copy2(package, install_updates / updater.EXPECTED_ASSET)
    (install_updates / "pending_update.json").write_text(
        json.dumps({
            "version": f"v{APP_VERSION}",
            "zip": updater.EXPECTED_ASSET,
            "sha256": expected_hash,
            "size": package.stat().st_size,
        }),
        encoding="utf-8",
    )
    sentinel = INSTALL_DIR / "data" / "preserve-me.txt"
    sentinel.write_text("user-data-sentinel", encoding="utf-8")
    marker = INSTALL_DIR / "_internal" / "old-only.marker"
    marker.write_text("old-install", encoding="utf-8")
    port = free_port()
    (INSTALL_DIR / "data" / "port.txt").write_text(str(port), encoding="utf-8")

    completed = subprocess.run([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(INSTALL_DIR / "update.ps1"), "-OldPid", "0", "-HeadlessRestart",
    ], cwd=INSTALL_DIR, capture_output=True, text=True, timeout=90)
    check(completed.returncode == 0, f"update helper failed: {completed.stderr}")
    check(wait_health(port, APP_VERSION), "installed app did not pass its health/version check")
    check(sentinel.read_text(encoding="utf-8") == "user-data-sentinel", "user data was changed")
    check(not marker.exists(), "obsolete internal files survived the update")
    result = json.loads((install_updates / "last_result.json").read_text(encoding="utf-8"))
    check(result.get("status") == "success", "successful install result was not recorded")
    check(not (install_updates / "pending_update.json").exists(), "pending state survived successful install")

    ALL_PASSED = True
    print(f"RESULT: {CHECKS} real GitHub update checks passed")
finally:
    stop_test_app()
    if ALL_PASSED:
        resolved_root = TEST_ROOT.resolve()
        resolved_parent = TEST_PARENT.resolve()
        if resolved_parent not in resolved_root.parents:
            raise RuntimeError(f"Refusing to clean unsafe test path: {resolved_root}")
        shutil.rmtree(resolved_root)
    else:
        print(f"Test artifacts kept at: {TEST_ROOT}")
