from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def test_offsite_builder_requires_and_verifies_independent_evidence_store():
    source = (ROOT / "scripts/hes-dropbox-offsite-build.sh").read_text(encoding="utf-8")
    assert "srv/hes-evidence" in source
    assert "BUILD_REJECTED evidence_store_missing" in source
    assert "evidence_store_incomplete" in source
    assert "expected_evidence_entries" in source
    assert "Required evidence store: /srv/hes-evidence (coverage verified by archive listing)." in source
    assert "MAX_BYTES=$((1536 * 1024 * 1024))" in source
    assert 'base="hes-offsite-core-$stamp.tar.zst.gpg"' in source
    assert "zstd -q -T1 -9" in source
    assert "zstd -t -q" in source
    assert "hes-offsite-decompress.py" in source
    subprocess.run(["bash", "-n", str(ROOT / "scripts/hes-dropbox-offsite-build.sh")], check=True)


def test_offsite_cycle_quota_guard_and_evidence_manifest_are_required():
    source = (ROOT / "scripts/hes-dropbox-offsite-cycle.sh").read_text(encoding="utf-8")
    assert "MAX_BYTES=$((1536 * 1024 * 1024))" in source
    assert 'REMOTE_FILE="$REMOTE_DIR/hes-offsite-latest.tar.zst.gpg"' in source
    assert 'LEGACY_REMOTE_FILE="$REMOTE_DIR/hes-offsite-latest.tar.gz.gpg"' in source
    assert "REMOTE_OBJECT_RENAME_START" in source
    assert "hes-offsite-decompress.py" in source
    assert "hes-offsite-latest.tar.zst.gpg.sha256" in source
    assert "free_bytes + remote_size >= size + RESERVE_BYTES" in source
    assert "EVIDENCE_STORE_COVERAGE_MISSING" in source
    assert "verify_remote_hash" in source
    assert "tail -n +3" in source
    subprocess.run(["bash", "-n", str(ROOT / "scripts/hes-dropbox-offsite-cycle.sh")], check=True)


def test_backup_manager_requires_local_and_offsite_evidence_coverage():
    source = (ROOT / "scripts/ops/hes_smart_cleanup_manager_v1.py").read_text(encoding="utf-8")
    assert '"local_evidence_store_covered": False' in source
    assert '"offsite_evidence_store_covered": False' in source
    assert 'backups.get("local_evidence_store_covered")' in source
    assert 'backups.get("offsite_evidence_store_covered")' in source

def test_offsite_builder_keeps_generated_recovery_metadata_outside_checkout():
    source = (ROOT / "scripts/hes-dropbox-offsite-build.sh").read_text(encoding="utf-8")
    assert 'SNAPSHOT_DIR="$OUTDIR/recovery-metadata/offsite-dependency-snapshot"' in source
    assert 'SNAPSHOT_DIR="$ROOT/docs/checkpoints/offsite-dependency-snapshot"' not in source
    assert "var/backups/hes-trade-agent/offsite-staging/recovery-metadata" in source
    assert "generated outside the application checkout" in source
    subprocess.run(["bash", "-n", str(ROOT / "scripts/hes-dropbox-offsite-build.sh")], check=True)


def test_offsite_systemd_dropin_removes_project_tree_write_exception():
    dropin = ROOT / "deploy/systemd/hes-dropbox-offsite.service.d/90-dependency-snapshot.conf"
    source = dropin.read_text(encoding="utf-8")
    assert "ReadWritePaths=" in source
    assert "ReadWritePaths=/var/backups/hes-trade-agent/offsite-staging /run/lock /root/.gnupg /root/.config/rclone" in source
    assert "/opt/hes-trade-agent" not in source


def test_zstd_restore_helper_is_published_and_hash_pinned():
    helper = ROOT / "scripts/hes-offsite-decompress.py"
    assert helper.is_file()
    cycle = (ROOT / "scripts/hes-dropbox-offsite-cycle.sh").read_text(encoding="utf-8")
    assert 'cp "$ROOT/scripts/hes-offsite-decompress.py"' in cycle
    assert "hes-offsite-decompress.py.sha256" in cycle
    subprocess.run(["python3", "-m", "py_compile", str(helper)], check=True)
