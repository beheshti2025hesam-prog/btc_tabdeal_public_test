from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "scripts" / "ops"
DEPLOY = ROOT / "deploy" / "systemd"


def test_local_restic_backup_has_43_recovery_roots_and_scope_safe_retention():
    source = (OPS / "hes_restic_incremental_backup_v1.sh").read_text()
    block = re.search(r"ROOTS=\((.*?)\n\)", source, re.S)
    assert block
    roots = block.group(1).split()
    assert len(roots) == 43
    assert '"$ACTIVE" "$ROLLBACK"' in source
    for p in ("/usr/local/sbin/hes-operational-healthcheck", "/usr/local/sbin/hes-restic-incremental-backup", "/usr/local/sbin/hes-restic-production-dropbox-sync"):
        assert p in roots
    assert "--group-by host,paths" in source
    assert "--keep-daily 7 --keep-weekly 4 --keep-monthly 6 --keep-yearly 2" in source
    assert "--read-data-subset=1/20" in source
    assert "RESTIC_NO_VALID_NON_FUTURE_43_ROOT_FULL_SCOPE_SNAPSHOT" in source


def test_restic_secret_is_not_included_in_backup_roots():
    source = (OPS / "hes_restic_incremental_backup_v1.sh").read_text()
    roots = source.split("ROOTS=(", 1)[1].split("\n)", 1)[0]
    assert "/root/.config/hes-backup/passphrase" not in roots
    assert "RESTIC_PASSWORD_FILE=\"$KEY\"" in source


def test_production_dropbox_sync_has_quota_reserve_and_remote_verification():
    source = (OPS / "hes_restic_production_dropbox_sync_v1.sh").read_text()
    assert "RESERVE_BYTES=$((128 * 1024 * 1024))" in source
    assert "free + remote_bytes >= local_bytes + RESERVE_BYTES" in source
    assert "restic-production-v1/repo" in source
    assert "len(s.get('paths') or [])!=43" in source
    assert "rclone copy" in source
    assert "rclone sync" not in source
    assert "--delete-after" not in source
    assert "RESTIC_PRODUCTION_REMOTE_SIZE_MISMATCH" in source
    assert "rclone check" in source
    assert "restic-compact-v1/repo" not in source


def test_systemd_units_are_sandboxed_and_timers_are_separate():
    sync_service = (DEPLOY / "hes-restic-production-dropbox-sync.service").read_text()
    sync_timer = (DEPLOY / "hes-restic-production-dropbox-sync.timer").read_text()
    local_service = (DEPLOY / "hes-encrypted-local-backup.service").read_text()
    local_timer = (DEPLOY / "hes-encrypted-local-backup.timer").read_text()
    assert "ProtectSystem=strict" in sync_service
    assert "ProtectHome=read-only" in sync_service
    assert "ReadOnlyPaths=/root/.config/hes-backup" in sync_service
    assert "restic-production-v1/repo" in sync_service
    assert "03:30:00 UTC" in sync_timer
    assert "02:30:00 UTC" in local_timer
    assert "hes-restic-incremental-backup" in local_service


def test_cache_exclusions_are_scoped_to_project_and_preserve_evidence_cache_names():
    source = (OPS / "hes_restic_incremental_backup_v1.sh").read_text()
    block = source.split("printf '%s\\n' \\", 1)[1].split(' > "$EXCLUDE"', 1)[0]
    patterns = re.findall(r"'([^']+)'", block)
    assert patterns
    assert all(pattern.startswith("/opt/hes-trade-agent/") for pattern in patterns)
    assert "/opt/hes-trade-agent/**/__pycache__" in patterns
    assert not any(pattern.startswith("**/") for pattern in patterns)
    assert not any("/srv/hes-evidence" in pattern for pattern in patterns)
