"""Frozen, chronological research runner for Range Strategy v2 (no live actions)."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from forward.range_strategy_engine_v2 import (CostModel, evaluate_range_strategy, _percentile, BOUNDARY_LOW_QUANTILE, BOUNDARY_HIGH_QUANTILE)
from forward.universal_indicator_engine_v1 import OHLCVBar

SOURCE = Path("/opt/hes-trade-agent/evidence/research/gateio_btcusdt_90d_20261104/hes-gateio-btcusdt-15m-90d-paginated-20261104T193800Z.jsonl")
COSTS_BPS = (5, 10, 15, 30)
MAX_HOLD = 64


def load_15m(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    bars = []
    for row in rows:
        if row.get("source") != "gateio_public_spot" or row.get("symbol") != "BTC_USDT" or row.get("timeframe") != "15m" or row.get("closed") is not True:
            raise ValueError("NONCANONICAL_OR_UNCLOSED_SOURCE_ROW")
        bars.append(OHLCVBar(int(row["open_time"]), float(row["open"]), float(row["high"]),
            float(row["low"]), float(row["close"]), float(row["volume"]), float(row["quote_volume"]), True))
    if any(bars[i+1].timestamp - bars[i].timestamp != 900 for i in range(len(bars)-1)):
        raise ValueError("SOURCE_15M_GAP")
    return bars


def resample(bars, group_size, seconds):
    # Align aggregates to UTC timeframe boundaries, not to the first source row.
    buckets = {}
    for bar in bars:
        buckets.setdefault(bar.timestamp // seconds, []).append(bar)
    out = []
    for bucket in sorted(buckets):
        group = buckets[bucket]
        expected_start = bucket * seconds
        if len(group) != group_size:
            continue
        if group[0].timestamp != expected_start:
            continue
        if any(group[i+1].timestamp-group[i].timestamp != 900 for i in range(group_size-1)):
            continue
        out.append(OHLCVBar(group[0].timestamp, group[0].open, max(b.high for b in group),
            min(b.low for b in group), group[-1].close, sum(b.volume for b in group),
            sum(b.quote_volume for b in group), True))
    if any(out[i+1].timestamp-out[i].timestamp != seconds for i in range(len(out)-1)):
        raise ValueError("RESAMPLED_HTF_GAP")
    return out

def settle_trade(bars, entry_i, direction, entry, stop, target, cost_fraction):
    last_i = min(len(bars)-1, entry_i + MAX_HOLD - 1)
    exit_price = exit_i = outcome = None
    for j in range(entry_i, last_i+1):
        b = bars[j]
        if direction == "LONG":
            if b.open <= stop: exit_price, exit_i, outcome = b.open, j, "STOP_GAP"; break
            if b.open >= target: exit_price, exit_i, outcome = target, j, "TARGET_GAP"; break
            if b.low <= stop: exit_price, exit_i, outcome = stop, j, "STOP"; break
            if b.high >= target: exit_price, exit_i, outcome = target, j, "TARGET"; break
        else:
            if b.open >= stop: exit_price, exit_i, outcome = b.open, j, "STOP_GAP"; break
            if b.open <= target: exit_price, exit_i, outcome = target, j, "TARGET_GAP"; break
            if b.high >= stop: exit_price, exit_i, outcome = stop, j, "STOP"; break
            if b.low <= target: exit_price, exit_i, outcome = target, j, "TARGET"; break
    if exit_price is None:
        exit_i, exit_price, outcome = last_i, bars[last_i].close, "TIME_EXIT"
    signed = exit_price-entry if direction == "LONG" else entry-exit_price
    cost = entry * cost_fraction
    net_r = (signed-cost)/(abs(entry-stop)+cost)
    return {"exit_index":exit_i,"exit_price":exit_price,"outcome":outcome,"net_r":net_r}


def summarize(trades):
    if not trades:
        return {"trades":0,"wins":0,"win_rate_pct":None,"avg_net_r":None,"median_net_r":None,
            "total_net_r":0.0,"profit_factor":None,"max_drawdown_r":0.0,"outcomes":{}}
    rs=[x["net_r"] for x in trades]
    wins=[x for x in rs if x>0]
    equity=peak=drawdown=0.0
    for value in rs:
        equity += value
        peak=max(peak,equity)
        drawdown=max(drawdown,peak-equity)
    gp=sum(x for x in rs if x>0)
    gl=abs(sum(x for x in rs if x<0))
    return {"trades":len(rs),"wins":len(wins),"win_rate_pct":round(100*len(wins)/len(rs),3),
        "avg_net_r":round(mean(rs),6),"median_net_r":round(median(rs),6),
        "total_net_r":round(sum(rs),6),"profit_factor":round(gp/gl,6) if gl else None,
        "max_drawdown_r":round(drawdown,6),"outcomes":dict(Counter(x["outcome"] for x in trades))}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,default=SOURCE)
    ap.add_argument("--output",type=Path,default=ROOT/"research/range_strategy_v2")
    args=ap.parse_args()
    raw=args.source.read_bytes()
    bars=load_15m(args.source)
    h1=resample(bars,4,3600)
    h4=resample(bars,16,14400)
    split=int(len(bars)*2/3)
    h1_close_times=[b.timestamp+3600 for b in h1]
    h4_close_times=[b.timestamp+14400 for b in h4]
    candidate_signals=[]
    prefilter_count=0
    rejection_counts=Counter()
    first_eval=None
    # Necessary-condition prefilter: the policy cannot emit unless the closed
    # signal candle sweeps and reclaims one of the prior-only 64-bar boundaries.
    for i in range(219,len(bars)-1):
        observed_epoch=bars[i].timestamp+900
        h1_count=bisect_right(h1_close_times,observed_epoch)
        h4_count=bisect_right(h4_close_times,observed_epoch)
        if h1_count < 220 or h4_count < 220: continue
        prior=bars[i-64:i]
        lower=_percentile([b.low for b in prior],BOUNDARY_LOW_QUANTILE)
        upper=_percentile([b.high for b in prior],BOUNDARY_HIGH_QUANTILE)
        bar=bars[i]
        if not ((bar.low < lower and bar.close > lower) or (bar.high > upper and bar.close < upper)):
            continue
        prefilter_count += 1
        w15=bars[max(0,i-239):i+1]
        w1h=h1[max(0,h1_count-240):h1_count]
        w4h=h4[max(0,h4_count-240):h4_count]
        observed=datetime.fromtimestamp(observed_epoch,tz=timezone.utc)
        if first_eval is None: first_eval=observed.isoformat()
        candidate=evaluate_range_strategy(source="gateio_public_spot",symbol="BTC_USDT",
            timeframe="15m",observed_at=observed,bars_15m=w15,bars_1h=w1h,bars_4h=w4h,
            cost_model=CostModel("ZERO_COST_SCREEN",0.0,False))
        if candidate.state=="RESEARCH_CANDIDATE":
            candidate_signals.append((i,candidate))
        else:
            rejection_counts.update(candidate.reason_codes)
    results={}
    for bps in COSTS_BPS:
        cost_fraction=bps/10000.0
        trades=[]
        next_free=0
        for i,candidate in candidate_signals:
            if i < next_free: continue
            entry_i=i+1
            entry=bars[entry_i].open
            stop,target=candidate.stop_loss,candidate.take_profit
            if candidate.direction=="LONG" and not stop < entry < target: continue
            if candidate.direction=="SHORT" and not target < entry < stop: continue
            cost=entry*cost_fraction
            risk=abs(entry-stop)
            reward=abs(target-entry)
            net_rr=(reward-cost)/(risk+cost)
            if reward<=cost or net_rr<1.20: continue
            settled=settle_trade(bars,entry_i,candidate.direction,entry,stop,target,cost_fraction)
            trades.append({"signal_index":i,"entry_index":entry_i,"entry_time":bars[entry_i].timestamp,
                "direction":candidate.direction,"entry":entry,"stop":stop,"target":target,
                "net_rr_at_entry":net_rr,**settled})
            next_free=settled["exit_index"]+1
        all_summary=summarize(trades)
        holdout=[x for x in trades if x["signal_index"]>=split]
        results[str(bps)]={"assumed_round_trip_cost_bps":bps,"raw_candidate_signals":len(candidate_signals),
            "all":all_summary,"chronological_final_third":summarize(holdout)}
    report={"schema":"hes_range_strategy_v2_research_report","policy_version":"2.0.0-research",
        "base_commit":"09f660d625df3f8964ba8ddd20c9a9cf8a400f19",
        "source_path":str(args.source),"source_sha256":hashlib.sha256(raw).hexdigest(),
        "source_rows":len(bars),"source_start_utc":datetime.fromtimestamp(bars[0].timestamp,tz=timezone.utc).isoformat(),
        "source_end_utc":datetime.fromtimestamp(bars[-1].timestamp+900,tz=timezone.utc).isoformat(),
        "source_gap_count":sum(bars[i+1].timestamp-bars[i].timestamp!=900 for i in range(len(bars)-1)),
        "resampled_1h_rows":len(h1),"resampled_4h_rows":len(h4),
        "htf_method":"causal aggregation of contiguous closed source 15m candles; not independent feed",
        "first_evaluated_setup_utc":first_eval,"boundary_sweep_prefilter_bars":prefilter_count,
        "candidate_rejection_reason_counts":dict(rejection_counts),"holdout_start_index":split,
        "entry_method":"next contiguous 15m open; no 1m refinement in this historical study",
        "intrabar_policy":"stop-first if stop and target both touch; stop gap filled at open; target gap filled at target",
        "max_holding_bars":MAX_HOLD,"non_overlapping":True,
        "execution_enabled":False,"orders_placed":False,"status":"RESEARCH_ONLY_NOT_ACTIVE",
        "results_by_round_trip_cost_bps":results,
        "limitations":["15m-only 90-day source; HTF series are resampled from same 15m data.",
            "No 1m precision-entry replay or derivatives execution model.",
            "Final-third slice is chronological holdout diagnostic, not independent external OOS.",
            "Cost levels are assumptions, not verified fills or fee schedule."]}
    args.output.mkdir(parents=True,exist_ok=True)
    out=args.output/"range_strategy_v2_90d_report.json"
    out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n")
    print(json.dumps({"output":str(out),"source_rows":len(bars),"first_eval":first_eval,
        "results":results},indent=2,allow_nan=False))

if __name__=="__main__": main()
