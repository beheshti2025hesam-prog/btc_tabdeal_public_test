"""Bounded live parity probe for Binance Spot native candle endpoints.

Makes two public read-only HTTPS GETs (BTCUSDT, 15m, limit 12), preserves
exact response SHA-256 values, compares only closed candles, and writes an
evidence JSON even when validation fails. No credentials or order APIs.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Running a script from scripts/ places that directory, not the repo root, on sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forward.native_ohlcv_v1 import BinanceSpotKlineSource

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
        "closed": c.closed,
    }


def main() -> int:
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "evidence_id": "BINANCE_SPOT_NATIVE_OHLCV_LIVE_PARITY_V1",
        "probe_kind": "bounded_public_read_only_live_probe",
        "request_scope": {
            "venue": "binance",
            "product": "spot",
            "symbol": "BTCUSDT",
            "interval": "15m",
            "limit_per_endpoint": 12,
            "endpoints": [
                "https://data-api.binance.vision/api/v3/uiKlines",
                "https://data-api.binance.vision/api/v3/klines",
            ],
        },
        "security": {
            "credentials_used": False,
            "private_endpoints_used": False,
            "orders_or_account_actions": False,
            "execution": "OFF",
        },
        "status": "BLOCKED",
        "failure_reasons": [],
    }
    try:
        chart = BinanceSpotKlineSource(chart_optimized=True).fetch(
            symbol="BTCUSDT", interval="15m", limit=12
        )
        standard = BinanceSpotKlineSource(chart_optimized=False).fetch(
            symbol="BTCUSDT", interval="15m", limit=12
        )
        evidence["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
        evidence["sources"] = {
            "uiKlines": {
                "endpoint_kind": chart.endpoint_kind,
                "fetched_at_ms": chart.fetched_at_ms,
                "fetched_at_utc": utc(chart.fetched_at_ms),
                "raw_response_sha256": chart.response_sha256,
                "closed_candle_count": len(chart.candles),
                "open_candles_excluded": chart.open_candles_excluded,
                "gaps": [
                    {
                        "expected_open_time_ms": g.expected_open_time_ms,
                        "next_observed_open_time_ms": g.next_observed_open_time_ms,
                        "missing_intervals": g.missing_intervals,
                    } for g in chart.gaps
                ],
                "candles": [candle_dict(c) for c in chart.candles],
            },
            "klines": {
                "endpoint_kind": standard.endpoint_kind,
                "fetched_at_ms": standard.fetched_at_ms,
                "fetched_at_utc": utc(standard.fetched_at_ms),
                "raw_response_sha256": standard.response_sha256,
                "closed_candle_count": len(standard.candles),
                "open_candles_excluded": standard.open_candles_excluded,
                "gaps": [
                    {
                        "expected_open_time_ms": g.expected_open_time_ms,
                        "next_observed_open_time_ms": g.next_observed_open_time_ms,
                        "missing_intervals": g.missing_intervals,
                    } for g in standard.gaps
                ],
                "candles": [candle_dict(c) for c in standard.candles],
            },
        }
        chart_by_open = {c.open_time_ms: c for c in chart.candles}
        standard_by_open = {c.open_time_ms: c for c in standard.candles}
        common = sorted(set(chart_by_open) & set(standard_by_open))
        mismatches = []
        for open_ms in common:
            a, b = chart_by_open[open_ms], standard_by_open[open_ms]
            for field in COMPARE_FIELDS:
                av = str(getattr(a, field))
                bv = str(getattr(b, field))
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
        if not evidence["failure_reasons"]:
            evidence["status"] = "PASS"
    except Exception as exc:
        evidence["failure_reasons"].append(
            f"SOURCE_OR_VALIDATION_ERROR:{type(exc).__name__}:{str(exc)[:300]}"
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": evidence["status"],
        "failure_reasons": evidence["failure_reasons"],
        "evidence_path": str(OUT),
        "uiKlines_sha256": evidence.get("sources", {}).get("uiKlines", {}).get("raw_response_sha256"),
        "klines_sha256": evidence.get("sources", {}).get("klines", {}).get("raw_response_sha256"),
        "common_closed_candles": evidence.get("comparison", {}).get("common_closed_candles", 0),
    }, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
