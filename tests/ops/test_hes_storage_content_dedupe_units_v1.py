from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dedupe_timer_is_daily_and_runs_after_backup_windows():
    timer = (ROOT / "deploy/systemd/hes-storage-content-dedupe.timer").read_text()
    assert "OnCalendar=*-*-* 04:05:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "hes-storage-content-dedupe.service" in timer


def test_dedupe_service_is_fail_closed_and_scoped_to_immutable_archives():
    service = (ROOT / "deploy/systemd/hes-storage-content-dedupe.service").read_text()
    assert "ProtectSystem=strict" in service
    assert "ProtectHome=read-only" in service
    assert "/var/backups/hes-trade-agent/offsite-staging" in service
    assert "/srv/hes-evidence/operations/storage-lifecycle" in service
    assert "--min-age-seconds 3600 --apply" in service
    assert "NoNewPrivileges=true" in service