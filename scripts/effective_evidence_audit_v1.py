#!/usr/bin/env python3
import json
from pathlib import Path
def main():
    d=json.loads(Path("concentration_sensitivity_audit_v1.json").read_text())
    p=d["prior_14"]["sensitivity"]; c=d["current_28"]["sensitivity"]
    pmin=p["effective_cluster_count_min"]; cmin=c["effective_cluster_count_min"]
    out={
      "protocol":"effective-evidence-protocol-v1",
      "raw_population":{"prior":14,"current":28,"combined":42},
      "conservative_population_effective_evidence_proxy":{"prior_min_threshold":pmin,"current_min_threshold":cmin,"combined_sum":pmin+cmin},
      "sensitivity_inputs":{
        "prior_effective_cluster_count_range":[p["effective_cluster_count_min"],p["effective_cluster_count_max"]],
        "current_effective_cluster_count_range":[c["effective_cluster_count_min"],c["effective_cluster_count_max"]]
      },
      "interpretation":"conservative dependence-adjusted evidence proxy, not a statistical effective sample size estimator",
      "claim_boundary":{"independence_proven":False,"predictive_validity":False,"causality":False,"market_generalization":False,"promotion":"BLOCKED"},
      "final_verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION"
    }
    Path("effective_evidence_audit_v1.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
