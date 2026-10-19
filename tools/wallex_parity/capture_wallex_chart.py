#!/usr/bin/env python3
"""Capture the official Wallex chart's UDF response and independently refetch
that exact URL; delegate all candle comparison to compare_ohlcv.py's core.
Read-only: no credentials, account endpoints, or trading actions.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from decimal import Decimal
from urllib.request import Request, urlopen
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright
from compare_ohlcv import compare_candles, load_candles

OUT = Path(os.environ.get("HES_PARITY_OUT", "artifacts/wallex-chart-parity"))
CHART_URL = "https://wallex.ir/app/trade/BTCUSDT"
FIELDS = ("o", "h", "l", "c", "v")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def closed_payload(payload: dict, now: int) -> list[dict]:
    if payload.get("s") != "ok":
        raise ValueError(f"UDF status is not ok: {payload.get('s')!r}")
    arrays = {key: payload.get(key) for key in ("t", *FIELDS)}
    if not all(isinstance(v, list) for v in arrays.values()):
        raise ValueError("UDF t/o/h/l/c/v fields must be arrays")
    lengths = {len(v) for v in arrays.values()}
    if len(lengths) != 1:
        raise ValueError(f"UDF array lengths differ: { {k: len(v) for k, v in arrays.items()} }")
    result = []
    seen = set()
    for i, ts in enumerate(arrays["t"]):
        if isinstance(ts, bool) or not isinstance(ts, int):
            raise ValueError(f"non-integer timestamp at index {i}")
        if ts in seen:
            raise ValueError(f"duplicate timestamp {ts}")
        seen.add(ts)
        if ts + 60 > now:
            continue
        row = {"timestamp": ts, "open": arrays["o"][i], "high": arrays["h"][i],
               "low": arrays["l"][i], "close": arrays["c"][i], "volume": arrays["v"][i]}
        result.append(row)
    return result


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    captured: list[tuple[str, bytes]] = []
    screenshot_error = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
        async def on_response(response):
            url = response.url
            if "/v1/udf/history?" not in url:
                return
            query = parse_qs(urlparse(url).query)
            if query.get("symbol") != ["BTCUSDT"] or query.get("resolution") != ["1"]:
                return
            try:
                body = await response.body()
            except Exception:
                return
            if body:
                captured.append((url, body))
        page.on("response", lambda response: asyncio.create_task(on_response(response)))
        navigation_error = None
        try:
            await page.goto(CHART_URL, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(10000)
        except Exception as exc:
            navigation_error = f"{type(exc).__name__}: {exc}"
        try:
            await page.screenshot(path=str(OUT / "wallex-chart-BTCUSDT.png"), full_page=False, timeout=15000)
        except Exception as exc:
            screenshot_error = f"{type(exc).__name__}: {exc}"
        canvas_error = None
        try:
            canvas_count = await asyncio.wait_for(
                asyncio.gather(*[frame.locator("canvas").count() for frame in page.frames]), timeout=5
            )
            canvas_count = sum(canvas_count)
        except Exception as exc:
            canvas_count = 0
            canvas_error = f"{type(exc).__name__}: {exc}"
        browser_close_error = None
        try:
            await asyncio.wait_for(browser.close(), timeout=10)
        except Exception as exc:
            browser_close_error = f"{type(exc).__name__}: {exc}"

    if not captured:
        manifest = {
            "schema": "hes.wallex.chart_browser_parity.v1",
            "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "chart_url": CHART_URL, "navigation_error": navigation_error, "screenshot_error": screenshot_error, "canvas_error": canvas_error, "browser_close_error": browser_close_error,
            "canvas_count": canvas_count, "screenshot_sha256": (digest((OUT / "wallex-chart-BTCUSDT.png").read_bytes()) if (OUT / "wallex-chart-BTCUSDT.png").exists() else None),
            "screenshot_bytes": ((OUT / "wallex-chart-BTCUSDT.png").stat().st_size if (OUT / "wallex-chart-BTCUSDT.png").exists() else 0),
            "status": "BLOCKED_NO_CHART_UDF_RESPONSE",
            "note": "No matching public 1m BTCUSDT UDF response was observed in the browser. Screenshot retained; no parity claim.",
        }
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
        return 1

    # Retain the largest observed browser response byte-for-byte, then refetch its exact URL.
    browser_url, browser_raw = max(captured, key=lambda item: len(item[1]))
    (OUT / "browser-chart-udf.raw.json").write_bytes(browser_raw)
    req = Request(browser_url, headers={"Accept": "application/json", "User-Agent": "HES-Trade-Agent-readonly/1"})
    try:
        with urlopen(req, timeout=20) as response:
            direct_raw = response.read()
            direct_status = response.status
            direct_date = response.headers.get("Date")
        (OUT / "direct-api.raw.json").write_bytes(direct_raw)
    except Exception as exc:
        manifest = {
            "schema": "hes.wallex.chart_browser_parity.v1",
            "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "chart_url": CHART_URL,
            "navigation_error": navigation_error, "canvas_error": canvas_error, "browser_close_error": browser_close_error,
            "canvas_count": canvas_count,
            "browser_history_request_url": browser_url,
            "browser_raw_sha256": digest(browser_raw),
            "browser_raw_bytes": len(browser_raw),
            "screenshot_error": screenshot_error, "screenshot_sha256": (digest((OUT / "wallex-chart-BTCUSDT.png").read_bytes()) if (OUT / "wallex-chart-BTCUSDT.png").exists() else None),
            "status": "BLOCKED_DIRECT_API_REFETCH_FAILED",
            "error": f"{type(exc).__name__}: {exc}",
            "note": "Browser response retained; direct refetch failed, so parity is not claimed."
        }
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
        return 1

    try:
        now = int(time.time())
        browser_rows = closed_payload(json.loads(browser_raw.decode("utf-8")), now)
        direct_rows = closed_payload(json.loads(direct_raw.decode("utf-8")), now)
        browser_closed_path = OUT / "browser-chart-closed.json"
        direct_closed_path = OUT / "direct-api-closed.json"
        browser_closed_path.write_text(json.dumps(browser_rows, separators=(",", ":")) + "\n", encoding="utf-8")
        direct_closed_path.write_text(json.dumps(direct_rows, separators=(",", ":")) + "\n", encoding="utf-8")
        normalized_a, _ = load_candles(str(browser_closed_path))
        normalized_b, _ = load_candles(str(direct_closed_path))
        comparison = compare_candles(normalized_a, normalized_b, abs_tolerance=Decimal("0"))
        comparison["source_a_label"] = "official_wallex_chart_browser_udf"
        comparison["source_b_label"] = "direct_http_refetch_of_same_url"
        comparison["symbol"] = "BTCUSDT"
        comparison["resolution"] = "1"
        (OUT / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        manifest = {
            "schema": "hes.wallex.chart_browser_parity.v1",
            "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "chart_url": CHART_URL,
            "navigation_error": navigation_error,
            "canvas_count": canvas_count,
            "browser_history_request_url": browser_url,
            "browser_raw_sha256": digest(browser_raw),
            "browser_raw_bytes": len(browser_raw),
            "direct_api_status": direct_status,
            "direct_api_date_header": direct_date,
            "direct_raw_sha256": digest(direct_raw),
            "direct_raw_bytes": len(direct_raw),
            "screenshot_sha256": digest((OUT / "wallex-chart-BTCUSDT.png").read_bytes()),
            "status": "BLOCKED_COMPARISON_ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "note": "Raw browser and direct API responses retained; comparator did not establish parity."
        }
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
        return 1

    manifest = {
        "schema": "hes.wallex.chart_browser_parity.v1",
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "read_only": True, "no_api_key_used": True,
        "no_account_or_order_endpoint_called": True,
        "chart_url": CHART_URL, "navigation_error": navigation_error,
        "canvas_count": canvas_count, "screenshot_error": screenshot_error,
        "screenshot_captured": (OUT / "wallex-chart-BTCUSDT.png").exists(),
        "screenshot_sha256": (digest((OUT / "wallex-chart-BTCUSDT.png").read_bytes()) if (OUT / "wallex-chart-BTCUSDT.png").exists() else None),
        "screenshot_bytes": (OUT / "wallex-chart-BTCUSDT.png").stat().st_size,
        "screenshot_path": "wallex-chart-BTCUSDT.png", "browser_history_request_url": browser_url,
        "direct_api_status": direct_status, "direct_api_date_header": direct_date,
        "browser_raw_sha256": digest(browser_raw), "browser_raw_bytes": len(browser_raw),
        "direct_raw_sha256": digest(direct_raw), "direct_raw_bytes": len(direct_raw),
        "browser_closed_count": len(browser_rows), "direct_closed_count": len(direct_rows),
        "comparison_report": "comparison.json",
        "comparison_pass": (OUT / "wallex-chart-BTCUSDT.png").exists() and canvas_count > 0 and comparison["pass"] and comparison["matched_timestamp_count"] >= 3,
        "status": "PASS_CAPTURED_FEED_EQUALS_DIRECT_API" if (OUT / "wallex-chart-BTCUSDT.png").exists() and canvas_count > 0 and comparison["pass"] and comparison["matched_timestamp_count"] >= 3 else "BLOCKED_PARITY_NOT_ESTABLISHED",
        "interpretation": "The core comparator compares the chart page's observed UDF response with a separate direct request to the exact same URL. This verifies the chart datafeed path only; the chart and API may share a backend, so it does not establish independent volume semantics or pixel-level value parity.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["comparison_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
