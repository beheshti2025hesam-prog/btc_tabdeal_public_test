#!/usr/bin/env python3
import json
from pathlib import Path
from collections import Counter

def share(c):
    n=sum(c.values())
    return max(c.values())/n if n else 0

def audit(d):
    w=d["winners"]
    direction=Counter(str(x.get("direction","UNKNOWN")).upper() for x in w)
    # The frozen protocol emits the fold-level regime as "fold_regime".
    regime=Counter(str(x.get("fold_regime","UNKNOWN")).lower() for x in w)
    fold=Counter(x["fold_index"] for x in w)
    result={
      "population":len(w),
      "direction_counts":dict(direction),
      "regime_counts":dict(regime),
      "fold_counts":dict(fold),
      "concentration":{
        "direction_max_share":share(direction),
        "regime_max_share":share(regime),
        "fold_max_share":share(fold),
      },
      "claims":{
        "direction":"DESCRIPTIVE_ONLY",
        "regime":"DESCRIPTIVE_ONLY",
        "concentration":"REQUIRES_REVIEW",
        "promotion":"BLOCKED"
      }
    }
    result["verdict"]="EVIDENCE_INSUFFICIENT_FOR_PROMOTION"
    return result

def main():
    prior=json.loads(Path("prior_1049_protocol.json").read_text())
    current=json.loads(Path("current_1027_protocol.json").read_text())
    out={"prior_14":audit(prior),"current_28":audit(current),
         "claim_boundary":{"threshold_tuned":False,"data_modified":False,"selection_changed":False},
         "final_verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION"}
    Path("direction_regime_concentration_audit_v1.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))

if __name__=="__main__":
    main()
