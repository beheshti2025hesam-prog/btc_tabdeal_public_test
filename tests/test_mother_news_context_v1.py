import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.orchestration.mother_runtime_specialists_v1 import ConfirmationSpecialistV1
from web.mother_runtime_dashboard_view import _load_news_context, _news_canonical_bytes


class FakeMarket:
    def ensure_confirmation(self):
        return {"confirmation": SimpleNamespace(
            state="CONFIRMED_LONG",
            passed_count=6,
            required_count=5,
            reason_codes=(),
            checks=(),
        )}

    def batch_refs(self):
        return ("market_batch_sha256:" + "a" * 64,)


def make_snapshot(now):
    localized = {
        lang: {
            "labels": {"title": "Interpretation"},
            "what_happened": "Headline",
            "why_it_matters": "Mechanism",
            "potential_effect": "Potential effect",
            "what_to_monitor": "Price and volume",
        }
        for lang in ("fa", "en", "de", "fr")
    }
    interpretation = {
        "schema_version": "hes.news_item_interpretation.v1",
        "potential_effect": "negative",
        "localized": localized,
        "mother_use": {"news_alone_can_authorize_trade": False},
    }
    brief = {
        "schema_version": "hes.news_brief.v1",
        "veto_flags": ["HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION"],
        "findings": [{
            "item_id": "event-1",
            "title": "Exchange security incident",
            "source": "Official",
            "published_at": now.isoformat(),
            "freshness": "fresh",
            "impact": 0.9,
            "relevance": 1.0,
            "directional_bias": "negative",
            "categories": ["security"],
            "interpretation": interpretation,
        }],
    }
    brief_digest = hashlib.sha256(_news_canonical_bytes(brief)).hexdigest()
    snapshot = {
        "schema_version": "hes.news_monitor_snapshot.v1",
        "monitor": {
            "status": "OK",
            "last_poll_at": now.isoformat().replace("+00:00", "Z"),
            "source_profile_status": "partial",
        },
        "brief": brief,
        "brief_sha256": brief_digest,
    }
    snapshot["snapshot_sha256"] = hashlib.sha256(_news_canonical_bytes(snapshot)).hexdigest()
    return snapshot


class MotherNewsContextTests(unittest.TestCase):
    def test_runtime_loads_only_digest_verified_fresh_multilingual_news(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "news.json"
            path.write_bytes(_news_canonical_bytes(make_snapshot(now)))
            with patch.dict(os.environ, {"HES_NEWS_MONITOR_SNAPSHOT": str(path)}):
                context = _load_news_context(observed_at=now)
        self.assertEqual(context["status"], "READY")
        self.assertEqual(context["findings"][0]["interpretation"]["schema_version"], "hes.news_item_interpretation.v1")
        self.assertEqual(set(context["findings"][0]["interpretation"]["localized"]), {"fa", "en", "de", "fr"})
        self.assertEqual(context["veto_flags"], ["HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION"])
        self.assertFalse(context["news_alone_can_authorize_trade"])

    def test_corrupt_news_digest_fails_closed_for_news_consumption(self):
        now = datetime.now(timezone.utc)
        snapshot = make_snapshot(now)
        snapshot["brief"]["findings"][0]["title"] = "tampered"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "news.json"
            path.write_bytes(_news_canonical_bytes(snapshot))
            with patch.dict(os.environ, {"HES_NEWS_MONITOR_SNAPSHOT": str(path)}):
                context = _load_news_context(observed_at=now)
        self.assertEqual(context["status"], "BLOCKED")
        self.assertEqual(context["reason_code"], "NEWS_BRIEF_DIGEST_MISMATCH")
        self.assertEqual(context["findings"], [])

    def test_high_impact_news_is_confirmation_veto_not_trade_direction(self):
        result = ConfirmationSpecialistV1(FakeMarket()).evaluate({
            "news_context": {
                "status": "READY",
                "coverage_status": "partial",
                "snapshot_sha256": "b" * 64,
                "brief_sha256": "c" * 64,
                "veto_flags": ["HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION"],
                "findings": [{
                    "item_id": "event-1",
                    "freshness": "fresh",
                    "interpretation": {
                        "schema_version": "hes.news_item_interpretation.v1",
                        "potential_effect": "negative",
                        "localized": {lang: {} for lang in ("fa", "en", "de", "fr")},
                    },
                }],
            }
        })
        self.assertEqual(result.state, "UNCONFIRMED")
        self.assertIn("HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION", result.reason_codes)
        self.assertEqual(result.payload["direction"], "NONE")
        self.assertFalse(result.payload["news_alone_can_authorize_trade"])
        self.assertEqual(len(result.payload["news_items"]), 1)
        self.assertIn("news_snapshot_sha256:" + "b" * 64, result.evidence_refs)


if __name__ == "__main__":
    unittest.main()
