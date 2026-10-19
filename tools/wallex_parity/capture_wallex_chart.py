#!/usr/bin/env python3
"""Capture the official Wallex chart's public UDF history response in Chromium,
then compare closed candles with a separate direct HTTP fetch of the same request.
Read-only; no credentials, account endpoints, or trading actions.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright

OUT = Path(os.environ.get("HES_PARITY_OUT", "artifacts/wallex-chart-parity"))
CHART_URL = "https://wallex.ir/app/trade/BTCUSDT"
FIELDS = ("o", "h", "l", "c", "v")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def rows(payload: dict) -> dict[int, dict[str, Decimal]]:
    if payload.get("s") != "ok":
        raise ValueError(f"UDF status is not ok: {payload.get('s')!r}")
    arrays = {key: payload.get(key) for key in ("t", *FIELDS)}
    if not all(isinstance(v, list) for v in arrays.values()):
        raise ValueError("UDF t/o/h/l/c/v fields must be arrays")
    lengths = {len(v) for v in arrays.values()}
    if len(lengths) != 1:
        raise ValueError(f"UDF array lengths differ: { {k: len(v) for k, v in arrays.items()} }")
    result: dict[int, dict[str, Decimal]] = {}
    for i, ts in enumerate(arrays["t"]):
        if isinstance(ts, bool) or not isinstance(ts, int):
            raise ValueError(f"non-integer timestamp at index {i}")
        if ts in result:
            raise ValueError(f"duplicate timestamp {ts}")
        result[ts] = {field: Decimal(str(arrays[field][i])) for field in FIELDS}
    return result


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    captured: list[tuple[str, bytes]] = []
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
            await page.goto(CHART_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(15000)
        except Exception as exc:
            navigation_error = f"{type(exc).__name__}: {exc}"
        await page.screenshot(path=str(OUT / "wallex-chart-BTCUSDT.png"), full_page=True)
        canvas_count = await page.locator("canvas").count()
        await browser.close()

    if not captured:
        manifest = {
            "schema": "hes.wallex.chart_browser_parity.v1",
            "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "chart_url": CHART_URL,
            "navigation_error": navigation_error,
            "canvas_count": canvas_count,
            "status": "BLOCKED_NO_CHART_UDF_RESPONSE",
            "note": "No matching public 1m BTCUSDT UDF response was observed in the browser. Screenshot retained; no parity claim.",
        }
        (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps(manifest, indent=2))
        return 1

    # Prefer the largest observed history window; retain the browser response bytes unchanged.
    browser_url, browser_raw = max(captured, key=lambda item: len(item[1]))
    (OUT / "browser-chart-udf.raw.json").write_bytes(browser_raw)
    req = Request(browser_url, headers={"Accept": "application/json", "User-Agent": "HES-Trade-Agent-readonly/1"})
    with urlopen(req, timeout=20) as response:
        direct_raw = response.read()
        direct_status = response.status
        direct_date = response.headers.get("Date")
    (OUT / "direct-api.raw.json").write_bytes(direct_raw)

    browser_payload = json.loads(browser_raw.decode("utf-8"))
    direct_payload = json.loads(direct_raw.decode("utf-8"))
    browser_rows, direct_rows = rows(browser_payload), rows(direct_payload)
    now = int(time.time())
    # Ignore any still-forming candle. UDF timestamps are Unix seconds at candle open.
    closed_a = {ts: val for ts, val in browser_rows.items() if ts + 60 <= now}
    closed_b = {ts: val for ts, val in direct_rows.items() if ts + 60 <= now}
    common = sorted(set(closed_a) & set(closed_b))
    mismatches = []
    for ts in common:
        fields = {
            field: {"browser_chart_datafeed": str(closed_a[ts][field]), "direct_api": str(closed_b[ts][field])}
            for field in FIELDS if closed_a[ts][field] != closed_b[ts][field]
        }
        if fields:
            mismatches.append({"timestamp": ts, "fields": fields})
    manifest = {
        "schema": "hes.wallex.chart_browser_parity.v1",
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "read_only": True,
        "no_api_key_used": True,
        "no_account_or_order_endpoint_called": True,
        "chart_url": CHART_URL,
        "navigation_error": navigation_error,
        "canvas_count": canvas_count,
        "browser_history_request_url": browser_url,
        "direct_api_status": direct_status,
        "direct_api_date_header": direct_date,
        "browser_raw_sha256": digest(browser_raw),
        "browser_raw_bytes": len(browser_raw),
        "direct_raw_sha256": digest(direct_raw),
        "direct_raw_bytes": len(direct_raw),
        "browser_candle_count": len(browser_rows),
        "direct_candle_count": len(direct_rows),
        "browser_closed_count": len(closed_a),
        "direct_closed_count": len(closed_b),
        "common_closed_timestamp_count": len(common),
        "common_closed_timestamps": common,
        "ohlcv_mismatch_count": len(mismatches),
        "ohlcv_mismatches": mismatches,
        "status": "PASS_CAPTURED_FEED_EQUALS_DIRECT_API" if len(common) >= 3 and not mismatches else "BLOCKED_PARITY_NOT_ESTABLISHED",
        "interpretation": "This compares the chart page's observed UDF datafeed response to a separate direct request for the exact same URL. It verifies the chart datafeed path, not independent volume semantics or pixel-level candle values. The chart and API may share a backend.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if len(common) >= 3 and not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
