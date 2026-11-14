from __future__ import annotations

import os
from pathlib import Path
import subprocess

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ops/hes_encrypted_local_backup_v1.sh"


def _retention_function() -> str:
    source = SCRIPT.read_text(encoding="utf-8")
    start = source.index("prune_archives() {")
    end = source.index("\n}\n\n[[ -d", start) + 2
    return source[start:end]


def test_backup_script_syntax_and_fail_closed_archive_checks() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    source = SCRIPT.read_text(encoding="utf-8")
    assert "ARCHIVE_MODE=FROZEN_EXPLICIT_PATH_LIST" in source
    assert "--no-recursion" in source
    assert "trap cleanup EXIT" in source
    assert "gzip -t" in source
    assert "tar -tzf -" in source
    assert "sha256sum" in source
    assert "MIN_FREE_KB=5242880" in source
    assert "srv/hes-evidence" in source
    assert "BACKUP_EVIDENCE_STORE_MISSING_OR_INCOMPLETE" in source
    assert "expected_evidence_entries" in source
    assert source.count("\nprune_archives\n") == 1
    assert "Required evidence store: /srv/hes-evidence" in source


def test_retention_keeps_daily_weekly_monthly_and_latest_duplicate(tmp_path: Path) -> None:
    stamps = [
        "20261101T010000Z",
        "20261102T010000Z",
        "20261107T024546Z",
        "20261108T010000Z",
        "20261109T010000Z",
        "20261110T010000Z",
        "20261111T010000Z",
        "20261112T010000Z",
        "20261113T010000Z",
        "20261114T010000Z",
        "20261114T030547Z",
    ]
    for stamp in stamps:
        archive = tmp_path / f"hes-full-{stamp}.tar.gz.gpg"
        archive.write_bytes(b"fixture")
        Path(str(archive) + ".sha256").write_text("fixture", encoding="utf-8")
        Path(str(archive) + ".manifest.txt").write_text("fixture", encoding="utf-8")

    env = dict(os.environ, BACKUP_DIR=str(tmp_path), HES_BACKUP_TODAY="2026-11-14")
    run = subprocess.run(
        ["bash", "-c", _retention_function() + "\nprune_archives\n"],
        capture_output=True, text=True, env=env, check=True,
    )
    remaining = {p.name for p in tmp_path.glob("hes-full-*.tar.gz.gpg")}
    expected = {
        "hes-full-20261101T010000Z.tar.gz.gpg",
        "hes-full-20261108T010000Z.tar.gz.gpg",
        "hes-full-20261109T010000Z.tar.gz.gpg",
        "hes-full-20261110T010000Z.tar.gz.gpg",
        "hes-full-20261111T010000Z.tar.gz.gpg",
        "hes-full-20261112T010000Z.tar.gz.gpg",
        "hes-full-20261113T010000Z.tar.gz.gpg",
        "hes-full-20261114T030547Z.tar.gz.gpg",
    }
    assert remaining == expected
    assert not (tmp_path / "hes-full-20261102T010000Z.tar.gz.gpg.sha256").exists()
    assert not (tmp_path / "hes-full-20261102T010000Z.tar.gz.gpg.manifest.txt").exists()
    assert "RETENTION_DELETE_EXPIRED" in run.stdout
    assert "RETENTION_DELETE_DUPLICATE" in run.stdout


def test_systemd_backup_unit_is_network_isolated_and_read_only_to_project() -> None:
    root = SCRIPT.parents[2]
    unit = (root / "deploy/systemd/hes-encrypted-local-backup.service").read_text(encoding="utf-8")
    timer = (root / "deploy/systemd/hes-encrypted-local-backup.timer").read_text(encoding="utf-8")
    assert "ProtectSystem=strict" in unit
    assert "ReadOnlyPaths=/opt/hes-trade-agent" in unit
    assert "RestrictAddressFamilies=AF_UNIX AF_NETLINK" in unit
    assert "Persistent=true" in timer
    assert "RandomizedDelaySec=20m" in timer