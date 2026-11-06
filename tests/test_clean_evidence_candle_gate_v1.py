from datetime import datetime, timezone, timedelta

from forward.clean_evidence_candle_gate_v1 import CleanEvidenceCandleGateV1


def rec(seq, ts, price="100"):
    return {
        "source": "tabdeal_ws_forward_v1",
        "symbol": "BTC_USDT",
        "price": price,
        "amount": "1",
        "side": "buy",
        "source_updated": ts.isoformat(),
        "sequence": seq,
    }


def test_empty_forward_input_blocks():
    result = CleanEvidenceCandleGateV1().evaluate([], as_of=datetime.now(timezone.utc))
    assert not result.safe and result.reason == "NO_FORWARD_RECORDS"


def test_future_input_does_not_override_unknown_sequence_capability_block():
    now = datetime.now(timezone.utc)
    result = CleanEvidenceCandleGateV1().evaluate(
        [rec(1, now + timedelta(seconds=1))], as_of=now
    )
    assert not result.safe and result.reason == "SEQUENCE_CAPABILITIES_UNVERIFIED"


def test_conflicting_duplicate_is_not_asserted_without_unique_identity_capability():
    now = datetime.now(timezone.utc)
    timestamp = now - timedelta(minutes=20)
    data = [rec(10, timestamp, "100"), rec(10, timestamp, "101")]
    result = CleanEvidenceCandleGateV1().evaluate(data, as_of=now)
    assert not result.safe and result.reason == "SEQUENCE_CAPABILITIES_UNVERIFIED"
    assert result.candles == ()


def test_numeric_jump_is_not_interpreted_as_a_missing_market_event():
    now = datetime.now(timezone.utc)
    data = [
        rec(10, now - timedelta(minutes=20)),
        rec(12, now - timedelta(minutes=1)),
    ]
    result = CleanEvidenceCandleGateV1().evaluate(data, as_of=now)
    assert not result.safe and result.reason == "SEQUENCE_CAPABILITIES_UNVERIFIED"
    assert result.candles == ()
