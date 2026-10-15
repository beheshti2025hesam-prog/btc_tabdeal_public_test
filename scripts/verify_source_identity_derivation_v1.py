#!/usr/bin/env python3
"""Independently derive and compare every locked source-identity record."""
from __future__ import annotations
import base64, hashlib, json, os, subprocess, sys, urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GH_TOKEN"]
ROOT = Path(os.environ["GITHUB_WORKSPACE"])
MANIFEST_PATH = ROOT / "evidence/source_identity_reconciliation_v1.json"
LOCK_PATH = ROOT / "evidence/source_identity_reconciliation_v1.lock.json"
COMPUTATION_COMMIT = "4a197977a82633468cb65d9c8cb1e91740bc3295"
COMPUTATION_ROOT = Path(os.environ["HES_LOCKED_COMPUTATION_ROOT"])
KEY_FIELDS = ["timestamp", "sequence_first", "sequence_last", "entry_price", "exit_price", "gross_return", "direction"]

def api_json(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)

def git_object_sha(raw):
    return hashlib.sha1(f"blob {len(raw)}".encode() + bytes([0]) + raw).hexdigest()

def git_blob(sha):
    obj = api_json(f"https://api.github.com/repos/{REPO}/git/blobs/{sha}")
    assert obj.get("sha") == sha and obj.get("encoding") == "base64", f"Unexpected Git blob response for {sha}"
    raw = base64.b64decode("".join(obj["content"].split()), validate=True)
    assert git_object_sha(raw) == sha, f"Git blob content hash mismatch for {sha}"
    return raw

def tree_blob(commit, path, expected_sha):
    tree = api_json(f"https://api.github.com/repos/{REPO}/git/trees/{commit}?recursive=1")
    assert not tree.get("truncated"), f"Git tree truncated for {commit}"
    files = {item["path"]: item["sha"] for item in tree.get("tree", [])}
    assert files.get(path) == expected_sha, f"{path} at {commit}: {files.get(path)!r} != {expected_sha!r}"

def record_key(row):
    return tuple(row[field] for field in KEY_FIELDS)

