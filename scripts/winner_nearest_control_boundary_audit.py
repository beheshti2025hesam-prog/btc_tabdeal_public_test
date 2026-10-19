#!/usr/bin/env python3
"""Boundary/Sequence/Outcome audit for the two fresh-snapshot >14bps winners.

Research-only. No tuning, fitting, promotion, or execution.
Nearest controls are the temporally closest <=14bps evaluated observations
within the same OOS fold: up to 2 immediately before and 2 immediately after
each winner. The audit also checks sequence ordering and one-step outcome
separation.
"""
from __future__ import annotations
import csv, json, os
from pathlib import Path
from datetime import datetime

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
EXPECTED_BLOB=os.environ.get("FRESH_BLOB_SHA","")
EXPECTED_COMMIT=os.environ.get("FRESH_SOURCE_COMMIT","")
TRAIN,TEST,STEP,FOLDS=800,400,400,8
THRESHOLD=0.0014

def parse_ts(s): return datetime.fromisoformat(s.replace("Z","+00:00"))

def rel(a,b): return (a-b)/b if b else 0.0

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
        e=int(t.timestamp.timestamp()); k=(t.symbol,e-e%60)
        grouped.setdefault(k,[]).append(t)
    pressure={}
    for k,g in grouped.items():
        buy=sum(t.quantity for t in g if t.side=="buy")
        sell=sum(t.quantity for t in g if t.side=="sell")
        total=buy+sell; seq=[t.sequence for t in g if t.sequence is not None]
        pressure[k]=(buy/total if total else 0.0,buy-sell,len(g),
                     min(seq) if seq else None,max(seq) if seq else None)
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
        obs.append({"timestamp":c.end.isoformat(),"timestamp_dt":c.end,"sequence_first":s0,
                    "sequence_last":s1,"entry_price":c.close,"exit_price":n.close,
                    "gross_return":gross,"direction":decision.value,
                    "evaluated":evaluated,"buy_ratio":br,"buy_sell_delta":delta,
                    "trade_count":count,"candle_index":i})
    rows=[]
    # Fold boundaries are defined over the complete chronological observation
    # sequence, not over the filtered evaluated subset. This must match the
    # fixed 8-fold OOS protocol used by contrast_audit_14_vs_1035.py.
    for fold in range(FOLDS):
        a=fold*STEP+TRAIN; b=a+TEST; test=obs[a:b]
        ev=[r for r in test if r["evaluated"]]
        total=sum(r["gross_return"] for r in ev)
        regime="uptrend" if total>=.01 else "downtrend" if total<=-.01 else "range"
        for r in ev:
            x=dict(r); x["fold_index"]=fold; x["fold_regime"]=regime; rows.append(x)
    return rows,invalid,len(trades),len(candles)

def nearest_controls(rows,winner):
    same=[r for r in rows if r["fold_index"]==winner["fold_index"] and r["gross_return"]<=THRESHOLD]
    same.sort(key=lambda r:r["timestamp_dt"])
    idx=next(i for i,r in enumerate(same) if r["timestamp_dt"]>winner["timestamp_dt"] or
             r["timestamp_dt"]==winner["timestamp_dt"])
    # Controls cannot share the winner timestamp; search insertion point robustly.
    before=[r for r in same if r["timestamp_dt"]<winner["timestamp_dt"]][-2:]
    after=[r for r in same if r["timestamp_dt"]>winner["timestamp_dt"]][:2]
    return before+after

def compact(w,wc):
    return {"timestamp":w["timestamp"],"fold":w["fold_index"],"direction":w["direction"],
            "sequence_first":w["sequence_first"],"sequence_last":w["sequence_last"],
            "entry_price":w["entry_price"],"exit_price":w["exit_price"],
            "gross_return":w["gross_return"],
            "sequence_span":w["sequence_last"]-w["sequence_first"] if w["sequence_first"] is not None and w["sequence_last"] is not None else None,
            "nearest_controls":[
                {"relative":("before" if c["timestamp_dt"]<w["timestamp_dt"] else "after"),
                 "timestamp":c["timestamp"],"sequence_first":c["sequence_first"],
                 "sequence_last":c["sequence_last"],"gross_return":c["gross_return"],
                 "direction":c["direction"],
                 "time_delta_seconds":(c["timestamp_dt"]-w["timestamp_dt"]).total_seconds(),
                 "sequence_delta_first":(c["sequence_first"]-w["sequence_first"]) if c["sequence_first"] is not None and w["sequence_first"] is not None else None,
                 "outcome_gap":c["gross_return"]-w["gross_return"]}
                for c in wc
            ]}

