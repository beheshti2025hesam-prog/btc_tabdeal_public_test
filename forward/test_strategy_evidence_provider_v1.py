from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import math

import pytest

from forward.native_ohlcv_v1 import NativeCandle, NativeOHLCVBatch, INTERVAL_MS, CandleGap
from forward.strategy_evidence_provider_v1 import StrategyEvidenceProviderV1, mfi14, adx14, _evidence_window_sha256


def make_batch(interval, now_ms, *, symbol="BTCUSDT", venue="binance", product="spot", count=240, digest="a"):
    interval_ms = INTERVAL_MS[interval]
    current_open = (now_ms // interval_ms) * interval_ms
    first_open = current_open - count * interval_ms
    candles = []
    previous_close = 20000.0
    for i in range(count):
        open_ms = first_open + i * interval_ms
        # Upward drift plus deterministic oscillation gives the structure engine
        # confirmed highs/lows while retaining a clear long-horizon trend.
        close = 20000.0 + i * (10.0 if interval == "4h" else 1.0) + 25.0 * math.sin(i * 0.7)
        open_price = previous_close
        high = max(open_price, close) + 2.0
        low = min(open_price, close) - 2.0
        volume = 10.0 + (i % 7)
        candles.append(NativeCandle(
            venue=venue, product=product, symbol=symbol, interval=interval,
            open_time_ms=open_ms, close_time_ms=open_ms + interval_ms - 1,
            open=Decimal(str(open_price)), high=Decimal(str(high)),
            low=Decimal(str(low)), close=Decimal(str(close)),
            volume=Decimal(str(volume)),
            quote_volume=Decimal(str(volume * close)),
            trade_count=100,
            taker_buy_volume=Decimal(str(volume * 0.55)),
            taker_buy_quote_volume=Decimal(str(volume * close * 0.55)),
            closed=True,
        ))
        previous_close = close
    return NativeOHLCVBatch(
        venue=venue, product=product, symbol=symbol, interval=interval,
        endpoint_kind="klines", fetched_at_ms=now_ms,
        response_sha256=digest * 64, candles=tuple(candles), gaps=(),
        open_candles_excluded=1,
    )


def test_mfi14_and_adx14_return_finite_values_from_closed_ohlcv():
    now = 1_800_000_000_000
    batch = make_batch("15m", now)
    mfi = mfi14(batch.candles)
    adx = adx14(batch.candles)
    assert mfi is not None and 0 <= mfi <= 100
    assert adx is not None
    assert all(math.isfinite(x) and x >= 0 for x in adx)
    assert adx[0] <= 100 and adx[1] <= 100 and adx[2] <= 100


def test_provider_emits_six_provenance_bound_checks_and_separate_risk_context():
    now = 1_800_000_000_000
    fifteen = make_batch("15m", now, digest="a")
    four_hour = make_batch("4h", now, digest="b")
    result = StrategyEvidenceProviderV1().evaluate(
        candles_15m=fifteen, candles_4h=four_hour, now_ms=now
    )
    assert len(result.strategy_checks) == 6
    assert {c.name for c in result.strategy_checks} == {
        "htf_trend_alignment", "pullback_location", "reversal_break_confirmation",
        "mfi_confirmation", "adx_directional_strength", "risk_geometry_3_to_1",
    }
    assert all(len(c.evidence_sha256) == 64 for c in result.strategy_checks)
    assert all(c.provider == "hes-native-strategy-evidence-v1" for c in result.strategy_checks)
    assert result.observed_at.tzinfo is not None
    assert result.risk_checks[-1].name == "execution_disabled"
    assert result.risk_checks[-1].state == "PASS"
    assert next(c for c in result.risk_checks if c.name == "risk_context_available").state == "UNKNOWN"


def test_provider_fails_closed_on_source_gaps():
    now = 1_800_000_000_000
    fifteen = make_batch("15m", now, digest="a")
    gap = CandleGap(
        expected_open_time_ms=fifteen.candles[-1].open_time_ms,
        next_observed_open_time_ms=fifteen.candles[-1].open_time_ms + 2 * INTERVAL_MS["15m"],
        missing_intervals=1,
    )
    fifteen = replace(fifteen, gaps=(gap,))
    four_hour = make_batch("4h", now, digest="b")
    result = StrategyEvidenceProviderV1().evaluate(
        candles_15m=fifteen, candles_4h=four_hour, now_ms=now
    )
    assert "STRATEGY_SOURCE_GAPS_PRESENT" in result.blocked_reasons
    assert all(c.state == "UNKNOWN" for c in result.strategy_checks)
    assert result.risk_geometry is None


def test_provider_fails_closed_on_stale_candles():
    now = 1_800_000_000_000
    fifteen = make_batch("15m", now, digest="a")
    four_hour = make_batch("4h", now, digest="b")
    result = StrategyEvidenceProviderV1().evaluate(
        candles_15m=fifteen, candles_4h=four_hour, now_ms=now + 10 * 60 * 60 * 1000
    )
    assert any(reason.startswith("STRATEGY_SOURCE_STALE:") for reason in result.blocked_reasons)
    assert all(c.state == "UNKNOWN" for c in result.strategy_checks)


def test_provider_rejects_wrong_market_or_symbol_scope():
    now = 1_800_000_000_000
    fifteen = make_batch("15m", now, symbol="ETHUSDT", digest="a")
    four_hour = make_batch("4h", now, symbol="ETHUSDT", digest="b")
    with pytest.raises(ValueError, match="unsupported 15m strategy source scope"):
        StrategyEvidenceProviderV1().evaluate(
            candles_15m=fifteen, candles_4h=four_hour, now_ms=now
        )


def test_provider_rejects_wrong_timeframe_pair():
    now = 1_800_000_000_000
    fifteen = make_batch("15m", now, digest="a")
    wrong = make_batch("1h", now, digest="b")
    with pytest.raises(ValueError, match="requires 15m and 4h"):
        StrategyEvidenceProviderV1().evaluate(
            candles_15m=fifteen, candles_4h=wrong, now_ms=now
        )


def test_evidence_window_hash_excludes_rows_after_common_as_of():
    now = 1_800_000_000_000
    batch = make_batch("15m", now, digest="a")
    as_of_ms = batch.candles[-1].close_time_ms
    before = _evidence_window_sha256(batch, as_of_ms=as_of_ms)
    changed_last = replace(
        batch.candles[-1], volume=Decimal("999"), quote_volume=Decimal("999999")
    )
    changed_batch = replace(batch, candles=batch.candles[:-1] + (changed_last,))
    after = _evidence_window_sha256(changed_batch, as_of_ms=as_of_ms)
    assert before == after


def test_mfi14_known_monotonic_flow_edges():
    now = 1_800_000_000_000
    base = make_batch("15m", now, count=30)
    rising = []
    falling = []
    for i, original in enumerate(base.candles):
        up_close = Decimal(100 + i)
        down_close = Decimal(200 - i)
        rising.append(replace(
            original, open=up_close - Decimal("0.5"), high=up_close + Decimal("1"),
            low=up_close - Decimal("1"), close=up_close, volume=Decimal("1"),
            quote_volume=up_close, taker_buy_volume=Decimal("0.5"),
            taker_buy_quote_volume=up_close / Decimal("2"),
        ))
        falling.append(replace(
            original, open=down_close + Decimal("0.5"), high=down_close + Decimal("1"),
            low=down_close - Decimal("1"), close=down_close, volume=Decimal("1"),
            quote_volume=down_close, taker_buy_volume=Decimal("0.5"),
            taker_buy_quote_volume=down_close / Decimal("2"),
        ))
    assert mfi14(rising) == 100.0
    assert mfi14(falling) == 0.0
    adx = adx14(rising)
    assert adx is not None
    assert adx[0] > 99.0
    assert adx[1] > adx[2]
