import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_gateio_analysis_v1 import run
from scripts.analyze_gateio_snapshot_v1 import mfi

PERIODS = {
    "15m": (900, "data/forward/global_market_candles_v1.jsonl"),
    "1h": (3600, "data/forward/global_market_candles_1h_v1.jsonl"),
    "4h": (14400, "data/forward/global_market_candles_4h_v1.jsonl"),
}


def write_fixture(root: Path, timeframe: str, count: int = 220) -> None:
    period, relative = PERIODS[timeframe]
    now = int(time.time())
    last_close = (now // period) * period
    first_open = last_close - count * period
    observed_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for index in range(count):
        open_time = first_open + index * period
        close_time = open_time + period
        open_price = 30000.0 + index * 2.0
        close_price = open_price + 0.5
        high = max(open_price, close_price) + 1.0
        low = min(open_price, close_price) - 1.0
        volume = 1.0 + (index % 5) * 0.1
        rows.append({
            "schema": "hes_global_candle_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": timeframe,
            "open_time": open_time,
            "close_time": close_time,
            "open": str(open_price),
            "high": str(high),
            "low": str(low),
            "close": str(close_price),
            "volume": str(volume),
            "quote_volume": str(volume * close_price),
            "closed": True,
            "observed_at": observed_at,
        })
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_all_fixtures(root: Path) -> None:
    for timeframe in PERIODS:
        write_fixture(root, timeframe)


class GateIOAnalysisIntegrationTests(unittest.TestCase):
    def test_fixture_input_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_all_fixtures(root)
            result = run(root)
            self.assertEqual(result["source"], "gateio_public_spot")
            self.assertEqual(result["decision"]["decision"], "NO_TRADE")
            self.assertFalse(result["execution_enabled"])
            self.assertFalse(result["orders_placed"])
            self.assertEqual(set(result["market_features"]), {"15m", "1h", "4h"})

    def test_decision_output_has_explicit_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_all_fixtures(root)
            result = run(root)
            self.assertEqual(result["decision"]["signal_state"], "NO_CANDIDATE")
            self.assertEqual(result["decision"]["confirmation_state"], "NOT_CONFIGURED")
            self.assertEqual(result["decision"]["risk_state"], "RISK_NOT_APPROVED")
            self.assertTrue(result["decision"]["no_trade_reason"])

    def test_zero_volume_mfi_is_unavailable_not_synthetic_100(self):
        rows = [
            {"high": "10", "low": "9", "close": "9.5", "volume": "0"}
            for _ in range(15)
        ]
        self.assertIsNone(mfi(rows))


if __name__ == "__main__":
    unittest.main()
