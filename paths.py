# -*- coding: utf-8 -*-
"""Shared install/data path handling for ShyBoard desktop, MCP and updater."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


CONFIG_NAME = "data-location.json"
EXPECTED_DATA_ENTRIES = {
    "backups",
    "port.txt",
    "updates",
    "webview",
    "workbench.db",
    "workbench.db-shm",
    "workbench.db-wal",
}


def install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _config_path(base: Path) -> Path:
    return base / CONFIG_NAME


def _read_config(base: Path) -> dict:
    try:
        value = json.loads(_config_path(base).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _write_config(base: Path, value: dict) -> None:
    path = _config_path(base)
    temporary = path.with_suffix(path.suffix + ".tmp")
    base.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def _normalized(path: os.PathLike | str) -> Path:
    return Path(os.path.abspath(os.path.expandvars(os.path.expanduser(str(path)))))


def get_data_dir(base: os.PathLike | str | None = None) -> Path:
    """Return the active data directory without activating a pending move."""
    env_path = os.environ.get("SHYBOARD_DATA_DIR", "").strip()
    if env_path:
        return _normalized(env_path)
    root = _normalized(base or install_dir())
    configured = str(_read_config(root).get("path", "")).strip()
    return _normalized(configured) if configured else root / "data"


def data_location_info(base: os.PathLike | str | None = None) -> dict[str, object]:
    root = _normalized(base or install_dir())
    config = _read_config(root)
    active = get_data_dir(root)
    pending = str(config.get("pending_path", "")).strip()
    return {
        "path": str(active),
        "pending_path": str(_normalized(pending)) if pending else "",
        "restart_required": bool(pending and _normalized(pending) != active),
        "migration_error": str(config.get("migration_error", "")),
    }


def prepare_data_directory(
    target: os.PathLike | str, base: os.PathLike | str | None = None
) -> dict[str, object]:
    """Validate a target and record a move for the next desktop startup.

    Migration is deliberately deferred until the current WebView and SQLite
    connections have closed. The old directory is copied, never deleted.
    """
    root = _normalized(base or install_dir())
    active = get_data_dir(root)
    destination = _normalized(target)
    if destination == active:
        config = _read_config(root)
        config.pop("pending_path", None)
        config.pop("migration_error", None)
        _write_config(root, config)
        return data_location_info(root)
    if destination == root or root in destination.parents:
        raise ValueError("数据目录不能放在 ShyBoard 程序目录内部")
    destination.mkdir(parents=True, exist_ok=True)
    unexpected = {
        item.name for item in destination.iterdir()
        if item.name not in EXPECTED_DATA_ENTRIES
    }
    if unexpected:
        raise ValueError("请选择空目录，或选择已有的 ShyBoard 数据目录")
    probe = destination / ".shyboard-write-test"
    try:
        probe.write_text("ok", encoding="ascii")
        probe.unlink()
    except OSError as exc:
        raise ValueError(f"所选目录不可写：{exc}") from exc
    config = _read_config(root)
    config["path"] = str(active)
    config["pending_path"] = str(destination)
    config.pop("migration_error", None)
    _write_config(root, config)
    return data_location_info(root)


def activate_pending_data_directory(
    base: os.PathLike | str | None = None,
) -> Path:
    """Copy pending data while no app resources are open, then switch paths."""
    root = _normalized(base or install_dir())
    config = _read_config(root)
    pending_value = str(config.get("pending_path", "")).strip()
    current = get_data_dir(root)
    if not pending_value:
        return current
    destination = _normalized(pending_value)
    if destination == current:
        config.pop("pending_path", None)
        config.pop("migration_error", None)
        _write_config(root, config)
        return current
    try:
        destination.mkdir(parents=True, exist_ok=True)
        if current.is_dir():
            shutil.copytree(current, destination, dirs_exist_ok=True, copy_function=shutil.copy2)
        config["path"] = str(destination)
        config.pop("pending_path", None)
        config.pop("migration_error", None)
        _write_config(root, config)
        return destination
    except Exception as exc:
        config["migration_error"] = str(exc)
        _write_config(root, config)
        return current
