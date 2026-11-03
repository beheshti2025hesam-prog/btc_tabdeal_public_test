"""Read-only post-publication impact attribution against persisted Gate.io candles.

This is an observational event study, not a causal model, signal generator, or trade evaluator.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from statistics import median, pstdev
from typing import Any

from forward.global_market_data_reader_v1 import MarketDataRejected, read_closed_candles

WINDOW_BARS = {"15m": 1, "1h": 4, "4h": 16, "24h": 96}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _parse_utc(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def load_event_ledger(state_dir: str | Path) -> tuple[list[dict[str, Any]], str]:
    root = Path(state_dir)
    records: list[dict[str, Any]] = []
    digests: list[str] = []
    for path in sorted(root.glob("news_events_*.jsonl")):
        raw = path.read_bytes()
        digests.append(path.name + ":" + hashlib.sha256(raw).hexdigest())
        for line_no, line in enumerate(raw.splitlines(), 1):
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"EVENT_LEDGER_INVALID:{path.name}:{line_no}") from exc
            if record.get("schema_version") != "hes.news_event_record.v1":
                raise ValueError(f"EVENT_LEDGER_SCHEMA_INVALID:{path.name}:{line_no}")
            stored_digest = record.pop("record_sha256", None)
            if not isinstance(stored_digest, str) or hashlib.sha256(_canonical(record)).hexdigest() != stored_digest:
                raise ValueError(f"EVENT_LEDGER_HASH_MISMATCH:{path.name}:{line_no}")
            record["record_sha256"] = stored_digest
            records.append(record)
    return records, hashlib.sha256(_canonical(digests)).hexdigest()


def _window_result(rows: list[dict[str, Any]], start: int, baseline: float, bars: int) -> dict[str, Any]:
    end = start + bars
    if end > len(rows):
        return {"status": "PENDING", "required_bars": bars, "available_bars": max(0, len(rows) - start)}
    segment = rows[start:end]
    closes = [float(row["close"]) for row in segment]
    highs = [float(row["high"]) for row in segment]
    lows = [float(row["low"]) for row in segment]
    volumes = [float(row["volume"]) for row in segment]
    prior_volumes = [float(row["volume"]) for row in rows[max(0, start - 20):start]]
    volume_baseline = median(prior_volumes) if prior_volumes else None
    log_returns = [math.log(closes[i] / (baseline if i == 0 else closes[i - 1])) for i in range(len(closes))]
    realized_vol = pstdev(log_returns) * math.sqrt(len(log_returns)) * 100 if len(log_returns) > 1 else abs(log_returns[0]) * 100
    return {
        "status": "MATURED",
        "bars": bars,
        "price_change_pct": round((closes[-1] / baseline - 1) * 100, 5),
        "max_favorable_excursion_pct": round((max(highs) / baseline - 1) * 100, 5),
        "max_adverse_excursion_pct": round((min(lows) / baseline - 1) * 100, 5),
        "realized_volatility_pct": round(realized_vol, 5),
        "volume_ratio_vs_pre_event_median": round((sum(volumes) / len(volumes)) / volume_baseline, 5) if volume_baseline and volume_baseline > 0 else None,
        "start_open_time": segment[0]["open_time"],
        "end_close_time": segment[-1]["close_time"],
    }


def evaluate_news_impact(
    *,
    state_dir: str | Path,
    data_root: str | Path,
    now: int | None = None,
    min_bars: int = 200,
) -> dict[str, Any]:
    """Evaluate observed price/volume response after each event cluster became knowable."""
    effective_now = int(datetime.now(timezone.utc).timestamp()) if now is None else int(now)
    records, ledger_digest = load_event_ledger(state_dir)
    candles = read_closed_candles("15m", root=data_root, now=effective_now, min_bars=min_bars)
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        cluster_id = record.get("event_cluster_id") or record.get("event_id")
        if isinstance(cluster_id, str) and cluster_id:
            groups.setdefault(cluster_id, []).append(record)

    events = []
    for cluster_id, items in sorted(groups.items()):
        observed_times = [_parse_utc(row.get("first_seen_at")) for row in items]
        published_times = [_parse_utc(row.get("published_at")) for row in items]
        observed_times = [value for value in observed_times if value is not None]
        published_times = [value for value in published_times if value is not None]
        if not observed_times:
            events.append({"event_cluster_id": cluster_id, "status": "TIME_UNVERIFIED", "record_count": len(items)})
            continue
        anchor = min(observed_times)
        anchor_ts = int(anchor.timestamp())
        first_published = min(published_times) if published_times else None
        if anchor_ts > effective_now:
            events.append({"event_cluster_id": cluster_id, "status": "FUTURE_EVENT", "first_seen_at": anchor.isoformat()})
            continue

        baseline_index = None
        for index, row in enumerate(candles):
            if int(row["close_time"]) <= anchor_ts:
                baseline_index = index
            else:
                break
        if baseline_index is None:
            events.append({"event_cluster_id": cluster_id, "status": "HISTORY_UNAVAILABLE", "first_seen_at": anchor.isoformat()})
            continue
        start = baseline_index + 1
        baseline = float(candles[baseline_index]["close"])
        windows = {name: _window_result(candles, start, baseline, bars) for name, bars in WINDOW_BARS.items()}
        source_ids = sorted({row.get("source_id") for row in items if row.get("source_id")})
        publishers = sorted({row.get("source") for row in items if row.get("source")})
        observation_delay = ((anchor - first_published).total_seconds() / 60) if first_published else None
        events.append({
            "event_cluster_id": cluster_id,
            "status": "PENDING" if any(row["status"] == "PENDING" for row in windows.values()) else "MATURED",
            "first_seen_at": anchor.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "first_published_at": first_published.isoformat(timespec="seconds").replace("+00:00", "Z") if first_published else None,
            "publication_to_first_seen_delay_minutes": round(observation_delay, 2) if observation_delay is not None else None,
            "record_count": len(items),
            "source_count": len(source_ids),
            "source_ids": source_ids,
            "publishers": publishers,
            "titles": sorted({row.get("title", "") for row in items if row.get("title")}),
            "max_news_impact_score": max((float(row.get("impact") or 0) for row in items), default=0),
            "max_news_relevance_score": max((float(row.get("relevance") or 0) for row in items), default=0),
            "baseline_close": baseline,
            "baseline_close_time": candles[baseline_index]["close_time"],
            "windows": windows,
        })

    result = {
        "schema": "hes_news_impact_attribution_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "source_reader": "global_market_data_reader_v1",
        "timeframe": "15m",
        "event_ledger_sha256": ledger_digest,
        "event_cluster_count": len(events),
        "events": events,
        "methodology": {
            "anchor": "earliest first_seen_at in the event cluster; this is when HES could first observe the item",
            "windows": {"15m": 1, "1h": 4, "4h": 16, "24h": 96},
            "metrics": ["close-to-close return", "maximum favorable/adverse excursion", "realized volatility", "volume ratio vs prior 20-bar median"],
            "limitations": ["post-publication response is observational and not causal attribution", "OHLCV does not provide spread or order-book liquidity", "windows remain PENDING until enough closed Gate.io candles exist"],
            "news_alone_can_authorize_trade": False,
        },
    }
    result["output_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result
