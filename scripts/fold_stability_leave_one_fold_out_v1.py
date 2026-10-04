#!/usr/bin/env python3
import csv,json,math,statistics
from pathlib import Path

THRESHOLD=0.0014
FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]

def smd(a,b):
    va=statistics.pvariance(a) if len(a)>1 else 0
    vb=statistics.pvariance(b) if len(b)>1 else 0
    d=math.sqrt((va+vb)/2)
    return (statistics.fmean(a)-statistics.fmean(b))/d if d else 0.0

src=Path("protocol_reconciliation_full_population_audit.json")
if not src.exists():
    raise SystemExit("Missing frozen protocol output; run the immutable protocol first.")
d=json.loads(src.read_text())
winners=d["winners"]
controls=[]
# Reconstruct the complete control population from the audit's categorical/feature source is not possible
# from the winners-only artifact, so this audit intentionally limits LOFO to winner concentration and
# gross evidence. No observation is removed from the upstream population.
for fold in range(8):
    wf=[r for r in winners if r["fold_index"]!=fold]
    removed=[r for r in winners if r["fold_index"]==fold]
    result={
      "winner_count_total":len(winners),
      "winner_count_removed":len(removed),
      "winner_count_remaining":len(wf),
      "removed_gross_sum":sum(r["gross_return"] for r in removed),
      "remaining_gross_sum":sum(r["gross_return"] for r in wf),
      "remaining_gross_mean":statistics.fmean(r["gross_return"] for r in wf) if wf else None,
      "remaining_direction_counts":{k:sum(r["direction"]==k for r in wf) for k in sorted(set(r["direction"] for r in winners))},
      "remaining_feature_smd_vs_all_winner_baseline":{
          f: (statistics.fmean([r[f] for r in wf])-statistics.fmean([r[f] for r in winners])) /
             (statistics.pstdev([r[f] for r in winners]) or 1.0)
          for f in FEATURES
      }
    }
    d.setdefault("lofo_fold_stability",{})[str(fold)]=result

# Immutable upstream 14-survivor fold counts from the locked downstream cost/fold audit.
survivor_fold_counts={"0":2,"1":3,"2":2,"3":7,"4":0,"5":0,"6":0,"7":0}
d["survivor_14_reference"]={
  "source":"evidence/downstream_cost_fold_survival_audit_v1.json",
  "source_commit":"e3f86f81c35506302e087fc8fc82bf972ac11a20",
  "round_trip_bps":14,
  "fold_counts":survivor_fold_counts,
  "total":sum(survivor_fold_counts.values()),
  "lineage_records_not_reconstructed_here":True
}
Path("fold_stability_leave_one_fold_out_v1.json").write_text(json.dumps({
  "status":"COMPLETE_FOR_28_WINNER_CONCENTRATION; SURVIVOR_REFERENCE_ONLY",
  "protocol":{"train":800,"test":400,"step":400,"folds":8,"threshold_bps":14},
  "winner_lofo":d["lofo_fold_stability"],
  "survivor_14_reference":d["survivor_14_reference"],
  "safety":{"observation_removal":False,"threshold_tuning":False,"parameter_tuning":False,"selection":False,"promotion":False,"execution":False}
},indent=2)+"\n")
print(json.dumps({"winner_total":len(winners),"winner_fold_counts":{str(i):sum(r["fold_index"]==i for r in winners) for i in range(8)},"survivor_14_fold_counts":survivor_fold_counts},indent=2))
