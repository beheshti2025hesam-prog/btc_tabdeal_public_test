import unittest

from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.vwap import VWAPCalculator


class VWAPTests(unittest.TestCase):
    def test_weighted_average_price(self):
        normalizer = RawDataNormalizer()
        trades = [
            normalizer.normalize_row({"symbol":"BTC_USDT","price":"100","amount":"2","side":"buy","updated":"2026-09-24T00:00:01Z","sequence":"1"}),
            normalizer.normalize_row({"symbol":"BTC_USDT","price":"110","amount":"1","side":"sell","updated":"2026-09-24T00:00:02Z","sequence":"2"}),
        ]
        result = VWAPCalculator().calculate(trades)[0]
        self.assertAlmostEqual(result.vwap, 310 / 3)
        self.assertEqual(result.volume, 3)
        self.assertEqual(result.trade_count, 2)


if __name__ == "__main__":
    unittest.main()
