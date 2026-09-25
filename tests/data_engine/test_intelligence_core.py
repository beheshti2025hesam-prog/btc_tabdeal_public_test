from datetime import datetime, timezone

from core.data_engine.candles import Candle, TradeCandleAggregator
from core.data_engine.pressure import BuySellPressureCalculator
from core.data_engine.regime import MarketRegimeClassifier
from core.data_engine.volatility import VolatilityCalculator
from core.data_engine.volume import VolumeIntelligenceCalculator
from core.data_engine.vwap import VWAPCalculator
from core.data_engine.normalizer import RawDataNormalizer


def make_trade(seq, sec, price, amount, side="buy"):
    minute, second = divmod(sec, 60)
    return RawDataNormalizer().normalize_row(
        {
            "symbol": "BTC_USDT",
            "price": str(price),
            "amount": str(amount),
            "side": side,
            "updated": f"2026-09-24T00:{minute:02d}:{second:02d}Z",
            "sequence": str(seq),
        }
    )


def make_candle(minute, o, h, l, c, volume=1.0):
    start = datetime(2026, 9, 24, 0, minute, tzinfo=timezone.utc)
    return Candle("BTC_USDT", 60, start, start, o, h, l, c, volume, 1)


def test_candle_aggregation_is_deterministic():
    result = TradeCandleAggregator(60).aggregate(
        [make_trade(3, 30, 101, .3), make_trade(1, 5, 100, .2), make_trade(2, 10, 103, .1)]
    )
    c = result[0]
    assert (c.open, c.high, c.low, c.close) == (100, 103, 100, 101)
    assert c.volume == .6 and c.trade_count == 3


def test_vwap_is_time_windowed_and_deterministic():
    trades = [
        make_trade(1, 1, 100, 2, "buy"),
        make_trade(2, 2, 110, 1, "sell"),
        make_trade(3, 61, 120, 1, "buy"),
    ]
    snapshots = VWAPCalculator(60).calculate(trades)
    assert len(snapshots) == 2
    first = snapshots[0]
    assert first.start == datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)
    assert first.end == datetime(2026, 9, 24, 0, 1, tzinfo=timezone.utc)
    assert abs(first.vwap - 310 / 3) < 1e-12
    assert first.volume == 3 and first.trade_count == 2


def test_vwap_rejects_naive_timestamp():
    trade = make_trade(1, 1, 100, 1)
    trade = trade.__class__(
        **{**trade.__dict__, "timestamp": datetime(2026, 9, 24, 0, 0, 1)}
    )
    try:
        VWAPCalculator().calculate([trade])
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive timestamps must be rejected")


def test_pressure_remains_deterministic():
    trades = [make_trade(1, 1, 100, 2, "buy"), make_trade(2, 2, 110, 1, "sell")]
    p = BuySellPressureCalculator().calculate(trades)[0]
    assert p.delta == 1 and p.buy_ratio == 0.6666666666666666


def test_volume_volatility_and_regime():
    candles = [
        make_candle(0, 100, 102, 99, 101, 10),
        make_candle(1, 101, 104, 100, 103, 10),
        make_candle(2, 103, 105, 102, 104, 20),
    ]
    v = VolumeIntelligenceCalculator().calculate(candles)[0]
    assert v.is_volume_spike and abs(v.latest_vs_average - 1.5) < 1e-12
    vol = VolatilityCalculator().calculate(candles)[0]
    assert vol.return_stddev > 0 and vol.average_true_range == (4 + 3) / 2
    regime = MarketRegimeClassifier().classify(candles)[0]
    assert regime.label == "uptrend"
