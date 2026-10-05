#!/usr/bin/env python3
import json, math, statistics
from pathlib import Path

FEATURES=["ema_distance_pct","vwap_distance_pct","buy_ratio","buy_sell_delta","trade_count"]
THRESHOLDS=[0.5,1.0,1.5,2.0]

def dist(a,b,mu,sd):
    return math.sqrt(sum(((a[f]-b[f])/sd[f])**2 for f in FEATURES))

def components(rows,threshold,mu,sd):
    n=len(rows); p=list(range(n))
    def find(x):
        while p[x]!=x:
            p[x]=p[p[x]]; x=p[x]
        return x
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:p[b]=a
    for i in range(n):
        for j in range(i+1,n):
            if dist(rows[i],rows[j],mu,sd)<=threshold: union(i,j)
    g={}
    for i in range(n): g.setdefault(find(i),[]).append(i)
    return list(g.values())

def eff(sizes):
    n=sum(sizes)
    return (n*n/sum(x*x for x in sizes)) if sizes else 0.0

def audit(rows,label,mu,sd):
    winners=[r for r in rows if r.get("class")=="Winner"]
    results={}
    for t in THRESHOLDS:
        cs=components(winners,t,mu,sd)
        sizes=sorted([len(c) for c in cs],reverse=True)
        results[str(t)]={"winner_clusters":len(cs),"largest_winner_cluster":sizes[0] if sizes else 0,
                         "effective_cluster_count":eff(sizes),"cluster_sizes":sizes}
    return {"label":label,"winners":len(winners),"thresholds":results}

def load(path): return json.loads(Path(path).read_text()).get("winners",[])

def main():
    prior=load("prior_1049_protocol.json"); current=load("current_1027_protocol.json")
    # Frozen combined population is used only to standardize locked numeric features.
    allr=prior+current
    numeric={f:[float(r[f]) for r in allr if r.get(f) not in (None,"")] for f in FEATURES}
    mu={f:statistics.fmean(v) for f,v in numeric.items()}
    sd={f:(statistics.pstdev(v) or 1.0) for f,v in numeric.items()}
    out={"protocol":"cluster-independence-protocol-v1","prior_14":audit(prior,"prior_14",mu,sd),
         "current_28":audit(current,"current_28",mu,sd),
         "standardization":"combined frozen population",
         "claim_boundary":{"threshold_selection":"fixed pre-registered sensitivity set",
           "independence_proven":False,"predictive_validity":False,"causality":False,
           "market_generalization":False,"promotion":"BLOCKED"},
         "final_verdict":"EVIDENCE_INSUFFICIENT_FOR_PROMOTION"}
    Path("cluster_independence_audit_v1.json").write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
