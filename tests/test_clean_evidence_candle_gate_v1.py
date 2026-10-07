from datetime import datetime, timezone, timedelta
import pytest

from forward.clean_evidence_candle_gate_v1 import CleanEvidenceCandleGateV1


def rec(seq, ts, price="100"):
    return {
        "symbol": "BTC_USDT", "price": price, "amount": "1",
        "side": "buy", "source_updated": ts.isoformat(), "sequence": seq,
    }


def test_empty_forward_input_blocks():
    r = CleanEvidenceCandleGateV1().evaluate([], as_of=datetime.now(timezone.utc))
    assert not r.safe and r.reason == "NO_FORWARD_RECORDS"


def test_future_input_blocks():
    now = datetime.now(timezone.utc)
    with pytest.raises(Exception):
        CleanEvidenceCandleGateV1().evaluate([rec(1, now + timedelta(seconds=1))], as_of=now)


def test_sequence_gap_blocks_candle_evidence():
    now = datetime.now(timezone.utc)
    data = [rec(10, now - timedelta(minutes=16)), rec(12, now - timedelta(minutes=1))]
    r = CleanEvidenceCandleGateV1().evaluate(data, as_of=now)
    assert not r.safe


def test_valid_forward_input_reaches_candle_layer():
    now = datetime.now(timezone.utc)
    data = [rec(10, now - timedelta(minutes=20)), rec(11, now - timedelta(minutes=1))]
    r = CleanEvidenceCandleGateV1().evaluate(data, as_of=now)
    assert r.reason in {"CANDLE_SAFE", "SEQUENCE_UNSAFE"}
