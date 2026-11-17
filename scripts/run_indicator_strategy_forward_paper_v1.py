#!/usr/bin/env python3
"""Forward-only indicator-family paper observer with 1m precision entry. No orders."""
from __future__ import annotations
import argparse, hashlib, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

CODE_ROOT=Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path: sys.path.insert(0,str(CODE_ROOT))
DATA_ROOT=Path(os.environ.get("HES_DATA_ROOT","/opt/hes-trade-agent")).expanduser().resolve()
from forward.global_market_data_reader_v1 import load_market_input, read_closed_candles, SOURCE, SYMBOL
from forward.universal_indicator_engine_v1 import OHLCVBar, build_snapshot
from forward.indicator_strategy_family_v1 import evaluate_indicator_family, geometry, VARIANTS
from forward.forward_journal_v1 import ForwardJournalV1

BASE=DATA_ROOT/"data/forward"
STATE=BASE/"indicator_strategy_forward_paper_state_v1.json"
DECISIONS=BASE/"indicator_strategy_forward_paper_journal_v1.jsonl"
OUTCOMES=BASE/"indicator_strategy_forward_paper_outcomes_v1.jsonl"
REPORT=BASE/"indicator_strategy_forward_paper_report_v1.json"
COST_BPS=20
MAX_HOLD_MINUTES=1440
POLL_SECONDS=20

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def sha256_obj(value):
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()

def to_bar(row, timeframe):
    seconds={"1m":60,"15m":900,"1h":3600,"4h":14400}[timeframe]
    if row.get("closed") is not True or int(row["close_time"]) != int(row["open_time"])+seconds:
        raise ValueError("CLOSED_CANDLE_CONTRACT_INVALID")
    return OHLCVBar(timestamp=int(row["close_time"]),open=float(row["open"]),high=float(row["high"]),
        low=float(row["low"]),close=float(row["close"]),volume=float(row["volume"]),
        quote_volume=float(row["quote_volume"]) if row.get("quote_volume") is not None else None,closed=True)

def snapshot_asof(rows, timeframe, signal_close_time):
    eligible=[r for r in rows if int(r["close_time"])<=signal_close_time]
    if len(eligible)<220:
        raise ValueError("INSUFFICIENT_ASOF_HISTORY:"+timeframe)
    window=eligible[-240:]
    snap=build_snapshot([to_bar(r,timeframe) for r in window],venue="gateio",market="spot",
        symbol=SYMBOL,timeframe=timeframe,volume_semantics_qualified=True)
    return snap,sha256_obj(window)

def _load_state():
    if not STATE.exists(): return None
    if STATE.is_symlink(): raise ValueError("STATE_PATH_SYMLINK_REJECTED")
    value=json.loads(STATE.read_text())
    if not isinstance(value,dict): raise ValueError("STATE_SCHEMA_INVALID")
    return value

