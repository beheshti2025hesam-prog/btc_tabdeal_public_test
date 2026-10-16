"""Bounded live read-only probes for native exchange candles.

Spot chart/standard parity is the required gate. USDⓈ-M Futures is probed
separately and is never compared to Spot; an unavailable Futures endpoint is
recorded as a product-specific limitation without erasing successful Spot
evidence. Exact response bytes are hashed by the source adapter.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forward.native_ohlcv_v1 import BinanceSpotKlineSource, BinanceUsdMPerpetualKlineSource

OUT = Path("artifacts/native_ohlcv_live_parity.json")
COMPARE_FIELDS = (
    "close_time_ms", "open", "high", "low", "close",
    "volume", "quote_volume", "trade_count",
)


def utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def candle_dict(c: Any) -> dict[str, Any]:
    return {
        "open_time_ms": c.open_time_ms,
        "close_time_ms": c.close_time_ms,
        "open": str(c.open),
        "high": str(c.high),
        "low": str(c.low),
        "close": str(c.close),
        "base_volume": str(c.volume),
        "quote_volume": str(c.quote_volume),
        "trade_count": c.trade_count,
        "taker_buy_volume": str(c.taker_buy_volume),
        "taker_buy_quote_volume": str(c.taker_buy_quote_volume),
        "closed": c.closed,
    }


def source_dict(batch: Any) -> dict[str, Any]:
    return {
        "endpoint_kind": batch.endpoint_kind,
        "product": batch.product,
        "fetched_at_ms": batch.fetched_at_ms,
        "fetched_at_utc": utc(batch.fetched_at_ms),
        "raw_response_sha256": batch.response_sha256,
        "closed_candle_count": len(batch.candles),
        "open_candles_excluded": batch.open_candles_excluded,
        "gaps": [
            {
                "expected_open_time_ms": g.expected_open_time_ms,
                "next_observed_open_time_ms": g.next_observed_open_time_ms,
                "missing_intervals": g.missing_intervals,
            } for g in batch.gaps
        ],
        "candles": [candle_dict(c) for c in batch.candles],
    }


def failure(exc: Exception) -> dict[str, str]:
    return {
        "type": type(exc).__name__,
        "message": str(exc)[:300],
    }


def main() -> int:
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "evidence_id": "BINANCE_NATIVE_OHLCV_LIVE_PARITY_V1",
        "probe_kind": "bounded_public_read_only_live_probe",
        "source_commit_sha": os.environ.get("HES_SOURCE_COMMIT_SHA"),
        "workflow_run_id": os.environ.get("HES_WORKFLOW_RUN_ID"),
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "request_scope": {
            "venue": "binance",
            "symbol": "BTCUSDT",
            "interval": "15m",
            "limit_per_endpoint": 12,
            "spot_endpoints": [
                "https://data-api.binance.vision/api/v3/uiKlines",
                "https://data-api.binance.vision/api/v3/klines",
            ],
            "usdm_futures_endpoint": "https://fapi.binance.com/fapi/v1/klines",
        },
        "security": {
            "credentials_used": False,
            "private_endpoints_used": False,
            "orders_or_account_actions": False,
            "execution": "OFF",
        },
        "sources": {},
        "spot_status": "BLOCKED",
        "usdm_futures_status": "NOT_ATTEMPTED",
        "status": "BLOCKED",
        "failure_reasons": [],
        "product_warnings": [],
    }

    chart = standard = futures = None
    try:
        chart = BinanceSpotKlineSource(chart_optimized=True).fetch(
            symbol="BTCUSDT", interval="15m", limit=12
        )
        evidence["sources"]["uiKlines"] = source_dict(chart)
    except Exception as exc:
        evidence["failure_reasons"].append(
            "UIKLINES_SOURCE_ERROR:" + type(exc).__name__ + ":" + str(exc)[:200]
        )

    try:
        standard = BinanceSpotKlineSource(chart_optimized=False).fetch(
            symbol="BTCUSDT", interval="15m", limit=12
        )
        evidence["sources"]["klines"] = source_dict(standard)
    except Exception as exc:
        evidence["failure_reasons"].append(
            "KLINES_SOURCE_ERROR:" + type(exc).__name__ + ":" + str(exc)[:200]
        )

    if chart is not None and standard is not None:
        chart_by_open = {c.open_time_ms: c for c in chart.candles}
        standard_by_open = {c.open_time_ms: c for c in standard.candles}
        common = sorted(set(chart_by_open) & set(standard_by_open))
        mismatches = []
        for open_ms in common:
            a, b = chart_by_open[open_ms], standard_by_open[open_ms]
            for field in COMPARE_FIELDS:
                av, bv = str(getattr(a, field)), str(getattr(b, field))
                if av != bv:
                    mismatches.append({
                        "open_time_ms": open_ms,
                        "open_time_utc": utc(open_ms),
                        "field": field,
                        "uiKlines": av,
                        "klines": bv,
                    })
        evidence["comparison"] = {
            "common_closed_candles": len(common),
            "common_open_times_ms": common,
            "common_open_times_utc": [utc(x) for x in common],
            "compared_fields": list(COMPARE_FIELDS),
            "mismatches": mismatches,
            "closed_candle_parity": bool(len(common) >= 8 and not mismatches),
            "threshold_min_common_closed_candles": 8,
        }
        if len(common) < 8:
            evidence["failure_reasons"].append("INSUFFICIENT_COMMON_CLOSED_CANDLES")
        if mismatches:
            evidence["failure_reasons"].append("CLOSED_CANDLE_FIELD_MISMATCH")
        if len(common) >= 8 and not mismatches:
            evidence["spot_status"] = "PASS"

    try:
        futures = BinanceUsdMPerpetualKlineSource().fetch(
            symbol="BTCUSDT", interval="15m", limit=12
        )
        evidence["sources"]["usdm_perpetual_klines"] = source_dict(futures)
        evidence["usdm_futures_status"] = (
            "PASS" if len(futures.candles) >= 8 else "BLOCKED_INSUFFICIENT_CLOSED_CANDLES"
        )
        if len(futures.candles) < 8:
            evidence["product_warnings"].append("USDM_FUTURES_INSUFFICIENT_CLOSED_CANDLES")
    except Exception as exc:
        evidence["usdm_futures_status"] = "BLOCKED_SOURCE_UNAVAILABLE"
        evidence["product_warnings"].append(
            "USDM_FUTURES_SOURCE_ERROR:" + type(exc).__name__ + ":" + str(exc)[:200
            ]
        )
        evidence["usdm_futures_error"] = failure(exc)

    if evidence["spot_status"] == "PASS":
        evidence["status"] = "PASS"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": evidence["status"],
        "spot_status": evidence["spot_status"],
        "usdm_futures_status": evidence["usdm_futures_status"],
        "failure_reasons": evidence["failure_reasons"],
        "product_warnings": evidence["product_warnings"],
        "evidence_path": str(OUT),
        "uiKlines_sha256": evidence["sources"].get("uiKlines", {}).get("raw_response_sha256"),
        "klines_sha256": evidence["sources"].get("klines", {}).get("raw_response_sha256"),
        "usdm_futures_sha256": evidence["sources"].get("usdm_perpetual_klines", {}).get("raw_response_sha256"),
        "common_closed_candles": evidence.get("comparison", {}).get("common_closed_candles", 0),
    }, sort_keys=True))
    return 0 if evidence["spot_status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
