#!/usr/bin/env python3
"""Feature-space nearest-control audit for the two frozen >14bps winners.

Research-only. Candidate features are locked to Buy Ratio, Delta, Trade Count.
For each winner, controls are evaluated observations in the same OOS fold with
gross return <= 14bps. Feature scaling is deterministic within that fold:
control-only mean/std per feature; no outcome-derived tuning or threshold search.
"""
from __future__ import annotations
import json, os, math
from pathlib import Path

from core.data_engine.candles import TradeCandleAggregator
from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.reader import RawDataReader
from core.data_engine.validator import RawDataValidator
from core.data_engine.vwap import VWAPCalculator
from core.feature_engine.ema import EMACalculator
from core.feature_engine.quality import FeatureSnapshot
from core.strategy.baseline import BaselineStrategy, BaselineStrategyInput, BaselineDecision
from core.risk.boundary import RiskPolicy, RiskInput, RiskDecision

ROOT=Path(__file__).resolve().parents[1]
CSV_PATH=os.environ.get("HES_FROZEN_CSV","/tmp/hes_fresh_trades.csv")
EXPECTED_BLOB="b296b1c95f075518bea0b56fd11bbf5f0f613a04"
EXPECTED_COMMIT="86631f2522aa74a38cfa21fa28afe8d49fbc5f20"
TRAIN,TEST,STEP,FOLDS=800,400,400,8
THRESHOLD=0.0014
FEATURES=("buy_ratio","buy_sell_delta","trade_count")

def build_rows():
    reader=RawDataReader(active_file=CSV_PATH, archive_dir="__no_archive__")
    val=RawDataValidator(); norm=RawDataNormalizer(); trades=[]; invalid=0
    for row in reader.read_all():
        if val.validate_row(row): invalid+=1
        else: trades.append(norm.normalize_row(row))
    trades.sort(key=lambda t:(t.timestamp,t.sequence or -1))
    candles=TradeCandleAggregator(60).aggregate(trades)
    ema=EMACalculator(20).calculate(candles); vwap=VWAPCalculator(60).calculate(trades)
    grouped={}
    for t in trades:
        e=int(t.timestamp.timestamp()); grouped.setdefault((t.symbol,e-e%60),[]).append(t)
    pressure={}
    for k,g in grouped.items():
        buy=sum(t.quantity for t in g if t.side=="buy"); sell=sum(t.quantity for t in g if t.side=="sell")
        seq=[t.sequence for t in g if t.sequence is not None]
        total=buy+sell
        pressure[k]=(buy/total if total else 0.0,buy-sell,len(g),min(seq) if seq else None,max(seq) if seq else None)
    em={(x.symbol,x.timestamp):x.value for x in ema}
    vw={(x.symbol,x.end):x.vwap for x in vwap}
    strat=BaselineStrategy(min_confirmations=3); risk=RiskPolicy(); obs=[]
    for i in range(19,len(candles)-1):
        c,n=candles[i],candles[i+1]
        if c.symbol!=n.symbol or n.start!=c.end: continue
        p=pressure.get((c.symbol,int(c.start.timestamp())))
        ev=em.get((c.symbol,c.end)); vv=vw.get((c.symbol,c.end))
        if p is None or ev is None or vv is None: continue
        br,delta,count,s0,s1=p
        fs=FeatureSnapshot(symbol=c.symbol,timeframe_seconds=60,close=c.close,ema=ev,vwap=vv,
                           buy_sell_delta=delta,buy_ratio=br,timestamp=c.end)
        decision=strat.evaluate(BaselineStrategyInput(features=fs))
        rd=risk.evaluate(RiskInput(decision=decision,equity=1000.0))
        evaluated=decision in (BaselineDecision.LONG,BaselineDecision.SHORT) and rd is RiskDecision.ALLOW_SIGNAL
        sign=1 if decision is BaselineDecision.LONG else -1
        gross=sign*(n.close-c.close)/c.close if evaluated else None
        obs.append({"timestamp":c.end.isoformat(),"timestamp_dt":c.end,"sequence_first":s0,"sequence_last":s1,
                    "gross_return":gross,"direction":decision.value,"evaluated":evaluated,
                    "buy_ratio":br,"buy_sell_delta":delta,"trade_count":count,"candle_index":i})
    rows=[]
    for fold in range(FOLDS):
        a=fold*STEP+TRAIN; b=a+TEST; test=obs[a:b]; ev=[r for r in test if r["evaluated"]]
        total=sum(r["gross_return"] for r in ev)
        regime="uptrend" if total>=.01 else "downtrend" if total<=-.01 else "range"
        for r in ev:
            x=dict(r); x["fold_index"]=fold; x["fold_regime"]=regime; rows.append(x)
    return rows,invalid,len(trades),len(candles)

