from datetime import date
from scripts.ops.hes_restic_retention_plan_v1 import (
    EXPECTED_HOST, EXPECTED_TAG, REQUIRED_FULL_PATHS,
    latest_full_snapshot_id, plan_retention,
)

def snap(sid, when, tags=(EXPECTED_TAG,), host=EXPECTED_HOST, paths=None):
    return {"id": sid, "time": when, "tags": list(tags), "hostname": host,
            "paths": sorted(REQUIRED_FULL_PATHS) if paths is None else list(paths)}

def rows(plan, key):
    return {x["snapshot_id"]: x["reason"] for x in plan[key]}

def test_daily_and_same_day_duplicate_policy_only_for_full_snapshots():
    p = plan_retention([
        snap("a", "2026-11-16T01:00:00Z"),
        snap("b", "2026-11-16T02:00:00Z"),
        snap("c", "2026-11-10T01:00:00Z"),
    ], date(2026, 11, 16))
    assert rows(p, "keep") == {"b": "DAILY_WINDOW", "c": "DAILY_WINDOW"}
    assert rows(p, "delete_candidates") == {"a": "SAME_DAY_SUPERSEDED_FULL_SCOPE"}
    assert p["deletion_authorized"] is False
    assert p["full_scope_snapshot_count"] == 3

def test_monthly_anchor_precedes_weekly_sunday_anchor():
    p = plan_retention([snap("monthly", "2026-11-01T01:00:00Z")], date(2026, 11, 16))
    assert rows(p, "keep") == {"monthly": "MONTHLY_FIRST_DAY_ANCHOR"}

def test_weekly_sunday_anchor_and_expired_weekday():
    p = plan_retention([
        snap("sunday", "2026-11-08T01:00:00Z"),
        snap("monday", "2026-11-09T01:00:00Z"),
    ], date(2026, 11, 16))
    assert rows(p, "keep") == {"sunday": "WEEKLY_SUNDAY_ANCHOR"}
    assert rows(p, "delete_candidates") == {"monday": "RETENTION_EXPIRED_FULL_SCOPE"}

def test_out_of_scope_invalid_and_future_snapshots_fail_closed():
    p = plan_retention([
        snap("other-host", "2026-11-16T01:00:00Z", host="other"),
        snap("other-tag", "2026-11-16T01:00:00Z", tags=("test",)),
        snap("bad-time", "not-a-time"),
        snap("future", "2026-11-17T01:00:00Z"),
    ], date(2026, 11, 16))
    assert rows(p, "keep") == {
        "other-host": "OUT_OF_SCOPE_FAIL_CLOSED",
        "other-tag": "OUT_OF_SCOPE_FAIL_CLOSED",
        "bad-time": "INVALID_TIMESTAMP_FAIL_CLOSED",
        "future": "FUTURE_DATED_FAIL_CLOSED",
    }
    assert p["delete_candidates"] == []

def test_newest_full_snapshot_is_preserved_when_all_are_outside_policy():
    p = plan_retention([
        snap("old-a", "2026-01-01T01:00:00Z"),
        snap("old-b", "2026-02-03T01:00:00Z"),
    ], date(2026, 11, 16))
    assert rows(p, "keep") == {"old-b": "LATEST_FULL_SCOPE_AVAILABLE_FAIL_SAFE"}
    assert rows(p, "delete_candidates") == {"old-a": "RETENTION_EXPIRED_FULL_SCOPE"}
    assert p["stale_latest_available"] is True

def test_newer_partial_snapshot_never_supersedes_or_deletes_full_snapshot():
    full = snap("full", "2026-11-16T13:55:53Z")
    partial = snap("evidence-only", "2026-11-16T14:01:05Z", paths=["/srv/hes-evidence"])
    p = plan_retention([full, partial], date(2026, 11, 16))
    assert rows(p, "keep") == {
        "full": "DAILY_WINDOW",
        "evidence-only": f"PARTIAL_SCOPE_NOT_ELIGIBLE_FOR_RETENTION:{len(REQUIRED_FULL_PATHS)-1}_MISSING_PATHS",
    }
    assert p["delete_candidates"] == []
    assert p["latest_full_snapshot_id"] == "full"

def test_latest_full_snapshot_selector_ignores_newer_partial_snapshots():
    full = snap("full-id", "2026-11-16T13:55:53Z")
    partial_a = snap("partial-a", "2026-11-16T14:00:07Z", paths=["/srv/hes-evidence"])
    partial_b = snap("partial-b", "2026-11-16T14:01:05Z", paths=["/srv/hes-evidence"])
    assert latest_full_snapshot_id([full, partial_a, partial_b]) == "full-id"

def test_missing_path_inventory_fails_closed_as_partial():
    incomplete = snap("missing-paths", "2026-11-16T13:55:53Z", paths=None)
    incomplete.pop("paths")
    p = plan_retention([incomplete], date(2026, 11, 16))
    assert rows(p, "keep") == {"missing-paths": f"PARTIAL_SCOPE_NOT_ELIGIBLE_FOR_RETENTION:{len(REQUIRED_FULL_PATHS)}_MISSING_PATHS"}
    assert p["delete_candidates"] == []
    assert p["latest_full_snapshot_id"] is None

def test_defaults_match_live_production_recovery_snapshot_identity():
    assert EXPECTED_HOST == "hes-vps-recovery-v1"
    assert EXPECTED_TAG == "hes-full-recovery-v1"
    assert len(REQUIRED_FULL_PATHS) == 43


def test_latest_full_snapshot_selector_rejects_future_dated_full_snapshots():
    full = snap("valid-full", "2026-11-16T13:55:53Z")
    future = snap("future-full", "2026-11-17T01:00:00Z")
    assert latest_full_snapshot_id([full, future], as_of=date(2026, 11, 16)) == "valid-full"


def test_latest_full_snapshot_selector_returns_none_when_only_full_snapshot_is_future():
    future = snap("future-full", "2026-11-17T01:00:00Z")
    assert latest_full_snapshot_id([future], as_of=date(2026, 11, 16)) is None


def test_legacy_40_root_snapshots_are_partial_after_backup_runner_paths_are_added():
    new_runner_paths = {
        "/usr/local/sbin/hes-operational-healthcheck",
        "/usr/local/sbin/hes-restic-incremental-backup",
        "/usr/local/sbin/hes-restic-production-dropbox-sync",
    }
    legacy_paths = sorted(REQUIRED_FULL_PATHS - new_runner_paths)
    legacy = snap("legacy-40-root", "2026-11-16T14:58:11Z", paths=legacy_paths)
    assert latest_full_snapshot_id([legacy]) is None
    plan = plan_retention([legacy], date(2026, 11, 16))
    assert rows(plan, "keep") == {
        "legacy-40-root": "PARTIAL_SCOPE_NOT_ELIGIBLE_FOR_RETENTION:3_MISSING_PATHS"
    }
    assert plan["delete_candidates"] == []
