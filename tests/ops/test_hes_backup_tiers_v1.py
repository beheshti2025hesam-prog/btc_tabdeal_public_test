from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_dropbox_capsule_is_small_and_excludes_full_restic_and_bulk_evidence():
 s=(ROOT/"scripts/ops/hes_dropbox_recovery_capsule_v1.sh").read_text()
 assert "MAX_BYTES=$((64 * 1024 * 1024))" in s
 assert "cd /" in s
 assert "zstd -q -T1 -19 --long=27" in s
 assert "restic-production-v1/repo" not in s
 assert "srv/hes-evidence" not in s
 assert "CAPSULE_CONTENT_VALIDATION_OK" in s
 assert "x.strip().rstrip(\"/\")" in s
def test_capsule_publish_is_immutable_quota_gated_and_non_destructive():
 s=(ROOT/"scripts/ops/hes_dropbox_recovery_capsule_publish_v1.sh").read_text()
 assert "rclone copyto" in s and "--immutable" in s and "RESERVE=" in s
 assert "REMOTE_DELETE=NONE" in s and "rclone sync" not in s and "--delete" not in s
def test_full_restic_mirror_is_separate_and_validates_remote_repository():
 s=(ROOT/"scripts/ops/hes_restic_google_drive_sync_v1.sh").read_text()
 assert 'RESTIC_REPOSITORY="rclone:$REMOTE" restic check' in s
 assert "rclone copy " in s and "rclone check " in s and "rclone sync" not in s
 assert "RESTIC_DRIVE_REMOTE_NOT_CONFIGURED" in s