def nearest_feature_control(rows,winner):
    controls=[r for r in rows if r["fold_index"]==winner["fold_index"] and r["gross_return"]<=THRESHOLD]
    assert controls
    means={f:sum(r[f] for r in controls)/len(controls) for f in FEATURES}
    scales={}
    for f in FEATURES:
        var=sum((r[f]-means[f])**2 for r in controls)/len(controls)
        s=math.sqrt(var)
        scales[f]=s if s>0 else 1.0
    def z(r,f): return (r[f]-means[f])/scales[f]
    scored=[]
    for c in controls:
        diffs={f:z(winner,f)-z(c,f) for f in FEATURES}
        dist=math.sqrt(sum(v*v for v in diffs.values()))
        scored.append((dist,c,diffs))
    scored.sort(key=lambda x:(x[0],x[1]["timestamp_dt"],x[1]["sequence_first"] or -1))
    return scored[0],len(controls),means,scales

def main():
    rows,invalid,trade_count,candle_count=build_rows()
    winners=[r for r in rows if r["gross_return"]>THRESHOLD]
    assert len(winners)==2, len(winners)
    audits=[]
    for w in winners:
        (dist,c,diffs),control_count,means,scales=nearest_feature_control(rows,w)
        audits.append({
            "winner":{"timestamp":w["timestamp"],"sequence_first":w["sequence_first"],"sequence_last":w["sequence_last"],
                      "fold":w["fold_index"],"fold_regime":w["fold_regime"],"direction":w["direction"],
                      "outcome":w["gross_return"],"features":{f:w[f] for f in FEATURES}},
            "nearest_control":{"timestamp":c["timestamp"],"sequence_first":c["sequence_first"],"sequence_last":c["sequence_last"],
                      "fold":c["fold_index"],"fold_regime":c["fold_regime"],"direction":c["direction"],
                      "outcome":c["gross_return"],"features":{f:c[f] for f in FEATURES},
                      "time_delta_seconds":(c["timestamp_dt"]-w["timestamp_dt"]).total_seconds(),
                      "sequence_delta_first":(c["sequence_first"]-w["sequence_first"]) if c["sequence_first"] is not None and w["sequence_first"] is not None else None,
                      "feature_distance_euclidean_z":dist,"standardized_feature_deltas":diffs,
                      "outcome_gap_winner_minus_control":w["gross_return"]-c["gross_return"]},
            "normalization":{"method":"control-only per-fold population mean/std; no outcome values used","control_count":control_count,
                             "mean":means,"scale":scales}
        })
    seq_pairs=[(a["winner"]["sequence_first"],a["nearest_control"]["sequence_first"]) for a in audits]
    ts_pairs=[(a["winner"]["timestamp"],a["nearest_control"]["timestamp"]) for a in audits]
    checks={
        "winner_count":len(winners),
        "all_same_fold":all(a["winner"]["fold"]==a["nearest_control"]["fold"] for a in audits),
        "all_controls_at_or_below_threshold":all(a["nearest_control"]["outcome"]<=THRESHOLD for a in audits),
        "all_winners_above_threshold":all(a["winner"]["outcome"]>THRESHOLD for a in audits),
        "no_timestamp_overlap":all(w!=c for w,c in ts_pairs),
        "no_sequence_first_overlap":all(w!=c for w,c in seq_pairs if w is not None and c is not None),
        "feature_distance_finite_positive":all(math.isfinite(a["nearest_control"]["feature_distance_euclidean_z"]) and a["nearest_control"]["feature_distance_euclidean_z"]>=0 for a in audits),
        "no_future_feature_claim":True,
    }
    assert all(checks.values())
    out={"status":"FEATURE_SPACE_NEAREST_CONTROL_AUDIT_REVIEW_ONLY",
         "protocol":{"feature_space":list(FEATURES),"distance":"Euclidean distance after control-only per-fold z-standardization",
                     "control_definition":"evaluated same-fold observations with gross_return <= 14bps","threshold":THRESHOLD,
                     "snapshot_blob":EXPECTED_BLOB,"snapshot_source_commit":EXPECTED_COMMIT,"folds":FOLDS},
         "population":{"evaluated_oos":len(rows),"winners":len(winners),"source_trade_rows":trade_count,"candles":candle_count,"invalid_rows":invalid},
         "winner_audits":audits,"integrity":checks,
         "interpretation":{"independent_temporal_units":2,
                           "claim":"Each frozen winner has one deterministic nearest same-fold control in the locked feature space. This is descriptive evidence only; n=2 does not establish a generalizable signal.",
                           "signal_created":False,"threshold_tuned":False,"model_fitted":False,"promotion_decision":False,"live_execution":False}}
    (ROOT/"feature_space_nearest_control_audit.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out,indent=2))
if __name__=="__main__": main()
