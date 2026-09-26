from datetime import datetime, timedelta, timezone

from core.data_engine.candles import Candle
from core.data_engine.pressure import BuySellPressureCalculator
from core.data_engine.volume import VolumeIntelligenceCalculator
from core.data_engine.volatility import VolatilityCalculator
from core.data_engine.regime import MarketRegimeClassifier
from core.models.trade import CanonicalTrade


START = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def candle(minute, close, volume=1.0):
    start = START + timedelta(minutes=minute)
    return Candle("BTC_USDT", 60, start, start + timedelta(minutes=1),
                  close, close + 1, close - 1, close, volume, 2)


def trade(minute, side, quantity, sequence):
    timestamp = START + timedelta(minutes=minute, seconds=10)
    return CanonicalTrade(
        event_id=f"e{sequence}", source="test", exchange="tabdeal",
        symbol="BTC_USDT", price=84000.0, quantity=quantity, side=side,
        timestamp=timestamp, sequence=sequence,
    )


def test_pressure_is_one_snapshot_per_time_window():
    rows = BuySellPressureCalculator(60).calculate([
        trade(0, "buy", 2.0, 1), trade(0, "sell", 1.0, 2),
        trade(1, "sell", 3.0, 3),
    ])
    assert [(r.window_start, r.window_end) for r in rows] == [
        (START, START + timedelta(minutes=1)),
        (START + timedelta(minutes=1), START + timedelta(minutes=2)),
    ]
    assert rows[0].delta == 1.0
    assert rows[1].sell_volume == 3.0


def test_volume_emits_window_aligned_snapshots():
    rows = VolumeIntelligenceCalculator(lookback=2).calculate([
        candle(0, 100, 2.0), candle(1, 101, 4.0), candle(2, 102, 8.0)
    ])
    assert len(rows) == 3
    assert all(r.window_end - r.window_start == timedelta(minutes=1) for r in rows)
    assert rows[-1].latest_volume == 8.0
    assert rows[-1].average_volume == 6.0


def test_volatility_emits_window_aligned_snapshots():
    rows = VolatilityCalculator(lookback=2).calculate([
        candle(0, 100), candle(1, 110), candle(2, 121)
    ])
    assert len(rows) == 3
    assert rows[-1].window_start == START + timedelta(minutes=2)
    assert rows[-1].candle_count == 2


def test_regime_emits_window_aligned_snapshots():
    rows = MarketRegimeClassifier(min_candles=2, lookback=2).classify([
        candle(0, 100), candle(1, 102), candle(2, 104)
    ])
    assert len(rows) == 3
    assert rows[-1].label == "uptrend"
    assert rows[-1].window_start == START + timedelta(minutes=2)


def test_outputs_preserve_symbol_and_timeframe_alignment():
    candles = [candle(0, 100), candle(1, 101), candle(2, 102)]
    assert all(r.symbol == "BTC_USDT" and r.timeframe_seconds == 60
               for r in VolumeIntelligenceCalculator().calculate(candles))
    assert all(r.symbol == "BTC_USDT" and r.timeframe_seconds == 60
               for r in VolatilityCalculator().calculate(candles))
    assert all(r.symbol == "BTC_USDT" and r.timeframe_seconds == 60
               for r in MarketRegimeClassifier().classify(candles))
