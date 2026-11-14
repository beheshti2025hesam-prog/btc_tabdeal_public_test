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
    assert "MAX_BYTES=$((1792 * 1024 * 1024))" in source
    subprocess.run(["bash", "-n", str(ROOT / "scripts/hes-dropbox-offsite-build.sh")], check=True)


def test_offsite_cycle_quota_guard_and_evidence_manifest_are_required():
    source = (ROOT / "scripts/hes-dropbox-offsite-cycle.sh").read_text(encoding="utf-8")
    assert "MAX_BYTES=$((1792 * 1024 * 1024))" in source
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