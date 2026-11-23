from datetime import datetime, timezone, timedelta
import json
from pathlib import Path

from scripts.ops.hes_restic_retention_apply_v1 import (
    EXPECTED_HOST, REPLACEMENT_ATTESTATION_SCHEMA,
    validate_replacement_host_attestation,
)

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
PATHS = ["/etc/hes-trade-agent", "/opt/hes-trade-agent", "/srv/hes-evidence"]


def attestation(snapshot_id="snapshot-1", recovery_host="replacement-vps-01", created_at=None):
    return {
        "schema": REPLACEMENT_ATTESTATION_SCHEMA,
        "status": "PASS",
        "source_snapshot_id": snapshot_id,
        "source_host": EXPECTED_HOST,
        "recovery_host_id": recovery_host,
        "recovery_host_fingerprint": "a" * 64,
        "created_at_utc": (created_at or NOW).isoformat(),
        "checks": {
            "repository_open": "PASS", "key_unlocked": "PASS", "full_scope_restore": "PASS",
            "release_manifests": "PASS", "git_strategy_ref": "PASS", "host_config": "PASS",
            "journals_and_evidence": "PASS", "boot_smoke_test": "PASS",
        },
        "restored_roots": PATHS,
        "restored_file_count": 1234,
        "restored_bytes": 987654321,
        "archive_sha256": "b" * 64,
        "restore_manifest_sha256": "c" * 64,
        "restic_version": "0.17.3",
    }


def files(tmp_path, data):
    a = tmp_path / "attestation.json"
    s = tmp_path / "attestation.sig"
    p = tmp_path / "pinned.pub"
    a.write_text(json.dumps(data), encoding="utf-8")
    s.write_bytes(b"signature")
    p.write_text("ed25519 public key placeholder", encoding="utf-8")
    return a, s, p


def verified(*args, **kwargs):
    return True, "signature_verified_test_fixture"


def test_valid_signed_independent_host_attestation_passes(tmp_path):
    a, s, p = files(tmp_path, attestation())
    ok, reason = validate_replacement_host_attestation(a, s, p, "snapshot-1", PATHS, NOW, verified)
    assert ok is True
    assert reason == "replacement_host_restore_attestation_verified"


def test_missing_or_invalid_signature_blocks_retention(tmp_path):
    a, s, p = files(tmp_path, attestation())
    ok, reason = validate_replacement_host_attestation(a, s, p, "snapshot-1", PATHS, NOW,
        lambda *args: (False, "replacement_host_attestation_signature_invalid"))
    assert ok is False and "signature_invalid" in reason


def test_same_host_cannot_satisfy_independent_restore_gate(tmp_path):
    a, s, p = files(tmp_path, attestation(recovery_host=EXPECTED_HOST))
    ok, reason = validate_replacement_host_attestation(a, s, p, "snapshot-1", PATHS, NOW, verified)
    assert ok is False and "not_independent" in reason


def test_snapshot_or_root_set_mismatch_blocks_retention(tmp_path):
    a, s, p = files(tmp_path, attestation(snapshot_id="older-snapshot"))
    ok, reason = validate_replacement_host_attestation(a, s, p, "snapshot-1", PATHS, NOW, verified)
    assert ok is False and "snapshot_mismatch" in reason
    a, s, p = files(tmp_path, attestation())
    ok, reason = validate_replacement_host_attestation(a, s, p, "snapshot-1", PATHS + ["/extra"], NOW, verified)
    assert ok is False and "root_set_mismatch" in reason


def test_stale_or_incomplete_restore_attestation_blocks_retention(tmp_path):
    stale = NOW - timedelta(days=2)
    a, s, p = files(tmp_path, attestation(created_at=stale))
    ok, reason = validate_replacement_host_attestation(a, s, p, "snapshot-1", PATHS, NOW, verified)
    assert ok is False and "stale" in reason
    broken = attestation()
    broken["checks"]["boot_smoke_test"] = "FAIL"
    a, s, p = files(tmp_path, broken)
    ok, reason = validate_replacement_host_attestation(a, s, p, "snapshot-1", PATHS, NOW, verified)
    assert ok is False and "checks_incomplete" in reason