def _save_state(state):
    BASE.mkdir(parents=True,exist_ok=True)
    tmp=STATE.with_name(STATE.name+".tmp")
    if STATE.is_symlink() or tmp.is_symlink(): raise ValueError("STATE_PATH_SYMLINK_REJECTED")
    with tmp.open("w",encoding="utf-8") as f:
        json.dump(state,f,indent=2,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
    os.replace(tmp,STATE)

def _append_decision(journal, row):
    try:
        journal.append_decision(row)
    except ValueError as exc:
        if str(exc)!="duplicate event_id": raise

def _decision_record(candidate, *, signal_bar, entry_bar, hashes, status, reasons, variant_id=None, regime=None):
    variant_id=candidate.variant_id if candidate else variant_id
    if variant_id not in VARIANTS: raise ValueError("INVALID_STRATEGY_VARIANT")
    direction=candidate.direction if candidate and status=="OPENED" else "NO_TRADE"
    return {
        "schema":"hes_indicator_strategy_forward_decision_v1",
        "event_id":f"hes-indicator-forward-{variant_id}-{signal_bar['close_time']}",
        "observed_at":utc_now(),"symbol":SYMBOL,"timeframe":"15m","decision":direction,
        "evidence_source":SOURCE,"signal_candle_close_time":int(signal_bar["close_time"]),
        "entry_candle_open_time":int(entry_bar["open_time"]),"entry":float(entry_bar["open"]) if candidate else None,
        "entry_timeframe":"1m","entry_model":"FIRST_1M_OPEN_AFTER_15M_SIGNAL_CLOSE",
        "strategy_family_id":"indicator_strategy","strategy_family_version":"hes-indicator-strategy-family-v1.0.0",
        "strategy_variant_id":variant_id,
        "direction":candidate.direction if candidate else None,
        "market_regime":candidate.regime if candidate else (regime or "UNKNOWN"),
        "reason_codes":list(candidate.reason_codes) if candidate else list(reasons),
        "feature_snapshot":dict(candidate.feature_snapshot) if candidate else {},
        "stop_loss":None,"take_profit":None,"rr":None,
        "status":status,"status_reasons":list(reasons),"input_sha256_by_timeframe":hashes,
        "cost_assumption_round_trip_bps":COST_BPS,
        "research_only":True,"performance_eligible":False,"training_label_eligible":False,
        "decision_authority":False,"candidate_generation_authorized":False,
        "risk_gate_bypass":False,"execution_enabled":False,"orders_placed":False,
        "outcome":None,"closed_at":None
    }

def _exit_for_bar(position, bar):
    entry=float(position["entry"]); stop=float(position["stop_loss"]); target=float(position["take_profit"])
    direction=position["direction"]; op=float(bar["open"]); hi=float(bar["high"]); lo=float(bar["low"])
    if direction=="LONG":
        if op<=stop: return op,"STOP_GAP"
        if op>=target: return target,"TAKE_PROFIT_GAP"
        sl=lo<=stop; tp=hi>=target
    elif direction=="SHORT":
        if op>=stop: return op,"STOP_GAP"
        if op<=target: return target,"TAKE_PROFIT_GAP"
        sl=hi>=stop; tp=lo<=target
    else: raise ValueError("INVALID_POSITION_DIRECTION")
    if sl and tp: return stop,"STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST"
    if sl: return stop,"STOP_LOSS"
    if tp: return target,"TAKE_PROFIT"
    return None,None

def _outcome(position, bar, exit_price, reason):
    direction=position["direction"];entry=float(position["entry"])
    gross_pct=((exit_price-entry)/entry if direction=="LONG" else (entry-exit_price)/entry)*100
    net_pct=gross_pct-COST_BPS/100
    short=direction=="SHORT"
    return {
        "schema":"hes_indicator_strategy_forward_outcome_v1",
        "event_id":"outcome-"+position["candidate_event_id"],
        "candidate_event_id":position["candidate_event_id"],"observed_at":utc_now(),
        "symbol":SYMBOL,"timeframe":"15m","entry_timeframe":"1m","exit_timeframe":"1m",
        "strategy_family_id":"indicator_strategy","strategy_family_version":position["strategy_family_version"],
        "strategy_variant_id":position["strategy_variant_id"],"direction":direction,
        "market_regime":position["market_regime"],"entry":entry,"stop_loss":position["stop_loss"],
        "take_profit":position["take_profit"],"exit_price":float(exit_price),
        "exit_candle_close_time":int(bar["close_time"]),"hold_minutes":int(position["hold_minutes"]),
        "outcome":reason,"gross_return_pct":round(gross_pct,8),
        "net_return_pct_assumption_20bps":round(net_pct,8),"cost_assumption_round_trip_bps":COST_BPS,
        "economics_status":"NOT_ECONOMICALLY_VALIDATED_FROM_SPOT" if short else "ASSUMPTION_BASED_SPOT_REFERENCE",
        "research_only":True,"performance_eligible":False,"research_label_eligible":True,
        "training_label_eligible":False,"decision_authority":False,"execution_enabled":False,"orders_placed":False
    }

def process_new_closed_minutes(frames, state, decision_journal, outcome_journal, save_state=None):
    mins=frames["1m"]; opens=[int(r["open_time"]) for r in mins]
    cursor=state["last_processed_1m_open_time"]
    start=opens.index(cursor) if cursor in set(opens) else None
    if start is None: raise ValueError("FORWARD_1M_CURSOR_OUTSIDE_AVAILABLE_WINDOW_FAIL_CLOSED")
    signal_by_close={int(r["close_time"]):r for r in frames["15m"]}
    new_minutes=mins[start+1:]
    # Validate every 15m boundary before writing anything; do not silently skip late/missing 15m context.
    last_signal=int(state["last_processed_signal_close_time"])
    for minute in new_minutes:
        mt=int(minute["open_time"])
        if mt%900==0 and mt>last_signal and mt not in signal_by_close:
            raise ValueError("15M_SIGNAL_NOT_AVAILABLE_AT_FIRST_1M_ENTRY_BAR")
    processed=0
    for minute in new_minutes:
        minute_open=int(minute["open_time"])
        # Resolve existing positions first using only the newly closed 1m bar.
        for variant,position in list(state["active"].items()):
            if int(position["entry_candle_open_time"])>=minute_open: continue
            position["hold_minutes"]+=1
            px,reason=_exit_for_bar(position,minute)
            if px is None and position["hold_minutes"]>=MAX_HOLD_MINUTES:
                px=float(minute["close"]);reason="MAX_HOLD_TIMEOUT"
            if px is not None:
                outcome_journal.append_event(_outcome(position,minute,px,reason))
                del state["active"][variant]
        # 15m setup can only be evaluated at its exact close; first 1m bar is the precision entry.
        if minute_open%900==0 and minute_open>int(state["last_processed_signal_close_time"]):
            signal_bar=signal_by_close[minute_open]
            s15,h15=snapshot_asof(frames["15m"],"15m",minute_open)
            s1,h1=snapshot_asof(frames["1h"],"1h",minute_open)
            s4,h4=snapshot_asof(frames["4h"],"4h",minute_open)
            hashes={"15m":h15,"1h":h1,"4h":h4}
            found=evaluate_indicator_family(s15,s1,s4,close=float(signal_bar["close"]))
            by_variant={c.variant_id:c for c in found}
            for variant in VARIANTS:
                candidate=by_variant.get(variant)
                if candidate is None:
                    row=_decision_record(None,signal_bar=signal_bar,entry_bar=minute,hashes=hashes,
                        status="NO_QUALIFIED_SETUP",reasons=["NO_QUALIFIED_SETUP"],variant_id=variant,regime=s15.regime.label)
                    _append_decision(decision_journal,row);continue
                if variant in state["active"]:
                    row=_decision_record(candidate,signal_bar=signal_bar,entry_bar=minute,hashes=hashes,
                        status="BLOCKED_OVERLAPPING_POSITION",reasons=["ONE_POSITION_PER_VARIANT"])
                    _append_decision(decision_journal,row);continue
                geo=geometry(candidate,float(minute["open"]))
                if geo is None:
                    row=_decision_record(candidate,signal_bar=signal_bar,entry_bar=minute,hashes=hashes,
                        status="BLOCKED_INVALID_GEOMETRY",reasons=["INVALID_STOP_TARGET_GEOMETRY"])
                    _append_decision(decision_journal,row);continue
                row=_decision_record(candidate,signal_bar=signal_bar,entry_bar=minute,hashes=hashes,
                    status="OPENED",reasons=[])
                row.update({"stop_loss":geo["stop_loss"],"take_profit":geo["take_profit"],"rr":geo["rr"]})
                candidate_id=row["event_id"]
                _append_decision(decision_journal,row)
                state["active"][variant]={
                    "candidate_event_id":candidate_id,"strategy_family_version":candidate.family_version,
                    "strategy_variant_id":variant,"direction":candidate.direction,"market_regime":candidate.regime,
                    "entry":geo["entry"],"stop_loss":geo["stop_loss"],"take_profit":geo["take_profit"],
                    "entry_candle_open_time":minute_open,"hold_minutes":0
                }
                px,reason=_exit_for_bar(state["active"][variant],minute)
                if px is not None:
                    outcome_journal.append_event(_outcome(state["active"][variant],minute,px,reason))
                    del state["active"][variant]
            state["last_processed_signal_close_time"]=minute_open
        state["last_processed_1m_open_time"]=minute_open
        state["processed_1m_bars"]+=1;processed+=1
        if save_state is not None: save_state(state)
    return processed

def _new_state(frames, *, migration_from=None):
    latest_1m=frames["1m"][-1];latest_15m=frames["15m"][-1]
    return {"schema":"hes_indicator_strategy_forward_paper_state_v2",
        "initialized_at":utc_now(),"bootstrap_mode":"NO_RETROACTIVE_TRADES",
        "migration_from_schema":migration_from,
        "last_processed_1m_open_time":int(latest_1m["open_time"]),
        "last_processed_signal_close_time":int(latest_15m["close_time"]),
        "processed_1m_bars":0,"active":{}}

def run_once():
    src=load_market_input(root=DATA_ROOT,min_bars=220)
    frames=src["timeframes"]
    frames["1m"]=read_closed_candles("1m",root=DATA_ROOT,min_bars=220)
    old=_load_state()
    if old is None:
        state=_new_state(frames)
        count=0
    elif old.get("schema")=="hes_indicator_strategy_forward_paper_state_v2":
        state=old
        decisions=ForwardJournalV1(DECISIONS);outcomes=ForwardJournalV1(OUTCOMES)
        count=process_new_closed_minutes(frames,state,decisions,outcomes,_save_state)
    elif old.get("schema")=="hes_indicator_strategy_forward_paper_state_v1":
        # Prior bootstrap-only state had no decision/outcome records; migrate cursor without backfill.
        dcount=sum(1 for _ in DECISIONS.open()) if DECISIONS.exists() else 0
        ocount=sum(1 for _ in OUTCOMES.open()) if OUTCOMES.exists() else 0
        if dcount or ocount: raise ValueError("LEGACY_STATE_HAS_LEDGER_DATA_REQUIRES_MANUAL_RECONCILIATION")
        state=_new_state(frames,migration_from=old.get("schema"))
        count=0
    else:
        raise ValueError("STATE_SCHEMA_INVALID")
    _save_state(state)
    decisions_count=sum(1 for _ in DECISIONS.open()) if DECISIONS.exists() else 0
    outcomes_count=sum(1 for _ in OUTCOMES.open()) if OUTCOMES.exists() else 0
    report={"schema":"hes_indicator_strategy_forward_paper_report_v1","updated_at":utc_now(),
        "status":"FORWARD_PAPER_OBSERVATION_ACTIVE" if state["processed_1m_bars"] else "BOOTSTRAPPED_WAITING_FOR_NEXT_15M_SIGNAL",
        "source":SOURCE,"symbol":SYMBOL,"latest_closed_15m_time":int(frames["15m"][-1]["close_time"]),
        "latest_closed_1m_time":int(frames["1m"][-1]["close_time"]),
        "new_1m_bars_processed":count,"processed_1m_bars_total":state["processed_1m_bars"],
        "decision_records":decisions_count,"outcome_records":outcomes_count,
        "active_positions_by_variant":{k:{"direction":v["direction"],"regime":v["market_regime"],"entry":v["entry"],"hold_minutes":v["hold_minutes"]} for k,v in state["active"].items()},
        "method":{"setup_timeframe":"15m","context_timeframes":["1h","4h"],
            "precision_entry_timeframe":"1m","signal_only_uses_closed_candles":True,
            "higher_timeframes_asof_signal_close":True,
            "entry":"first 1m candle open at the 15m signal close",
            "stop":"1.5 x setup ATR(14)","target":"3R",
            "max_hold_minutes":MAX_HOLD_MINUTES,"same_candle_stop_target":"STOP_FIRST",
            "overlap":"one open position per variant","round_trip_cost_bps_assumption":COST_BPS},
        "limitations":["Paper-only hypothetical fills; no order routing.",
            "1m bar-open fills are simulated and recorded only after the 1m candle closes.",
            "20 bps is an unverified cost assumption, not actual fees/slippage.",
            "SHORT results are not economically validated by Spot data.",
            "No model training, threshold tuning, strategy promotion or performance acceptance.",
            "Only data after the bootstrap cursor is included; no historical backfill."],
        "safety":{"research_only":True,"performance_eligible":False,"training_label_eligible":False,
            "decision_authority":False,"candidate_generation_authorized":False,"risk_gate_bypass":False,
            "execution_enabled":False,"orders_placed":False}}
    REPORT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--daemon",action="store_true")
    ap.add_argument("--poll-seconds",type=int,default=POLL_SECONDS)
    args=ap.parse_args()
    if not args.daemon:
        print(json.dumps(run_once(),indent=2));return
    while True:
        try: print(json.dumps(run_once(),sort_keys=True),flush=True)
        except Exception as exc:
            print(json.dumps({"error":type(exc).__name__+":"+str(exc)[:200],
                "decision":"NO_TRADE","execution_enabled":False}),flush=True)
        time.sleep(max(10,args.poll_seconds))
if __name__=="__main__":main()
