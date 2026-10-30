import unittest
from datetime import datetime, timezone

from core.market_intelligence.news_brain import MarketContext, NewsIntelligenceBrain, NewsItem
from forward.decision_engine_v1 import DecisionResult
from forward.news_decision_gate_v1 import apply_news_veto

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


class NewsDecisionGateTests(unittest.TestCase):
    def setUp(self):
        self.brain = NewsIntelligenceBrain()
        self.long = DecisionResult(NOW, "LONG", ("ALL_REQUIRED_GATES_PASSED",), ("market:candle:1",), 0.8)

    def test_high_impact_news_vetoes_directional_decision(self):
        brief = self.brain.analyze(
            [NewsItem("Major crypto exchange hack; withdrawals suspended", source="wire",
                      url="https://wire.test/hack", published_at="2026-10-23T11:45:00Z")],
            MarketContext("crypto", "BTCUSDT", "range"), now=NOW)
        result = apply_news_veto(self.long, brief)
        self.assertEqual(result.decision, "NO_TRADE")
        self.assertIn("NEWS_GATE_VETO", result.reason_codes)
        self.assertIn("HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION", result.reason_codes)
        self.assertIn("news:https://wire.test/hack", result.evidence_refs)
        self.assertEqual(result.quality_score, 0.8)

    def test_clean_context_only_brief_preserves_decision(self):
        brief = self.brain.analyze([], MarketContext("crypto", "BTCUSDT", "range"), now=NOW)
        self.assertEqual(brief.suggested_action, "CONTEXT_ONLY")
        self.assertEqual(apply_news_veto(self.long, brief), self.long)

    def test_disabled_source_coverage_vetoes_directional_decision(self):
        brief = self.brain.run_from_registry(
            "config/news_sources_v1.json", MarketContext("iran_equities", "TSE", "unknown"), now=NOW)
        result = apply_news_veto(self.long, brief)
        self.assertEqual(result.decision, "NO_TRADE")
        self.assertIn("NEWS_SOURCE_COVERAGE_INCOMPLETE", result.reason_codes)

    def test_partial_source_profile_vetoes_directional_decision(self):
        brief = self.brain.analyze([], MarketContext("crypto", "BTCUSDT", "range"), now=NOW)
        object.__setattr__(brief, "provenance", {**brief.provenance, "source_profile_status": "partial_official_macro_regulatory_only"})
        result = apply_news_veto(self.long, brief)
        self.assertEqual(result.decision, "NO_TRADE")
        self.assertIn("NEWS_SOURCE_COVERAGE_INCOMPLETE", result.reason_codes)

    def test_unknown_schema_fails_closed(self):
        brief = self.brain.analyze([], MarketContext("crypto", "BTCUSDT", "range"), now=NOW)
        object.__setattr__(brief, "schema_version", "future.schema")
        result = apply_news_veto(self.long, brief)
        self.assertEqual(result.decision, "NO_TRADE")
        self.assertIn("NEWS_BRIEF_SCHEMA_UNSUPPORTED", result.reason_codes)

    def test_existing_no_trade_is_preserved(self):
        no_trade = DecisionResult(NOW, "NO_TRADE", ("RISK_NOT_APPROVED",), (), None)
        brief = self.brain.analyze(
            [NewsItem("Major crypto exchange hack", source="wire", url="https://wire.test/hack")],
            MarketContext("crypto", "BTCUSDT", "range"), now=NOW)
        self.assertEqual(apply_news_veto(no_trade, brief), no_trade)


if __name__ == "__main__":
    unittest.main()
