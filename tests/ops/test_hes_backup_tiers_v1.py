from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_dropbox_capsule_is_small_and_excludes_full_restic_and_bulk_evidence():
 s=(ROOT/"scripts/ops/hes_dropbox_recovery_capsule_v1.sh").read_text()
 assert "MAX_BYTES=$((24 * 1024 * 1024))" in s
 assert "cd /" in s
 assert "zstd -q -T1 -19 --long=27" in s
 assert "restic-production-v1/repo" not in s
 assert "srv/hes-evidence" not in s
 assert "CAPSULE_CONTENT_VALIDATION_OK" in s
 assert "x.strip().rstrip(\"/\")" in s
 assert "CAPSULE_ISOLATED_RESTORE_PASS" in s
 assert "--transform=" in s
def test_capsule_publish_is_immutable_quota_gated_and_non_destructive():
 s=(ROOT/"scripts/ops/hes_dropbox_recovery_capsule_publish_v1.sh").read_text()
 assert "rclone copyto" in s and "--immutable" in s and "RESERVE=" in s
 assert "REMOTE_DELETE_SCOPE=VERSIONED_RECOVERY_CAPSULES_ONLY" in s and "rclone sync" not in s and "--delete" not in s
def test_full_restic_mirror_is_separate_and_validates_remote_repository():
 s=(ROOT/"scripts/ops/hes_restic_google_drive_sync_v1.sh").read_text()
 assert 'RESTIC_REPOSITORY="$REMOTE_REPO"' in s and 'restic check --read-data-subset=1/20' in s
 assert "restic copy --from-repo" in s
 assert "--copy-chunker-params" in s
 assert "restic forget" in s
 assert "RESTIC_DRIVE_SNAPSHOT_COVERAGE_OK" in s
 assert "rclone size" in s and "rclone sync" not in s
 assert "rclone copy " not in s and "rclone check" not in s
 assert "RESTIC_DRIVE_REMOTE_NOT_CONFIGURED" in s


def test_daily_capsule_cycle_and_scoped_remote_rotation_are_sandboxed():
    cycle = (ROOT / "scripts/ops/hes_dropbox_recovery_capsule_cycle_v1.sh").read_text()
    publish = (ROOT / "scripts/ops/hes_dropbox_recovery_capsule_publish_v1.sh").read_text()
    service = (ROOT / "deploy/systemd/hes-dropbox-recovery-capsule.service").read_text()
    timer = (ROOT / "deploy/systemd/hes-dropbox-recovery-capsule.timer").read_text()
    assert 'PUBLISH_ARGS+=(--enforce-20pct)' in cycle
    assert "i=7" in cycle
    assert "CAPSULE_REMOTE_READBACK_PASS" in publish
    assert "i=2" in publish
    assert "hes-recovery-capsule-" in publish
    assert "rclone deletefile" in publish
    assert "rclone sync" not in publish
    assert "REMOTE_DELETE_SCOPE=VERSIONED_RECOVERY_CAPSULES_ONLY" in publish
    assert "CAPSULE_20PCT_ACCOUNT_BUDGET_BLOCK" in publish
    assert "used+bytes<=total/5" in publish
    assert "--enforce-20pct" in cycle
    assert "enforce-dropbox-20pct" in cycle
    assert "ProtectSystem=strict" in service
    assert "ProtectHome=read-only" in service
    assert "CPUWeight=20" in service
    assert "04:00:00 UTC" in timer


def test_google_drive_full_restic_timer_is_separate_and_safe_to_leave_disabled():
    service = (ROOT / "deploy/systemd/hes-restic-google-drive-sync.service").read_text()
    timer = (ROOT / "deploy/systemd/hes-restic-google-drive-sync.timer").read_text()
    script = (ROOT / "scripts/ops/hes_restic_google_drive_sync_v1.sh").read_text()
    assert "ConditionPathExists=/root/.config/rclone/rclone.conf" in service
    assert "ProtectSystem=strict" in service
    assert "ProtectHome=read-only" in service
    assert "ReadWritePaths=/run/hes-restic /run/lock" in service
    assert "03:30:00 UTC" in timer
    assert "RESTIC_DRIVE_REMOTE_NOT_CONFIGURED" in script


def test_weekly_remote_restore_drill_checks_live_release_trees_and_writes_evidence():
    script = (ROOT / "scripts/ops/hes_restic_google_drive_restore_drill_v1.sh").read_text()
    service = (ROOT / "deploy/systemd/hes-restic-google-drive-restore-drill.service").read_text()
    timer = (ROOT / "deploy/systemd/hes-restic-google-drive-restore-drill.timer").read_text()
    assert "restic restore" in script
    assert "RESTIC_DRIVE_ISOLATED_RESTORE_PASS" in script
    assert "pointer_paths" in script
    assert "release_paths" in script
    assert "result\\\":\\\"PASS" in script
    assert "ProtectSystem=strict" in service
    assert "ProtectHome=read-only" in service
    assert "ReadWritePaths=/run/hes-restic /run/lock /var/lib/hes-operational-health" in service
    assert "Sun *-*-* 05:00:00 UTC" in timer
