from datetime import date
from scripts.ops.hes_backup_retention_v2 import plan_retention

def _names(report, key):
    return {row["name"]: row["reason"] for row in report[key]}

def test_mixed_gzip_zstd_same_day_keeps_latest_timestamp_only():
    report = plan_retention([
        "hes-full-20261116T010000Z.tar.gz.gpg",
        "hes-full-20261116T020000Z.tar.zst.gpg",
    ], date(2026, 11, 16))
    keep, delete = _names(report, "keep"), _names(report, "delete")
    assert keep == {"hes-full-20261116T020000Z.tar.zst.gpg": "DAILY_WINDOW"}
    assert delete == {"hes-full-20261116T010000Z.tar.gz.gpg": "SAME_DAY_SUPERSEDED"}
    assert report["delete_authorized"] is False
    assert report["automatic_action"] == "NONE"

def test_daily_window_boundary_and_sunday_weekly_anchor():
    report = plan_retention([
        "hes-full-20261110T010000Z.tar.gz.gpg",
        "hes-full-20261108T010000Z.tar.zst.gpg",
        "hes-full-20261109T010000Z.tar.gz.gpg",
    ], date(2026, 11, 16))
    keep, delete = _names(report, "keep"), _names(report, "delete")
    assert keep["hes-full-20261110T010000Z.tar.gz.gpg"] == "DAILY_WINDOW"
    assert keep["hes-full-20261108T010000Z.tar.zst.gpg"] == "WEEKLY_SUNDAY_ANCHOR"
    assert delete["hes-full-20261109T010000Z.tar.gz.gpg"] == "RETENTION_EXPIRED"

def test_monthly_anchor_is_preserved_after_daily_and_weekly_windows():
    report = plan_retention(["hes-full-20261101T010000Z.tar.zst.gpg"], date(2026, 11, 16))
    assert _names(report, "keep")["hes-full-20261101T010000Z.tar.zst.gpg"] == "MONTHLY_FIRST_DAY_ANCHOR"

def test_future_invalid_and_unparseable_names_fail_closed():
    report = plan_retention([
        "hes-full-20261117T010000Z.tar.zst.gpg",
        "hes-full-20261399T010000Z.tar.gz.gpg",
        "unexpected-backup.tar.zst.gpg",
    ], date(2026, 11, 16))
    keep = _names(report, "keep")
    assert keep["hes-full-20261117T010000Z.tar.zst.gpg"] == "FUTURE_DATED_FAIL_CLOSED"
    assert keep["hes-full-20261399T010000Z.tar.gz.gpg"] == "INVALID_DATE_FAIL_CLOSED"
    assert keep["unexpected-backup.tar.zst.gpg"] == "INVALID_NAME_FAIL_CLOSED"

def test_old_non_anchor_archive_is_marked_expired_not_authorized():
    report = plan_retention(["hes-full-20261020T010000Z.tar.gz.gpg"], date(2026, 11, 16))
    assert _names(report, "delete")["hes-full-20261020T010000Z.tar.gz.gpg"] == "RETENTION_EXPIRED"
    assert report["delete_authorized"] is False
