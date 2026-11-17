from types import SimpleNamespace
import json
import pytest
from scripts import run_indicator_strategy_forward_paper_v1 as paper
from scripts.run_indicator_strategy_learning_v1 import build_report

def bar(open_time, seconds, o=100, h=101, l=99, c=100):
    return {"open_time":open_time,"close_time":open_time+seconds,"open":o,"high":h,"low":l,"close":c,
        "volume":1.0,"quote_volume":100.0,"closed":True,"source":"gateio_public_spot","symbol":"BTC_USDT",
        "timeframe":{900:"15m",3600:"1h",14400:"4h"}[seconds]}

def test_decision_ids_are_unique_per_variant_even_without_signal():
    signal=bar(900,900); entry=bar(1800,900)
    ids=[]
    for variant in paper.VARIANTS:
        row=paper._decision_record(None,signal_bar=signal,entry_bar=entry,hashes={},status="NO_QUALIFIED_SETUP",
            reasons=["NO_QUALIFIED_SETUP"],variant_id=variant,regime="RANGE")
        ids.append(row["event_id"])
        assert row["strategy_variant_id"]==variant
        assert row["market_regime"]=="RANGE"
        assert row["decision"]=="NO_TRADE"
    assert len(set(ids))==len(paper.VARIANTS)

def test_long_and_short_same_candle_stop_target_are_stop_first():
    long={"direction":"LONG","entry":100,"stop_loss":95,"take_profit":115}
    short={"direction":"SHORT","entry":100,"stop_loss":105,"take_profit":85}
    b={"open":100,"high":116,"low":80,"close":101}
    assert paper._exit_for_bar(long,b)==(95,"STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST")
    assert paper._exit_for_bar(short,b)==(105,"STOP_AND_TARGET_SAME_CANDLE_STOP_FIRST")

def test_gap_through_stop_uses_adverse_open():
    assert paper._exit_for_bar({"direction":"LONG","entry":100,"stop_loss":95,"take_profit":115},
        {"open":93,"high":100,"low":92,"close":94})==(93.0,"STOP_GAP")

def test_snapshot_asof_never_uses_higher_timeframe_future_candle(monkeypatch):
    rows=[]
    for i in range(240):
        t=i*3600
        rows.append(bar(t,3600,100,101,99,100))
    signal_close=238*3600
    captured={}
    def fake_build(bars,**kwargs):
        captured["last"]=bars[-1].timestamp
        return SimpleNamespace(as_of=bars[-1].timestamp)
    monkeypatch.setattr(paper,"build_snapshot",fake_build)
    snap,_=paper.snapshot_asof(rows,"1h",signal_close)
    assert snap.as_of<=signal_close
    assert captured["last"]<=signal_close

def test_learning_bridge_keeps_forward_paper_separate_from_training(tmp_path):
    historical_j=tmp_path/"historical.jsonl";historical_o=tmp_path/"historical_out.jsonl"
    forward_j=tmp_path/"forward.jsonl";forward_o=tmp_path/"forward_out.jsonl";report=tmp_path/"report.json"
    historical_j.write_text("");historical_o.write_text("")
    d={"event_id":"forward-candidate-1","strategy_family_id":"indicator_strategy","strategy_variant_id":"trend_confirmation",
       "market_regime":"BULLISH","research_only":True,"status":"OPENED"}
    o={"event_id":"forward-outcome-1","candidate_event_id":"forward-candidate-1","strategy_variant_id":"trend_confirmation",
       "market_regime":"BULLISH","direction":"LONG","research_only":True,
       "economics_status":"ASSUMPTION_BASED_SPOT_REFERENCE","net_return_pct_assumption_20bps":0.2}
    forward_j.write_text(json.dumps(d)+"\n");forward_o.write_text(json.dumps(o)+"\n")
    result=build_report(historical_j,historical_o,report,forward_j,forward_o)
    assert result["forward_paper"]["decision_records"]==1
    assert result["forward_paper"]["variants"]["trend_confirmation"]["resolved"]==1
    assert result["forward_paper"]["training_eligible_labels"]==0
    assert result["training_gate"]["eligible_forward_paper_labels"]==0


def test_forward_processor_writes_one_variant_decision_per_new_bar(monkeypatch):
    class Journal:
        def __init__(self): self.rows=[]
        def append_decision(self,row): self.rows.append(row)
    class OutcomeJournal:
        def append_event(self,row): raise AssertionError("no outcomes expected")
    rows=[bar(i*900,900) for i in range(222)]
    frames={"15m":rows,"1h":[bar(i*3600,3600) for i in range(240)],
        "4h":[bar(i*14400,14400) for i in range(240)]}
    dummy=SimpleNamespace(regime=SimpleNamespace(label="RANGE"))
    monkeypatch.setattr(paper,"snapshot_asof",lambda rows,tf,ts:(dummy,"a"*64))
    monkeypatch.setattr(paper,"evaluate_indicator_family",lambda *args,**kwargs:[])
    state={"last_processed_entry_open_time":rows[-2]["open_time"],"active":{},"processed_bars":0}
    journal=Journal()
    n=paper.process_new_closed_bar(frames,state,journal,OutcomeJournal())
    assert n==1
    assert len(journal.rows)==len(paper.VARIANTS)
    assert len({r["event_id"] for r in journal.rows})==len(paper.VARIANTS)
    assert {r["strategy_variant_id"] for r in journal.rows}==set(paper.VARIANTS)
    assert all(r["market_regime"]=="RANGE" and r["decision"]=="NO_TRADE" for r in journal.rows)
    assert state["last_processed_entry_open_time"]==rows[-1]["open_time"]
    assert state["processed_bars"]==1
