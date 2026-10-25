import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.audit_gateio_soak_v2 import audit_log


def make_sample(seq, when, elapsed, *, ok=True, source="gateio_public_spot", symbol="BTC_USDT", age=60):
    return {
        "schema": "hes_gateio_soak_sample_v2",
        "sample": seq,
        "observed_at": when.isoformat(),
        "elapsed_seconds": elapsed,
        "source": source,
        "symbol": symbol,
        "ok": ok,
        "timeframes": {
            "15m": {"bars": 240, "age_seconds": age, "last_close_time": int(when.timestamp()) - age, "close": 80000.0},
            "1h": {"bars": 240, "age_seconds": age, "last_close_time": int(when.timestamp()) - age, "close": 80000.0},
            "4h": {"bars": 240, "age_seconds": age, "last_close_time": int(when.timestamp()) - age, "close": 80000.0},
        },
        "services": {
            "hes-global-market-data-gateio.service": "active",
            "hes-global-market-data-gateio-1h.service": "active",
            "hes-global-market-data-gateio-4h.service": "active",
        },
    }


def write_log(records):
    temp = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False)
    with temp:
        for record in records:
            temp.write(json.dumps(record) + "\n")
    return Path(temp.name)


class GateioSoakAuditTests(unittest.TestCase):
    def test_passes_continuous_minimum_duration_fixture(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = [make_sample(1, start, 0), make_sample(2, start + timedelta(seconds=60), 60)]
        summary = {
            "schema": "hes_gateio_soak_summary_v2",
            "finished_at": (start + timedelta(seconds=120)).isoformat(),
            "samples": 2,
            "duration_seconds": 120,
            "passed": True,
        }
        result = audit_log(write_log(samples + [summary]), min_samples=2, min_duration_seconds=120)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["passed"])
        self.assertEqual(result["max_sample_gap_seconds"], 60.0)

    def test_stays_in_progress_without_summary(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = audit_log(write_log([make_sample(1, start, 0)]), min_samples=1, min_duration_seconds=60)
        self.assertEqual(result["status"], "IN_PROGRESS")
        self.assertFalse(result["passed"])

    def test_rejects_gap_larger_than_continuity_limit(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = [make_sample(1, start, 0), make_sample(2, start + timedelta(seconds=120), 120)]
        summary = {
            "schema": "hes_gateio_soak_summary_v2",
            "finished_at": (start + timedelta(seconds=180)).isoformat(),
            "samples": 2,
            "duration_seconds": 180,
            "passed": True,
        }
        result = audit_log(write_log(samples + [summary]), min_samples=2, min_duration_seconds=180)
        self.assertEqual(result["status"], "FAILED")
        self.assertTrue(any(error.startswith("SAMPLE_GAP_EXCEEDED") for error in result["errors"]))

    def test_rejects_invalid_sample_even_if_summary_claims_pass(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = [make_sample(1, start, 0, ok=False), make_sample(2, start + timedelta(seconds=60), 60)]
        summary = {
            "schema": "hes_gateio_soak_summary_v2",
            "finished_at": (start + timedelta(seconds=120)).isoformat(),
            "samples": 2,
            "duration_seconds": 120,
            "passed": True,
        }
        result = audit_log(write_log(samples + [summary]), min_samples=2, min_duration_seconds=120)
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("SAMPLE_NOT_OK:1", result["errors"])

    def test_rejects_source_or_sequence_mismatch(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        samples = [make_sample(1, start, 0), make_sample(3, start + timedelta(seconds=60), 60, symbol="ETH_USDT")]
        summary = {
            "schema": "hes_gateio_soak_summary_v2",
            "finished_at": (start + timedelta(seconds=120)).isoformat(),
            "samples": 2,
            "duration_seconds": 120,
            "passed": True,
        }
        result = audit_log(write_log(samples + [summary]), min_samples=2, min_duration_seconds=120)
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("SAMPLE_SEQUENCE_GAP:2", result["errors"])
        self.assertIn("SOURCE_IDENTITY_MISMATCH:2", result["errors"])


if __name__ == "__main__":
    unittest.main()
