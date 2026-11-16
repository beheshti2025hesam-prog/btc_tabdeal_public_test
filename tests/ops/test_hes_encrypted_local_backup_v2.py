from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "hes_encrypted_local_backup_v2.sh"

def test_local_backup_v2_writes_new_zstd_format_without_overwriting_old_archives():
    text = SCRIPT.read_text()
    assert 'base="hes-full-$stamp.tar.zst.gpg"' in text
    assert 'zstd -q -T1 -9' in text
    assert 'hes_backup_archive_verify_v1.py' in text
    assert 'zstd -q -dc | tar -tf -' in text
    assert 'refusing to overwrite an existing backup' in text
    assert 'gzip -1' not in text

def test_local_backup_v2_checks_active_and_rollback_release_targets():
    text = SCRIPT.read_text()
    assert '[[ -L "$ROOT/current" && -L "$ROOT/current-before-4329a3df" ]]' in text
    assert 'ACTIVE_REL=' in text and 'ROLLBACK_REL=' in text
    assert '--active-release "$ACTIVE_REL"' in text
    assert '--rollback-release "$ROLLBACK_REL"' in text

def test_local_backup_v2_uses_mixed_format_retention_planner():
    text = SCRIPT.read_text()
    assert "hes_backup_retention_v2.py" in text
    assert "hes-full-*.tar.gz.gpg" in text
    assert "hes-full-*.tar.zst.gpg" in text

def test_local_backup_v2_keeps_network_isolation_outside_script():
    text = SCRIPT.read_text()
    for forbidden in ("rclone", "curl ", "wget "):
        assert forbidden not in text
