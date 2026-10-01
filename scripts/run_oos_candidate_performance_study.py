"""Descriptive candidate performance study over a verified frozen OOS population.

No parameter search, candidate selection, fitting, compounding, or execution.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

SCENARIOS = ((0.0, 0.0), (5.0, 2.0), (10.0, 5.0))

def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default="oos_snapshot_integrity_v1.json")
    parser.add_argument("--replay", default="oos_raw_replay_evidence_v1.json")
    parser.add_argument("--output", default="oos_candidate_performance_study_v1.json")
    args = parser.parse_args()
    snap=json.loads(Path(args.snapshot).read_text())
    replay=json.loads(Path(args.replay).read_text())
    if replay.get("status") != "PASS":
        raise AssertionError("Raw Replay gate did not pass")
    meta=snap["snapshot"]
    if replay["raw_input_sha256"] != meta["raw_input_sha256"] or replay["population_sha256"] != meta["population_sha256"] or replay["manifest_sha256"] != meta["manifest_sha256"]:
        raise AssertionError("Replay and snapshot lineage mismatch")
    rows=snap["population"]["rows"]
    folds=sorted({r["fold_index"] for r in rows})
    if len(folds)!=8 or len(rows)!=1049: raise AssertionError("unexpected frozen population")
    summaries=[]
    for fee,slip in SCENARIOS:
        per_fold=[]
        all_returns=[]
        for fold in folds:
            values=[float(r["gross_return"])-2*(fee+slip)/10000 for r in rows if r["fold_index"]==fold]
            if not all(math.isfinite(v) for v in values): raise AssertionError("non-finite outcome")
            per_fold.append({"fold_index":fold,"evaluated":len(values),"net_return_sum":sum(values),"positive_net":sum(v>0 for v in values),"negative_net":sum(v<0 for v in values)})
            all_returns.extend(values)
        if len(all_returns)!=1049: raise AssertionError("fold population does not reconcile")
        summaries.append({
            "transaction_cost_bps_per_side":fee,"slippage_bps_per_side":slip,
            "evaluated":len(all_returns),"sum_of_trade_returns_no_compounding":sum(all_returns),
            "wins":sum(v>0 for v in all_returns),"losses":sum(v<0 for v in all_returns),
            "zero_net":sum(v==0 for v in all_returns),
            "positive_folds":sum(f["net_return_sum"]>0 for f in per_fold),
            "negative_folds":sum(f["net_return_sum"]<0 for f in per_fold),
            "folds":per_fold,
        })
    evidence={
      "study_id":"real-btcusdt-oos-candidate-performance-v1",
      "lineage":{"raw_input_sha256":meta["raw_input_sha256"],"population_sha256":meta["population_sha256"],"manifest_sha256":meta["manifest_sha256"]},
      "population":{"fold_count":8,"evaluated":1049},
      "method":"descriptive frozen-population OOS measurement; simple sum of per-trade returns; no compounding",
      "scenarios":summaries,
      "safety":{"execution":False,"parameter_tuning":False,"model_fitting":False,"capital_mutation":False,"promotion":False},
      "interpretation":"Evidence only; not a profitability guarantee or live-trading authorization."
    }
    Path(args.output).write_bytes(canonical_bytes(evidence))
    print(json.dumps(evidence,indent=2))
if __name__=="__main__": main()
