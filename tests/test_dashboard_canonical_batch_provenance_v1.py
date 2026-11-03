"""Canonical dashboard/analysis candle batch provenance digest tests."""
from __future__ import annotations

import hashlib
import json
import unittest

from web.dashboard import _canonical_candle_batch_sha256


def sample_rows(count: int = 260) -> list[dict]:
    return [
        {
            "schema": "hes_global_candle_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "1m",
            "open_time": i * 60,
            "close_time": (i + 1) * 60,
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": str(100 + i / 1000),
            "volume": "1.0",
            "quote_volume": "100.0",
            "closed": True,
        }
        for i in range(count)
    ]


class CanonicalCandleBatchDigestTests(unittest.TestCase):
    def test_matches_chart_contract_for_last_240_rows(self):
        rows = sample_rows()
        expected = hashlib.sha256(
            json.dumps(rows[-240:], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(_canonical_candle_batch_sha256(rows), expected)

    def test_changes_when_a_row_inside_the_batch_changes(self):
        rows = sample_rows()
        before = _canonical_candle_batch_sha256(rows)
        rows[-1]["close"] = "999.0"
        self.assertNotEqual(_canonical_candle_batch_sha256(rows), before)

    def test_ignores_rows_outside_the_bounded_chart_batch(self):
        rows = sample_rows()
        before = _canonical_candle_batch_sha256(rows)
        rows[0]["close"] = "999.0"
        self.assertEqual(_canonical_candle_batch_sha256(rows), before)

    def test_is_independent_of_mapping_key_insertion_order(self):
        row = sample_rows(1)[0]
        reversed_row = dict(reversed(list(row.items())))
        self.assertEqual(_canonical_candle_batch_sha256([row]), _canonical_candle_batch_sha256([reversed_row]))

    def test_rejects_empty_or_invalid_inputs(self):
        for rows, limit in (([], 240), ([{}], 0), (None, 240)):
            with self.subTest(rows=rows, limit=limit):
                with self.assertRaises(ValueError):
                    _canonical_candle_batch_sha256(rows, limit=limit)


if __name__ == "__main__":
    unittest.main()
