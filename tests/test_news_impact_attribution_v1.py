from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.market_intelligence.news_impact_attribution_v1 import evaluate_news_impact


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def make_record(event_id, source_id, cluster_id, first_seen, published):
    record = {
        "schema_version": "hes.news_event_record.v1",
        "event_id": event_id,
        "event_cluster_id": cluster_id,
        "first_seen_at": first_seen,
        "published_at": published,
        "source_id": source_id,
        "source": source_id,
        "url": f"https://example.test/{event_id}",
        "feed_payload_sha256": "a" * 64,
        "raw_item_sha256": "b" * 64,
        "retrieved_at": first_seen,
        "brief_sha256": "c" * 64,
        "title": "Bitcoin security incident",
        "impact": 0.9,
        "relevance": 0.95,
        "directional_bias": "negative",
        "categories": ["security", "crypto_market"],
        "freshness": "fresh",
        "caveats": [],
    }
    record["record_sha256"] = hashlib.sha256(canonical(record)).hexdigest()
    return record


class NewsImpactAttributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.data = self.root / "market"
        candle_dir = self.data / "data" / "forward"
        candle_dir.mkdir(parents=True)
        self.base = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
        self.rows = []
        for i in range(320):
            open_time = self.base + i * 900
            close_time = open_time + 900
            opening = 10000.0 + i
            closing = opening + 0.5
            volume = 10.0 if i < 150 else 20.0
            self.rows.append({
                "schema": "hes_global_candle_v1",
                "source": "gateio_public_spot",
                "symbol": "BTC_USDT",
                "timeframe": "15m",
                "closed": True,
                "open_time": open_time,
                "close_time": close_time,
                "open": opening,
                "high": closing + 2.0,
                "low": opening - 1.0,
                "close": closing,
                "volume": volume,
                "quote_volume": volume * closing,
                "observed_at": close_time + 1,
            })
        path = candle_dir / "global_market_candles_v1.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in self.rows), encoding="utf-8")
        self.now = self.rows[-1]["close_time"] + 900

    def tearDown(self):
        self.temp.cleanup()

    def write_events(self, records, year="2026"):
        path = self.state / f"news_events_{year}.jsonl"
        path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records), encoding="utf-8")
        return path

    def test_cluster_uses_gateio_candles_and_reports_matured_windows(self):
        anchor = self.base + 150 * 900 + 450
        first_seen = datetime.fromtimestamp(anchor, timezone.utc).isoformat().replace("+00:00", "Z")
        published = datetime.fromtimestamp(anchor - 60, timezone.utc).isoformat().replace("+00:00", "Z")
        records = [
            make_record("item-a", "decrypt_news", "binance_security_incident", first_seen, published),
            make_record("item-b", "investin_news_newsdesk", "binance_security_incident", first_seen, published),
        ]
        self.write_events(records)
        report = evaluate_news_impact(state_dir=self.state, data_root=self.data, now=self.now, min_bars=200)
        self.assertEqual(report["source"], "gateio_public_spot")
        self.assertEqual(report["source_reader"], "global_market_data_reader_v1")
        self.assertEqual(report["event_cluster_count"], 1)
        event = report["events"][0]
        self.assertEqual(event["status"], "MATURED")
        self.assertEqual(event["record_count"], 2)
        self.assertEqual(event["source_count"], 2)
        self.assertEqual(event["publication_to_first_seen_delay_minutes"], 1.0)
        self.assertGreaterEqual(event["first_full_post_event_candle_open_time"], anchor)
        self.assertGreaterEqual(event["first_full_candle_delay_minutes"], 0)
        self.assertEqual(event["windows"]["24h"]["status"], "MATURED")
        self.assertGreater(event["windows"]["1h"]["price_change_pct"], 0)
        self.assertEqual(event["windows"]["1h"]["volume_ratio_vs_pre_event_median"], 2.0)
        first_full = next(row for row in self.rows if row["open_time"] >= anchor)
        expected_return = (first_full["close"] / first_full["open"] - 1) * 100
        self.assertAlmostEqual(event["windows"]["15m"]["price_change_pct"], round(expected_return, 5))
        self.assertIsNotNone(event["gap_return_excluded_from_windows_pct"])
        self.assertFalse(report["methodology"]["news_alone_can_authorize_trade"])

    def test_recent_event_remains_pending_for_unmatured_windows(self):
        anchor = self.rows[-2]["close_time"] + 60
        first_seen = datetime.fromtimestamp(anchor, timezone.utc).isoformat().replace("+00:00", "Z")
        record = make_record("item-recent", "decrypt_news", "recent_event", first_seen, first_seen)
        self.write_events([record])
        report = evaluate_news_impact(state_dir=self.state, data_root=self.data, now=self.now, min_bars=200)
        event = report["events"][0]
        self.assertEqual(event["status"], "PENDING")
        self.assertEqual(event["windows"]["24h"]["status"], "PENDING")

    def test_event_older_than_retained_gateio_window_is_not_guessed(self):
        old = datetime.fromtimestamp(self.base - 900, timezone.utc).isoformat().replace("+00:00", "Z")
        self.write_events([make_record("item-old", "decrypt_news", "old_event", old, old)])
        report = evaluate_news_impact(state_dir=self.state, data_root=self.data, now=self.now, min_bars=200)
        self.assertEqual(report["events"][0]["status"], "HISTORY_UNAVAILABLE")

    def test_corrupt_event_record_hash_is_rejected(self):
        record = make_record("item-bad", "decrypt_news", "bad_event", "2026-10-02T00:00:00Z", "2026-10-02T00:00:00Z")
        record["title"] = "tampered after hash"
        self.write_events([record])
        with self.assertRaisesRegex(ValueError, "EVENT_LEDGER_HASH_MISMATCH"):
            evaluate_news_impact(state_dir=self.state, data_root=self.data, now=self.now, min_bars=200)


if __name__ == "__main__":
    unittest.main()
