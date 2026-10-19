import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "wallex_parity"))
from compare_ohlcv import InputError, compare_candles, load_candles


def candle(ts, volume="3"):
    # compare_candles consumes the normalized records returned by load_candles.
    return {
        "timestamp": ts, "open": Decimal("100"), "high": Decimal("110"),
        "low": Decimal("90"), "close": Decimal("105"), "volume": Decimal(volume),
    }


class CompareOhlcvTests(unittest.TestCase):
    def test_identical_candles_pass(self):
        report = compare_candles([candle(60)], [candle(60)])
        self.assertTrue(report["pass"])
        self.assertEqual(report["ohlcv_mismatch_count"], 0)

    def test_volume_exactly_twice_is_reported_not_corrected(self):
        report = compare_candles([candle(60, "0.5")], [candle(60, "1.0")])
        self.assertFalse(report["pass"])
        self.assertEqual(report["exact_2x_volume_mismatch_timestamps"], [60])
        self.assertEqual(report["ohlcv_mismatches"][0]["fields"]["volume"]["source_b"], "1.0")

    def test_missing_timestamp_fails_without_alignment_guess(self):
        report = compare_candles([candle(60)], [candle(120)])
        self.assertFalse(report["pass"])
        self.assertEqual(report["source_a_only_timestamps"], [60])
        self.assertEqual(report["source_b_only_timestamps"], [120])
        self.assertEqual(report["matched_timestamp_count"], 0)

    def test_duplicate_timestamp_fails(self):
        report = compare_candles([candle(60), candle(60)], [candle(60)])
        self.assertFalse(report["pass"])
        self.assertEqual(report["duplicate_timestamps"]["source_a"], [60])

    def test_nonpositive_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad-ts.json"
            path.write_text(json.dumps([{
                "timestamp": 0, "open": "1", "high": "1", "low": "1", "close": "1", "volume": "0"
            }]), encoding="utf-8")
            with self.assertRaises(InputError):
                load_candles(str(path))

    def test_udf_parallel_array_length_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps({
                "s": "ok", "t": [60], "o": ["1"], "h": ["1"],
                "l": ["1"], "c": ["1"], "v": []
            }), encoding="utf-8")
            with self.assertRaises(InputError):
                load_candles(str(path))

    def test_empty_sources_cannot_pass_vacuously(self):
        with self.assertRaises(InputError):
            compare_candles([], [])
        with self.assertRaises(InputError):
            compare_candles([candle(60)], [])

    def test_negative_tolerance_is_rejected_by_core(self):
        with self.assertRaises(InputError):
            compare_candles([candle(60)], [candle(60)], Decimal("-0.01"))

    def test_decimal_comparison_is_not_float_based(self):
        a = candle(60, "0.1000000000000000001")
        b = candle(60, "0.1000000000000000002")
        report = compare_candles([a], [b])
        self.assertFalse(report["pass"])
        self.assertEqual(
            report["ohlcv_mismatches"][0]["fields"]["volume"]["absolute_delta"],
            "1E-19"
        )


if __name__ == "__main__":
    unittest.main()
