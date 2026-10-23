import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

from core.market_intelligence.news_brain import MarketContext, NewsIntelligenceBrain, NewsItem, fetch_rss, load_source_registry

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


class NewsBrainTests(unittest.TestCase):
    def setUp(self):
        self.brain = NewsIntelligenceBrain()

    def test_relevant_crypto_security_news_escalates_confirmation(self):
        item = NewsItem("Major crypto exchange reports security breach; withdrawals suspended",
                        "Bitcoin market watches venue risk", "ExampleWire",
                        "https://example.test/news/1", "2026-10-23T11:30:00Z")
        brief = self.brain.analyze([item], MarketContext("crypto", "BTCUSDT", "range", "1m"), now=NOW)
        self.assertEqual(brief.schema_version, "hes.news_brief.v1")
        self.assertEqual(len(brief.findings), 1)
        self.assertIn("security", brief.findings[0].categories)
        self.assertIn("exchange", brief.findings[0].categories)
        self.assertIn("HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION", brief.veto_flags)
        self.assertEqual(brief.suggested_action, "NO_TRADE_PENDING_CONFIRMATION")
        self.assertFalse(brief.provenance["news_alone_can_authorize_trade"])

    def test_irrelevant_item_scores_lower_than_symbol_market_match(self):
        items = [NewsItem("Local football club announces coach", source="A", url="https://a.test/1"),
                 NewsItem("Bitcoin ETF sees large inflows", source="B", url="https://b.test/2")]
        brief = self.brain.analyze(items, MarketContext("crypto", "BTCUSDT", "uptrend"), now=NOW)
        self.assertEqual(brief.findings[0].title, "Bitcoin ETF sees large inflows")
        self.assertGreater(brief.findings[0].relevance, brief.findings[1].relevance)

    def test_duplicate_url_deduplicates(self):
        items = [NewsItem("Bitcoin ETF inflows", source="A", url="https://a.test/story"),
                 NewsItem("Bitcoin ETF inflows with details", summary="more", source="B", url="https://a.test/story")]
        brief = self.brain.analyze(items, MarketContext("crypto", "BTC", "range"), now=NOW)
        self.assertEqual(len(brief.findings), 1)
        self.assertEqual(brief.provenance["sources_seen"], 1)

    def test_stale_news_is_dropped(self):
        item = NewsItem("Bitcoin hack", source="wire", url="https://wire.test/old",
                        published_at="2026-10-10T12:00:00Z")
        brief = self.brain.analyze([item], MarketContext("crypto", "BTC", "range"), now=NOW)
        self.assertEqual(len(brief.findings), 0)
        self.assertEqual(brief.provenance["stale_items_dropped"], 1)

    def test_missing_sources_degrade_and_request_confirmation(self):
        brief = self.brain.analyze([], MarketContext("crypto", "BTC", "uptrend"), now=NOW,
                                   source_failures=["primary_feed:timeout"])
        self.assertEqual(brief.status, "degraded")
        self.assertIn("NEWS_SOURCE_COVERAGE_INCOMPLETE", brief.veto_flags)
        self.assertEqual(brief.suggested_action, "NO_TRADE_PENDING_CONFIRMATION")

    def test_unknown_regime_never_turns_news_into_directional_trade(self):
        brief = self.brain.analyze([NewsItem("Bitcoin ETF sees inflows", source="wire",
            url="https://wire.test/1")], MarketContext("crypto", "BTC", "unknown"), now=NOW)
        self.assertEqual(brief.suggested_action, "NO_TRADE_PENDING_CONFIRMATION")
        self.assertIn("Market regime is unknown", " ".join(brief.market_implications))

    def test_future_timestamp_is_flagged(self):
        brief = self.brain.analyze([NewsItem("Bitcoin ETF approved", source="wire",
            url="https://wire.test/future", published_at="2026-10-23T13:00:00Z")],
            MarketContext("crypto", "BTC", "range"), now=NOW)
        self.assertIn("NEWS_TIMESTAMP_SUSPECT", brief.veto_flags)
        self.assertIn("publication_time_in_future", brief.findings[0].caveats)

    def test_json_contract_is_machine_readable(self):
        brief = self.brain.analyze([], MarketContext("fx", "EURUSD", "range"), now=NOW)
        self.assertIn('"schema_version": "hes.news_brief.v1"', brief.to_json())
        self.assertIn('"news_alone_can_authorize_trade": false', brief.to_json())

    def test_mother_payload_is_compact_and_carries_veto(self):
        brief = self.brain.analyze(
            [NewsItem("Major crypto exchange hack; withdrawals suspended", source="wire",
                      url="https://wire.test/hack")],
            MarketContext("crypto", "BTC", "range"), now=NOW)
        payload = brief.to_mother_payload()
        self.assertEqual(payload["schema_version"], "hes.news_brief.v1")
        self.assertIn("suggested_action", payload)
        self.assertIn("HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION", payload["veto_flags"])
        self.assertFalse(payload["news_alone_can_authorize_trade"])
        self.assertLessEqual(len(payload["top_findings"]), 3)

    def test_registry_is_disabled_until_source_qualification(self):
        registry_path = Path(__file__).resolve().parents[1] / "config" / "news_sources_v1.json"
        registry = load_source_registry(registry_path)
        self.assertEqual(registry["schema_version"], "hes.news_sources.v1")
        self.assertTrue(registry["sources"])
        enabled = [source for source in registry["sources"] if source["enabled"]]
        self.assertEqual({source["id"] for source in enabled},
                         {"ecb_press_releases", "cftc_general_press_releases"})
        self.assertTrue(all(source["qualification_status"] == "qualified" for source in enabled))
        self.assertFalse(next(source for source in registry["sources"]
                              if source["id"] == "coindesk_news")["enabled"])
        self.assertEqual(registry["market_profiles"]["iran_equities"]["status"],
                         "blocked_no_qualified_source")

    def test_unverified_source_vetoes_trade_context(self):
        brief = self.brain.analyze(
            [NewsItem("Bitcoin ETF approved", url="https://unknown.test/item")],
            MarketContext("crypto", "BTC", "range"), now=NOW)
        self.assertIn("NEWS_SOURCE_UNVERIFIED", brief.veto_flags)
        self.assertEqual(brief.suggested_action, "NO_TRADE_PENDING_CONFIRMATION")

    def test_pipeline_fails_closed_when_no_source_is_enabled(self):
        registry_path = Path(__file__).resolve().parents[1] / "config" / "news_sources_v1.json"
        brief = self.brain.run_from_registry(
            registry_path, MarketContext("iran_equities", "TSE", "unknown"), now=NOW)
        self.assertEqual(brief.status, "degraded")
        self.assertIn("NEWS_SOURCE_COVERAGE_INCOMPLETE", brief.veto_flags)
        self.assertEqual(brief.suggested_action, "NO_TRADE_PENDING_CONFIRMATION")
        self.assertTrue(brief.provenance["source_failures"])
        self.assertEqual(brief.provenance["source_profile_status"], "blocked_no_qualified_source")

    def test_registry_cannot_enable_unqualified_source(self):
        bad_registry = {
            "schema_version": "hes.news_sources.v1",
            "sources": [{
                "id": "bad", "url": "https://example.test/feed", "host": "example.test",
                "enabled": True, "qualification_status": "candidate", "markets": ["crypto"]
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sources.json"
            path.write_text(json.dumps(bad_registry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "before qualification"):
                load_source_registry(path)

    def test_non_https_feed_rejected_before_network(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            fetch_rss("http://example.test/feed", source="test")


if __name__ == "__main__":
    unittest.main()
