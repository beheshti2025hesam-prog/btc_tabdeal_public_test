#!/usr/bin/env python3
"""Audit the Gate.io v2 soak log for a continuous, fully passing 24-hour run."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

DURATION_SECONDS = 24 * 60 * 60
MIN_SAMPLES = 1400
MAX_SAMPLE_GAP_SECONDS = 90
TIMEFRAME_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400}
GRACE_SECONDS = 180
REQUIRED_SERVICES = (
    "hes-global-market-data-gateio.service",
    "hes-global-market-data-gateio-1h.service",
    "hes-global-market-data-gateio-4h.service",
)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def audit_log(
    path: str | Path,
    *,
    min_samples: int = MIN_SAMPLES,
    min_duration_seconds: int = DURATION_SECONDS,
    max_gap_seconds: int = MAX_SAMPLE_GAP_SECONDS,
) -> dict:
    log_path = Path(path)
    errors: list[str] = []
    try:
        records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        return {"schema": "hes_gateio_soak_audit_v1", "status": "FAILED", "passed": False,
                "errors": [f"LOG_UNREADABLE:{type(exc).__name__}"], "samples": 0}

    samples = [r for r in records if r.get("schema") == "hes_gateio_soak_sample_v2"]
    summaries = [r for r in records if r.get("schema") == "hes_gateio_soak_summary_v2"]
    unknown = [r for r in records if r.get("schema") not in {
        "hes_gateio_soak_sample_v2", "hes_gateio_soak_summary_v2"
    }]
    if unknown:
        errors.append("UNKNOWN_RECORD_SCHEMA")
    if len(summaries) > 1:
        errors.append("MULTIPLE_SUMMARIES")
    if not samples:
        errors.append("NO_SAMPLES")

    times: list[datetime] = []
    previous_elapsed = -1
    for expected_seq, sample in enumerate(samples, start=1):
        if sample.get("sample") != expected_seq:
            errors.append(f"SAMPLE_SEQUENCE_GAP:{expected_seq}")
        if sample.get("ok") is not True:
            errors.append(f"SAMPLE_NOT_OK:{expected_seq}")
        if sample.get("source") != "gateio_public_spot" or sample.get("symbol") != "BTC_USDT":
            errors.append(f"SOURCE_IDENTITY_MISMATCH:{expected_seq}")
        elapsed = sample.get("elapsed_seconds")
        if not isinstance(elapsed, int) or elapsed < previous_elapsed:
            errors.append(f"ELAPSED_TIME_NON_MONOTONIC:{expected_seq}")
        else:
            previous_elapsed = elapsed
        try:
            times.append(_parse_time(sample["observed_at"]))
        except (KeyError, TypeError, ValueError):
            errors.append(f"INVALID_SAMPLE_TIMESTAMP:{expected_seq}")
        tf_data = sample.get("timeframes")
        if not isinstance(tf_data, dict):
            errors.append(f"TIMEFRAMES_MISSING:{expected_seq}")
        else:
            for tf, period in TIMEFRAME_SECONDS.items():
                entry = tf_data.get(tf)
                if not isinstance(entry, dict):
                    errors.append(f"TIMEFRAME_MISSING:{expected_seq}:{tf}")
                    continue
                bars = entry.get("bars")
                age = entry.get("age_seconds")
                if not isinstance(bars, int) or bars < 200:
                    errors.append(f"INSUFFICIENT_BARS:{expected_seq}:{tf}")
                if not isinstance(age, int) or age < -GRACE_SECONDS or age > period + GRACE_SECONDS:
                    errors.append(f"STALE_OR_FUTURE_CANDLE:{expected_seq}:{tf}")
        services = sample.get("services")
        if not isinstance(services, dict) or any(services.get(svc) != "active" for svc in REQUIRED_SERVICES):
            errors.append(f"SERVICE_NOT_ACTIVE:{expected_seq}")

    gaps = [(times[i] - times[i - 1]).total_seconds() for i in range(1, len(times))]
    max_gap = max(gaps, default=0.0)
    if any(gap <= 0 for gap in gaps):
        errors.append("SAMPLE_TIMESTAMPS_NOT_INCREASING")
    if max_gap > max_gap_seconds:
        errors.append(f"SAMPLE_GAP_EXCEEDED:{max_gap:.3f}")

    summary = summaries[0] if len(summaries) == 1 else None
    if summary is None:
        if errors:
            status = "FAILED"
        else:
            status = "IN_PROGRESS"
        return {
            "schema": "hes_gateio_soak_audit_v1", "status": status, "passed": False,
            "samples": len(samples), "first_sample_at": times[0].isoformat() if times else None,
            "last_sample_at": times[-1].isoformat() if times else None,
            "max_sample_gap_seconds": round(max_gap, 3), "errors": errors,
        }

    duration = summary.get("duration_seconds")
    if summary.get("passed") is not True:
        errors.append("SUMMARY_NOT_PASSED")
    if summary.get("samples") != len(samples):
        errors.append("SUMMARY_SAMPLE_COUNT_MISMATCH")
    if not isinstance(duration, int) or duration < min_duration_seconds:
        errors.append("DURATION_BELOW_MINIMUM")
    if len(samples) < min_samples:
        errors.append("SAMPLE_COUNT_BELOW_MINIMUM")
    try:
        finished = _parse_time(summary["finished_at"])
        if times:
            wall_duration = (finished - times[0]).total_seconds()
            tail_gap = (finished - times[-1]).total_seconds()
            if wall_duration < min_duration_seconds - 2:
                errors.append("WALL_DURATION_BELOW_MINIMUM")
            if tail_gap < 0 or tail_gap > max_gap_seconds:
                errors.append("FINAL_SAMPLE_TO_SUMMARY_GAP_EXCEEDED")
        else:
            wall_duration = 0.0
            errors.append("NO_SAMPLES")
    except (KeyError, TypeError, ValueError):
        finished = None
        wall_duration = 0.0
        errors.append("INVALID_SUMMARY_TIMESTAMP")

    passed = not errors
    return {
        "schema": "hes_gateio_soak_audit_v1",
        "status": "PASS" if passed else "FAILED",
        "passed": passed,
        "samples": len(samples),
        "duration_seconds": duration,
        "wall_duration_seconds": round(wall_duration, 3),
        "first_sample_at": times[0].isoformat() if times else None,
        "last_sample_at": times[-1].isoformat() if times else None,
        "finished_at": finished.isoformat() if finished else None,
        "max_sample_gap_seconds": round(max_gap, 3),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", default="/opt/hes-trade-agent/data/forward/gateio_feed_soak_24h_v2.jsonl")
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    parser.add_argument("--min-duration-seconds", type=int, default=DURATION_SECONDS)
    parser.add_argument("--max-gap-seconds", type=int, default=MAX_SAMPLE_GAP_SECONDS)
    args = parser.parse_args()
    result = audit_log(args.log, min_samples=args.min_samples,
                       min_duration_seconds=args.min_duration_seconds,
                       max_gap_seconds=args.max_gap_seconds)
    print(json.dumps(result, sort_keys=True))
    if result["status"] == "IN_PROGRESS":
        return 2
    return 0 if result["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