def main():
    rows,invalid,trade_count,candle_count=build_rows()
    winners=[r for r in rows if r["gross_return"]>THRESHOLD]
    if len(winners) != 2:
        precondition={
            "status":"BOUNDARY_SEQUENCE_OUTCOME_AUDIT_BLOCKED_PROTOCOL_PRECONDITION",
            "reason":"The frozen audit contract requires exactly two >14bps winners; the new raw snapshot produced a different winner count. No winner subset was selected and no threshold was changed.",
            "protocol":{"threshold":THRESHOLD,"required_winner_count":2,"actual_winner_count":len(winners),"folds":FOLDS,
                        "snapshot_blob":EXPECTED_BLOB,"snapshot_source_commit":EXPECTED_COMMIT},
            "population":{"evaluated_oos":len(rows),"source_trade_rows":trade_count,"candles":candle_count,"invalid_rows":invalid},
            "safety":{"signal_created":False,"threshold_tuned":False,"model_fitted":False,"promotion_decision":False,"live_execution":False}
        }
        (ROOT/"winner_nearest_control_boundary_audit.json").write_text(json.dumps(precondition,indent=2)+"\\n",encoding="utf-8")
        print(json.dumps(precondition,indent=2))
        raise SystemExit(2)
    results=[]
    for w in winners:
        controls=nearest_controls(rows,w)
        assert controls
        results.append(compact(w,controls))
    boundary_checks=[]
    for r in results:
        w=r
        for c in r["nearest_controls"]:
            boundary_checks.append({
                "winner_timestamp":w["timestamp"],"control_timestamp":c["timestamp"],
                "same_fold":True,
                "same_direction":c["direction"]==w["direction"],
                "timestamp_order_valid":c["time_delta_seconds"]!=0,
                "sequence_order_valid":c["sequence_delta_first"] is None or c["sequence_delta_first"]!=0,
                "winner_exceeds_threshold":w["gross_return"]>THRESHOLD,
                "control_at_or_below_threshold":c["gross_return"]<=THRESHOLD,
                "outcome_separation":w["gross_return"]-c["gross_return"],
            })
    # Explicitly verify no winner/control boundary overlap by sequence or timestamp.
    all_w=[(r["sequence_first"],r["timestamp"]) for r in winners]
    all_c=[(c["sequence_first"],c["timestamp"]) for r in results for c in r["nearest_controls"]]
    seq_overlap=set(x[0] for x in all_w if x[0] is not None)&set(x[0] for x in all_c if x[0] is not None)
    ts_overlap=set(x[1] for x in all_w)&set(x[1] for x in all_c)
    out={
      "status":"BOUNDARY_SEQUENCE_OUTCOME_AUDIT_REVIEW_ONLY",
      "protocol":{"threshold":THRESHOLD,"nearest_control_definition":"up to 2 temporally nearest controls before and after each winner, same OOS fold","folds":FOLDS,
                  "snapshot_blob":EXPECTED_BLOB,"snapshot_source_commit":EXPECTED_COMMIT},
      "population":{"evaluated_oos":len(rows),"winners":len(winners),"controls":len(rows)-len(winners),
                    "source_trade_rows":trade_count,"candles":candle_count,"invalid_rows":invalid},
      "winner_audits":results,
      "boundary_checks":boundary_checks,
      "integrity":{"winner_control_sequence_first_overlap_count":len(seq_overlap),
                   "winner_control_timestamp_overlap_count":len(ts_overlap),
                   "all_control_outcomes_le_threshold":all(c["control_at_or_below_threshold"] for c in boundary_checks),
                   "all_timestamp_order_valid":all(c["timestamp_order_valid"] for c in boundary_checks),
                   "all_sequence_order_valid":all(c["sequence_order_valid"] for c in boundary_checks)},
      "interpretation":{"independent_temporal_units":2,"winner_fold_count":2,
                        "claim":"Both winners are temporally distinct and outcome-distinct from their nearest same-fold controls, but the evidence remains n=2 and therefore does not establish a generalizable signal.",
                        "signal_created":False,"threshold_tuned":False,"model_fitted":False,
                        "promotion_decision":False,"live_execution":False}
    }
    (ROOT/"winner_nearest_control_boundary_audit.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(out,indent=2))

if __name__=="__main__": main()
