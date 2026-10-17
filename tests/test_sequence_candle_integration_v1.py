from datetime import datetime, timezone

from forward.sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1
from forward.tabdeal_readonly_adapter_v1 import parse_trade_frame


ASOF = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)


def rec(seq, ts="2026-10-07T06:30:00+00:00", price="100"):
    return {
        "source": "tabdeal_ws_forward_v1",
        "symbol": "BTC_USDT",
        "price": price,
        "amount": "1",
        "side": "buy",
        "source_updated": ts,
        "sequence": seq,
        # Synthetic fixture only; production adapter remains UNKNOWN_OPAQUE.
        "sequence_semantics": "VERIFIED_MONOTONIC",
    }


def test_clean_sequence_reaches_closed_candle():
    s = SequenceAwareCandleIngestionV1()
    result = s.ingest(
        [
            rec(1, "2026-10-07T06:30:00+00:00", "100"),
            rec(2, "2026-10-07T06:35:00+00:00", "105"),
        ],
        as_of=ASOF,
    )
    assert result.safe_for_decision is True
    assert len(result.candles) == 1
    assert [e.status for e in result.events] == ["ACCEPTED", "ACCEPTED"]


def test_identical_duplicate_does_not_duplicate_candle_input():
    s = SequenceAwareCandleIngestionV1()
    r = rec(1)
    result = s.ingest([r, dict(r)], as_of=ASOF)
    assert result.safe_for_decision is True
    assert len(result.candles) == 1
    assert [e.status for e in result.events] == ["ACCEPTED", "IDEMPOTENT_DUPLICATE"]


def test_conflicting_duplicate_stops_candle_formation():
    s = SequenceAwareCandleIngestionV1()
    result = s.ingest([rec(1), rec(1, price="101")], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.events[-1].reason == "CONFLICTING_DUPLICATE_SEQUENCE"


def test_non_contiguous_sequence_is_accepted_as_monotonic_progress():
    s = SequenceAwareCandleIngestionV1()
    result = s.ingest([rec(1), rec(3)], as_of=ASOF)
    assert result.safe_for_decision is True
    assert result.events[-1].status == "ACCEPTED"



def test_reconnect_requires_explicit_reset_before_new_continuity():
    s = SequenceAwareCandleIngestionV1()
    first = s.ingest([rec(10)], as_of=ASOF)
    assert first.safe_for_decision is True
    s.sequence.reset_for_reconnect()
    second = s.ingest([rec(100)], as_of=ASOF)
    assert second.safe_for_decision is True
    assert second.events[0].status == "ACCEPTED"

def test_unknown_opaque_sequence_is_blocked_before_candle_formation():
    record = rec("opaque-007")
    record["sequence_semantics"] = "UNKNOWN_OPAQUE"
    result = SequenceAwareCandleIngestionV1().ingest([record], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.gaps == ()
    assert result.events[-1].reason == "UNKNOWN_SEQUENCE_SEMANTICS"


def test_missing_sequence_semantics_is_blocked_before_candle_formation():
    record = rec(7)
    record.pop("sequence_semantics")
    result = SequenceAwareCandleIngestionV1().ingest([record], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.gaps == ()
    assert result.events[-1].reason == "UNKNOWN_SEQUENCE_SEMANTICS"

def test_actual_adapter_output_is_blocked_before_candle_formation():
    frame = {
        "type": "trade",
        "symbol": "BTC_USDT",
        "price": "100",
        "amount": "0.1",
        "side": "buy",
        "sequence": "opaque-007",
        "timestamp": 1791356400000,
    }
    record = parse_trade_frame(frame, as_of=ASOF)
    assert record["sequence"] == "opaque-007"
    assert record["sequence_semantics"] == "UNKNOWN_OPAQUE"

    result = SequenceAwareCandleIngestionV1().ingest([record], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.gaps == ()
    assert result.events[-1].reason == "UNKNOWN_SEQUENCE_SEMANTICS"
