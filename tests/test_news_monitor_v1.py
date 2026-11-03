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
            provenance={"source_failures": failures or [], "source_profile_status": "partial_official_macro_regulatory_and_venue_announcements", "source_health": [{"source_id": "fed_press_all", "status": "ok_empty", "item_count": 0}]},
            to_dict=lambda: {
                "schema_version": "hes.news_brief.v1",
                "status": status,
                "provenance": {"source_failures": failures or [], "source_profile_status": "partial_official_macro_regulatory_and_venue_announcements", "source_health": [{"source_id": "fed_press_all", "status": "ok_empty", "item_count": 0}]},
                "suggested_action": "CONTEXT_ONLY",
            },
        )

    def test_poll_once_atomically_persists_digest_verified_snapshot(self):
        self.brain.run_from_registry.return_value = self._brief()
        snapshot = self.monitor.poll_once()
        self.assertEqual(snapshot["schema_version"], SCHEMA_VERSION)
        self.assertEqual(snapshot["monitor"]["status"], "OK")
        self.assertEqual(snapshot["monitor"]["source_profile_status"], "partial_official_macro_regulatory_and_venue_announcements")
        self.assertEqual(snapshot["monitor"]["source_health"][0]["status"], "ok_empty")
        self.assertTrue(self.path.is_file())
        loaded = self.monitor.read_snapshot()
        self.assertEqual(loaded["brief"]["schema_version"], "hes.news_brief.v1")
        self.assertEqual(len(loaded["brief_sha256"]), 64)
        self.brain.run_from_registry.assert_called_once_with(
            self.monitor.registry_path, self.context, now=NOW
        )

    def test_event_ledger_persists_each_source_item_once_with_provenance(self):
        brief = self._brief()
        finding = {
            "item_id": "news-item-001",
            "title": "Bitcoin ETF investors exit after Binance hack",
            "source": "Decrypt",
            "url": "https://decrypt.example/story-1",
            "published_at": "2026-10-31T11:00:00Z",
            "impact": 0.9,
            "relevance": 1.0,
            "directional_bias": "negative",
            "categories": ["security", "crypto_market"],
            "freshness": "fresh",
            "caveats": [],
        }
        brief.provenance["source_evidence"] = [{
            "source_id": "decrypt_news",
            "url": finding["url"],
            "feed_payload_sha256": "a" * 64,
            "raw_item_sha256": "b" * 64,
            "retrieved_at": NOW.isoformat(),
        }]
        brief.provenance["high_impact_event_clusters"] = [{
            "event_id": "binance_security_incident",
            "item_ids": ["news-item-001"],
        }]
        base = brief.to_dict()
        base["findings"] = [finding]
        brief.to_dict = lambda: base
        self.brain.run_from_registry.return_value = brief

        first = self.monitor.poll_once()
        second = self.monitor.poll_once()
        ledger = self.path.with_name("news_events.jsonl")
        rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_id"], "news-item-001")
        self.assertEqual(rows[0]["event_cluster_id"], "binance_security_incident")
        self.assertEqual(rows[0]["source_id"], "decrypt_news")
        self.assertEqual(rows[0]["raw_item_sha256"], "b" * 64)
        self.assertEqual(rows[0]["brief_sha256"], first["brief_sha256"])
        self.assertEqual(first["event_ledger"]["records_appended"], 1)
        self.assertEqual(second["event_ledger"]["records_appended"], 0)
        self.assertEqual(second["event_ledger"]["records_total"], 1)

    def test_corrupt_event_ledger_fails_closed(self):
        ledger = self.path.with_name("news_events.jsonl")
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("{not-json}\n", encoding="utf-8")
        brief = self._brief()
        base = brief.to_dict()
        base["findings"] = [{
            "item_id": "news-item-002", "title": "Bitcoin hack",
            "url": "https://news.example/2",
        }]
        brief.to_dict = lambda: base
        self.brain.run_from_registry.return_value = brief
        with self.assertRaisesRegex(ValueError, "ledger line 1 is invalid"):
            self.monitor.poll_once()

    def test_source_freshness_is_distinct_from_transport_health(self):
        now = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
        self.monitor.clock = lambda: now
        brief = self._brief()
        brief.provenance["source_health"] = [
            {"source_id": "fresh", "status": "ok", "newest_published_at": "2026-10-31T11:00:00Z"},
            {"source_id": "aging", "status": "ok", "newest_published_at": "2026-10-30T00:00:00Z"},
            {"source_id": "stale", "status": "ok", "newest_published_at": "2026-10-27T00:00:00Z"},
            {"source_id": "empty", "status": "ok_empty", "newest_published_at": None},
            {"source_id": "failed", "status": "failed", "newest_published_at": None},
            {"source_id": "unknown", "status": "ok", "newest_published_at": None},
        ]
        self.brain.run_from_registry.return_value = brief
        snapshot = self.monitor.poll_once()
        health = {x["source_id"]: x for x in snapshot["monitor"]["source_health"]}
        self.assertEqual(health["fresh"]["freshness_status"], "fresh")
        self.assertEqual(health["aging"]["freshness_status"], "aging")
        self.assertEqual(health["stale"]["freshness_status"], "stale")
        self.assertEqual(health["empty"]["freshness_status"], "empty")
        self.assertEqual(health["failed"]["freshness_status"], "failed")
        self.assertEqual(health["unknown"]["freshness_status"], "unknown")
        self.assertEqual(health["stale"]["freshness_threshold_hours"], 72)
        self.assertEqual(health["fresh"]["newest_age_minutes"], 60.0)

    def test_source_failure_is_persisted_as_degraded_not_clean(self):
        self.brain.run_from_registry.return_value = self._brief("degraded", ["ecb_press_releases:timeout"])
        snapshot = self.monitor.poll_once()
        self.assertEqual(snapshot["monitor"]["status"], "DEGRADED")
        self.assertIsNone(snapshot["monitor"]["last_success_at"])
        self.assertEqual(snapshot["brief"]["provenance"]["source_failures"],
                         ["ecb_press_releases:timeout"])

    def test_run_forever_performs_immediate_poll_and_stops_cleanly(self):
        from threading import Event
        stop = Event()
        self.brain.run_from_registry.return_value = self._brief()
        self.monitor.on_brief = lambda brief: stop.set()
        self.monitor.run_forever(stop)
        self.brain.run_from_registry.assert_called_once()
        self.assertEqual(self.monitor.last_status, "OK")

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
        future_time = datetime.now(timezone.utc) + timedelta(days=1)
        future_monitor = NewsMonitorV1(
            brain=self.brain, registry_path=self.monitor.registry_path,
            context=self.context, snapshot_path=self.path, interval_seconds=60,
            clock=lambda: future_time,
        )
        self.brain.run_from_registry.return_value = self._brief()
        future_monitor.poll_once()
        with self.assertRaisesRegex(ValueError, "future"):
            future_monitor.read_snapshot(max_age_seconds=180)

    def test_monitor_metadata_tampering_is_rejected_by_snapshot_digest(self):
        self.brain.run_from_registry.return_value = self._brief()
        self.monitor.poll_once()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["monitor"]["status"] = "BLOCKED"
        data["monitor"]["source_failures"] = []
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "snapshot digest mismatch"):
            self.monitor.read_snapshot()

    def test_invalid_interval_rejected(self):
        with self.assertRaises(ValueError):
            NewsMonitorV1(
                brain=self.brain, registry_path=self.monitor.registry_path,
                context=self.context, snapshot_path=self.path, interval_seconds=1,
            )


if __name__ == "__main__":
    unittest.main()
