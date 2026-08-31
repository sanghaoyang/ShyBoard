# -*- coding: utf-8 -*-
"""Verify first-launch removal of Zone.Identifier from bundled runtime files."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import _unblock_bundled_runtime


if os.name != "nt":
    print("SKIP: alternate data streams are Windows-only")
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix="shyboard-motw-") as temp:
    root = Path(temp)
    runtime = root / "_internal" / "pythonnet" / "runtime" / "Python.Runtime.dll"
    executable = root / "ShyBoard.exe"
    unrelated = root / "_internal" / "readme.txt"
    runtime.parent.mkdir(parents=True)
    unrelated.parent.mkdir(parents=True, exist_ok=True)
    runtime.write_bytes(b"managed assembly fixture")
    executable.write_bytes(b"executable fixture")
    unrelated.write_text("fixture", encoding="utf-8")

    for target in (runtime, executable, unrelated):
        Path(str(target) + ":Zone.Identifier").write_text(
            "[ZoneTransfer]\nZoneId=3\n", encoding="ascii"
        )

    result = _unblock_bundled_runtime(str(root))
    assert result == {"checked": 2, "unblocked": 2}, result
    for target in (runtime, executable):
        try:
            Path(str(target) + ":Zone.Identifier").read_text(encoding="ascii")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError(f"MOTW was not removed from {target}")
    assert Path(str(unrelated) + ":Zone.Identifier").read_text(encoding="ascii")

print("PASS: runtime DLL/EXE MOTW streams are removed before pythonnet loads")
