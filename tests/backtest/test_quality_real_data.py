"""Integration tests for the POST-QUALITY real-data replay path."""
import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.backtest.quality_real_data import QualityRealDataBacktest


class QualityRealDataBacktestTests(unittest.TestCase):
    @staticmethod
    def _write(path: Path, candles: int = 820) -> None:
        rows = []
        base = 100.0
        for i in range(candles):
            # One trade per 15m candle; enough history to exercise the 1h HTF path.
            price = base + (i % 80) * 0.05 + (i // 80) * 0.2
            timestamp = datetime(2026, 9, 25, tzinfo=timezone.utc) + timedelta(minutes=i * 15)
            rows.append({
                "symbol": "BTC_USDT",
                "price": f"{price:.6f}",
                "amount": "1",
                "side": "Buy" if i % 2 == 0 else "Sell",
                "updated": timestamp.isoformat(),
                "sequence": str(100000 + i),
            })
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def test_post_quality_replay_accepts_valid_rows_and_is_selective(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"
            self._write(path)
            result = QualityRealDataBacktest(str(path), timeframe_seconds=900).run()

        self.assertEqual(result.rows_read, 820)
        self.assertEqual(result.rows_valid, 820)
        self.assertEqual(result.rows_invalid, 0)
        self.assertEqual(result.candles, 820)
        self.assertEqual(result.observations, result.backtest.samples)
        self.assertGreaterEqual(result.backtest.no_trade, 1)
        self.assertGreaterEqual(result.backtest.vetoed, 0)

    def test_invalid_rows_do_not_enter_quality_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trades.csv"
            self._write(path, candles=20)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(
                    "BTC_USDT,100,1,Bad,2026-09-25T05:00:00+00:00,999999\n"
                )
            result = QualityRealDataBacktest(str(path), timeframe_seconds=900).run()

        self.assertEqual(result.rows_read, 21)
        self.assertEqual(result.rows_valid, 20)
        self.assertEqual(result.rows_invalid, 1)


if __name__ == "__main__":
    unittest.main()
