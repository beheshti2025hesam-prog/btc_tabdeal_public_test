from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from forward.global_market_data_reader_v1 import MarketDataRejected, read_closed_candles


def rows_1m(count: int = 200, start: int = 1_800_000_000):
    rows = []
    for i in range(count):
        open_time = start + i * 60
        rows.append({
            "schema": "hes_global_candle_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "1m",
            "open_time": open_time,
            "close_time": open_time + 60,
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100.5",
            "volume": "2",
            "quote_volume": "200",
            "closed": True,
            "observed_at": "2026-11-03T00:00:00+00:00",
        })
    return rows


class GateioOneMinuteReaderTests(unittest.TestCase):
    def _read(self, rows, *, now=None, minimum=200):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data/forward/global_market_candles_1m_v1.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            return read_closed_candles("1m", root=temp, now=now, min_bars=minimum)

    def test_reads_only_canonical_gateio_spot_1m_closed_candles(self):
        rows = rows_1m()
        result = self._read(rows, now=rows[-1]["close_time"] + 1)
        self.assertEqual(len(result), 200)
        self.assertEqual(result[-1]["timeframe"], "1m")
        self.assertEqual(result[-1]["source"], "gateio_public_spot")

    def test_rejects_gap(self):
        rows = rows_1m()
        rows[100]["open_time"] += 60
        rows[100]["close_time"] += 60
        with self.assertRaisesRegex(MarketDataRejected, "CANDLE_INTERVAL_GAP"):
            self._read(rows, now=rows[-1]["close_time"] + 1)

    def test_rejects_wrong_source_identity(self):
        rows = rows_1m()
        rows[-1]["source"] = "other_venue"
        with self.assertRaisesRegex(MarketDataRejected, "SOURCE_IDENTITY_MISMATCH"):
            self._read(rows, now=rows[-1]["close_time"] + 1)

    def test_rejects_stale_feed(self):
        rows = rows_1m()
        with self.assertRaisesRegex(MarketDataRejected, "CANDLE_FEED_STALE"):
            self._read(rows, now=rows[-1]["close_time"] + 121)

    def test_rejects_open_candle(self):
        rows = rows_1m()
        rows[-1]["closed"] = False
        with self.assertRaisesRegex(MarketDataRejected, "OPEN_CANDLE_REJECTED"):
            self._read(rows, now=rows[-1]["close_time"] + 1)


if __name__ == "__main__":
    unittest.main()
