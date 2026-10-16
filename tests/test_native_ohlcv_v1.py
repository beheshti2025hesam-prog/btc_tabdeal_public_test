from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from forward.native_ohlcv_v1 import (
    BinanceSpotKlineSource,
    BinanceUsdMPerpetualKlineSource,
    normalize_native_klines,
)

BASE = 1_800_000_000_000
INTERVAL = 900_000


def row(open_time: int, *, close: str = "100.25", volume: str = "2.50",
        trade_count: int = 12, high: str = "102", low: str = "99") -> list[object]:
    return [
        open_time, "100.00", high, low, close, volume,
        open_time + INTERVAL - 1, "250.625", trade_count,
        "1.25", "125.00", "0",
    ]


def normalize(rows: list[object], *, as_of: int = BASE + INTERVAL * 5):
    raw = json.dumps(rows, separators=(",", ":")).encode()
    return normalize_native_klines(
        rows, venue="binance", product="spot", symbol="BTCUSDT",
        interval="15m", endpoint_kind="klines", as_of_ms=as_of,
        fetched_at_ms=as_of, response_sha256=hashlib.sha256(raw).hexdigest(),
    )


def test_preserves_native_decimal_precision_and_source_identity():
    batch = normalize([row(BASE)])
    candle = batch.candles[0]
    assert candle.open == Decimal("100.00")
    assert candle.close == Decimal("100.25")
    assert candle.volume == Decimal("2.50")
    assert candle.venue == "binance"
    assert candle.product == "spot"
    assert candle.symbol == "BTCUSDT"
    assert candle.closed is True
    assert batch.response_sha256


def test_excludes_current_unclosed_candle():
    batch = normalize([row(BASE), row(BASE + INTERVAL)], as_of=BASE + INTERVAL + 100)
    assert [c.open_time_ms for c in batch.candles] == [BASE]
    assert batch.open_candles_excluded == 1


def test_reports_missing_intervals_without_fabricating_candles():
    batch = normalize([row(BASE), row(BASE + 3 * INTERVAL)])
    assert len(batch.candles) == 2
    assert len(batch.gaps) == 1
    assert batch.gaps[0].expected_open_time_ms == BASE + INTERVAL
    assert batch.gaps[0].missing_intervals == 2


def test_identical_duplicate_is_idempotent_but_conflicting_duplicate_fails():
    batch = normalize([row(BASE), row(BASE)])
    assert len(batch.candles) == 1
    with pytest.raises(ValueError, match="conflicting duplicate"):
        normalize([row(BASE), row(BASE, close="100.26")])


@pytest.mark.parametrize("mutate", [
    lambda r: r[:11],
    lambda r: [True, *r[1:]],
    lambda r: [r[0], "NaN", *r[2:]],
    lambda r: [r[0], r[1], "98", r[3], r[4], *r[5:]],
    lambda r: [r[0], r[1], r[2], r[3], r[4], "-1", *r[6:]],
    lambda r: [r[0] + 1, *r[1:]],
    lambda r: [float(r[0]), *r[1:]],
    lambda r: [r[0], 100.0, *r[2:]],
])
def test_rejects_malformed_rows(mutate):
    with pytest.raises(ValueError):
        normalize([mutate(row(BASE))])


def test_rejects_out_of_order_and_future_rows():
    with pytest.raises(ValueError, match="not ordered"):
        normalize([row(BASE + INTERVAL), row(BASE)])
    with pytest.raises(ValueError, match="future"):
        normalize([row(BASE + INTERVAL * 10)], as_of=BASE)


def test_spot_chart_and_standard_endpoints_are_distinct_and_read_only():
    seen = []

    def transport(url: str, timeout: int) -> bytes:
        seen.append((url, timeout))
        return json.dumps([row(BASE)]).encode()

    spot = BinanceSpotKlineSource(chart_optimized=True, transport=transport,
                                  clock_ms=lambda: BASE + INTERVAL * 2)
    batch = spot.fetch(symbol="BTCUSDT", interval="15m", limit=5,
                       as_of_ms=BASE + INTERVAL * 2)
    assert "/api/v3/uiKlines?" in seen[0][0]
    assert "timeZone=0" in seen[0][0]
    assert seen[0][1] == 10
    assert batch.endpoint_kind == "uiKlines"
    assert len(batch.candles) == 1

    standard = BinanceSpotKlineSource(chart_optimized=False, transport=transport,
                                      clock_ms=lambda: BASE + INTERVAL * 2)
    standard.fetch(symbol="BTCUSDT", interval="15m", limit=5,
                   as_of_ms=BASE + INTERVAL * 2)
    assert "/api/v3/klines?" in seen[1][0]


def test_usdm_perpetual_uses_product_specific_public_kline_endpoint():
    seen = []

    def transport(url: str, timeout: int) -> bytes:
        seen.append(url)
        return json.dumps([row(BASE)]).encode()

    source = BinanceUsdMPerpetualKlineSource(
        transport=transport, clock_ms=lambda: BASE + INTERVAL * 2
    )
    batch = source.fetch(symbol="BTCUSDT", interval="15m", limit=5,
                         as_of_ms=BASE + INTERVAL * 2)
    assert seen[0].startswith("https://fapi.binance.com/fapi/v1/klines?")
    assert batch.product == "usdm_perpetual"
    with pytest.raises(ValueError, match="not documented"):
        BinanceUsdMPerpetualKlineSource(chart_optimized=True, transport=transport)


def test_invalid_configuration_and_bad_response_fail_closed():
    with pytest.raises(ValueError, match="unsupported fixed interval"):
        normalize_native_klines(
            [], venue="binance", product="spot", symbol="BTCUSDT",
            interval="1M", endpoint_kind="klines", as_of_ms=BASE,
            fetched_at_ms=BASE, response_sha256="0" * 64,
        )
    source = BinanceSpotKlineSource(transport=lambda _url, _timeout: b'{"error":"bad"}')
    with pytest.raises(ValueError, match="must be a list"):
        source.fetch(symbol="BTCUSDT", interval="15m", limit=5, as_of_ms=BASE)


def test_raw_response_hash_is_exact_sha256():
    body = json.dumps([row(BASE)]).encode()
    source = BinanceSpotKlineSource(
        transport=lambda _url, _timeout: body,
        clock_ms=lambda: BASE + INTERVAL * 2,
    )
    batch = source.fetch(symbol="BTCUSDT", interval="15m", limit=5,
                         as_of_ms=BASE + INTERVAL * 2)
    assert batch.response_sha256 == hashlib.sha256(body).hexdigest()
