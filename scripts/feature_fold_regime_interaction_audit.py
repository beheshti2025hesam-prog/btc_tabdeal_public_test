#!/usr/bin/env python3
"""Frozen feature x fold x regime interaction audit; evidence-only."""
import json, math, statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"14_vs_1035_contrast_audit.json"
OUT=ROOT/"feature_fold_regime_interaction_audit.json"
FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]
BLOB="1a44d52a0588deb765bbbea04bfb5783dcb1050b"
COMMIT="b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
RUN=36489452534

def smd(a,b):
    if len(a)<2 or len(b)<2: return None
    va=statistics.pvariance(a); vb=statistics.pvariance(b); d=math.sqrt((va+vb)/2)
    return (statistics.fmean(a)-statistics.fmean(b))/d if d else 0.0

def one_group(rows, winners, controls):
    out={}
    for f in FEATURES:
        a=[r[f] for r in winners]; b=[r[f] for r in controls]
        out[f]={"winner_n":len(a),"control_n":len(b),"smd":smd(a,b)}
    return out

def main():
    d=json.loads(SRC.read_text())
    assert d["protocol"]["snapshot_data_blob_sha"]==BLOB
    assert d["protocol"]["snapshot_source_commit"]==COMMIT
    assert d["protocol"]["snapshot_run_id"]==RUN
    assert d["counts"]=={"winners_gt_14bps":14,"controls_le_14bps":1035}
    rows=d["winners"]+[] 
    # Controls are reconstructed from fold/regime/direction population only where
    # the source audit does not retain controls. Therefore this audit uses the
    # immutable winner rows for concentration and the source's categorical counts
    # for coverage, without inventing control feature values.
    result={"status":"evidence-only","lineage":{"snapshot_data_blob_sha":BLOB,"snapshot_source_commit":COMMIT,"snapshot_source_run_id":RUN},
            "population":{"winners":14,"controls":1035,"evaluated_oos":1049},
            "winner_feature_by_fold":{},"winner_feature_by_regime":{},
            "winner_feature_by_fold_regime":{},"coverage":{},
            "claim_boundary":{"control_feature_values_not_reconstructed":True,"signal_created":False,"threshold_tuned":False,"model_fitting":False,"live_execution":False}}
    for fold in range(8):
        w=[r for r in rows if r["fold_index"]==fold]
        result["winner_feature_by_fold"][str(fold)]={"winner_n":len(w),"features":{f:{"mean":statistics.fmean([r[f] for r in w]),"median":statistics.median([r[f] for r in w])} for f in FEATURES} if w else {}}
    for regime in sorted(set(r["fold_regime"] for r in rows)):
        w=[r for r in rows if r["fold_regime"]==regime]
        result["winner_feature_by_regime"][regime]={"winner_n":len(w),"features":{f:{"mean":statistics.fmean([r[f] for r in w]),"median":statistics.median([r[f] for r in w])} for f in FEATURES}}
    for fold in range(8):
        for regime in ["range","uptrend","downtrend"]:
            w=[r for r in rows if r["fold_index"]==fold and r["fold_regime"]==regime]
            if w:
                result["winner_feature_by_fold_regime"][f"{fold}:{regime}"]={"winner_n":len(w),"features":{f:{"mean":statistics.fmean([r[f] for r in w]),"median":statistics.median([r[f] for r in w])} for f in FEATURES}}
    result["coverage"]={"winner_counts_by_fold":d["categorical"]["fold_winners"],"winner_counts_by_regime":d["categorical"]["regime_winners"],"winner_counts_by_direction":d["categorical"]["direction_winners"],
                         "feature_contrast_smd_full":{f:d["feature_contrast"][f]["smd"] for f in FEATURES},
                         "note":"This layer deliberately does not fabricate fold/regime control feature distributions. Full SMDs come from the frozen 14-vs-1035 contrast; fold/regime tables are winner-side concentration diagnostics."}
    OUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"status":"evidence-only","winner_n":14,"folds":d["categorical"]["fold_winners"],"regimes":d["categorical"]["regime_winners"],"feature_smd_full":result["coverage"]["feature_contrast_smd_full"]},indent=2))
if __name__=="__main__": main()
