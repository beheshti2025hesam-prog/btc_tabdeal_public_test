from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "archive/vps_github_identity_reconciliation_v2.json"
LOCK_PATH = ROOT / "archive/vps_github_identity_reconciliation_v2.lock.json"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


raw = ARTIFACT_PATH.read_bytes()
try:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    artifact = json.loads(raw)
except (OSError, json.JSONDecodeError) as exc:
    fail(f"artifact or lock is unreadable/invalid JSON: {exc}")

sha256 = hashlib.sha256(raw).hexdigest()
git_blob_sha1 = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()

if lock.get("status") != "LOCKED":
    fail("lock status is not LOCKED")
if lock.get("artifact_path") != str(ARTIFACT_PATH.relative_to(ROOT)):
    fail("lock points to a different artifact path")
if lock.get("artifact_bytes") != len(raw):
    fail("artifact byte count does not match lock")
if lock.get("artifact_sha256") != sha256:
    fail("artifact SHA-256 does not match lock")
if lock.get("artifact_git_blob_sha1") != git_blob_sha1:
    fail("artifact Git blob SHA-1 does not match lock")
if artifact.get("artifact_id") != "HES-VPS-GITHUB-IDENTITY-RECONCILIATION-V2":
    fail("unexpected artifact ID")
if artifact.get("schema") != "hes.vps_github_identity_reconciliation.v2":
    fail("unexpected artifact schema")

archive = artifact.get("archive_reconciliation", {})
if archive.get("archive_files_expected_found") != 16:
    fail("archive count is not the independently reconciled 16")
if archive.get("bytes_sha256_git_blob_matches") != 16:
    fail("not all 16 archive identities are matched")
if archive.get("archive_to_active_sequence_intersection") != 0:
    fail("archive/active exact sequence intersection is not zero")

tail = artifact.get("current_tail_reconciliation", {})
if tail.get("active_equals_checkpoint_bytes") is not True:
    fail("active CSV does not match checkpoint bytes")
if tail.get("base_is_exact_byte_prefix") is not True:
    fail("base-to-checkpoint prefix identity is not verified")
if tail.get("source_artifact_status") != "LOCK_PENDING":
    fail("historical current-tail gate status was silently changed")

observations = artifact.get("observation_artifacts", {})
if observations.get("manifest_json", {}).get("parse") != "FAIL_TRAILING_LITERAL_BACKSLASH_N":
    fail("manifest syntax defect was silently removed from the audit")
if observations.get("run_ledger_jsonl", {}).get("parse") != "FAIL_TRAILING_LITERAL_BACKSLASH_N":
    fail("run-ledger syntax defect was silently removed from the audit")

writer = artifact.get("single_writer_reconciliation", {})
if writer.get("lock_hash_matches_proof") is not False:
    fail("single-writer lock mismatch is not preserved")
if writer.get("result") != "OPEN_STALE_LOCK_PROOF_HASH_MISMATCH_WRITER_ATTRIBUTION_UNRESOLVED":
    fail("single-writer gate was incorrectly closed")

safety = artifact.get("safety_boundary", {})
for key in ("source_data_modified", "historical_artifacts_modified", "collector_started_or_enabled",
            "continuous_48h_observation_running", "feature_extraction", "effective_evidence_calculation",
            "trading_authorized"):
    if safety.get(key) is not False:
        fail(f"safety boundary {key!r} must remain false")

print(json.dumps({
    "status": "PASS",
    "artifact_sha256": sha256,
    "artifact_bytes": len(raw),
    "git_blob_sha1": git_blob_sha1,
    "archive_identity": "PASS_16_OF_16",
    "current_tail_prefix": "PASS",
    "observation_artifact_syntax": "BLOCKED_AS_RECORDED",
    "single_writer": "OPEN_AS_RECORDED",
    "execution": "OFF"
}, sort_keys=True))
