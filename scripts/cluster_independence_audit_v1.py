#!/usr/bin/env python3
import csv, json, math
from pathlib import Path
from collections import Counter, defaultdict

FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]

def zscore(v, mu, sd):
    return (v-mu)/sd if sd else 0.0

def distance(a,b,means,sds):
    vals=[]
    for f in FEATURES:
        vals.append((zscore(a[f],means[f],sds[f])-zscore(b[f],means[f],sds[f]))**2)
    return math.sqrt(sum(vals))

def summarize(rows,label):
    winners=[r for r in rows if r.get("class")=="Winner"]
    # Conservative clustering: exact feature-vector duplicates are one cluster.
    # No arbitrary similarity threshold is introduced.
    groups=defaultdict(list)
    for r in winners:
        key=tuple(r.get(f,"") for f in FEATURES)
        groups[key].append(r)
    sizes=sorted((len(v) for v in groups.values()),reverse=True)
    return {
      "label":label,"winners":len(winners),"exact_feature_clusters":len(groups),
      "largest_exact_cluster":sizes[0] if sizes else 0,
      "cluster_size_distribution":sizes,
      "claim":"EXACT_DUPLICATE_STRUCTURE_ONLY",
      "promotion":"BLOCKED"
    }

def main():
    # This audit intentionally refuses to invent a continuous-distance threshold.
    # It consumes the frozen protocol snapshots and only tests exact feature-vector
    # duplication; richer clustering requires a pre-registered metric/threshold.
    prior=json.loads(Path("prior_1049_protocol.json").read_text())
    current=json.loads(Path("current_1027_protocol.json").read_text())
    # Snapshot JSONs are not guaranteed to retain raw rows; inspect their winner records.
    out={"prior_14":summarize(prior.get("winners",[]),"prior_14"),
         "current_28":summarize(current.get("winners",[]),"current_28"),
         "claim_boundary":{
           "distance_threshold_tuned":False,"cluster_selection":False,
           "data_modified":False,"promotion_blocked":True,
           "note":"No continuous clustering threshold is introduced in v1."
         },
         "final_verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION"}
    Path("cluster_independence_audit_v1.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
