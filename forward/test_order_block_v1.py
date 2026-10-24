from decimal import Decimal

import pytest

from forward.native_ohlcv_v1 import NativeCandle
from forward.order_block_v1 import detect_order_block_v1


def candle(i, open_, high, low, close, volume=10):
    return NativeCandle(
        venue="binance", product="spot", symbol="BTCUSDT", interval="15m",
        open_time_ms=900_000 * i, close_time_ms=900_000 * (i + 1) - 1,
        open=Decimal(str(open_)), high=Decimal(str(high)), low=Decimal(str(low)),
        close=Decimal(str(close)), volume=Decimal(str(volume)),
        quote_volume=Decimal(str(volume * close)), trade_count=10,
        taker_buy_volume=Decimal(str(volume / 2)),
        taker_buy_quote_volume=Decimal(str(volume * close / 2)), closed=True,
    )


def bullish_break_candles():
    return (
        candle(0, 96, 100, 95, 99),
        candle(1, 99, 102, 96, 101),
        candle(2, 98, 99, 90, 94),   # sweep under prior swing low, closes back above
        candle(3, 98, 99, 93, 95),   # last bearish candle: bullish order block
        candle(4, 101, 105, 100, 104),  # bullish FVG vs candle 2
        candle(5, 104, 111, 102, 110, volume=30),  # confirmed break
    )


def test_bullish_order_block_score_is_context_only_and_provenance_bound():
    result = detect_order_block_v1(
        bullish_break_candles(), direction="BULLISH", break_confirmed=True,
        htf_direction="BULLISH", last_swing_high=Decimal("105"),
        last_swing_low=Decimal("92"), ema50=96.0, source_response_sha256="a" * 64,
    )
    assert result is not None
    assert result.direction == "BULLISH"
    assert result.break_type == "BOS"
    assert result.zone_low == Decimal("93")
    assert result.zone_high == Decimal("98")
    assert result.bos_choch_confirmed
    assert result.liquidity_sweep
    assert result.fair_value_gap
    assert result.fresh and not result.mitigated
    assert result.htf_aligned and result.volume_expansion and result.ema_or_swing_confluence
    assert result.score == 7 and result.max_score == 7
    assert result.status == "CONTEXT_ONLY"
    assert result.score_threshold_authorized is False
    assert result.source_response_sha256 == "a" * 64


def test_order_block_is_not_emitted_without_confirmed_break():
    assert detect_order_block_v1(
        bullish_break_candles(), direction="BULLISH", break_confirmed=False,
        htf_direction="BULLISH", last_swing_high=None, last_swing_low=None,
        ema50=None, source_response_sha256="a" * 64,
    ) is None


def test_wrong_direction_and_invalid_hash_fail_closed():
    assert detect_order_block_v1(
        bullish_break_candles(), direction="UNKNOWN", break_confirmed=True,
        htf_direction="BULLISH", last_swing_high=None, last_swing_low=None,
        ema50=None, source_response_sha256="a" * 64,
    ) is None
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        detect_order_block_v1(
            bullish_break_candles(), direction="BULLISH", break_confirmed=True,
            htf_direction="BULLISH", last_swing_high=None, last_swing_low=None,
            ema50=None, source_response_sha256="bad",
        )


def test_mitigated_order_block_loses_freshness_point():
    rows = list(bullish_break_candles())
    rows[4] = candle(4, 97, 100, 94, 99)  # trades back into the block
    result = detect_order_block_v1(
        tuple(rows), direction="BULLISH", break_confirmed=True,
        htf_direction="BEARISH", last_swing_high=None,
        last_swing_low=Decimal("92"), ema50=96.0, source_response_sha256="b" * 64,
    )
    assert result is not None
    assert result.mitigated and not result.fresh
    assert result.score < result.max_score
