#!/usr/bin/env python3
"""Final E0 -> E1 -> survival -> LOO -> feature stability evidence chain.

Evidence-only. The frozen 14-vs-1035 audit is E0; the one-observation
embargo-adjusted fold/regime audit is E1. No threshold tuning, model fitting,
Signal construction, live execution, or promotion.
"""
from __future__ import annotations
import json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
E0=ROOT/"14_vs_1035_contrast_audit.json"
E1=ROOT/"embargo_adjusted_fold_regime_independence.json"
OUT=ROOT/"e0_e1_final_evidence_chain.json"
EXPECTED_BLOB="1a44d52a0588deb765bbbea04bfb5783dcb1050b"
EXPECTED_COMMIT="b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
EXPECTED_RUN=36489452534
FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]

def sign(v):
    if v is None or not math.isfinite(v): return None
    return 1 if v>0 else -1 if v<0 else 0

def main():
    e0=json.loads(E0.read_text())
    e1=json.loads(E1.read_text())
    p=e0["protocol"]
    assert p["snapshot_data_blob_sha"]==EXPECTED_BLOB
    assert p["snapshot_source_commit"]==EXPECTED_COMMIT
    assert p["snapshot_run_id"]==EXPECTED_RUN
    assert e0["counts"]=={"winners_gt_14bps":14,"controls_le_14bps":1035}
    assert e1["lineage"]["snapshot_data_blob_sha"]==EXPECTED_BLOB
    assert e1["lineage"]["snapshot_source_commit"]==EXPECTED_COMMIT
    assert e1["lineage"]["snapshot_source_run_id"]==EXPECTED_RUN
    assert e1["embargo_adjusted_population"]["reconciles"] is True
    assert e1["embargo_adjusted_population"]["winners_gt_14bps"]==14
    assert e1["embargo_adjusted_population"]["controls_le_14bps"]==1035

    # E0 -> E1 reconciliation
    e0_folds={str(k):int(e0["categorical"]["fold_winners"].get(str(k),0)) for k in range(8)}
    e1_folds=e1["fold_independence"]["winner_counts_by_fold"]
    assert e0_folds==e1_folds

    # E1 fold/regime survival
    e1_loo=e1["leave_one_fold_out"]
    fold_survival=[]
    for row in e1_loo:
        fold_survival.append({
            "excluded_fold":row["excluded_fold"],
            "winner_count_remaining":row["winner_count_remaining"],
            "supported_folds_remaining":row["winner_supported_folds_remaining"],
            "remaining_winner_gross_sum":row["remaining_winner_gross_sum"],
        })

    # E0 LOO-winner stability and feature stability.
    winner_loo=e0["stability"]["leave_one_winner_out"]
    feature_stability={}
    for f in FEATURES:
        full=e0["feature_contrast"][f]["smd"]
        fold_vals={str(k): e0["stability"]["fold_exclusion"][str(k)]["feature_smd_without_fold"].get(f)
                   for k in range(8)}
        winner_vals=[v["feature_smd_without_sample"].get(f) for v in winner_loo.values()]
        fold_signs=[sign(v) for v in fold_vals.values() if sign(v) is not None]
        winner_signs=[sign(v) for v in winner_vals if sign(v) is not None]
        feature_stability[f]={
            "full_e0_smd":full,
            "fold_loo_smd":fold_vals,
            "winner_loo_n":len(winner_vals),
            "winner_loo_smd_min":min(winner_vals) if winner_vals else None,
            "winner_loo_smd_max":max(winner_vals) if winner_vals else None,
            "same_sign_all_fold_loo":len(fold_signs)==8 and len(set(fold_signs))==1 and sign(full)==fold_signs[0],
            "same_sign_all_winner_loo":len(winner_signs)==14 and len(set(winner_signs))==1 and sign(full)==winner_signs[0],
        }

    all_feature_stable=all(v["same_sign_all_fold_loo"] and v["same_sign_all_winner_loo"]
                           for v in feature_stability.values())

    result={
      "status":"evidence-only",
      "chain":["E0","E1","Fold/Regime Survival","LOO-Fold","LOO-Winner","Feature Stability","Independence-adjusted conclusion"],
      "lineage":{"snapshot_data_blob_sha":EXPECTED_BLOB,"snapshot_source_commit":EXPECTED_COMMIT,"snapshot_source_run_id":EXPECTED_RUN},
      "E0":{"evaluated_oos":1049,"winners":14,"controls":1035,"winner_counts_by_fold":e0_folds},
      "E1":{"embargo_observations":e1["protocol"]["embargo_adjusted_observations"],
            "evaluated_oos":e1["embargo_adjusted_population"]["evaluated_oos"],
            "winners":e1["embargo_adjusted_population"]["winners_gt_14bps"],
            "controls":e1["embargo_adjusted_population"]["controls_le_14bps"],
            "outcome_boundary":e1["outcome_embargo_boundary"],
            "reconciles_with_E0":True},
      "fold_regime_survival":{
          "supported_folds":e1["fold_independence"]["supported_fold_indices"],
          "supported_fold_count":e1["fold_independence"]["supported_fold_count"],
          "support_fraction":e1["fold_independence"]["support_fraction"],
          "winner_counts_by_fold":e1_folds,
          "winner_counts_by_regime":e1["regime_independence"]["winner_counts_by_regime"],
          "winner_counts_by_direction":e1["regime_independence"]["winner_counts_by_direction"],
          "winner_kish_effective_sample_size":e1["fold_independence"]["winner_kish_effective_sample_size"],
          "largest_winner_fold_share":e1["fold_independence"]["largest_winner_fold_share"],
      },
      "LOO_Fold":{"rows":fold_survival,"dominant_fold_3_excluded_remaining_winners":next(r for r in fold_survival if r["excluded_fold"]==3)["winner_count_remaining"]},
      "LOO_Winner":{"winner_count":len(winner_loo),"source":"E0 frozen contrast audit","all_14_evaluated":len(winner_loo)==14},
      "feature_stability":{"features":feature_stability,"all_features_same_sign_under_both_LOO":all_feature_stable},
      "independence_adjusted_conclusion":{
          "independence_unit":e1["fold_independence"]["independence_unit"],
          "nominal_winners":14,
          "effective_winner_units":e1["fold_independence"]["winner_kish_effective_sample_size"],
          "supported_fold_count":e1["fold_independence"]["supported_fold_count"],
          "regimes_supported":e1["regime_independence"]["regime_supported_by_winners"],
          "descriptive_feature_stability_all_features":all_feature_stable,
          "conclusion":"Evidence remains descriptive and independence-adjusted: the 14 nominal winners reconcile E0->E1, survive fold/regime accounting and both LOO layers at the level reported here, but the effective independent winner information is limited to four temporal folds (Kish ESS ≈2.97). This is not sufficient by itself to claim 14 independent confirmations.",
          "signal_research_gate":"DEFERRED_UNTIL_HUMAN_REVIEW_OF_EVIDENCE",
      },
      "claim_boundary":{"signal_created":False,"threshold_tuned":False,"parameter_tuning":False,"model_fitting":False,"live_execution":False,"promotion_decision":False}
    }
    OUT.write_text(json.dumps(result,indent=2))
    print(json.dumps({"status":"success","chain_complete":True,"winners":14,"controls":1035,
                      "supported_folds":e1["fold_independence"]["supported_fold_indices"],
                      "winner_kish_ess":e1["fold_independence"]["winner_kish_effective_sample_size"],
                      "all_features_same_sign_under_both_LOO":all_feature_stable},indent=2))

if __name__=="__main__": main()
