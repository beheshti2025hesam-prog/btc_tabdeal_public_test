"""Isolated, filesystem-only rehearsal of versioned dashboard release and rollback."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_switch(link: Path, target: Path) -> None:
    if not target.is_dir():
        raise FileNotFoundError(target)
    temporary = link.with_name(link.name + ".next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(target, target_is_directory=True)
    os.replace(temporary, link)


class DashboardReleaseRollbackTests(unittest.TestCase):
    def test_service_template_is_loopback_only_and_grants_only_narrow_journal_write(self):
        unit = (Path(__file__).resolve().parents[1] / "deploy/systemd/hes-readonly-dashboard.service").read_text(encoding="utf-8")
        for required in (
            "User=sentinelx",
            "WorkingDirectory=/opt/hes-trade-agent/current",
            "Environment=HES_DASHBOARD_HOST=127.0.0.1",
            "Environment=HES_DASHBOARD_PORT=8765",
            "Environment=HES_TRADE_JOURNAL_PATH=/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl",
            "ConditionPathExists=/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl",
            "ConditionPathExists=/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl.lock",
            "ExecStart=/opt/hes-trade-agent/.venv/bin/python -m web.dashboard",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectSystem=strict",
            "ProtectHome=true",
            "MemoryDenyWriteExecute=true",
            "Restart=on-failure",
            "ReadOnlyPaths=/opt/hes-trade-agent/releases /opt/hes-trade-agent/data/forward",
            "ReadWritePaths=/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl /opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl.lock",
        ):
            with self.subTest(required=required):
                self.assertIn(required, unit)
        self.assertNotIn("ReadWritePaths=/opt/hes-trade-agent/data/forward\n", unit)
        self.assertNotIn("HES_BINANCE_STREAM_ENABLED=1", unit)
        self.assertNotIn("order", unit.lower().split("execstart", 1)[-1])

    def test_versioned_install_and_rollback_restore_exact_previous_artifact(self):
        with tempfile.TemporaryDirectory(prefix="hes-dashboard-release-test-") as temp:
            root = Path(temp)
            releases = root / "releases"
            releases.mkdir()
            old = releases / "release-old"
            new = releases / "release-new"
            old.mkdir()
            new.mkdir()
            (old / "dashboard.py").write_text("version = 'old'\n", encoding="utf-8")
            (new / "dashboard.py").write_text("version = 'new'\n", encoding="utf-8")
            old_hash = digest(old / "dashboard.py")
            new_hash = digest(new / "dashboard.py")
            self.assertNotEqual(old_hash, new_hash)

            current = root / "current"
            atomic_switch(current, old)
            self.assertEqual(current.resolve(), old.resolve())
            self.assertEqual(digest(current / "dashboard.py"), old_hash)

            atomic_switch(current, new)
            self.assertEqual(current.resolve(), new.resolve())
            self.assertEqual(digest(current / "dashboard.py"), new_hash)

            # Simulate a failed health gate: switch atomically to the exact old release.
            atomic_switch(current, old)
            self.assertEqual(current.resolve(), old.resolve())
            self.assertEqual(digest(current / "dashboard.py"), old_hash)
            self.assertEqual(digest(old / "dashboard.py"), old_hash)
            self.assertEqual(digest(new / "dashboard.py"), new_hash)
            self.assertFalse((root / "current.next").exists())

    def test_missing_release_target_does_not_replace_current_link(self):
        with tempfile.TemporaryDirectory(prefix="hes-dashboard-release-fail-") as temp:
            root = Path(temp)
            releases = root / "releases"
            releases.mkdir()
            old = releases / "release-old"
            old.mkdir()
            current = root / "current"
            atomic_switch(current, old)
            previous = current.resolve()
            missing = releases / "missing"
            with self.assertRaises(OSError):
                atomic_switch(current, missing)
            self.assertEqual(current.resolve(), previous)


if __name__ == "__main__":
    unittest.main()
