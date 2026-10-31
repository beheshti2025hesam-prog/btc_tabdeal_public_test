import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from core.market_intelligence.news_brain import MarketContext
from core.market_intelligence.news_monitor import NewsMonitorV1, SCHEMA_VERSION


NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)


class NewsMonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "state" / "news_brief_latest.json"
        self.brain = Mock()
        self.context = MarketContext("crypto", "BTCUSDT", "unknown", "15m", venue="gateio")
        self.monitor = NewsMonitorV1(
            brain=self.brain,
            registry_path=Path(self.temp.name) / "registry.json",
            context=self.context,
            snapshot_path=self.path,
            interval_seconds=60,
            clock=lambda: NOW,
        )

    def _brief(self, status="ok", failures=None):
        return SimpleNamespace(
            status=status,
            provenance={"source_failures": failures or [], "source_profile_status": "partial_official_macro_regulatory_and_venue_announcements"},
            to_dict=lambda: {
                "schema_version": "hes.news_brief.v1",
                "status": status,
                "provenance": {"source_failures": failures or [], "source_profile_status": "partial_official_macro_regulatory_and_venue_announcements"},
                "suggested_action": "CONTEXT_ONLY",
            },
        )

    def test_poll_once_atomically_persists_digest_verified_snapshot(self):
        self.brain.run_from_registry.return_value = self._brief()
        snapshot = self.monitor.poll_once()
        self.assertEqual(snapshot["schema_version"], SCHEMA_VERSION)
        self.assertEqual(snapshot["monitor"]["status"], "OK")
        self.assertEqual(snapshot["monitor"]["source_profile_status"], "partial_official_macro_regulatory_and_venue_announcements")
        self.assertTrue(self.path.is_file())
        loaded = self.monitor.read_snapshot()
        self.assertEqual(loaded["brief"]["schema_version"], "hes.news_brief.v1")
        self.assertEqual(len(loaded["brief_sha256"]), 64)
        self.brain.run_from_registry.assert_called_once_with(
            self.monitor.registry_path, self.context, now=NOW
        )

    def test_source_failure_is_persisted_as_degraded_not_clean(self):
        self.brain.run_from_registry.return_value = self._brief("degraded", ["ecb_press_releases:timeout"])
        snapshot = self.monitor.poll_once()
        self.assertEqual(snapshot["monitor"]["status"], "DEGRADED")
        self.assertIsNone(snapshot["monitor"]["last_success_at"])
        self.assertEqual(snapshot["brief"]["provenance"]["source_failures"],
                         ["ecb_press_releases:timeout"])

    def test_worker_failure_writes_blocked_state_and_preserves_last_success(self):
        self.brain.run_from_registry.side_effect = ValueError("registry unavailable")
        snapshot = self.monitor.record_failure(ValueError("registry unavailable"))
        self.assertEqual(snapshot["monitor"]["status"], "BLOCKED")
        self.assertEqual(snapshot["monitor"]["last_error"], "ValueError")
        self.assertIsNone(snapshot["brief"])
        self.assertIsNone(snapshot["monitor"]["last_success_at"])
        self.assertEqual(self.monitor.read_snapshot()["monitor"]["status"], "BLOCKED")

    def test_corrupt_digest_is_rejected(self):
        self.brain.run_from_registry.return_value = self._brief()
        self.monitor.poll_once()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["brief"]["suggested_action"] = "LONG"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.monitor.read_snapshot()

    def test_failure_preserves_previous_success_timestamp(self):
        self.brain.run_from_registry.return_value = self._brief()
        first = self.monitor.poll_once()
        previous_success = first["monitor"]["last_success_at"]
        failed = self.monitor.record_failure(ValueError("temporary"))
        self.assertEqual(failed["monitor"]["last_success_at"], previous_success)

    def test_future_poll_timestamp_is_rejected_by_reader(self):
        future_monitor = NewsMonitorV1(
            brain=self.brain, registry_path=self.monitor.registry_path,
            context=self.context, snapshot_path=self.path, interval_seconds=60,
            clock=lambda: NOW + timedelta(days=1),
        )
        self.brain.run_from_registry.return_value = self._brief()
        future_monitor.poll_once()
        with self.assertRaisesRegex(ValueError, "future"):
            future_monitor.read_snapshot(max_age_seconds=180)

    def test_invalid_interval_rejected(self):
        with self.assertRaises(ValueError):
            NewsMonitorV1(
                brain=self.brain, registry_path=self.monitor.registry_path,
                context=self.context, snapshot_path=self.path, interval_seconds=1,
            )


if __name__ == "__main__":
    unittest.main()
