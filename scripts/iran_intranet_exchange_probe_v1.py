#!/usr/bin/env python3
"""Read-only exchange reachability probe for an in-Iran network vantage.

No credentials, account endpoints, order placement, withdrawals, package installs,
or telemetry. It records HTTP/TLS/DNS observations and response hashes only.
A failed external control does NOT prove an international outage; this script
never declares a national-intranet pass automatically.
Requires Python 3.9+ standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

USER_AGENT = "HES-Iran-Intranet-Probe/1.0 (read-only)"
MAX_BODY_BYTES = 2_000_000


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def iso_epoch_seconds(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.timestamp()
    except (ValueError, OverflowError):
        return None


def first_number(row: Any, keys: tuple[str, ...] = ("price",)) -> float | None:
    try:
        value = row
        if isinstance(row, dict):
            value = next((row[k] for k in keys if k in row), None)
        elif isinstance(row, (list, tuple)) and row:
            value = row[0]
        return float(value)
    except (TypeError, ValueError, IndexError):
        return None


def summarize_payload(name: str, payload: Any, now_epoch: float) -> dict[str, Any]:
    """Small, deterministic summaries; never prints whole market payloads."""
    if name == "bitpin_markets":
        rows = payload if isinstance(payload, list) else payload.get("results", []) if isinstance(payload, dict) else []
        symbols = {r.get("symbol") for r in rows if isinstance(r, dict)}
        return {"json_type": type(payload).__name__, "market_count": len(rows),
                "has_BTC_USDT": "BTC_USDT" in symbols, "has_BTC_IRT": "BTC_IRT" in symbols}

    if name == "bitpin_trades":
        rows = payload if isinstance(payload, list) else []
        ids = [r.get("id") for r in rows if isinstance(r, dict) and r.get("id") is not None]
        times = [r.get("time") for r in rows if isinstance(r, dict) and isinstance(r.get("time"), (int, float))]
        return {"row_count": len(rows), "first_trade": rows[0] if rows and isinstance(rows[0], dict) else None,
                "id_field_present": bool(ids), "unique_ids_in_sample": len(set(ids)),
                "timestamps_descending_in_sample": all(times[i] >= times[i + 1] for i in range(len(times) - 1)),
                "latest_trade_age_s": round(now_epoch - float(times[0]), 3) if times else None}

    if name in ("bitpin_book", "wallex_depth", "nobitex_book"):
        if not isinstance(payload, dict):
            return {"json_type": type(payload).__name__}
        root = payload.get("result", payload.get("data", payload))
        if not isinstance(root, dict):
            return {"json_type": type(payload).__name__, "root_type": type(root).__name__}
        asks = root.get("asks", root.get("ask", root.get("sells", []))) or []
        bids = root.get("bids", root.get("bid", root.get("buys", []))) or []
        ask = first_number(asks[0], ("price",)) if asks else None
        bid = first_number(bids[0], ("price",)) if bids else None
        spread = ask - bid if ask is not None and bid is not None else None
        return {"ask_levels": len(asks), "bid_levels": len(bids), "best_ask": ask, "best_bid": bid,
                "spread_abs": spread, "spread_pct_of_mid": round(100 * spread / ((ask + bid) / 2), 6)
                if spread is not None and ask + bid else None}

    if name == "wallex_markets":
        root = payload.get("result", {}) if isinstance(payload, dict) else {}
        symbols = root.get("symbols", {}) if isinstance(root, dict) else {}
        btc = symbols.get("BTCUSDT", {}) if isinstance(symbols, dict) else {}
        stats = btc.get("stats", {}) if isinstance(btc, dict) else {}
        return {"market_count": len(symbols), "has_BTCUSDT": "BTCUSDT" in symbols,
                "lastPrice": stats.get("lastPrice"), "bidPrice": stats.get("bidPrice"),
                "askPrice": stats.get("askPrice"), "24h_quoteVolume": stats.get("24h_quoteVolume")}

    if name == "wallex_trades":
        root = payload.get("result", {}) if isinstance(payload, dict) else {}
        rows = root.get("latestTrades", []) if isinstance(root, dict) else []
        first = rows[0] if rows and isinstance(rows[0], dict) else None
        ts = iso_epoch_seconds(first.get("timestamp")) if first else None
        return {"row_count": len(rows), "first_trade": first,
                "trade_id_field_present": bool(first and any(k.lower() in {"id", "tradeid", "trade_id"} for k in first)),
                "latest_trade_age_s": round(now_epoch - ts, 3) if ts is not None else None}

    if name in ("wallex_candles", "nobitex_candles"):
        if not isinstance(payload, dict):
            return {"json_type": type(payload).__name__}
        timestamps = payload.get("t", [])
        latest = timestamps[-1] if timestamps else None
        return {"status_field": payload.get("s"), "bar_count": len(timestamps),
                "latest_bar_t": latest, "latest_bar_age_s": round(now_epoch - float(latest), 3) if latest is not None else None,
                "explicit_closed_flag_present": any(k.lower() in {"closed", "is_closed", "final"} for k in payload),
                "payload_keys": sorted(payload.keys())[:20]}

    if name == "nobitex_trades":
        rows = payload.get("trades", []) if isinstance(payload, dict) else []
        first = rows[0] if rows and isinstance(rows[0], dict) else None
        ts = float(first["time"]) / 1000 if first and isinstance(first.get("time"), (int, float)) else None
        return {"row_count": len(rows), "first_trade": first,
                "trade_id_field_present": bool(first and any(k.lower() in {"id", "tradeid", "trade_id"} for k in first)),
                "latest_trade_age_s": round(now_epoch - ts, 3) if ts is not None else None}

    return {"json_type": type(payload).__name__, "top_level_keys": list(payload.keys())[:20]
            if isinstance(payload, dict) else None}


def resolve_host(host: str) -> dict[str, Any]:
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ips = sorted({record[4][0] for record in records})
        return {"host": host, "resolved": bool(ips), "ips": ips}
    except Exception as exc:  # diagnostic only; the HTTPS request is the primary test
        return {"host": host, "resolved": False, "error": f"{type(exc).__name__}: {str(exc)[:180]}"}


def http_probe(name: str, endpoint_class: str, url: str, timeout_s: float) -> dict[str, Any]:
    started_utc = utc_now()
    started = time.monotonic()
    result: dict[str, Any] = {"name": name, "class": endpoint_class, "url": url, "started_utc": started_utc}
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,*/*"})
    body = b""
    headers: Any = {}
    status: int | None = None
    error: str | None = None
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = response.status
            headers = response.headers
            body = response.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        headers = exc.headers
        try:
            body = exc.read(MAX_BODY_BYTES + 1)
        except Exception:
            body = b""
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:220]}"

    truncated = len(body) > MAX_BODY_BYTES
    body_for_hash = body[:MAX_BODY_BYTES] if truncated else body
    result.update({
        "finished_utc": utc_now(),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        "http_status": status,
        "https_request_succeeded": status is not None,
        "content_type": headers.get("Content-Type") if headers else None,
        "server_date_header": headers.get("Date") if headers else None,
        "body_bytes_hashed": len(body_for_hash),
        "body_truncated": truncated,
        "body_sha256": hashlib.sha256(body_for_hash).hexdigest() if body_for_hash else None,
    })
    if error:
        result["error"] = error
    try:
        parsed = json.loads(body_for_hash.decode("utf-8")) if body_for_hash else None
        result["json_valid"] = parsed is not None
        if parsed is not None:
            result["summary"] = summarize_payload(name, parsed, time.time())
    except (UnicodeDecodeError, json.JSONDecodeError):
        result["json_valid"] = False
    return result


def build_endpoints(now_epoch: int) -> list[tuple[str, str, str]]:
    start_epoch = now_epoch - 3600
    # Bitpin's documented base host is api.bitpin.org. The candles route below is
    # deliberately marked experimental because its current public contract could
    # not be verified; its result must not be treated as native-candle approval.
    return [
        ("google_control", "control", "https://www.google.com/generate_204"),
        ("github_control", "control", "https://api.github.com/zen"),
        ("bitpin_markets", "exchange_rest", "https://api.bitpin.org/api/v1/mkt/markets/"),
        ("bitpin_trades", "exchange_rest", "https://api.bitpin.org/api/v1/mth/matches/BTC_USDT/"),
        ("bitpin_book", "exchange_rest", "https://api.bitpin.org/api/v1/mth/orderbook/BTC_USDT/"),
        ("bitpin_candles_experimental", "experimental_unverified_contract",
         "https://api.bitpin.org/api/v1/mkt/candles/?market=BTC_USDT"),
        ("wallex_markets", "exchange_rest", "https://api.wallex.ir/v1/markets"),
        ("wallex_trades", "exchange_rest", "https://api.wallex.ir/v1/trades?symbol=BTCUSDT"),
        ("wallex_depth", "exchange_rest", "https://api.wallex.ir/v1/depth?symbol=BTCUSDT"),
        ("wallex_candles", "exchange_native_candle_candidate",
         f"https://api.wallex.ir/v1/udf/history?symbol=BTCUSDT&resolution=1&from={start_epoch}&to={now_epoch}"),
        ("nobitex_book", "exchange_rest", "https://apiv2.nobitex.ir/v3/orderbook/BTCUSDT"),
        ("nobitex_trades", "exchange_rest", "https://apiv2.nobitex.ir/v2/trades/BTCUSDT"),
        ("nobitex_candles", "exchange_native_candle_candidate",
         f"https://apiv2.nobitex.ir/market/udf/history?symbol=BTCUSDT&resolution=1&from={start_epoch}&to={now_epoch}"),
    ]


def self_test() -> None:
    now = 1000.0
    bitpin = summarize_payload("bitpin_trades", [
        {"id": "a", "time": 998.0}, {"id": "b", "time": 997.0}
    ], now)
    assert bitpin["row_count"] == 2 and bitpin["unique_ids_in_sample"] == 2
    assert bitpin["timestamps_descending_in_sample"] is True
    candles = summarize_payload("wallex_candles", {"s": "ok", "t": [940], "o": [1], "c": [2]}, now)
    assert candles["bar_count"] == 1 and candles["explicit_closed_flag_present"] is False
    book = summarize_payload("bitpin_book", {"asks": [["102", "1"]], "bids": [["100", "2"]]}, now)
    assert book["spread_abs"] == 2.0
    print("SELF_TEST_OK: parsers and safety labels passed; no network calls made.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only HES exchange API reachability probe; no keys or orders.")
    parser.add_argument("--timeout", type=float, default=4.0, help="Per-request timeout in seconds (default: 4).")
    parser.add_argument("--out", default=None, help="Output JSON path (default: timestamped file in current directory).")
    parser.add_argument("--context", default=None, help="Optional non-sensitive test context, e.g. 'Iran mobile network during reported outage'.")
    parser.add_argument("--self-test", action="store_true", help="Run local parser tests only; do not access the network.")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    now_epoch = int(time.time())
    endpoints = build_endpoints(now_epoch)
    hosts = sorted({urllib.parse.urlparse(url).hostname for _, _, url in endpoints if urllib.parse.urlparse(url).hostname})
    report: dict[str, Any] = {
        "probe_version": "1.0",
        "started_utc": utc_now(),
        "context": args.context,
        "mode": "READ_ONLY_NO_CREDENTIALS_NO_ORDERS_NO_TELEMETRY",
        "vantage_note": "This report is only valid for the network/device that ran it. It cannot by itself prove a nationwide international outage or certify national-intranet access.",
        "external_controls": "Reachability samples only; failures can have causes other than an international outage.",
        "dns": [resolve_host(host) for host in hosts],
        "results": [],
        "overall_classification": "OBSERVATIONAL_ONLY_NO_AUTOMATIC_PASS",
    }
    for name, endpoint_class, url in endpoints:
        report["results"].append(http_probe(name, endpoint_class, url, max(1.0, args.timeout)))
    report["finished_utc"] = utc_now()
    report["counts"] = {
        "http_responses": sum(1 for item in report["results"] if item.get("http_status") is not None),
        "exchange_http_200": sum(1 for item in report["results"] if item.get("class") != "control"
                                 and item.get("class") != "experimental_unverified_contract"
                                 and item.get("http_status") == 200),
        "control_http_responses": sum(1 for item in report["results"] if item.get("class") == "control"
                                      and item.get("http_status") is not None),
        "experimental_endpoint_http_200": any(item.get("name") == "bitpin_candles_experimental"
                                               and item.get("http_status") == 200 for item in report["results"]),
    }
    out_path = Path(args.out) if args.out else Path(f"hes_iran_intranet_probe_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nSaved report: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
