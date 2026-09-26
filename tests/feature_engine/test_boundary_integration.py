"""End-to-end real calculator -> Feature Boundary integration tests."""
import unittest
from datetime import datetime, timedelta, timezone

from core.data_engine.candles import TradeCandleAggregator
from core.data_engine.pressure import BuySellPressureCalculator
from core.data_engine.volume import VolumeIntelligenceCalculator
from core.data_engine.volatility import VolatilityCalculator
from core.data_engine.regime import MarketRegimeClassifier
from core.data_engine.vwap import VWAPCalculator
from core.feature_engine.ema import EMACalculator
from core.feature_engine.adapter import IntelligenceFeatureInput
from core.feature_engine.boundary import FeatureBoundaryGate
from core.models.trade import CanonicalTrade


class FeatureBoundaryIntegrationTests(unittest.TestCase):
    def _trades(self):
        base = datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
        prices = [100.0, 101.0, 102.0, 103.0]
        trades = []
        seq = 1000
        for minute, price in enumerate(prices):
            for offset, side in ((5, "buy"), (20, "sell"), (40, "buy")):
                ts = base + timedelta(minutes=minute, seconds=offset)
                trades.append(CanonicalTrade(
                    event_id=f"e{seq}",
                    source="test",
                    exchange="tabdeal",
                    symbol="BTC_USDT",
                    price=price,
                    quantity=1.0,
                    side=side,
                    timestamp=ts,
                    sequence=seq,
                    ingested_at=ts,
                ))
                seq += 1
        return trades

    def test_real_calculator_chain_reaches_feature_boundary(self):
        trades = self._trades()
        candles = TradeCandleAggregator(60).aggregate(trades)
        self.assertEqual(len(candles), 4)

        pressure = BuySellPressureCalculator(60).calculate(trades)
        volume = VolumeIntelligenceCalculator(lookback=3).calculate(candles)
        volatility = VolatilityCalculator(lookback=3).calculate(candles)
        regime = MarketRegimeClassifier(min_candles=2, lookback=3).classify(candles)
        vwap = VWAPCalculator(60).calculate(trades)
        ema = EMACalculator(period=3).calculate(candles)

        self.assertEqual(len(pressure), 4)
        self.assertEqual(len(volume), 4)
        self.assertEqual(len(volatility), 4)
        self.assertEqual(len(regime), 4)
        self.assertEqual(len(vwap), 4)
        self.assertEqual(len(ema), 2)

        candle = candles[2]
        ema_item = next(x for x in ema if x.timestamp == candle.end)
        vwap_item = next(x for x in vwap if x.end == candle.end)
        pressure_item = next(x for x in pressure if x.window_end == candle.end)
        volume_item = next(x for x in volume if x.window_end == candle.end)
        volatility_item = next(x for x in volatility if x.window_end == candle.end)
        regime_item = next(x for x in regime if x.window_end == candle.end)

        result = FeatureBoundaryGate().evaluate(
            IntelligenceFeatureInput(
                candle=candle,
                ema=ema_item,
                vwap=vwap_item,
                pressure=pressure_item,
                volume=volume_item,
                volatility=volatility_item,
                market_regime=regime_item,
            )
        )

        self.assertTrue(result.passed)
        self.assertIsNotNone(result.snapshot)
        self.assertEqual(result.snapshot.symbol, "BTC_USDT")
        self.assertEqual(result.snapshot.timeframe_seconds, 60)
        self.assertEqual(result.snapshot.timestamp, candle.end)
        self.assertEqual(result.snapshot.buy_sell_delta, 1.0)
        self.assertEqual(result.snapshot.regime, "uptrend")
        self.assertEqual(result.quality.violations, ())


if __name__ == "__main__":
    unittest.main()
