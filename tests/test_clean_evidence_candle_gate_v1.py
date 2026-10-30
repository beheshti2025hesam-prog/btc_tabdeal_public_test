from tests.sequence_registry_fixtures import verified_tabdeal_test_registry
from datetime import datetime, timezone, timedelta

from forward.clean_evidence_candle_gate_v1 import CleanEvidenceCandleGateV1
from forward.sequence_semantics_v1 import TABDEAL_TRADE_SEQUENCE_KEY

CAPS = verified_tabdeal_test_registry().resolve_tabdeal_trade_sequence()


def rec(seq, ts, price="100"):
    return {
        "source": "tabdeal_ws_forward_v1",
        "symbol": "BTC_USDT",
        "price": price,
        "amount": "1",
        "side": "buy",
        "source_updated": ts.isoformat(),
        "sequence": seq,
        "sequence_contract_key": TABDEAL_TRADE_SEQUENCE_KEY,
    }


def test_empty_forward_input_blocks():
    r = CleanEvidenceCandleGateV1().evaluate([], as_of=datetime.now(timezone.utc))
    assert not r.safe and r.reason == "NO_FORWARD_RECORDS"


def test_future_input_fails_closed():
    now = datetime.now(timezone.utc)
    r = CleanEvidenceCandleGateV1().evaluate(
        [rec(1, now + timedelta(seconds=1))], as_of=now, capabilities=CAPS
    )
    assert not r.safe and r.reason == "INVALID_FORWARD_INPUT"


def test_conflicting_duplicate_blocks_candle_evidence():
    now = datetime.now(timezone.utc)
    timestamp = now - timedelta(minutes=20)
    data = [rec(10, timestamp, "100"), rec(10, timestamp, "101")]
    r = CleanEvidenceCandleGateV1().evaluate(data, as_of=now, capabilities=CAPS)
    assert not r.safe and r.reason == "CONFLICTING_DUPLICATE_IDENTITY"
    assert r.candles == ()


def test_numeric_jump_is_not_a_gap_without_contiguity_capability():
    now = datetime.now(timezone.utc)
    data = [
        rec(10, now - timedelta(minutes=20)),
        rec(12, now - timedelta(minutes=1)),
    ]
    r = CleanEvidenceCandleGateV1().evaluate(data, as_of=now, capabilities=CAPS)
    assert r.safe and r.reason == "CANDLE_SAFE"


def test_unknown_sequence_semantics_block_candle_evidence():
    now = datetime.now(timezone.utc)
    r = CleanEvidenceCandleGateV1().evaluate([rec(10, now-timedelta(minutes=20))], as_of=now)
    assert not r.safe and r.reason == "SEQUENCE_SEMANTICS_UNVERIFIED"
