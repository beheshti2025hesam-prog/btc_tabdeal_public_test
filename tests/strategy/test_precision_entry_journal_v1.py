from datetime import datetime, timezone
from forward.forward_journal_v1 import ForwardJournalV1
from scripts.run_precision_entry_journal_v1 import (
    build_paper_candidate, build_precision_event, resolve_candidate,
)

NOW=datetime(2026,11,3,9,0,tzinfo=timezone.utc)
CONTEXT={
    "setup_id":"hes-setup-BTC_USDT-15m-1800000000-LONG",
    "evidence_sha256":"a"*64,
    "direction":"LONG",
    "stop_price":99.0,
    "target_price":103.0,
}

def candidate():
    return build_paper_candidate(setup_context=CONTEXT,
        candle={"close_time":1800000000,"close":"100.0"},observed_at=NOW)

def bar(open_time,high,low,close):
    return {"open_time":open_time,"close_time":open_time+60,
            "high":str(high),"low":str(low),"close":str(close)}

def test_event_id_is_stable_per_setup_and_closed_candle():
    engine={"state":"WAIT","reason_codes":["MICROSTRUCTURE_TRIGGER_NOT_CONFIRMED"],"evidence":{"close":100.0}}
    candle={"close_time":1800000060,"close":"100.0","open_time":1800000000}
    a=build_precision_event(setup_context=CONTEXT,candle=candle,engine_result=engine,observed_at=NOW)
    b=build_precision_event(setup_context=CONTEXT,candle=candle,engine_result=engine,observed_at=NOW)
    assert a["event_id"]==b["event_id"]
    assert len(a["evidence_sha256"])==64
    assert a["execution_enabled"] is False and a["orders_placed"] is False

def test_paper_candidate_is_bound_to_setup_and_never_an_order():
    row=candidate()
    assert row["setup_id"]==CONTEXT["setup_id"]
    assert row["preapproval_paper_eligible"] is True
    assert row["paper_only"] is True
    assert row["execution_enabled"] is False and row["orders_placed"] is False

def test_append_only_writer_deduplicates_precision_events(tmp_path):
    journal=ForwardJournalV1(tmp_path/"precision.jsonl")
    row=candidate()
    assert journal.append_event(row) is True
    assert journal.append_event(row) is False

def test_long_take_profit_resolves_win():
    c=candidate()
    outcome=resolve_candidate(c,[bar(c["entry_time"],103.5,100.1,103.0)])
    assert outcome["outcome"]=="WIN"
    assert outcome["gross_r"]==3.0

def test_long_stop_loss_resolves_loss():
    c=candidate()
    outcome=resolve_candidate(c,[bar(c["entry_time"],101.0,98.5,99.0)])
    assert outcome["outcome"]=="LOSS"
    assert outcome["gross_r"]==-1.0

def test_same_candle_stop_and_target_is_conservatively_a_loss():
    c=candidate()
    outcome=resolve_candidate(c,[bar(c["entry_time"],104.0,98.0,101.0)])
    assert outcome["outcome"]=="LOSS"
    assert outcome["reason"]=="STOP_AND_TARGET_SAME_CANDLE_CONSERVATIVE_LOSS"

def test_future_gap_remains_unresolved():
    c=candidate()
    outcome=resolve_candidate(c,[bar(c["entry_time"]+60,104.0,100.0,103.0)])
    assert outcome is None

def test_short_direction_uses_inverse_stop_target_geometry():
    c=candidate()
    c.update({"direction":"SHORT","entry_price":100.0,"stop_price":101.0,"target_price":97.0})
    outcome=resolve_candidate(c,[bar(c["entry_time"],101.5,96.5,98.0)])
    assert outcome["outcome"]=="LOSS"
    assert outcome["gross_r"]==-1.0

def test_24_hour_timeout_requires_contiguous_one_minute_candles():
    c=candidate()
    rows=[bar(c["entry_time"]+i*60,100.5,99.5,100.0) for i in range(1440)]
    outcome=resolve_candidate(c,rows)
    assert outcome["outcome"]=="TIMEOUT"
    assert outcome["reason"]=="MAX_HOLD_24H_REACHED"
