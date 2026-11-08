#!/usr/bin/env python3
"""Small, bounded disk-growth trend state for the existing HES health monitor."""
from __future__ import annotations

from pathlib import Path
import json
import math
import os
import shutil
import time
from typing import Any, Callable

SCHEMA = "hes_capacity_trend_v1"
DEFAULT_STATE_PATH = Path("/var/lib/hes-operational-health/capacity-trend-v1.json")
SAMPLE_INTERVAL_SECONDS = 3600
MAX_SAMPLE_GAP_SECONDS = 48 * 3600
EWMA_ALPHA = 0.25
MIN_SAMPLES_FOR_FORECAST = 6
WARN_HOURS_TO_FULL = 72.0
CRITICAL_HOURS_TO_FULL = 24.0


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    with temp.open("w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def _baseline(now: float, total: int, used: int) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "sample_count": 1,
        "last_sample_at": float(now),
        "last_total_bytes": int(total),
        "last_used_bytes": int(used),
        "ewma_growth_bytes_per_second": None,
    }


def _validate_state(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError("capacity_state_schema_invalid")
    numeric = ("last_sample_at", "last_total_bytes", "last_used_bytes")
    if any(type(payload.get(key)) not in (int, float) for key in numeric):
        raise ValueError("capacity_state_field_invalid")
    if type(payload.get("sample_count")) is not int:
        raise ValueError("capacity_state_sample_count_invalid")
    if any(not math.isfinite(float(payload[key])) for key in numeric):
        raise ValueError("capacity_state_non_finite")
    ewma = payload.get("ewma_growth_bytes_per_second")
    if ewma is not None and (type(ewma) not in (int, float) or not math.isfinite(float(ewma)) or ewma < 0):
        raise ValueError("capacity_state_growth_invalid")
    if payload["sample_count"] < 1 or payload["last_total_bytes"] <= 0:
        raise ValueError("capacity_state_range_invalid")
    if not 0 <= payload["last_used_bytes"] <= payload["last_total_bytes"]:
        raise ValueError("capacity_state_usage_invalid")
    return payload


def collect_capacity_trend(
    *,
    root: Path = Path("/"),
    state_path: Path = DEFAULT_STATE_PATH,
    now: float | None = None,
    usage_provider: Callable[[Path], Any] = shutil.disk_usage,
    sample_interval_seconds: int = SAMPLE_INTERVAL_SECONDS,
    max_sample_gap_seconds: int = MAX_SAMPLE_GAP_SECONDS,
    alpha: float = EWMA_ALPHA,
    min_samples: int = MIN_SAMPLES_FOR_FORECAST,
    warn_hours: float = WARN_HOURS_TO_FULL,
    critical_hours: float = CRITICAL_HOURS_TO_FULL,
) -> dict[str, Any]:
    """Update one compact hourly sample and return a conservative time-to-full estimate."""
    if sample_interval_seconds <= 0 or max_sample_gap_seconds < sample_interval_seconds:
        return {"state": "WARN", "detail": "capacity_sampling_config_invalid", "sample_updated": False}
    if not 0.0 < alpha <= 1.0 or min_samples < 2 or critical_hours <= 0 or warn_hours <= critical_hours:
        return {"state": "WARN", "detail": "capacity_forecast_config_invalid", "sample_updated": False}
    now_s = time.time() if now is None else float(now)
    if not math.isfinite(now_s):
        return {"state": "WARN", "detail": "capacity_clock_invalid", "sample_updated": False}
    usage = usage_provider(root)
    total, used, free = int(usage.total), int(usage.used), int(usage.free)
    if total <= 0 or not 0 <= used <= total or not 0 <= free <= total:
        return {"state": "CRITICAL", "detail": "disk_metrics_invalid", "sample_updated": False}

    if not state_path.exists():
        baseline = _baseline(now_s, total, used)
        try:
            _write_state(state_path, baseline)
        except OSError as exc:
            return {"state": "WARN", "detail": f"capacity_state_write_failed:{type(exc).__name__}", "sample_updated": False}
        return {
            "state": "OK", "detail": f"insufficient_history:1/{min_samples}",
            "sample_updated": True, "sample_count": 1, "time_to_full_hours": None,
        }

    try:
        state = _validate_state(json.loads(state_path.read_text(encoding="utf-8")))
    except Exception as exc:
        return {
            "state": "WARN", "detail": f"capacity_state_invalid:{type(exc).__name__}",
            "sample_updated": False, "time_to_full_hours": None,
        }

    last_at = float(state["last_sample_at"])
    elapsed = now_s - last_at
    if elapsed < 0:
        return {"state": "WARN", "detail": "capacity_clock_moved_backwards", "sample_updated": False}

    if total != int(state["last_total_bytes"]) or elapsed > max_sample_gap_seconds:
        baseline = _baseline(now_s, total, used)
        try:
            _write_state(state_path, baseline)
        except OSError as exc:
            return {"state": "WARN", "detail": f"capacity_state_reset_failed:{type(exc).__name__}", "sample_updated": False}
        reason = "filesystem_size_changed" if total != int(state["last_total_bytes"]) else "sample_gap_reset"
        return {
            "state": "OK", "detail": f"{reason};insufficient_history:1/{min_samples}",
            "sample_updated": True, "sample_count": 1, "time_to_full_hours": None,
        }

    ewma = state.get("ewma_growth_bytes_per_second")
    sample_count = int(state["sample_count"])
    sample_updated = False
    if elapsed >= sample_interval_seconds:
        instant_rate = max(0.0, (used - int(state["last_used_bytes"])) / elapsed)
        ewma = instant_rate if ewma is None else (alpha * instant_rate) + ((1.0 - alpha) * float(ewma))
        sample_count = min(min_samples, sample_count + 1)
        state = {
            "schema": SCHEMA,
            "sample_count": sample_count,
            "last_sample_at": now_s,
            "last_total_bytes": total,
            "last_used_bytes": used,
            "ewma_growth_bytes_per_second": ewma,
        }
        try:
            _write_state(state_path, state)
        except OSError as exc:
            return {"state": "WARN", "detail": f"capacity_state_write_failed:{type(exc).__name__}", "sample_updated": False}
        sample_updated = True

    if sample_count < min_samples:
        return {
            "state": "OK", "detail": f"insufficient_history:{sample_count}/{min_samples}",
            "sample_updated": sample_updated, "sample_count": sample_count,
            "time_to_full_hours": None,
        }
    if ewma is None or float(ewma) <= 0:
        return {
            "state": "OK", "detail": "no_positive_disk_growth_observed",
            "sample_updated": sample_updated, "sample_count": sample_count,
            "growth_bytes_per_hour": 0.0, "time_to_full_hours": None,
        }

    growth_per_hour = float(ewma) * 3600.0
    hours_to_full = free / float(ewma) / 3600.0
    state_name = "CRITICAL" if hours_to_full < critical_hours else ("WARN" if hours_to_full < warn_hours else "OK")
    detail = f"growth={growth_per_hour:.0f}_bytes_per_hour;time_to_full={hours_to_full:.1f}h"
    return {
        "state": state_name, "detail": detail, "sample_updated": sample_updated,
        "sample_count": sample_count, "growth_bytes_per_hour": round(growth_per_hour, 2),
        "time_to_full_hours": round(hours_to_full, 2),
    }


def inode_free_check(
    root: Path = Path("/"),
    *,
    statvfs_provider: Callable[[Path], Any] = os.statvfs,
    warn_percent: float = 10.0,
    critical_percent: float = 5.0,
) -> tuple[str, str]:
    """Return an inode-capacity state using available-to-user inodes."""
    try:
        metrics = statvfs_provider(root)
        total = int(metrics.f_files)
        available = int(metrics.f_favail)
        if total <= 0 or not 0 <= available <= total:
            return "CRITICAL", "inode_metrics_invalid"
        free_percent = 100.0 * available / total
        state = "CRITICAL" if free_percent < critical_percent else ("WARN" if free_percent < warn_percent else "OK")
        return state, f"{free_percent:.1f}%_free;available={available};total={total}"
    except Exception as exc:
        return "CRITICAL", f"inode_probe_failed:{type(exc).__name__}"
