from datetime import datetime, timezone
from forward.sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1

ASOF = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)

def rec(seq, ts="2026-10-07T06:30:00+00:00", price="100"):
    return {"source":"tabdeal_ws_forward_v1","symbol":"BTC_USDT","price":price,"amount":"1",
            "side":"buy","source_updated":ts,"sequence":seq}

def test_unknown_capabilities_block_even_monotonic_numeric_progress():
    result=SequenceAwareCandleIngestionV1().ingest([rec(1),rec(2,"2026-10-07T06:35:00+00:00","105")],as_of=ASOF)
    assert not result.safe_for_decision
    assert result.reason=="SEQUENCE_CAPABILITIES_UNVERIFIED"
    assert result.candles==() and result.events==()
    assert result.diagnostics[0]["capabilities"]=={
        "event_identity_unique":"unknown","ordered_within_scope":"unknown",
        "contiguous_within_scope":"unknown","gap_detectable":"unknown"}

def test_reused_sequence_is_not_claimed_as_conflicting_duplicate():
    result=SequenceAwareCandleIngestionV1().ingest([rec(1,price="100"),rec(1,price="101")],as_of=ASOF)
    assert not result.safe_for_decision
    assert result.reason=="SEQUENCE_CAPABILITIES_UNVERIFIED"
    assert result.events==() and result.candles==()

def test_numeric_jump_is_not_inferred_as_missing_market_event():
    result=SequenceAwareCandleIngestionV1().ingest([rec(10),rec(12,"2026-10-07T06:35:00+00:00","105")],as_of=ASOF)
    assert not result.safe_for_decision
    assert result.reason=="SEQUENCE_CAPABILITIES_UNVERIFIED"
