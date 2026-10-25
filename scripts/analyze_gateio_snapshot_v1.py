#!/usr/bin/env python3
"""Read-only feature snapshot from validated Gate.io closed candles; never trades."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from forward.global_market_data_reader_v1 import load_market_input


def ema(values: Sequence[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    out: list[float] = []
    current = values[0]
    for value in values:
        current = alpha * value + (1 - alpha) * current
        out.append(current)
    return out


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(delta, 0.0) for delta in deltas]
    losses = [max(-delta, 0.0) for delta in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_gain == 0 and avg_loss == 0:
        return None
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def mfi(rows: Sequence[Mapping[str, Any]], period: int = 14) -> float | None:
    if len(rows) <= period:
        return None
    typical = [
        (float(row["high"]) + float(row["low"]) + float(row["close"])) / 3
        for row in rows
    ]
    positive = 0.0
    negative = 0.0
    for i in range(len(typical) - period, len(typical)):
        flow = typical[i] * float(rows[i]["volume"])
        if typical[i] > typical[i - 1]:
            positive += flow
        elif typical[i] < typical[i - 1]:
            negative += flow
    # Missing/zero volume must not be converted into a synthetic MFI=100.
    if positive + negative <= 0:
        return None
    if negative == 0:
        return 100.0
    return 100 - 100 / (1 + positive / negative)


def snapshot(timeframe: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    closes = [float(row["close"]) for row in rows]
    ema50 = ema(closes, 50)[-1]
    ema200 = ema(closes, 200)[-1]
    recent = rows[-20:]
    prior = recent[:-1]
    prior_high = max(float(row["high"]) for row in prior)
    prior_low = min(float(row["low"]) for row in prior)
    last = rows[-1]
    typical = [
        (float(row["high"]) + float(row["low"]) + float(row["close"])) / 3
        for row in recent
    ]
    volumes = [float(row["volume"]) for row in recent]
    total_volume = sum(volumes)
    vwap = (
        sum(price * volume for price, volume in zip(typical, volumes)) / total_volume
        if total_volume > 0
        else None
    )
    true_ranges = []
    for i in range(1, len(rows)):
        high = float(rows[i]["high"])
        low = float(rows[i]["low"])
        previous_close = float(rows[i - 1]["close"])
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    atr = (
        sum(true_ranges[-14:]) / min(14, len(true_ranges))
        if true_ranges
        else None
    )
    close = closes[-1]
    rsi_value = rsi(closes)
    mfi_value = mfi(rows)
    return {
        "timeframe": timeframe,
        "bars": len(rows),
        "last_closed_open_time": int(last["open_time"]),
        "last_closed_at_utc": datetime.fromtimestamp(
            int(last["close_time"]), timezone.utc
        ).isoformat(),
        "close": close,
        "ema50": round(ema50, 4),
        "ema200": round(ema200, 4),
        "ema50_vs_ema200": "BULLISH" if ema50 > ema200 else "BEARISH" if ema50 < ema200 else "FLAT",
        "close_vs_ema50": "ABOVE" if close > ema50 else "BELOW" if close < ema50 else "AT",
        "rsi14": round(rsi_value, 2) if rsi_value is not None else None,
        "mfi14": round(mfi_value, 2) if mfi_value is not None else None,
        "atr14": round(atr, 4) if atr is not None else None,
        "vwap20": round(vwap, 4) if vwap is not None else None,
        "close_vs_vwap20": "ABOVE" if vwap is not None and close > vwap else "BELOW" if vwap is not None and close < vwap else "AT" if vwap is not None else "UNAVAILABLE",
        "prior20_high": prior_high,
        "prior20_low": prior_low,
        "close_breakout20": "UP" if close > prior_high else "DOWN" if close < prior_low else "NONE",
        "volume_last": float(last["volume"]),
        "candle_closed": last["closed"] is True,
    }


def main(root: str | Path = ROOT) -> dict[str, Any]:
    root = Path(root)
    data = load_market_input(root=root)
    result = {
        "schema": "hes_gateio_market_snapshot_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": data["source"],
        "symbol": data["symbol"],
        "timeframes": {
            timeframe: snapshot(timeframe, rows)
            for timeframe, rows in data["timeframes"].items()
        },
        "decision": "NO_TRADE",
        "decision_reason": (
            "READ_ONLY_SNAPSHOT_ONLY; this snapshot does not approve structure, "
            "confirmation, risk, or execution. No live order is permitted."
        ),
    }
    destination = root / "data/forward/gateio_market_snapshot_v1.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    import json
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(main(), indent=2))
