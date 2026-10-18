"""Read-only Wallex REST fallback for public Spot market data.

The official REST endpoint returns only a latest-trades window, not a guaranteed
complete event log. This collector is deliberately rate-limited and marks coverage
as LATEST_WINDOW_ONLY; it does not infer missing trades or sequence semantics.
The per-trade hash is a canonicalized-object fingerprint, not the exact raw HTTP
response bytes; the source response bytes are not retained by this adapter.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

BASE_URL = "https://api.wallex.ir"
SYMBOL = "BTCUSDT"
SOURCE = "wallex_spot_rest_window_v1"


def _get_json(path: str, *, timeout: float = 8.0, opener: Callable[..., Any] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        BASE_URL + path,
        headers={"Accept": "application/json", "User-Agent": "HES-Wallex-Readonly/1.0"},
        method="GET",
    )
    open_url = opener or urllib.request.urlopen
    with open_url(request, timeout=timeout) as response:
        if getattr(response, "status", 200) != 200:
            raise RuntimeError("Wallex public API returned non-200 status")
        payload = json.loads(response.read(2_000_000))
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ValueError("Wallex API response did not satisfy success contract")
    return payload


def fetch_public_snapshot(*, opener: Callable[..., Any] | None = None) -> dict[str, Any]:
    """Fetch current market metadata, depth snapshot, and recent-trade window."""
    market_response = _get_json("/v1/markets", opener=opener)
    depth_response = _get_json("/v1/depth?" + urllib.parse.urlencode({"symbol": SYMBOL}), opener=opener)
    trades_response = _get_json("/v1/trades?" + urllib.parse.urlencode({"symbol": SYMBOL}), opener=opener)

    symbols = market_response.get("result", {}).get("symbols", {})
    depth = depth_response.get("result", {})
    latest = trades_response.get("result", {}).get("latestTrades")
    if SYMBOL not in symbols:
        raise ValueError("BTCUSDT is absent from Wallex market metadata")
    if not isinstance(depth.get("ask"), list) or not isinstance(depth.get("bid"), list):
        raise ValueError("Wallex depth response has invalid shape")
    if not isinstance(latest, list):
        raise ValueError("Wallex latestTrades response has invalid shape")
    return {
        "venue": "wallex",
        "product": "spot",
        "symbol": SYMBOL,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "market": symbols[SYMBOL],
        "depth": depth,
        "latest_trades": latest,
        "trade_window_coverage": "LATEST_WINDOW_ONLY",
        "sequence_semantics": "NOT_DOCUMENTED_BY_VENUE",
    }


def normalize_rest_trade(data: dict[str, Any], *, received_at: datetime | None = None) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("symbol") != SYMBOL:
        raise ValueError("unexpected Wallex trade symbol")
    price, quantity, timestamp, is_buy = (
        data.get("price"), data.get("quantity"), data.get("timestamp"), data.get("isBuyOrder")
    )
    if price is None or quantity is None or timestamp is None or type(is_buy) is not bool:
        raise ValueError("incomplete Wallex trade payload")
    try:
        p, q = Decimal(str(price)), Decimal(str(quantity))
    except InvalidOperation as exc:
        raise ValueError("invalid trade decimal") from exc
    if not p.is_finite() or not q.is_finite() or p <= 0 or q <= 0:
        raise ValueError("price and quantity must be finite and positive")
    if not isinstance(timestamp, str):
        raise ValueError("invalid trade timestamp")
    try:
        source_dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid trade timestamp") from exc
    if source_dt.tzinfo is None or source_dt.utcoffset() is None:
        raise ValueError("trade timestamp must include timezone")
    source_updated = source_dt.astimezone(timezone.utc).isoformat()
    received = received_at or datetime.now(timezone.utc)
    if received.tzinfo is None or received.utcoffset() is None:
        raise ValueError("received_at must be timezone-aware")
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    fingerprint = hashlib.sha256(canonical).hexdigest()
    return {
        "schema": "hes_normalized_trade_observation_v1",
        "source": SOURCE,
        "venue": "wallex",
        "product": "spot",
        "symbol": SYMBOL,
        "price": str(p),
        "amount": str(q),
        "side": "BUY" if is_buy else "SELL",
        "source_updated": source_updated,
        "observed_at": received.astimezone(timezone.utc).isoformat(),
        "identity": {"kind": "canonical_trade_sha256", "value": fingerprint},
        "canonical_trade_sha256": fingerprint,
        "sequence": None,
        "sequence_semantics": "NOT_DOCUMENTED_BY_VENUE",
        "coverage": "LATEST_WINDOW_ONLY",
    }


class WallexRestWindowCollectorV1:
    """Bounded, slow-polling collector for the latest-trades REST window."""

    def __init__(
        self,
        output: str = "data/forward/wallex_btcusdt_rest_observations.jsonl",
        *,
        enabled: bool = False,
        interval_seconds: float = 15.0,
        max_runtime_seconds: float = 60.0,
        snapshot_provider: Callable[[], dict[str, Any]] = fetch_public_snapshot,
    ) -> None:
        if interval_seconds < 15:
            raise ValueError("interval_seconds must be at least 15s to reduce rate-limit risk")
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        self.output = Path(output)
        self.enabled = enabled
        self.interval_seconds = float(interval_seconds)
        self.max_runtime_seconds = float(max_runtime_seconds)
        self.snapshot_provider = snapshot_provider
        self.seen_hashes: set[str] = set()
        if self.output.exists():
            for line in self.output.read_text(encoding="utf-8").splitlines():
                try:
                    saved = json.loads(line)
                    # Read legacy field names while writing the corrected, explicit name.
                    self.seen_hashes.add(
                        saved.get("canonical_trade_sha256", saved.get("raw_payload_sha256"))
                    )
                except (ValueError, KeyError, TypeError):
                    continue
        self.records_written = 0

    def collect_once(self) -> int:
        snapshot = self.snapshot_provider()
        new_records = 0
        for trade in snapshot["latest_trades"]:
            record = normalize_rest_trade(trade)
            fingerprint = record["canonical_trade_sha256"]
            if fingerprint in self.seen_hashes:
                continue
            self.output.parent.mkdir(parents=True, exist_ok=True)
            with self.output.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self.seen_hashes.add(fingerprint)
            self.records_written += 1
            new_records += 1
        return new_records

    def run(self) -> None:
        if not self.enabled:
            raise RuntimeError("Wallex REST collector is disabled by default")
        deadline = time.monotonic() + self.max_runtime_seconds
        while time.monotonic() < deadline:
            self.collect_once()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(self.interval_seconds, remaining))
