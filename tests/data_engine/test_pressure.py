import unittest

from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.pressure import BuySellPressureCalculator


def trade(sequence, side, amount):
    return RawDataNormalizer().normalize_row({
        "symbol": "BTC_USDT",
        "price": "100",
        "amount": str(amount),
        "side": side,
        "updated": f"2026-09-24T00:00:{sequence:02d}Z",
        "sequence": str(sequence),
    })


class BuySellPressureTests(unittest.TestCase):
    def test_calculates_volume_delta_and_ratios(self):
        result = BuySellPressureCalculator().calculate([
            trade(1, "buy", 2),
            trade(2, "buy", 1),
            trade(3, "sell", 1),
        ])[0]

        self.assertEqual(result.buy_volume, 3)
        self.assertEqual(result.sell_volume, 1)
        self.assertEqual(result.total_volume, 4)
        self.assertEqual(result.delta, 2)
        self.assertAlmostEqual(result.buy_ratio, 0.75)
        self.assertAlmostEqual(result.sell_ratio, 0.25)
        self.assertEqual(result.buy_trade_count, 2)
        self.assertEqual(result.sell_trade_count, 1)

    def test_zero_volume_is_safe(self):
        result = BuySellPressureCalculator().calculate([])

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
