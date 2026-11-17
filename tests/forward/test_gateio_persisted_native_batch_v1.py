from datetime import datetime, timezone

import pytest

import forward.native_ohlcv_gateio_v1 as gateio_adapter

from_persisted_global_rows = getattr(gateio_adapter, "from_persisted_global_rows", None)


def test_persisted_gateio_normalizer_is_exposed():
    assert callable(from_persisted_global_rows)


def _requires_normalizer(test):
    return pytest.mark.skipif(from_persisted_global_rows is None, reason="normalizer not implemented yet")(test)

BASE = 1_800_000_000


def make_rows(timeframe="15m", count=3, *, skip_index=None):
    seconds = {"15m": 900, "1h": 3600, "4h": 14400}[timeframe]
    rows = []
    for index in range(count):
        if index == skip_index:
            continue
        opened = BASE + index * seconds
        rows.append({
            "schema": "hes_global_candle_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": timeframe,
            "open_time": opened,
            "close_time": opened + seconds,
            "open": "100.0",
            "high": "102.0",
            "low": "99.0",
            "close": "101.0",
            "volume": "1.5",
            "quote_volume": "151.5",
            "closed": True,
            "observed_at": datetime.fromtimestamp(BASE + count * seconds + 2, timezone.utc).isoformat(),
        })
    return rows


@_requires_normalizer
def test_persisted_gateio_rows_normalize_to_native_batch_without_fabricated_flow():
    rows = make_rows()
    now_ms = int(datetime.fromisoformat(rows[-1]["observed_at"]).timestamp() * 1000)

    batch = from_persisted_global_rows(rows, timeframe="15m", now_ms=now_ms)

    assert (batch.venue, batch.product, batch.symbol, batch.interval) == ("gateio", "spot", "BTCUSDT", "15m")
    assert batch.endpoint_kind == "global_market_data_reader_v1"
    assert batch.candles[-1].close_time_ms == rows[-1]["close_time"] * 1000 - 1
    assert all(c.trade_count is None and c.taker_buy_volume is None and c.taker_buy_quote_volume is None for c in batch.candles)
    assert batch.gaps == ()
    assert len(batch.response_sha256) == 64


@_requires_normalizer
def test_persisted_gateio_rows_preserve_missing_interval_as_explicit_gap():
    rows = make_rows(count=4, skip_index=1)
    now_ms = int(datetime.fromisoformat(rows[-1]["observed_at"]).timestamp() * 1000)

    batch = from_persisted_global_rows(rows, timeframe="15m", now_ms=now_ms)

    assert len(batch.gaps) == 1
    assert batch.gaps[0].missing_intervals == 1


@pytest.mark.parametrize("field,value", [
    ("source", "binance_public_spot"),
    ("symbol", "ETH_USDT"),
    ("timeframe", "1h"),
    ("schema", "other_schema"),
    ("closed", False),
])
@_requires_normalizer
def test_persisted_gateio_rows_reject_wrong_identity_or_open_candles(field, value):
    rows = make_rows()
    rows[-1][field] = value
    now_ms = int(datetime.fromisoformat(rows[-1]["observed_at"]).timestamp() * 1000)

    with pytest.raises(ValueError):
        from_persisted_global_rows(rows, timeframe="15m", now_ms=now_ms)


@_requires_normalizer
def test_persisted_gateio_rows_reject_noncanonical_trade_flow_fields():
    rows = make_rows()
    rows[-1]["trade_count"] = 42
    now_ms = int(datetime.fromisoformat(rows[-1]["observed_at"]).timestamp() * 1000)

    with pytest.raises(ValueError, match="trade-flow fields must remain unavailable"):
        from_persisted_global_rows(rows, timeframe="15m", now_ms=now_ms)


@pytest.mark.parametrize("field,value", [
    ("close_time", BASE + 899),
    ("open", "NaN"),
    ("volume", "-1"),
    ("observed_at", "2026-11-08T04:00:00"),
])
@_requires_normalizer
def test_persisted_gateio_rows_reject_malformed_values_and_timestamps(field, value):
    rows = make_rows()
    rows[-1][field] = value
    now_ms = int(datetime.fromtimestamp(BASE + 10_000, timezone.utc).timestamp() * 1000)

    with pytest.raises(ValueError):
        from_persisted_global_rows(rows, timeframe="15m", now_ms=now_ms)


@_requires_normalizer
def test_persisted_gateio_batch_hash_binds_exact_row_values():
    rows = make_rows()
    now_ms = int(datetime.fromisoformat(rows[-1]["observed_at"]).timestamp() * 1000)
    first = from_persisted_global_rows(rows, timeframe="15m", now_ms=now_ms)
    changed = [dict(row) for row in rows]
    changed[-1]["quote_volume"] = "151.6"
    second = from_persisted_global_rows(changed, timeframe="15m", now_ms=now_ms)

    assert first.response_sha256 != second.response_sha256


@_requires_normalizer
def test_persisted_gateio_batch_rejects_future_fetch_timestamp():
    rows = make_rows()
    fetched_at = int(datetime.fromisoformat(rows[-1]["observed_at"]).timestamp() * 1000)

    with pytest.raises(ValueError, match="observation time is ahead"):
        from_persisted_global_rows(rows, timeframe="15m", now_ms=fetched_at - 120_000)


@_requires_normalizer
def test_persisted_gateio_batch_rejects_candle_that_has_not_closed_at_now():
    rows = make_rows()
    close_boundary_ms = rows[-1]["close_time"] * 1000
    now_ms = close_boundary_ms - 1

    with pytest.raises(ValueError, match="candle close is in the future"):
        from_persisted_global_rows(rows, timeframe="15m", now_ms=now_ms)


@_requires_normalizer
def test_persisted_batch_fetch_time_is_the_reader_invocation_time_not_last_candle_observation():
    rows = make_rows()
    observed_ms = int(datetime.fromisoformat(rows[-1]["observed_at"]).timestamp() * 1000)
    now_ms = observed_ms + 60_000

    batch = from_persisted_global_rows(rows, timeframe="15m", now_ms=now_ms)

    assert batch.fetched_at_ms == now_ms


@_requires_normalizer
def test_persisted_batch_rejects_feed_older_than_two_intervals():
    rows = make_rows()
    close_boundary_ms = rows[-1]["close_time"] * 1000
    now_ms = close_boundary_ms + 2 * 900_000 + 1

    with pytest.raises(ValueError, match="persisted Gate.io candle feed is stale"):
        from_persisted_global_rows(rows, timeframe="15m", now_ms=now_ms)
