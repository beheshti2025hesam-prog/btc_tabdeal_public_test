"""Tests for the execution-free real-data historical pipeline."""
import csv
import tempfile
import unittest
from pathlib import Path

from core.backtest.real_data import RealDataBacktest


class RealDataBacktestTests(unittest.TestCase):
    def test_runs_from_valid_csv_without_execution(self):
        rows = []
        base_sequence = 1000
        for minute in range(25):
            for trade_index in range(2):
                second = trade_index * 20
                rows.append(
                    {
                        "symbol": "BTC_USDT",
                        "price": str(100 + minute + trade_index * 0.1),
                        "amount": "1",
                        "side": "Buy" if trade_index == 0 else "Sell",
                        "updated": f"2026-09-25T00:{minute:02d}:{second:02d}+00:00",
                        "sequence": str(base_sequence + minute * 2 + trade_index),
                    }
                )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            result = RealDataBacktest(str(path), timeframe_seconds=60, ema_period=20).run()

        self.assertEqual(result.rows_read, 50)
        self.assertEqual(result.rows_valid, 50)
        self.assertEqual(result.rows_invalid, 0)
        self.assertEqual(result.candles, 25)
        self.assertEqual(result.observations, 5)
        self.assertEqual(result.continuity_excluded, 0)
        self.assertEqual(result.backtest.samples, 5)

    def test_excludes_non_contiguous_next_candle_from_measurement(self):
        rows = []
        base_sequence = 2000
        sequence = base_sequence
        for minute in range(25):
            if minute == 20:
                continue
            for trade_index in range(2):
                second = trade_index * 20
                rows.append(
                    {
                        "symbol": "BTC_USDT",
                        "price": str(100 + minute + trade_index * 0.1),
                        "amount": "1",
                        "side": "Buy" if trade_index == 0 else "Sell",
                        "updated": f"2026-09-25T00:{minute:02d}:{second:02d}+00:00",
                        "sequence": str(sequence),
                    }
                )
                sequence += 1

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            result = RealDataBacktest(str(path), timeframe_seconds=60, ema_period=20).run()

        self.assertEqual(result.candles, 24)
        self.assertGreaterEqual(result.continuity_excluded, 1)
        self.assertEqual(result.backtest.samples, result.observations)

    def test_invalid_rows_are_quarantined_from_derivation(self):
        rows = [
            {
                "symbol": "BTC_USDT",
                "price": "100",
                "amount": "1",
                "side": "Buy",
                "updated": "2026-09-25T00:00:00+00:00",
                "sequence": "1",
            },
            {
                "symbol": "BTC_USDT",
                "price": "101",
                "amount": "1",
                "side": "Buy",
                "updated": "",
                "sequence": "2",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)

            result = RealDataBacktest(str(path), timeframe_seconds=60, ema_period=1).run()

        self.assertEqual(result.rows_read, 2)
        self.assertEqual(result.rows_valid, 1)
        self.assertEqual(result.rows_invalid, 1)


if __name__ == "__main__":
    unittest.main()
