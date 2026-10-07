from datetime import datetime, timezone

import pytest

from forward.forward_tabdeal_ingestion_v1 import ingest_closed_candles, to_trade_observation


AS_OF = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)


def rec(ts="2026-10-07T01:01:00+00:00", seq=1, symbol="BTC_USDT"):
    return {
        "observed_at": "2026-10-07T01:01:01+00:00",
        "source_updated": ts,
        "symbol": symbol,
        "price": "100.25",
        "amount": "2.0",
        "side": "Buy",
        "sequence": seq,
        "source": "tabdeal_ws_forward_v1",
    }


def test_valid_tabdeal_record_becomes_trade_observation():
    trade = to_trade_observation(rec(), as_of=AS_OF)
    assert trade.symbol == "BTC_USDT"
    assert str(trade.price) == "100.25"
    assert trade.sequence == 1


def test_future_record_is_rejected():
    with pytest.raises(ValueError, match="future"):
        to_trade_observation(rec("2026-10-07T02:00:01+00:00"), as_of=AS_OF)


def test_wrong_source_and_symbol_are_rejected():
    bad = rec()
    bad["source"] = "historical"
    with pytest.raises(ValueError, match="source"):
        to_trade_observation(bad, as_of=AS_OF)

    with pytest.raises(ValueError, match="symbol"):
        to_trade_observation(rec(symbol="ETH_USDT"), as_of=AS_OF)


def test_ingestion_emits_only_closed_candles():
    records = [rec("2026-10-07T01:01:00+00:00", 1),
               rec("2026-10-07T01:14:59+00:00", 2)]
    candles, gaps = ingest_closed_candles(records, as_of=AS_OF)
    assert len(candles) == 1
    assert candles[0].close_time == datetime(2026, 10, 7, 1, 15, tzinfo=timezone.utc)
    assert gaps == ()
