#!/usr/bin/env python3
"""Deterministic record-level cluster assignment artifact.

Research/provenance only. Reuses the locked snapshot feature vectors produced by
protocol_reconciliation_independent_snapshot_v1.py. No new feature engineering,
selection, evidence, ESS, or promotion calculations are performed.
"""
import hashlib
import json
import math
import os
from pathlib import Path

FEATURES = ["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]
THRESHOLDS = [0.5, 1.0, 1.5, 2.0]
RECORD_KEY = ["timestamp","sequence_first","sequence_last","entry_price","exit_price","gross_return","direction"]

def canonical_key(row):
    vals = [row[k] for k in RECORD_KEY]
    return json.dumps(vals, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

def key_sha(row):
    return hashlib.sha256(canonical_key(row).encode()).hexdigest()

def moments(rows):
    mu = {f: sum(float(r[f]) for r in rows) / len(rows) for f in FEATURES}
    sd = {}
    for f in FEATURES:
        v = [float(r[f]) for r in rows]
        m = mu[f]
        var = sum((x-m)*(x-m) for x in v) / len(v)
        s = math.sqrt(var)
        assert s > 0, f"zero std for {f}"
        sd[f] = s
    return mu, sd

def dist(a,b,mu,sd):
    return math.sqrt(sum(((float(a[f])-float(b[f]))/sd[f])**2 for f in FEATURES))

def components(rows, threshold, mu, sd):
    n=len(rows)
    parent=list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    def union(a,b):
        a,b=find(a),find(b)
        if a != b:
            parent[b]=a
    for i in range(n):
        for j in range(i+1,n):
            if dist(rows[i],rows[j],mu,sd) <= threshold:
                union(i,j)
    groups={}
    for i in range(n):
        groups.setdefault(find(i),[]).append(i)
    return list(groups.values())

def assign(rows, threshold, mu, sd):
    comps=components(rows,threshold,mu,sd)
    members=[]
    for comp in comps:
        ordered=sorted((rows[i] for i in comp), key=canonical_key)
        members.append(ordered)
    members.sort(key=lambda xs: canonical_key(xs[0]))
    out={}
    clusters=[]
    for idx, xs in enumerate(members,1):
        cid=f"C{idx:03d}"
        ids=[]
        for r in xs:
            k=canonical_key(r)
            out[key_sha(r)] = cid
            ids.append({
                "record_key_sha256": key_sha(r),
                "record_key": {k:r[k] for k in RECORD_KEY},
                "source_row": {
                    "timestamp": r["timestamp"],
                    "sequence_first": r["sequence_first"],
                    "sequence_last": r["sequence_last"],
                    "candle_index": r.get("candle_index"),
                    "fold_index": r.get("fold_index"),
                    "fold_regime": r.get("fold_regime"),
                },
                "feature_vector": {f:r[f] for f in FEATURES},
            })
        clusters.append({"cluster_id":cid,"members":ids})
    return clusters

def main():
    prior=json.loads(Path(os.environ.get("PRIOR_SNAPSHOT","prior_1049_protocol.json")).read_text())
    current=json.loads(Path(os.environ.get("CURRENT_SNAPSHOT","current_1027_protocol.json")).read_text())
    prior_rows=prior["winners"]
    current_rows=current["winners"]
    all_rows=prior_rows+current_rows
    mu,sd=moments(all_rows)

    result={
        "schema":"hes.cluster_record_lineage.v1",
        "status":"RECORD_LEVEL_ASSIGNMENT_LOCK_CANDIDATE",
        "purpose":"Durable record_key to deterministic cluster_id mapping; provenance only.",
        "claim_boundary":{
            "new_feature_engineering":False,
            "winner_reselection":False,
            "threshold_search":False,
            "evidence_calculation":False,
            "effective_evidence":False,
            "ess":False,
            "promotion":False
        },
        "algorithm":{
            "distance":"standardized Euclidean over locked five feature fields",
            "link_rule":"pairwise distance <= threshold, connected components",
            "thresholds":THRESHOLDS,
            "cluster_id_rule":"lexicographic order of canonical record key minimum member; IDs assigned C001..",
            "record_key":RECORD_KEY,
            "features":FEATURES,
            "standardization_scope":"pooled prior_14 + current_28 frozen winner rows"
        },
        "sources":{
            "prior_snapshot_path":"prior_1049_protocol.json",
            "current_snapshot_path":"current_1027_protocol.json",
            "prior_source_commit":os.environ["OLD_RAW_SOURCE_COMMIT"],
            "prior_raw_blob_sha":os.environ["OLD_RAW_BLOB_SHA"],
            "current_source_commit":os.environ["CURRENT_RAW_SOURCE_COMMIT"],
            "current_raw_blob_sha":os.environ["CURRENT_RAW_BLOB_SHA"],
            "protocol_contract_commit":os.environ["PROTOCOL_CONTRACT_SOURCE_COMMIT"],
            "protocol_contract_blob_sha":os.environ["PROTOCOL_CONTRACT_BLOB_SHA"],
            "generator_commit":os.environ.get("GENERATOR_COMMIT","")
        },
        "populations":{
            "prior_14":{"count":len(prior_rows)},
            "current_28":{"count":len(current_rows)}
        },
        "standardization_moments":{"mean":mu,"std":sd},
        "assignments":{}
    }
    for label,rows in [("prior_14",prior_rows),("current_28",current_rows)]:
        assert len({key_sha(r) for r in rows})==len(rows), f"duplicate record keys in {label}"
        result["assignments"][label]={}
        for t in THRESHOLDS:
            result["assignments"][label][str(t)]={"clusters":assign(rows,t,mu,sd)}
    Path("cluster_record_lineage_v1.json").write_text(
        json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8"
    )

if __name__=="__main__":
    main()
