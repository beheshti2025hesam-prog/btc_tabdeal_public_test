"""Tests for causal POST-QUALITY evidence extraction."""
import unittest
from datetime import datetime, timedelta, timezone
from core.data_engine.candles import Candle
from core.feature_engine.quality_evidence import QualityEvidenceEngine


class QualityEvidenceTests(unittest.TestCase):
    def make_candles(self, count=850):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        out = []
        price = 100.0
        for i in range(count):
            drift = 0.08 if i < 500 else (0.12 if i % 7 else -0.25)
            open_ = price
            close = price + drift
            high = max(open_, close) + 0.12
            low = min(open_, close) - 0.10
            if i % 23 == 0:
                low = price - 0.8
                close = price + 0.25
            if i % 29 == 0:
                high = price + 0.8
                close = price - 0.25
            out.append(Candle(
                "BTC_USDT", 900,
                start + timedelta(minutes=15*i),
                start + timedelta(minutes=15*(i+1)),
                open_, high, low, close, 10.0 + (i % 5), 5
            ))
            price = close
        return out

    def test_engine_is_causal_and_returns_complete_schema(self):
        candles = self.make_candles()
        index = len(candles) - 2
        evidence = QualityEvidenceEngine().build(candles, index)
        self.assertIn(evidence.htf_trend, ("long", "short", "range"))
        self.assertTrue(hasattr(evidence, "rr"))
        self.assertTrue(hasattr(evidence, "stop_price"))

        # Future candles must not alter the snapshot at an earlier index.
        truncated = candles[:index + 1]
        replay = QualityEvidenceEngine().build(truncated, index)
        self.assertEqual(evidence, replay)

    def test_early_history_does_not_invent_evidence(self):
        candles = self.make_candles()
        evidence = QualityEvidenceEngine().build(candles, 20)
        self.assertIsNone(evidence.htf_trend)
        self.assertIsNone(evidence.structure_bias)
        self.assertIsNone(evidence.stop_price)


if __name__ == "__main__":
    unittest.main()
