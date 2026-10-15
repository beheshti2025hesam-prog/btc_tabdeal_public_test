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
    r = CleanEvidenceCandleGateV1().evaluate([], as_of=datetime.now(timezone.utc))
    assert not r.safe and r.reason == "NO_FORWARD_RECORDS"


def test_future_input_fails_closed_without_candles():
    now = datetime.now(timezone.utc)
    r = CleanEvidenceCandleGateV1().evaluate(
        [rec(1, now + timedelta(seconds=1))], as_of=now
    )
    assert not r.safe and r.reason == "INVALID_FORWARD_INPUT"
    assert r.candles == ()


def test_conflicting_same_timestamp_prices_block_all_candle_evidence():
    now = datetime.now(timezone.utc)
    timestamp = now - timedelta(minutes=20)
    data = [rec(10, timestamp, "100"), rec(10, timestamp, "101")]
    r = CleanEvidenceCandleGateV1().evaluate(data, as_of=now)
    assert not r.safe and r.reason == "INVALID_FORWARD_INPUT"
    assert r.candles == ()


def test_unverified_sequence_jump_does_not_itself_block_closed_candles():
    now = datetime.now(timezone.utc)
    data = [
        rec(10, now - timedelta(minutes=20)),
        rec(12, now - timedelta(minutes=1)),
    ]
    r = CleanEvidenceCandleGateV1().evaluate(data, as_of=now)
    assert r.safe and r.reason == "CANDLE_SAFE"
    # The older bucket is closed; the most recent bucket is still open.
    assert len(r.candles) == 1
    assert r.candles[0].close_time <= now
