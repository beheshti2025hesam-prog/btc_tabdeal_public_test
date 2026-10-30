from __future__ import annotations

import hashlib
import json

import pytest

from forward.native_ohlcv_feature_adapter_v1 import to_feature_batch
from forward.native_ohlcv_v1 import normalize_native_klines

BASE = 1_760_000_400_000
INTERVAL = 900_000


def row(open_time: int, *, close: str = "101.25") -> list[object]:
    return [
        open_time, "100.00", "102.00", "99.00", close, "2.500",
        open_time + INTERVAL - 1, "250.625", 12, "1.250", "125.3125", "0",
    ]


def batch(rows, *, fetched_at=BASE + INTERVAL * 4):
    raw = json.dumps(rows, separators=(",", ":")).encode()
    return normalize_native_klines(
        rows, venue="binance", product="spot", symbol="BTCUSDT",
        interval="15m", endpoint_kind="uiKlines",
        as_of_ms=fetched_at, fetched_at_ms=fetched_at,
        response_sha256=hashlib.sha256(raw).hexdigest(),
    )


def test_converts_native_closed_candles_to_core_feature_contract_without_losing_provenance():
    source = batch([row(BASE), row(BASE + INTERVAL)])
    result = to_feature_batch(source, now_ms=source.fetched_at_ms + 1)
    assert result.venue == "binance"
    assert result.product == "spot"
    assert result.symbol == "BTCUSDT"
    assert result.timeframe_seconds == 900
    assert result.source_response_sha256 == source.response_sha256
    assert len(result.candles) == 2
    candle = result.candles[0]
    assert candle.start.timestamp() * 1000 == BASE
    assert candle.end.timestamp() * 1000 == BASE + INTERVAL
    assert candle.open == 100.0
    assert candle.close == 101.25
    assert candle.volume == 2.5


def test_historical_cutoff_excludes_candles_not_closed_by_as_of():
    source = batch([row(BASE), row(BASE + INTERVAL), row(BASE + 2 * INTERVAL)])
    cutoff = BASE + INTERVAL
    result = to_feature_batch(source, as_of_ms=cutoff, now_ms=source.fetched_at_ms + 1)
    assert [c.start.timestamp() * 1000 for c in result.candles] == [BASE]
    assert result.as_of_candles_excluded == 2


def test_future_as_of_and_future_fetch_fail_closed():
    source = batch([row(BASE)])
    with pytest.raises(ValueError, match="must not be after"):
        to_feature_batch(source, as_of_ms=source.fetched_at_ms + 1, now_ms=source.fetched_at_ms + 1)
    with pytest.raises(ValueError, match="future"):
        to_feature_batch(source, now_ms=source.fetched_at_ms - 120_000)


def test_preserves_product_identity_and_rejects_bad_source_digest():
    spot = batch([row(BASE)])
    assert to_feature_batch(spot, now_ms=spot.fetched_at_ms + 1).product == "spot"
    invalid = spot.__class__(
        venue=spot.venue, product="usdm_perpetual", symbol=spot.symbol,
        interval=spot.interval, endpoint_kind=spot.endpoint_kind,
        fetched_at_ms=spot.fetched_at_ms, response_sha256="bad",
        candles=spot.candles, gaps=spot.gaps,
        open_candles_excluded=spot.open_candles_excluded,
    )
    with pytest.raises(ValueError, match="SHA-256"):
        to_feature_batch(invalid, now_ms=spot.fetched_at_ms + 1)
