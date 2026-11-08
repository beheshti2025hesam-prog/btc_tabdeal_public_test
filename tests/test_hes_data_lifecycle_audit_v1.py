from datetime import datetime, timezone
from pathlib import Path

from scripts.ops.hes_data_lifecycle_audit_v1 import _classify, build_report


def _item(report, path):
    return next(row for row in report["items"] if row["path"] == str(path))


def test_protected_data_and_evidence_are_keep(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "journal.jsonl").write_text("{}\n", encoding="utf-8")
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "proof.json").write_text("{}", encoding="utf-8")

    report = build_report([tmp_path], now=datetime.now(timezone.utc))

    assert _item(report, data)["classification"] == "KEEP_PROTECTED"
    assert _item(report, evidence)["classification"] == "KEEP_PROTECTED"
    assert all(row["automatic_action"] == "NONE" for row in report["items"])


def test_old_tmp_is_review_only_never_delete():
    classification, _ = _classify(
        Path("/tmp/old-run"), age_days=8.0, is_symlink=False, stale_after_days=7
    )
    assert classification == "REVIEW_STALE_TEMP"


def test_same_day_extra_backup_is_review_candidate(tmp_path):
    root = tmp_path / "var/backups/hes-trade-agent/encrypted-local"
    root.mkdir(parents=True)
    older = root / "hes-full-20261108T010000Z.tar.gz.gpg"
    newer = root / "hes-full-20261108T020000Z.tar.gz.gpg"
    older.write_bytes(b"a")
    newer.write_bytes(b"b")

    report = build_report([root], now=datetime(2026, 11, 8, 3, tzinfo=timezone.utc))

    assert _item(report, older)["classification"] == "REVIEW_SAME_DAY_EXTRA_BACKUP"
    assert _item(report, newer)["classification"] == "KEEP_LATEST_SAME_DAY_BACKUP"
    assert report["backup_summary"]["same_day_extra_snapshot_candidates"] == 1
    assert all(row["automatic_action"] == "NONE" for row in report["items"])


def test_backup_parent_protects_unencrypted_and_security_backups():
    classification, _ = _classify(
        Path("/var/backups/hes-trade-agent/hes-trade-agent-20261107T160758Z.tar.gz"),
        age_days=1.0,
        is_symlink=False,
    )
    assert classification == "KEEP_BACKUP"


def test_symlink_is_not_followed(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "big.bin").write_bytes(b"x" * 1000)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    report = build_report([tmp_path], now=datetime.now(timezone.utc))
    row = _item(report, link)

    assert row["kind"] == "symlink"
    assert row["allocated_bytes"] == 0
    assert row["classification"] == "KEEP_SYMLINK"


def test_unknown_is_keep(tmp_path):
    unknown = tmp_path / "unknown-artifact"
    unknown.write_text("keep", encoding="utf-8")

    report = build_report([tmp_path], now=datetime.now(timezone.utc))

    assert _item(report, unknown)["classification"] == "KEEP_UNKNOWN"
    assert _item(report, unknown)["automatic_action"] == "NONE"
