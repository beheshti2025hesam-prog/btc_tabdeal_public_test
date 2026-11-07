from decimal import Decimal

import pytest

from forward.native_ohlcv_v1 import INTERVAL_MS, NativeCandle, NativeOHLCVBatch
from forward.strategy_evidence_provider_v1 import StrategyEvidenceProviderV1


def _gateio_batch(interval: str, *, endpoint_kind: str, fabricated_flow: bool = False):
    interval_ms = INTERVAL_MS[interval]
    candle = NativeCandle(
        venue="gateio",
        product="spot",
        symbol="BTCUSDT",
        interval=interval,
        open_time_ms=0,
        close_time_ms=interval_ms - 1,
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=Decimal("1"),
        quote_volume=Decimal("101"),
        trade_count=1 if fabricated_flow else None,
        taker_buy_volume=Decimal("0.5") if fabricated_flow else None,
        taker_buy_quote_volume=Decimal("50.5") if fabricated_flow else None,
        closed=True,
    )
    return NativeOHLCVBatch(
        venue="gateio",
        product="spot",
        symbol="BTCUSDT",
        interval=interval,
        endpoint_kind=endpoint_kind,
        fetched_at_ms=interval_ms + 1,
        response_sha256="a" * 64,
        candles=(candle,),
        gaps=(),
        open_candles_excluded=0,
    )


def test_gateio_provider_rejects_generic_or_unqualified_endpoint_alias():
    with pytest.raises(ValueError, match="unsupported Gate.io evidence endpoint contract"):
        StrategyEvidenceProviderV1().evaluate(
            candles_15m=_gateio_batch("15m", endpoint_kind="klines"),
            candles_4h=_gateio_batch("4h", endpoint_kind="klines"),
            now_ms=INTERVAL_MS["4h"] + 1,
        )


def test_gateio_provider_rejects_fabricated_trade_count_and_taker_flow():
    with pytest.raises(ValueError, match="unavailable trade-flow fields must remain unknown"):
        StrategyEvidenceProviderV1().evaluate(
            candles_15m=_gateio_batch("15m", endpoint_kind="spot_candlesticks", fabricated_flow=True),
            candles_4h=_gateio_batch("4h", endpoint_kind="spot_candlesticks"),
            now_ms=INTERVAL_MS["4h"] + 1,
        )
