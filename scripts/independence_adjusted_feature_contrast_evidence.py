#!/usr/bin/env python3
"""Independence-adjusted 14-vs-1035 feature contrast evidence.

Reconciles the frozen 14-vs-1035 feature contrast with embargo-adjusted
fold independence and both leave-one-fold-out and leave-one-winner-out
feature stability. Evidence-only: no tuning, fitting, selection, signal,
live execution, or promotion decision.
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CONTRAST=ROOT/"14_vs_1035_contrast_audit.json"
INDEPENDENCE=ROOT/"embargo_adjusted_fold_regime_independence.json"
OUTPUT=ROOT/"independence_adjusted_feature_contrast_evidence.json"

FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]
EXPECTED_BLOB="1a44d52a0588deb765bbbea04bfb5783dcb1050b"
EXPECTED_SOURCE_COMMIT="b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
EXPECTED_RUN_ID=36489452534

def sign(v):
    if v>0: return 1
    if v<0: return -1
    return 0

def summary(values):
    vals=[v for v in values if v is not None and math.isfinite(v)]
    if not vals:
        return {"n":0,"positive":0,"negative":0,"zero":0,"sign_consistency":None,
                "min":None,"max":None,"mean":None,"median":None}
    pos=sum(v>0 for v in vals); neg=sum(v<0 for v in vals); zero=len(vals)-pos-neg
    return {"n":len(vals),"positive":pos,"negative":neg,"zero":zero,
            "sign_consistency":max(pos,neg,zero)/len(vals),
            "min":min(vals),"max":max(vals),"mean":statistics.fmean(vals),
            "median":statistics.median(vals)}

def main():
    contrast=json.loads(CONTRAST.read_text(encoding="utf-8"))
    independence=json.loads(INDEPENDENCE.read_text(encoding="utf-8"))
    p=contrast["protocol"]
    assert p["snapshot_data_blob_sha"]==EXPECTED_BLOB
    assert p["snapshot_source_commit"]==EXPECTED_SOURCE_COMMIT
    assert p["snapshot_run_id"]==EXPECTED_RUN_ID
    assert contrast["counts"]=={"winners_gt_14bps":14,"controls_le_14bps":1035}
    assert independence["lineage"]["snapshot_data_blob_sha"]==EXPECTED_BLOB
    assert independence["lineage"]["snapshot_source_commit"]==EXPECTED_SOURCE_COMMIT
    assert independence["lineage"]["snapshot_source_run_id"]==EXPECTED_RUN_ID

    result_features={}
    for f in FEATURES:
        full=contrast["feature_contrast"][f]["smd"]
        fold_rows=contrast["stability"]["fold_exclusion"]
        fold_vals={str(k):fold_rows[str(k)]["feature_smd_without_fold"].get(f) for k in range(8)}
        winner_rows=contrast["stability"]["leave_one_winner_out"]
        winner_vals=list(v["feature_smd_without_sample"].get(f) for v in winner_rows.values())
        fold_summary=summary(list(fold_vals.values()))
        winner_summary=summary(winner_vals)
        result_features[f]={
            "full_sample_smd":full,
            "leave_one_fold_out_smd":fold_vals,
            "leave_one_fold_out_summary":fold_summary,
            "leave_one_winner_out_summary":winner_summary,
            "same_sign_across_all_fold_exclusions":(
                all(v is not None for v in fold_vals.values()) and
                len({sign(v) for v in fold_vals.values()})==1 and
                sign(full)==sign(next(iter(fold_vals.values())))
            ),
            "same_sign_across_all_winner_exclusions":(
                len(winner_vals)==14 and
                all(v is not None for v in winner_vals) and
                len({sign(v) for v in winner_vals})==1 and
                sign(full)==sign(winner_vals[0])
            ),
            "independence_adjusted_context":{
                "supported_fold_count":independence["fold_survival"]["supported_fold_count"],
                "support_fraction":independence["fold_survival"]["support_fraction"],
                "winner_kish_effective_sample_size":independence["frozen_population"]["winner_kish_effective_sample_size"],
            },
        }

    fold_counts=contrast["categorical"]["fold_winners"]
    result={
        "status":"evidence-only",
        "lineage":{"snapshot_data_blob_sha":EXPECTED_BLOB,
                   "snapshot_source_commit":EXPECTED_SOURCE_COMMIT,
                   "snapshot_source_run_id":EXPECTED_RUN_ID},
        "population":{"winners":14,"controls":1035,"evaluated_oos":1049},
        "independence_adjustment":{
            "independence_unit":independence["claim_boundary"]["independence_unit"],
            "supported_fold_indices":independence["frozen_population"]["winner_supported_fold_indices"],
            "supported_fold_count":independence["fold_survival"]["supported_fold_count"],
            "support_fraction":independence["fold_survival"]["support_fraction"],
            "winner_fold_sizes":independence["frozen_population"]["winner_fold_sizes"],
            "winner_kish_effective_sample_size":independence["frozen_population"]["winner_kish_effective_sample_size"],
            "largest_winner_fold_share":independence["fold_survival"]["winner_concentration"],
        },
        "feature_contrast_stability":result_features,
        "fold_winner_counts":{str(k):int(fold_counts.get(str(k),0)) for k in range(8)},
        "interpretation":{
            "fold_loo_survival_rule":"descriptive only: report whether the direction/sign of the full 14-vs-1035 SMD is unchanged after excluding each fold",
            "winner_loo_survival_rule":"descriptive only: report whether the direction/sign is unchanged after removing each winner one at a time",
            "no_claim_of_independent_winners":True,
            "signal_created":False,"threshold_tuned":False,"parameter_tuning":False,
            "model_fitting":False,"live_execution":False,"promotion_decision":False,
        },
    }
    OUTPUT.write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "winner_ess":result["independence_adjustment"]["winner_kish_effective_sample_size"],
        "supported_folds":result["independence_adjustment"]["supported_fold_indices"],
        "features":{
            f:{
                "full_smd":v["full_sample_smd"],
                "fold_loo_sign_consistency":v["leave_one_fold_out_summary"]["sign_consistency"],
                "winner_loo_sign_consistency":v["leave_one_winner_out_summary"]["sign_consistency"],
                "same_sign_all_fold_exclusions":v["same_sign_across_all_fold_exclusions"],
                "same_sign_all_winner_exclusions":v["same_sign_across_all_winner_exclusions"],
            } for f,v in result_features.items()
        }
    },indent=2))

if __name__=="__main__":
    main()