def recompute(csv_path, contract_path, source, contract_source, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update({
        "HES_FROZEN_CSV": str(csv_path),
        "LOCKED_RAW_BLOB_SHA": source["raw_blob_sha"],
        "LOCKED_RAW_SOURCE_COMMIT": source["source_commit"],
        "PROTOCOL_CONTRACT_SOURCE_COMMIT": contract_source["source_commit"],
        "PROTOCOL_CONTRACT_BLOB_SHA": contract_source["blob_sha"],
        "PROTOCOL_CONTRACT_PATH": str(contract_path),
    })
    subprocess.run(
        [sys.executable, str(COMPUTATION_ROOT / "scripts/protocol_reconciliation_independent_snapshot_v1.py")],
        cwd=output_dir, env=env, check=True, timeout=240,
    )
    return json.loads((output_dir / "protocol_reconciliation_full_population_audit.json").read_text())

manifest_raw = MANIFEST_PATH.read_bytes()
manifest = json.loads(manifest_raw)
lock = json.loads(LOCK_PATH.read_text())
assert manifest["schema"] == "hes.source_identity_reconciliation.v1"
assert lock["status"] == "SOURCE_IDENTITY_RECONCILIATION_HASH_LOCKED"
assert lock["artifact_path"] == "evidence/source_identity_reconciliation_v1.json"
assert lock["artifact_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
assert lock["artifact_bytes"] == len(manifest_raw)
assert lock["record_count"] == len(manifest["records"]) == 42

sources = manifest["sources"]
prior_source, current_source, contract_source = sources["prior"], sources["current"], sources["protocol_contract"]
tree_blob(prior_source["source_commit"], "data/trades.csv", prior_source["raw_blob_sha"])
tree_blob(current_source["source_commit"], "data/trades.csv", current_source["raw_blob_sha"])
tree_blob(contract_source["source_commit"], "evidence/protocol_reconciliation_v1.json", contract_source["blob_sha"])

prior_raw = git_blob(prior_source["raw_blob_sha"])
current_raw = git_blob(current_source["raw_blob_sha"])
contract_raw = git_blob(contract_source["blob_sha"])
assert git_object_sha(prior_raw) == prior_source["raw_blob_sha"]
assert git_object_sha(current_raw) == current_source["raw_blob_sha"]
assert git_object_sha(contract_raw) == contract_source["blob_sha"]
assert subprocess.check_output(["git", "-C", str(COMPUTATION_ROOT), "rev-parse", "HEAD"], text=True).strip() == COMPUTATION_COMMIT

with TemporaryDirectory(prefix="hes-source-identity-") as tmp:
    tmp_path = Path(tmp)
    prior_csv, current_csv, contract_path = tmp_path / "prior_trades.csv", tmp_path / "current_trades.csv", tmp_path / "protocol_contract.json"
    prior_csv.write_bytes(prior_raw)
    current_csv.write_bytes(current_raw)
    contract_path.write_bytes(contract_raw)
    prior_audit = recompute(prior_csv, contract_path, prior_source, contract_source, tmp_path / "prior")
    current_audit = recompute(current_csv, contract_path, current_source, contract_source, tmp_path / "current")

    derived = {
        "prior_14_survivor": prior_audit["winners"],
        "current_28_winner": current_audit["winners"],
    }
    assert len(derived["prior_14_survivor"]) == 14, "Prior source did not reproduce 14 survivors"
    assert len(derived["current_28_winner"]) == 28, "Current source did not reproduce 28 winners"
    for audit, source in [(prior_audit, prior_source), (current_audit, current_source)]:
        assert audit["protocol"]["snapshot_data_blob_sha"] == source["raw_blob_sha"]
        assert audit["protocol"]["protocol_contract_blob_sha"] == contract_source["blob_sha"]

    groups = {
        lineage: [row for row in manifest["records"] if row["lineage"] == lineage]
        for lineage in derived
    }
    matches = []
    for lineage, rows in derived.items():
        actual_rows = groups[lineage]
        assert len(actual_rows) == (14 if lineage.startswith("prior") else 28)
        expected_by_key = {record_key(row): row for row in rows}
        actual_by_key = {record_key(row): row for row in actual_rows}
        assert len(expected_by_key) == len(rows), f"Duplicate derived keys: {lineage}"
        assert len(actual_by_key) == len(actual_rows), f"Duplicate manifest keys: {lineage}"
        missing, extra = set(expected_by_key) - set(actual_by_key), set(actual_by_key) - set(expected_by_key)
        assert not missing and not extra, f"Record key mismatch {lineage}: missing={len(missing)} extra={len(extra)}"
        for k, row in actual_by_key.items():
            derived_row = expected_by_key[k]
            assert row["fold_index"] == derived_row["fold_index"], f"Fold mismatch: {lineage} {k}"
            assert row["evaluated"] is derived_row["evaluated"] is True
            matches.append({
                "lineage": lineage, "key": {field: row[field] for field in KEY_FIELDS},
                "fold_index": row["fold_index"],
                "source_blob_sha": prior_source["raw_blob_sha"] if lineage.startswith("prior") else current_source["raw_blob_sha"],
                "match": "EXACT",
            })

    assert {record_key(r) for r in derived["prior_14_survivor"]}.isdisjoint(
        {record_key(r) for r in derived["current_28_winner"]}
    ), "Unexpected cross-lineage exact match"
    assert manifest["counts"] == {"prior_survivor_records": 14, "current_winner_records": 28, "exact_record_key_matches": 0}

    report = {
        "schema": "hes.source_identity_derivation_verification.v1",
        "status": "PASS_EXACT_RECORD_LEVEL_REPRODUCTION",
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "computation_commit": COMPUTATION_COMMIT,
        "source_blobs": {
            "prior": {"source_commit": prior_source["source_commit"], "git_blob_sha": prior_source["raw_blob_sha"], "bytes": len(prior_raw), "sha256": hashlib.sha256(prior_raw).hexdigest(), "recomputed_winners": 14},
            "current": {"source_commit": current_source["source_commit"], "git_blob_sha": current_source["raw_blob_sha"], "bytes": len(current_raw), "sha256": hashlib.sha256(current_raw).hexdigest(), "recomputed_winners": 28},
            "protocol_contract": {"source_commit": contract_source["source_commit"], "git_blob_sha": contract_source["blob_sha"], "bytes": len(contract_raw), "sha256": hashlib.sha256(contract_raw).hexdigest()},
        },
        "record_counts": {"prior": 14, "current": 28, "exact_matches": 0, "exact_field_matches": len(matches)},
        "records": matches,
        "claim_boundary": {"feature_extraction_performed": False, "effective_evidence_performed": False, "threshold_changed": False, "winner_reselected": False, "records_deleted": False, "promotion": False, "live_execution": False},
    }
    report_path = ROOT / "evidence/source_identity_derivation_verification_v1.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_raw = report_path.read_bytes()
    report_lock = {
        "status": "SOURCE_IDENTITY_DERIVATION_HASH_LOCKED",
        "artifact_path": "evidence/source_identity_derivation_verification_v1.json",
        "artifact_sha256": hashlib.sha256(report_raw).hexdigest(),
        "artifact_bytes": len(report_raw),
        "source_manifest_sha256": report["manifest_sha256"],
        "computation_commit": COMPUTATION_COMMIT,
        "record_count": len(matches),
        "exact_field_matches": len(matches),
        "claim_boundary": report["claim_boundary"],
    }
    (ROOT / "evidence/source_identity_derivation_verification_v1.lock.json").write_text(
        json.dumps(report_lock, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report_lock, indent=2, sort_keys=True))
