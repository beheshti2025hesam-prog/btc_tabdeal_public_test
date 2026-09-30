#!/usr/bin/env python3
"""Fold-3 concentration/independence audit over the frozen E0/E1 evidence chain.

Evidence-only: no threshold/model/signal changes.
"""
from __future__ import annotations
import json, math
from pathlib import Path

FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]
EXPECTED={0:2,1:3,2:2,3:7,4:0,5:0,6:0,7:0}

def smd(a,b):
    import statistics
    va=statistics.pvariance(a) if len(a)>1 else 0.0
    vb=statistics.pvariance(b) if len(b)>1 else 0.0
    d=math.sqrt((va+vb)/2)
    return (statistics.fmean(a)-statistics.fmean(b))/d if d else 0.0

def main():
    e0=json.loads(Path("14_vs_1035_contrast_audit.json").read_text())
    e1=json.loads(Path("embargo_adjusted_fold_regime_independence.json").read_text())
    winners=e0["winners"]
    controls=[r for r in e0["winners"] if False]  # populated from fold stability only below
    assert len(winners)==14
    fold_counts={int(k):int(v) for k,v in e0["categorical"]["fold_winners"].items()}
    assert fold_counts=={k:v for k,v in EXPECTED.items() if v or k in fold_counts}
    f3=[r for r in winners if r["fold_index"]==3]
    remaining=[r for r in winners if r["fold_index"]!=3]
    total_gross=sum(r["gross_return"] for r in winners)
    f3_gross=sum(r["gross_return"] for r in f3)
    remaining_gross=sum(r["gross_return"] for r in remaining)
    full_smd={f:e0["feature_contrast"][f]["smd"] for f in FEATURES}
    no3=e0["stability"]["fold_exclusion"]["3"]
    no3_smd=no3["feature_smd_without_fold"]
    feature_rows={}
    for f in FEATURES:
        full=full_smd[f]
        excl=no3_smd[f]
        feature_rows[f]={
            "full_smd":full,
            "without_fold_3_smd":excl,
            "absolute_smd_retained_ratio":abs(excl)/abs(full) if full else None,
            "smd_change":excl-full,
            "sign_full":0 if full==0 else (1 if full>0 else -1),
            "sign_without_fold_3":0 if excl==0 else (1 if excl>0 else -1),
            "sign_preserved":(full==0 and excl==0) or (full>0 and excl>0) or (full<0 and excl<0),
        }
    # Contrast concentration uses the exact same frozen winner/control population;
    # it is descriptive, not a causal attribution.
    result={
      "status":"evidence-only",
      "lineage":{
        "snapshot_data_blob_sha":e0["protocol"]["snapshot_data_blob_sha"],
        "snapshot_source_commit":e0["protocol"]["snapshot_source_commit"],
        "snapshot_run_id":e0["protocol"]["snapshot_run_id"],
      },
      "population":{
        "nominal_winners":len(winners),
        "fold_3_winners":len(f3),
        "winners_remaining_without_fold_3":len(remaining),
        "fold_3_winner_share":len(f3)/len(winners),
        "winner_gross_sum":total_gross,
        "fold_3_winner_gross_sum":f3_gross,
        "fold_3_gross_share_of_winner_sum":f3_gross/total_gross if total_gross else None,
        "remaining_winner_gross_sum":remaining_gross,
      },
      "fold_distribution":{
        "winner_counts_by_fold":fold_counts,
        "supported_folds_full":[k for k,v in fold_counts.items() if v>0],
        "supported_folds_without_fold_3":[k for k,v in fold_counts.items() if k!=3 and v>0],
        "supported_fold_count_full":4,
        "supported_fold_count_without_fold_3":3,
        "largest_fold_share_full":max(fold_counts.values())/len(winners),
        "largest_fold_share_without_fold_3":max(v for k,v in fold_counts.items() if k!=3)/len(remaining),
        "winner_ess_full":e1["fold_independence"]["winner_kish_effective_sample_size"],
        "winner_ess_without_fold_3":(len(remaining)**2)/sum(v*v for k,v in fold_counts.items() if k!=3),
      },
      "feature_concentration":feature_rows,
      "decision_gate":{
        "remaining_winners_across_multiple_folds":len({r["fold_index"] for r in remaining})>=3,
        "all_feature_signs_preserved_after_fold_3":all(x["sign_preserved"] for x in feature_rows.values()),
        "any_feature_sign_flip_after_fold_3":any(not x["sign_preserved"] for x in feature_rows.values()),
        "signal_research_status":"REQUIRES_REVIEW_OF_FOLD3_REMOVAL_EVIDENCE",
      },
      "claim_boundary":{
        "signal_created":False,"threshold_tuned":False,"parameter_tuning":False,
        "model_fitting":False,"live_execution":False,"promotion_decision":False
      }
    }
    Path("fold3_concentration_independence_audit.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__": main()
