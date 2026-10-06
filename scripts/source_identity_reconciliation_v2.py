#!/usr/bin/env python3
"""Fail-closed reconciliation of the locked 42-record identity artifact
against a fresh deterministic recomputation from the exact pinned raw blobs.

Research-only. No winner reselection, tuning, deletion, feature extraction,
effective-evidence calculation, promotion, or live execution.
"""
import hashlib, json, os, subprocess, tempfile
from pathlib import Path

IDENTITY = Path("evidence/source_identity_reconciliation_v1.json")
OUT = Path("evidence/source_identity_reconciliation_v2.json")

KEY = [
    "timestamp","sequence_first","sequence_last",
    "entry_price","exit_price","gross_return","direction"
]

EXPECTED = {
    "prior_14_survivor": 14,
    "current_28_winner": 28,
}

def key(r):
    return tuple(r.get(k) for k in KEY)

def load_identity():
    d=json.loads(IDENTITY.read_text(encoding="utf-8"))
    assert d["status"]=="SOURCE_IDENTITY_LOCKED"
    assert d["record_key"]==KEY
    assert d["counts"]=={
        "prior_survivor_records":14,
        "current_winner_records":28,
        "exact_record_key_matches":0,
    }
    assert len(d["records"])==42
    return d

def fetch_blob(sha, path):
    import base64, urllib.request
    token=os.environ["GH_TOKEN"]
    repo=os.environ["GITHUB_REPOSITORY"]
    req=urllib.request.Request(
        f"https://api.github.com/repos/{repo}/git/blobs/{sha}",
        headers={"Authorization":f"Bearer {token}","Accept":"application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as r:
        d=json.load(r)
    assert d["sha"]==sha
    Path(path).write_bytes(base64.b64decode(d["content"]))

def recompute(raw_path, raw_sha, source_commit, contract_path, out_path):
    env=os.environ.copy()
    env.update({
        "HES_FROZEN_CSV":raw_path,
        "LOCKED_RAW_BLOB_SHA":raw_sha,
        "LOCKED_RAW_SOURCE_COMMIT":source_commit,
        "PROTOCOL_CONTRACT_SOURCE_COMMIT":os.environ["PROTOCOL_CONTRACT_SOURCE_COMMIT"],
        "PROTOCOL_CONTRACT_BLOB_SHA":os.environ["PROTOCOL_CONTRACT_BLOB_SHA"],
        "PROTOCOL_CONTRACT_PATH":contract_path,
    })
    subprocess.run(
        ["python","scripts/protocol_reconciliation_independent_snapshot_v1.py"],
        check=True, env=env,
    )
    Path("protocol_reconciliation_full_population_audit.json").replace(out_path)

def summarize(rows):
    from collections import Counter
    return {
        "count":len(rows),
        "direction_counts":dict(Counter(r["direction"] for r in rows)),
        "fold_counts":{str(k):v for k,v in sorted(Counter(r["fold_index"] for r in rows).items())},
        "gross_sum":sum(r["gross_return"] for r in rows),
    }

def main():
    identity=load_identity()
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        prior_csv=td/"prior.csv"; current_csv=td/"current.csv"; contract=td/"contract.json"
        prior_json=td/"prior.json"; current_json=td/"current.json"
        fetch_blob(identity["sources"]["prior"]["raw_blob_sha"], prior_csv)
        fetch_blob(identity["sources"]["current"]["raw_blob_sha"], current_csv)
        fetch_blob(identity["sources"]["protocol_contract"]["blob_sha"], contract)
        recompute(
            str(prior_csv), identity["sources"]["prior"]["raw_blob_sha"],
            identity["sources"]["prior"]["source_commit"], str(contract), prior_json)
        recompute(
            str(current_csv), identity["sources"]["current"]["raw_blob_sha"],
            identity["sources"]["current"]["source_commit"], str(contract), current_json)
        prior=json.loads(prior_json.read_text())
        current=json.loads(current_json.read_text())

    identity_by={}
    for r in identity["records"]:
        identity_by.setdefault(r["lineage"],[]).append(r)

    recomputed={
        "prior_14_survivor":prior["winners"],
        "current_28_winner":current["winners"],
    }

    comparisons={}
    for lineage in EXPECTED:
        locked={key(r) for r in identity_by[lineage]}
        fresh={key(r) for r in recomputed[lineage]}
        comparisons[lineage]={
            "locked_count":len(locked),
            "recomputed_count":len(fresh),
            "exact_matches":len(locked & fresh),
            "missing_from_locked_identity":len(fresh-locked),
            "extra_in_locked_identity":len(locked-fresh),
            "missing_records":[list(x) for x in sorted(fresh-locked)],
            "extra_records":[list(x) for x in sorted(locked-fresh)],
            "locked_summary":summarize(identity_by[lineage]),
            "recomputed_summary":summarize(recomputed[lineage]),
        }

    current_ok=(comparisons["current_28_winner"]["exact_matches"]==28
                and comparisons["current_28_winner"]["missing_from_locked_identity"]==0
                and comparisons["current_28_winner"]["extra_in_locked_identity"]==0)
    prior_ok=(comparisons["prior_14_survivor"]["exact_matches"]==14
              and comparisons["prior_14_survivor"]["missing_from_locked_identity"]==0
              and comparisons["prior_14_survivor"]["extra_in_locked_identity"]==0)

    result={
        "schema":"hes.source_identity_reconciliation.v2",
        "status":"SOURCE_IDENTITY_RECONCILIATION_CLOSED" if (current_ok and prior_ok) else "SOURCE_IDENTITY_RECONCILIATION_FAILED_CLOSED",
        "purpose":"Record-level reconciliation between the locked identity artifact and deterministic protocol recomputation from the exact pinned raw blobs.",
        "inputs":{
            "identity_artifact_sha256":hashlib.sha256(IDENTITY.read_bytes()).hexdigest(),
            "prior_raw_blob_sha":identity["sources"]["prior"]["raw_blob_sha"],
            "current_raw_blob_sha":identity["sources"]["current"]["raw_blob_sha"],
            "protocol_contract_blob_sha":identity["sources"]["protocol_contract"]["blob_sha"],
            "protocol":{"train":800,"test":400,"step":400,"folds":8,"gross_threshold_bps":14},
        },
        "comparisons":comparisons,
        "claim_boundary":{
            "feature_extraction_performed":False,
            "effective_evidence_performed":False,
            "threshold_changed":False,
            "winner_reselected":False,
            "records_deleted":False,
            "independence_proven":False,
            "promotion":False,
            "live_execution":False,
        },
        "next_gate":"FEATURE_EXTRACTION_FORBIDDEN_UNTIL_RECONCILIATION_CLOSED" if not (current_ok and prior_ok) else "HASH_LOCK_VERIFICATION_REQUIRED_BEFORE_FEATURE_EXTRACTION",
    }
    OUT.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    lock={
        "status":"SOURCE_IDENTITY_RECONCILIATION_V2_HASH_LOCK",
        "artifact_path":str(OUT),
        "artifact_sha256":hashlib.sha256(OUT.read_bytes()).hexdigest(),
        "artifact_bytes":OUT.stat().st_size,
        "reconciliation_status":result["status"],
    }
    Path("evidence/source_identity_reconciliation_v2.lock.json").write_text(
        json.dumps(lock,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
    print(json.dumps(lock,indent=2))

if __name__=="__main__":
    main()
