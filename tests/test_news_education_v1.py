import unittest
from datetime import datetime, timezone

from core.market_intelligence.news_brain import MarketContext, NewsIntelligenceBrain, NewsItem
from core.market_intelligence.news_education_v1 import (
    LOCALES,
    SCHEMA_VERSION,
    build_news_item_interpretation_v1,
)

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


class NewsEducationV1Tests(unittest.TestCase):
    def test_interpretation_has_complete_four_locale_educational_content(self):
        brief = NewsIntelligenceBrain().analyze(
            [NewsItem(
                "Bitcoin ETF approved after regulator review",
                "Institutional adoption and inflows are expected.",
                "Example Wire",
                "https://example.test/bitcoin-etf",
                "2026-11-14T11:30:00Z",
            )],
            MarketContext("crypto", "BTCUSDT", "range", "15m", venue="gateio"),
            now=NOW,
        )
        finding = brief.findings[0]
        interpretation = finding.interpretation
        self.assertEqual(interpretation["schema_version"], SCHEMA_VERSION)
        self.assertEqual(set(interpretation["localized"]), set(LOCALES))
        for locale in LOCALES:
            localized = interpretation["localized"][locale]
            self.assertTrue(localized["what_happened"])
            self.assertTrue(localized["why_it_matters"])
            self.assertTrue(localized["affected_market"])
            self.assertTrue(localized["potential_effect"])
            self.assertTrue(localized["transmission_channel"])
            self.assertTrue(localized["time_horizon"])
            self.assertTrue(localized["what_to_monitor"])
            self.assertTrue(localized["educational_concept"])
            self.assertTrue(localized["uncertainty"])
            self.assertTrue(localized["disclaimer"])

    def test_same_canonical_analysis_is_shared_with_mother_payload(self):
        brief = NewsIntelligenceBrain().analyze(
            [NewsItem(
                "Bitcoin ETF approved",
                "New inflows reported",
                "Example Wire",
                "https://example.test/etf",
                "2026-11-14T11:30:00Z",
            )],
            MarketContext("crypto", "BTCUSDT", "unknown", "15m", venue="gateio"),
            now=NOW,
        )
        finding = brief.findings[0]
        mother_payload = brief.to_mother_payload()
        self.assertEqual(
            mother_payload["top_findings"][0]["interpretation"],
            finding.interpretation,
        )
        self.assertFalse(mother_payload["news_alone_can_authorize_trade"])
        self.assertFalse(finding.interpretation["mother_use"]["news_alone_can_authorize_trade"])

    def test_unknown_direction_is_not_invented(self):
        interpretation = build_news_item_interpretation_v1(
            title="Central bank publishes routine meeting minutes",
            context={"market": "crypto", "symbol": "BTCUSDT", "venue": "gateio"},
            categories=("monetary_policy",),
            directional_bias="mixed_or_unknown",
            impact=0.5,
            confidence=0.4,
            freshness="fresh",
            caveats=("direction_not_established_by_rules",),
            reasons=("market_relevant_category",),
        )
        self.assertEqual(interpretation["potential_effect"], "mixed_or_unknown")
        self.assertEqual(interpretation["time_horizon"], "not_established")
        self.assertFalse(interpretation["scores_are_probabilities"])
        self.assertEqual(interpretation["relevance_scope"], "market_or_category_level")

    def test_other_asset_is_not_assigned_directly_to_target_symbol(self):
        interpretation = build_news_item_interpretation_v1(
            title="Ethereum upgrade announced",
            context={"market": "crypto", "symbol": "BTCUSDT", "venue": "gateio"},
            categories=("crypto_market",),
            directional_bias="positive",
            impact=0.4,
            confidence=0.5,
            freshness="fresh",
            caveats=("market_relevance_is_category_based",),
            reasons=("market_relevant_category",),
        )
        self.assertEqual(interpretation["relevance_scope"], "market_or_category_level")
        self.assertNotEqual(interpretation["relevance_scope"], "direct_symbol_or_explicit_tag")

    def test_unknown_category_discloses_insufficient_evidence(self):
        interpretation = build_news_item_interpretation_v1(
            title="An unrelated corporate announcement",
            context={"market": "crypto", "symbol": "BTCUSDT"},
            categories=(),
            directional_bias="mixed_or_unknown",
            impact=0.2,
            confidence=0.2,
            freshness="unknown",
            caveats=("publication_time_unverified",),
            reasons=(),
        )
        self.assertEqual(interpretation["category"], "unclassified")
        self.assertIn("insufficient", interpretation["localized"]["en"]["why_it_matters"].lower())
        self.assertIn("تأیید نشده", interpretation["localized"]["fa"]["relevance_scope"])


if __name__ == "__main__":
    unittest.main()
