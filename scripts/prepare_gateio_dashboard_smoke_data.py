#!/usr/bin/env python3
"""CI-only live Gate.io fixture writer for the persisted-reader dashboard smoke."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from core.market_intelligence.news_education_v1 import build_news_item_interpretation_v1

from forward.native_ohlcv_gateio_v1 import GateioSpotKlineSource
from forward.native_ohlcv_v1 import INTERVAL_MS, validate_native_batch

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = {
    "1m": ROOT / "data/forward/global_market_candles_1m_v1.jsonl",
    "15m": ROOT / "data/forward/global_market_candles_v1.jsonl",
    "1h": ROOT / "data/forward/global_market_candles_1h_v1.jsonl",
    "4h": ROOT / "data/forward/global_market_candles_4h_v1.jsonl",
}


def main() -> None:
    if os.environ.get("CI") != "true" or os.environ.get("HES_DASHBOARD_SMOKE_FIXTURE") != "1":
        raise SystemExit("refusing to write fixture data outside explicit CI smoke mode")
    source = GateioSpotKlineSource()
    for interval, output in OUTPUTS.items():
        batch = source.fetch(symbol="BTCUSDT", interval=interval, limit=240)
        validate_native_batch(batch)
        if len(batch.candles) < 200 or batch.gaps:
            raise RuntimeError(f"insufficient or discontinuous live Gate.io candles for {interval}")
        observed_at = datetime.now(timezone.utc).isoformat()
        seconds = INTERVAL_MS[interval] // 1000
        records = []
        for candle in batch.candles:
            open_time = candle.open_time_ms // 1000
            records.append({
                "schema": "hes_global_candle_v1",
                "source": "gateio_public_spot",
                "symbol": "BTC_USDT",
                "timeframe": interval,
                "open_time": open_time,
                "close_time": open_time + seconds,
                "open": str(candle.open),
                "high": str(candle.high),
                "low": str(candle.low),
                "close": str(candle.close),
                "volume": str(candle.volume),
                "quote_volume": str(candle.quote_volume),
                "closed": True,
                "observed_at": observed_at,
                "source_response_sha256": batch.response_sha256,
            })
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in records),
                          encoding="utf-8")
        print(json.dumps({"interval": interval, "rows": len(records),
                          "source_response_sha256": batch.response_sha256,
                          "output": str(output.relative_to(ROOT))}, sort_keys=True))

    # A genuinely empty journal is a valid first-run observation fixture.
    journal_path = ROOT / "data/forward/trade_journal_v2.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text("", encoding="utf-8")

    # Mother reads News server-side; the browser's /api/news route fixture alone
    # cannot provide this input. Build a digest-verified, four-locale snapshot.
    now = datetime.now(timezone.utc)
    item_id = "browser-smoke-news-1"
    title = "Bitcoin market update requires independent confirmation"
    categories = ["crypto_market"]
    reasons = ["market_keyword_match", "symbol_keyword_match", "market_relevant_category"]
    interpretation = build_news_item_interpretation_v1(
        title=title,
        context={"market": "crypto", "symbol": "BTCUSDT", "venue": "gateio", "timeframe": "15m"},
        categories=categories,
        directional_bias="mixed_or_unknown",
        impact=0.8,
        confidence=0.8,
        freshness="fresh",
        caveats=[],
        reasons=reasons,
    )
    brief = {
        "schema_version": "hes.news_brief.v1",
        "context": {"market": "crypto", "symbol": "BTCUSDT", "venue": "gateio", "timeframe": "15m"},
        "veto_flags": [],
        "findings": [{
            "item_id": item_id, "title": title, "source": "Official smoke fixture",
            "published_at": now.isoformat(), "freshness": "fresh", "impact": 0.8,
            "relevance": 0.95, "directional_bias": "mixed_or_unknown",
            "categories": categories, "caveats": [], "reasons": reasons,
            "confidence": 0.8, "interpretation": interpretation,
        }],
        "provenance": {
            "event_cluster_assignments": [{"item_id": item_id, "event_cluster_id": "browser-smoke-cluster-1"}],
            "high_impact_event_clusters": [{
                "event_id": "browser-smoke-cluster-1", "item_count": 1, "source_count": 1,
                "sources": ["Official smoke fixture"], "item_ids": [item_id],
            }],
        },
    }
    canonical = lambda value: json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    snapshot = {
        "schema_version": "hes.news_monitor_snapshot.v1",
        "monitor": {
            "status": "OK", "last_poll_at": now.isoformat().replace("+00:00", "Z"),
            "interval_seconds": 300, "source_profile_status": "complete",
            "source_health": [{
                "source_id": "browser-smoke-official", "source_scope": "international",
                "status": "ok", "checked_at": now.isoformat(), "item_count": 1,
                "newest_published_at": now.isoformat(),
            }],
        },
        "brief": brief,
        "brief_sha256": hashlib.sha256(canonical(brief)).hexdigest(),
    }
    snapshot["snapshot_sha256"] = hashlib.sha256(canonical(snapshot)).hexdigest()
    Path("/tmp/hes-news-monitor-browser-smoke.json").write_bytes(canonical(snapshot) + b"\n")


if __name__ == "__main__":
    main()
