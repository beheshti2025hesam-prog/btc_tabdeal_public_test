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

    report = build_report([tmp_path], now=datetime.now(timezone.utc), registered_worktrees=set())

    assert _item(report, data)["classification"] == "KEEP_PROTECTED"
    assert _item(report, evidence)["classification"] == "KEEP_PROTECTED"
    assert all(row["automatic_action"] == "NONE" for row in report["items"])


def test_old_tmp_is_review_only_never_delete():
    classification, _ = _classify(
        Path("/tmp/old-run"), age_days=8.0, is_symlink=False, stale_after_days=7,
        registered_worktrees=set(),
    )
    assert classification == "REVIEW_STALE_TEMP"


def test_same_day_extra_backup_is_review_candidate(tmp_path):
    root = tmp_path / "var/backups/hes-trade-agent/encrypted-local"
    root.mkdir(parents=True)
    older = root / "hes-full-20261108T010000Z.tar.gz.gpg"
    newer = root / "hes-full-20261108T020000Z.tar.gz.gpg"
    older.write_bytes(b"a")
    newer.write_bytes(b"b")

    report = build_report(
        [root], now=datetime(2026, 11, 8, 3, tzinfo=timezone.utc), registered_worktrees=set()
    )

    assert _item(report, older)["classification"] == "REVIEW_SAME_DAY_EXTRA_BACKUP"
    assert _item(report, newer)["classification"] == "KEEP_LATEST_SAME_DAY_BACKUP"
    assert report["backup_summary"]["same_day_extra_snapshot_candidates"] == 1
    assert all(row["automatic_action"] == "NONE" for row in report["items"])


def test_backup_parent_protects_unencrypted_and_security_backups():
    classification, _ = _classify(
        Path("/var/backups/hes-trade-agent/hes-trade-agent-20261107T160758Z.tar.gz"),
        age_days=1.0,
        is_symlink=False,
        registered_worktrees=set(),
    )
    assert classification == "KEEP_BACKUP"


def test_symlink_is_not_followed(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "big.bin").write_bytes(b"x" * 1000)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    report = build_report([tmp_path], now=datetime.now(timezone.utc), registered_worktrees=set())
    row = _item(report, link)

    assert row["kind"] == "symlink"
    assert row["allocated_bytes"] == 0
    assert row["classification"] == "KEEP_SYMLINK"


def test_registered_git_worktree_is_protected(tmp_path):
    worktree = tmp_path / "registered-worktree"
    worktree.mkdir()
    report = build_report(
        [tmp_path], now=datetime.now(timezone.utc), registered_worktrees={worktree}
    )
    assert _item(report, worktree)["classification"] == "KEEP_REGISTERED_WORKTREE"


def test_registered_repository_root_does_not_mask_specific_classification():
    classification, _ = _classify(
        Path("/opt/hes-trade-agent/releases"), age_days=1.0, is_symlink=False,
        registered_worktrees={Path("/opt/hes-trade-agent")},
    )
    assert classification == "KEEP_PROTECTED"


def test_tmp_is_kept_unknown_when_worktree_registry_fails():
    classification, _ = _classify(
        Path("/tmp/old-run"), age_days=30.0, is_symlink=False,
        registered_worktrees=set(), worktree_registry_ok=False,
    )
    assert classification == "KEEP_UNKNOWN"


def test_unknown_is_keep(tmp_path):
    unknown = tmp_path / "unknown-artifact"
    unknown.write_text("keep", encoding="utf-8")

    report = build_report([tmp_path], now=datetime.now(timezone.utc), registered_worktrees=set())

    assert _item(report, unknown)["classification"] == "KEEP_UNKNOWN"
    assert _item(report, unknown)["automatic_action"] == "NONE"


def test_dropbox_staging_is_protected_but_not_assumed_offsite():
    classification, reason = _classify(
        Path("/var/backups/hes-trade-agent/dropbox-staging/hes-agent-offsite.tar.gz.gpg"),
        age_days=1.0,
        is_symlink=False,
        registered_worktrees=set(),
    )
    assert classification == "KEEP_BACKUP_STAGING"
    assert "not an offsite copy" in reason


def test_backup_retention_plan_mirrors_current_policy_without_deleting(tmp_path):
    root = tmp_path / "var/backups/hes-trade-agent/encrypted-local"
    root.mkdir(parents=True)
    names = {
        "daily": "hes-full-20261107T010000Z.tar.gz.gpg",
        "weekly": "hes-full-20261101T010000Z.tar.gz.gpg",
        "monthly": "hes-full-20261001T010000Z.tar.gz.gpg",
        "expired": "hes-full-20260501T010000Z.tar.gz.gpg",
        "future": "hes-full-20261109T010000Z.tar.gz.gpg",
        "unparsed": "hes-full-unknown.tar.gz.gpg",
    }
    for name in names.values():
        (root / name).write_bytes(b"archive")
        (root / (name + ".sha256")).write_text("sidecar", encoding="utf-8")
    report = build_report(
        [root], now=datetime(2026, 11, 8, tzinfo=timezone.utc), registered_worktrees=set()
    )
    rows = {Path(row["path"]).name: row for row in report["items"]}
    assert rows[names["daily"]]["retention_class"] == "KEEP_DAILY_WINDOW"
    assert rows[names["weekly"]]["retention_class"] == "KEEP_WEEKLY_ANCHOR"
    assert rows[names["monthly"]]["retention_class"] == "KEEP_MONTHLY_ANCHOR"
    assert rows[names["expired"]]["retention_class"] == "REVIEW_RETENTION_EXPIRED"
    assert rows[names["future"]]["retention_class"] == "KEEP_FUTURE_DATED_BACKUP"
    assert rows[names["unparsed"]]["retention_class"] == "KEEP_UNPARSED_BACKUP_NAME"
    assert all(row.get("retention_action", "NONE") == "NONE" for row in report["items"])
    assert report["backup_retention_plan"]["deletion_authorized"] is False
    assert report["backup_retention_plan"]["expired_review_candidates"] == 1
    assert rows[names["daily"]]["checksum_sidecar_present"] is True


def test_srv_evidence_store_is_protected():
    classification, reason = _classify(
        Path("/srv/hes-evidence/records/manifest.json"),
        age_days=365.0,
        is_symlink=False,
        registered_worktrees=set(),
    )
    assert classification == "KEEP_EVIDENCE"
    assert "Immutable project evidence store" in reason
