from datetime import datetime, timezone

from forward.sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1


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
        # Explicit test fixture only; live adapter output is UNKNOWN_OPAQUE.
        "sequence_semantics": "VERIFIED_MONOTONIC",
    }


def test_clean_verified_sequence_reaches_closed_candle():
    s = SequenceAwareCandleIngestionV1()
    result = s.ingest(
        [rec(1, "2026-10-07T06:30:00+00:00", "100"), rec(2, "2026-10-07T06:35:00+00:00", "105")],
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


def test_non_contiguous_verified_sequence_is_accepted_as_monotonic_progress():
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


def test_unknown_sequence_semantics_blocks_before_candle_formation():
    s = SequenceAwareCandleIngestionV1()
    unknown = rec("opaque-007")
    unknown["sequence_semantics"] = "UNKNOWN_OPAQUE"
    result = s.ingest([unknown], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.blocked_reason == "SEQUENCE_SEMANTICS_UNVERIFIED"
    assert result.candles == ()
    assert result.gaps == ()
    assert result.events == ()


def test_missing_sequence_semantics_blocks_before_candle_formation():
    s = SequenceAwareCandleIngestionV1()
    unknown = rec(7)
    del unknown["sequence_semantics"]
    result = s.ingest([unknown], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.blocked_reason == "SEQUENCE_SEMANTICS_UNVERIFIED"
    assert result.candles == ()


def test_decreasing_verified_sequence_blocks_before_candle_formation():
    s = SequenceAwareCandleIngestionV1()
    result = s.ingest([rec(7), rec(6)], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.events[-1].reason == "OUT_OF_ORDER_SEQUENCE"
