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
    }


def verified_ingestion():
    return SequenceAwareCandleIngestionV1(
        sequence_contract_verified=True,
        sequence_contract_evidence_ref="test-fixture:reviewed-exact-feed-contract",
    )


def test_verified_contract_allows_unique_records_to_reach_closed_candle():
    s = verified_ingestion()
    result = s.ingest(
        [
            rec(1, "2026-10-07T06:30:00+00:00", "100"),
            rec(3, "2026-10-07T06:35:00+00:00", "105"),
        ],
        as_of=ASOF,
    )
    assert result.safe_for_decision is True
    assert len(result.candles) == 1
    assert [e.status for e in result.events] == ["ACCEPTED", "ACCEPTED"]


def test_unverified_contract_never_produces_decision_grade_candles():
    result = SequenceAwareCandleIngestionV1().ingest([rec(1)], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()


def test_identical_repeated_sequence_blocks_candle_formation():
    result = verified_ingestion().ingest([rec(1), dict(rec(1))], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.events[-1].reason == "REPEATED_SEQUENCE_IDENTITY_UNPROVEN"


def test_conflicting_reused_sequence_stops_candle_formation():
    result = verified_ingestion().ingest([rec(1), rec(1, price="101")], as_of=ASOF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.events[-1].reason == "SOURCE_SEQUENCE_REUSE_OBSERVED_ORDERING_SEMANTICS_UNKNOWN"


def test_decreasing_sequence_is_not_assumed_to_be_out_of_order():
    result = verified_ingestion().ingest([rec(12), rec(11)], as_of=ASOF)
    assert result.safe_for_decision is True
    assert [e.status for e in result.events] == ["ACCEPTED", "ACCEPTED"]


def test_reconnect_requires_explicit_reset_before_new_sequence_epoch():
    s = verified_ingestion()
    first = s.ingest([rec(10)], as_of=ASOF)
    assert first.safe_for_decision is True
    s.sequence.reset_for_reconnect()
    second = s.ingest([rec(10)], as_of=ASOF)
    assert second.safe_for_decision is True
    assert second.events[0].status == "ACCEPTED"
