from datetime import datetime, timezone

from forward.clean_evidence_sequence_gate_v1 import CleanEvidenceSequenceGateV1
from forward.sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1


ASOF = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)


def trade(sequence, **extra):
    return {
        "source": "tabdeal_ws_forward_v1",
        "symbol": "BTC_USDT",
        "price": "100",
        "amount": "1",
        "side": "buy",
        "source_updated": "2026-10-07T06:30:00+00:00",
        "sequence": sequence,
        **extra,
    }


def test_non_market_field_conflict_is_not_treated_as_identical_duplicate():
    first = trade(10, transport_tag="A")
    changed = trade(10, transport_tag="B")
    result = CleanEvidenceSequenceGateV1().evaluate([first, changed])
    assert not result.safe
    assert result.reason == "CONFLICTING_DUPLICATE_SEQUENCE"


def test_conflict_followed_by_valid_record_stops_batch_before_candle_creation():
    first = trade(10)
    conflicting = {**first, "price": "101"}
    later_valid = trade(11, source_updated="2026-10-07T06:35:00+00:00")
    result = SequenceAwareCandleIngestionV1().ingest(
        [first, conflicting, later_valid], as_of=ASOF
    )
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert [event.status for event in result.events] == ["ACCEPTED", "REJECT_STREAM"]
    assert len(result.events) == 2
