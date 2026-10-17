from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from core.strategy.baseline import BaselineDecision, BaselineStrategy, BaselineStrategyInput
from forward.native_ohlcv_feature_pipeline_v1 import NativeOHLCVFeaturePipelineV1
from forward.native_ohlcv_v1 import normalize_native_klines

BASE = 1_760_000_400_000
INTERVAL = 900_000


def row(open_time: int, *, close: str = "101.25", volume: str = "2.500",
        quote: str = "250.625", taker_buy: str = "1.250",
        taker_buy_quote: str = "125.3125") -> list[object]:
    high = str(max(102.0, float(close)))
    return [
        open_time, "100.00", high, "99.00", close, volume,
        open_time + INTERVAL - 1, quote, 12, taker_buy, taker_buy_quote, "0",
    ]


def batch(rows, *, fetched_at=BASE + INTERVAL * 10, product="spot"):
    raw = json.dumps(rows, separators=(",", ":")).encode()
    return normalize_native_klines(
        rows, venue="binance", product=product, symbol="BTCUSDT",
        interval="15m", endpoint_kind="uiKlines",
        as_of_ms=fetched_at, fetched_at_ms=fetched_at,
        response_sha256=hashlib.sha256(raw).hexdigest(),
    )


def test_builds_feature_snapshot_from_native_ohlcv_without_trade_sequence():
    rows = [row(BASE + i * INTERVAL, close=str(100 + i)) for i in range(4)]
    source = batch(rows)
    result = NativeOHLCVFeaturePipelineV1(ema_period=3, vwap_period=3, momentum_period=2).build(
        source, now_ms=source.fetched_at_ms + 1
    )
    assert result.venue == "binance" and result.product == "spot"
    assert result.source_response_sha256 == source.response_sha256
    assert result.candle_count == 4
    assert result.snapshot.close == 103.0
    assert result.snapshot.ema is not None
    assert result.snapshot.vwap == 100.25
    assert result.snapshot.buy_ratio == 0.5
    assert result.snapshot.buy_sell_delta == 0.0
    assert result.snapshot.regime == "uptrend"
    assert result.quality.passed
    assert result.decision_ready
    assert result.reason == "NATIVE_OHLCV_FEATURES_READY"


def test_observed_gaps_block_decision_readiness_without_fabricating_candles():
    source = batch([row(BASE), row(BASE + 3 * INTERVAL)])
    result = NativeOHLCVFeaturePipelineV1(ema_period=2, vwap_period=2).build(
        source, now_ms=source.fetched_at_ms + 1
    )
    assert result.candle_count == 2
    assert len(result.gaps) == 1
    assert not result.decision_ready
    assert result.snapshot is None
    assert result.reason == "OBSERVED_CANDLE_GAPS"


def test_insufficient_closed_history_fails_closed():
    source = batch([row(BASE)])
    result = NativeOHLCVFeaturePipelineV1(ema_period=3, vwap_period=3).build(
        source, now_ms=source.fetched_at_ms + 1
    )
    assert not result.decision_ready
    assert result.reason == "INSUFFICIENT_CLOSED_CANDLES"
    assert not result.quality.passed
    assert result.snapshot is None


def test_spot_and_futures_identity_remain_separate():
    spot = batch([row(BASE), row(BASE + INTERVAL), row(BASE + 2 * INTERVAL)])
    futures = batch([row(BASE), row(BASE + INTERVAL), row(BASE + 2 * INTERVAL)], product="usdm_perpetual")
    pipeline = NativeOHLCVFeaturePipelineV1(ema_period=2, vwap_period=2)
    spot_result = pipeline.build(spot, now_ms=spot.fetched_at_ms + 1)
    futures_result = pipeline.build(futures, now_ms=futures.fetched_at_ms + 1)
    assert spot_result.product == "spot"
    assert futures_result.product == "usdm_perpetual"
    assert spot_result.source_response_sha256 != ""
    assert futures_result.source_response_sha256 != ""


def test_ready_native_snapshot_can_feed_signal_only_baseline_strategy():
    rows = [
        row(BASE + i * INTERVAL, close=str(100 + i), taker_buy="1.600",
            taker_buy_quote="160.400")
        for i in range(4)
    ]
    source = batch(rows)
    result = NativeOHLCVFeaturePipelineV1(
        ema_period=3, vwap_period=3, momentum_period=2
    ).build(source, now_ms=source.fetched_at_ms + 1)
    assert result.decision_ready and result.snapshot is not None
    decision = BaselineStrategy().evaluate(BaselineStrategyInput(features=result.snapshot))
    assert decision == BaselineDecision.LONG
