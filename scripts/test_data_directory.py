"""Isolated checks for custom data-directory selection and migration."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import paths


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="shyboard-data-path-") as temporary:
        root = Path(temporary)
        install = root / "app"
        old_data = install / "data"
        target = root / "chosen-data"
        old_data.mkdir(parents=True)
        (old_data / "workbench.db").write_bytes(b"sqlite-test")
        local_storage = old_data / "webview" / "EBWebView" / "Local Storage"
        local_storage.mkdir(parents=True)
        (local_storage / "rankings.test").write_text("personal-best", encoding="utf-8")

        info = paths.prepare_data_directory(target, install)
        check(info["restart_required"], "move was not deferred until restart")
        check(paths.get_data_dir(install) == old_data, "active path changed while app was running")

        activated = paths.activate_pending_data_directory(install)
        check(activated == target, "pending directory was not activated")
        check((target / "workbench.db").read_bytes() == b"sqlite-test", "database was not copied")
        check(
            (target / "webview" / "EBWebView" / "Local Storage" / "rankings.test").read_text(encoding="utf-8")
            == "personal-best",
            "WebView local storage was not copied",
        )
        check((old_data / "workbench.db").exists(), "old data was deleted")
        check(not paths.data_location_info(install)["restart_required"], "pending state survived migration")

        config = json.loads((install / paths.CONFIG_NAME).read_text(encoding="utf-8"))
        check(Path(config["path"]) == target, "active pointer was not saved")

        occupied = root / "occupied"
        occupied.mkdir()
        (occupied / "unrelated.txt").write_text("keep", encoding="utf-8")
        try:
            paths.prepare_data_directory(occupied, install)
        except ValueError:
            pass
        else:
            raise AssertionError("unrelated non-empty directory was accepted")

    print("PASS: custom data directory is deferred, copied, activated, and preserves the original")


if __name__ == "__main__":
    main()
