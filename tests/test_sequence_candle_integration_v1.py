from datetime import datetime, timezone

from forward.sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1


ASOF = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)


def rec(seq, ts="2026-10-07T06:30:00+00:00", price="100", **extra):
    return {
        "source": "tabdeal_ws_forward_v1",
        "symbol": "BTC_USDT",
        "price": price,
        "amount": "1",
        "side": "buy",
        "source_updated": ts,
        "sequence": seq,
        **extra,
    }


def test_clean_timestamps_reach_closed_candle_without_sequence_claims():
    s = SequenceAwareCandleIngestionV1()
    result = s.ingest([
        rec(1, "2026-10-07T06:30:00+00:00", "100"),
        rec(2, "2026-10-07T06:35:00+00:00", "105"),
    ], as_of=ASOF)
    assert result.safe_for_decision is True
    assert len(result.candles) == 1
    assert [e.status for e in result.events] == ["ACCEPTED", "ACCEPTED"]


def test_exact_duplicate_without_raw_digest_is_not_silently_deduplicated():
    s = SequenceAwareCandleIngestionV1()
    r = rec(1)
    result = s.ingest([r, dict(r)], as_of=ASOF)
    assert result.safe_for_decision is True
    assert len(result.candles) == 1
    assert result.candles[0].trade_count == 2
    assert [e.status for e in result.events] == ["ACCEPTED", "ACCEPTED"]


def test_same_timestamp_conflicting_prices_block_candle_formation():
    s = SequenceAwareCandleIngestionV1()
    result = s.ingest([rec(1), rec(1, price="101")], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.events[-1].reason == "AMBIGUOUS_TIMESTAMP_ORDER"


def test_non_contiguous_sequence_is_accepted_without_gap_inference():
    s = SequenceAwareCandleIngestionV1()
    result = s.ingest([rec(1), rec(3, ts="2026-10-07T06:35:00+00:00")], as_of=ASOF)
    assert result.safe_for_decision is True
    assert result.events[-1].status == "ACCEPTED"



def test_signed_ordering_capability_is_explicitly_required_for_timestamp_ties():
    records = [
        rec(2, "2026-10-07T06:30:00+00:00", "105"),
        rec(1, "2026-10-07T06:30:00+00:00", "100"),
    ]
    blocked = SequenceAwareCandleIngestionV1().ingest(records, as_of=ASOF)
    assert blocked.safe_for_decision is False
    assert blocked.events[-1].reason == "AMBIGUOUS_TIMESTAMP_ORDER"

    authorized = SequenceAwareCandleIngestionV1(
        sequence_ordering_authorized=True
    ).ingest(records, as_of=ASOF)
    assert authorized.safe_for_decision is True
    assert len(authorized.candles) == 1
    assert authorized.candles[0].open == 100
    assert authorized.candles[0].close == 105


def test_ordering_capability_does_not_imply_duplicate_identity():
    records = [
        rec(1, "2026-10-07T06:30:00+00:00", "100"),
        rec(1, "2026-10-07T06:30:00+00:00", "101"),
    ]
    result = SequenceAwareCandleIngestionV1(
        sequence_ordering_authorized=True
    ).ingest(records, as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.events[-1].reason == "AMBIGUOUS_TIMESTAMP_ORDER"

def test_reconnect_does_not_compare_sequence_across_sessions():
    s = SequenceAwareCandleIngestionV1()
    first = s.ingest([rec(10)], as_of=ASOF)
    assert first.safe_for_decision is True
    s.sequence.reset_for_reconnect()
    second = s.ingest([rec(100, ts="2026-10-07T06:35:00+00:00")], as_of=ASOF)
    assert second.safe_for_decision is True
    assert second.events[0].status == "ACCEPTED"
