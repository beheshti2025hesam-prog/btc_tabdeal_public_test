#!/usr/bin/env python3
"""Fail-closed Gate.io 24h soak and immutable per-file runtime lineage audit."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

DURATION_SECONDS = 86_400
MIN_SAMPLES = 1_400
MAX_SAMPLE_GAP_SECONDS = 90
TIMEFRAME_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400}
GRACE_SECONDS = 180
REQUIRED_SERVICES = (
    "hes-global-market-data-gateio.service",
    "hes-global-market-data-gateio-1h.service",
    "hes-global-market-data-gateio-4h.service",
)
LINEAGE_MANIFEST_SHA256 = "9d9f73c7312377bb111ec64386a6a966c592fd6317ebe9c2baac40722076da83"
REQUIRED_LINEAGE_PATHS = frozenset({
    "scripts/soak_gateio_feed_24h_v2.py",
    "forward/global_market_data_reader_v1.py",
    "forward/global_market_data_gateio_v1.py",
    "scripts/run_global_market_data_gateio_service.py",
    "/etc/systemd/system/hes-global-market-data-gateio.service",
    "/etc/systemd/system/hes-global-market-data-gateio-1h.service",
    "/etc/systemd/system/hes-global-market-data-gateio-4h.service",
    "/etc/systemd/system/hes-global-market-data-gateio-soak.service",
    "/etc/systemd/system/hes-global-market-data-gateio.service.d/20-hes-security-umask.conf",
    "/etc/systemd/system/hes-global-market-data-gateio.service.d/30-hes-sandbox.conf",
    "/etc/systemd/system/hes-global-market-data-gateio-1h.service.d/20-hes-security-umask.conf",
    "/etc/systemd/system/hes-global-market-data-gateio-1h.service.d/30-hes-sandbox.conf",
    "/etc/systemd/system/hes-global-market-data-gateio-4h.service.d/20-hes-security-umask.conf",
    "/etc/systemd/system/hes-global-market-data-gateio-4h.service.d/30-hes-sandbox.conf",
    "data/forward/gateio_feed_soak_24h_v2.jsonl",
})


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed


def _resolve_manifest_path(value: str, root: Path, system_root: Path) -> Path:
    path = Path(value)
    return (system_root / str(path).lstrip("/")) if path.is_absolute() else (root / path)


def verify_lineage(manifest_path: str | Path, *, root: str | Path,
                   system_root: str | Path = "/") -> list[str]:
    errors: list[str] = []
    path = Path(manifest_path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [f"LINEAGE_MANIFEST_UNREADABLE:{type(exc).__name__}"]
    digest = hashlib.sha256(raw).hexdigest()
    if digest != LINEAGE_MANIFEST_SHA256:
        return ["LINEAGE_MANIFEST_SHA256_MISMATCH"]
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError:
        return ["LINEAGE_MANIFEST_INVALID_JSON"]
    if not isinstance(manifest, dict):
        return ["LINEAGE_MANIFEST_INVALID_SCHEMA"]
    if (manifest.get("schema") != "hes_gateio_soak_runtime_lineage_v1"
            or manifest.get("source") != "gateio_public_spot"
            or manifest.get("symbol") != "BTC_USDT"
            or manifest.get("source_commit") != "2e8d3859ef154b030e0965ad4479f3fad36ae4c0"):
        errors.append("LINEAGE_MANIFEST_IDENTITY_MISMATCH")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        return errors + ["LINEAGE_FILES_INVALID"]
    seen: set[str] = set()
    root_path = Path(root)
    system_path = Path(system_root)
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append("LINEAGE_ENTRY_INVALID")
            continue
        name, expected = entry.get("path"), entry.get("sha256")
        if not isinstance(name, str) or name in seen:
            errors.append("LINEAGE_PATH_MISSING_OR_DUPLICATE")
            continue
        seen.add(name)
        if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            errors.append(f"LINEAGE_HASH_INVALID:{name}")
            continue
        target = _resolve_manifest_path(name, root_path, system_path)
        try:
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
        except OSError:
            errors.append(f"LINEAGE_FILE_MISSING:{name}")
            continue
        if actual != expected:
            errors.append(f"LINEAGE_HASH_MISMATCH:{name}")
    missing = REQUIRED_LINEAGE_PATHS - seen
    extra = seen - REQUIRED_LINEAGE_PATHS
    if missing:
        errors.append("LINEAGE_REQUIRED_PATHS_MISSING:" + ",".join(sorted(missing)))
    if extra:
        errors.append("LINEAGE_UNEXPECTED_PATHS:" + ",".join(sorted(extra)))
    return errors


def audit_log(path: str | Path, *, root: str | Path = "/opt/hes-trade-agent",
              system_root: str | Path = "/",
              manifest_path: str | Path | None = None) -> dict:
    root_path = Path(root)
    selected_manifest = Path(manifest_path) if manifest_path else root_path / "forward/gateio_soak_runtime_lineage_v1.json"
    errors = verify_lineage(selected_manifest, root=root_path, system_root=system_root)
    log_path = Path(path)
    try:
        raw = log_path.read_bytes()
        records = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"schema": "hes_gateio_soak_audit_v2", "status": "FAILED", "passed": False,
                "errors": errors + [f"LOG_UNREADABLE:{type(exc).__name__}"], "samples": 0}
    manifest = json.loads(selected_manifest.read_text(encoding="utf-8")) if selected_manifest.is_file() and not any(x.startswith("LINEAGE_MANIFEST") or x.startswith("LINEAGE_MANIFEST_UNREADABLE") for x in errors) else {}
    expected_log = next((x.get("sha256") for x in manifest.get("files", [])
                         if x.get("path") == "data/forward/gateio_feed_soak_24h_v2.jsonl"), None)
    actual_log = hashlib.sha256(raw).hexdigest()
    if expected_log != actual_log:
        errors.append("SOAK_LOG_NOT_BOUND_TO_ACCEPTED_LINEAGE")

    known = {"hes_gateio_soak_sample_v2", "hes_gateio_soak_summary_v2"}
    samples = [r for r in records if isinstance(r, dict) and r.get("schema") == "hes_gateio_soak_sample_v2"]
    summaries = [r for r in records if isinstance(r, dict) and r.get("schema") == "hes_gateio_soak_summary_v2"]
    if any(not isinstance(r, dict) or r.get("schema") not in known for r in records):
        errors.append("UNKNOWN_RECORD_SCHEMA")
    if len(summaries) != 1:
        errors.append("SUMMARY_COUNT_INVALID")
    if len(samples) < MIN_SAMPLES:
        errors.append("SAMPLE_COUNT_BELOW_MINIMUM")
    times: list[datetime] = []
    previous_elapsed = -1
    for seq, sample in enumerate(samples, start=1):
        if sample.get("sample") != seq:
            errors.append(f"SAMPLE_SEQUENCE_GAP:{seq}")
        if sample.get("ok") is not True:
            errors.append(f"SAMPLE_NOT_OK:{seq}")
        if sample.get("source") != "gateio_public_spot" or sample.get("symbol") != "BTC_USDT":
            errors.append(f"SOURCE_IDENTITY_MISMATCH:{seq}")
        elapsed = sample.get("elapsed_seconds")
        if type(elapsed) is not int or elapsed <= previous_elapsed:
            errors.append(f"ELAPSED_TIME_NON_MONOTONIC:{seq}")
        else:
            previous_elapsed = elapsed
        try:
            times.append(_parse_time(sample["observed_at"]))
        except (KeyError, TypeError, ValueError):
            errors.append(f"INVALID_SAMPLE_TIMESTAMP:{seq}")
        tf_data = sample.get("timeframes")
        if not isinstance(tf_data, dict) or set(tf_data) != set(TIMEFRAME_SECONDS):
            errors.append(f"TIMEFRAME_SET_INVALID:{seq}")
            continue
        for tf, period in TIMEFRAME_SECONDS.items():
            entry = tf_data.get(tf)
            if not isinstance(entry, dict):
                errors.append(f"TIMEFRAME_MISSING:{seq}:{tf}")
                continue
            bars, age = entry.get("bars"), entry.get("age_seconds")
            if type(bars) is not int or bars < 200:
                errors.append(f"INSUFFICIENT_BARS:{seq}:{tf}")
            if type(age) is not int or age < -GRACE_SECONDS or age > period + GRACE_SECONDS:
                errors.append(f"STALE_OR_FUTURE_CANDLE:{seq}:{tf}")
        services = sample.get("services")
        if not isinstance(services, dict) or any(services.get(svc) != "active" for svc in REQUIRED_SERVICES):
            errors.append(f"SERVICE_NOT_ACTIVE:{seq}")
    gaps = [(times[i] - times[i - 1]).total_seconds() for i in range(1, len(times))]
    max_gap = max(gaps, default=0.0)
    if any(gap <= 0 or gap > MAX_SAMPLE_GAP_SECONDS for gap in gaps):
        errors.append("SAMPLE_GAP_INVALID")
    summary = summaries[0] if len(summaries) == 1 else None
    wall_duration = 0.0
    finished = None
    if summary is not None:
        duration = summary.get("duration_seconds")
        if summary.get("passed") is not True:
            errors.append("SUMMARY_NOT_PASSED")
        if summary.get("samples") != len(samples):
            errors.append("SUMMARY_SAMPLE_COUNT_MISMATCH")
        if type(duration) is not int or duration < DURATION_SECONDS:
            errors.append("DURATION_BELOW_MINIMUM")
        try:
            finished = _parse_time(summary["finished_at"])
            if times:
                wall_duration = (finished - times[0]).total_seconds()
                tail_gap = (finished - times[-1]).total_seconds()
                if wall_duration < DURATION_SECONDS - 2:
                    errors.append("WALL_DURATION_BELOW_MINIMUM")
                if tail_gap < 0 or tail_gap > MAX_SAMPLE_GAP_SECONDS:
                    errors.append("FINAL_SAMPLE_TO_SUMMARY_GAP_EXCEEDED")
            else:
                errors.append("NO_SAMPLES")
        except (KeyError, TypeError, ValueError):
            errors.append("INVALID_SUMMARY_TIMESTAMP")
    passed = not errors
    return {
        "schema": "hes_gateio_soak_audit_v2",
        "status": "PASS" if passed else ("IN_PROGRESS" if summary is None and not errors else "FAILED"),
        "passed": passed,
        "samples": len(samples),
        "duration_seconds": summary.get("duration_seconds") if summary else None,
        "wall_duration_seconds": round(wall_duration, 3),
        "first_sample_at": times[0].isoformat() if times else None,
        "last_sample_at": times[-1].isoformat() if times else None,
        "finished_at": finished.isoformat() if finished else None,
        "max_sample_gap_seconds": round(max_gap, 3),
        "log_sha256": actual_log,
        "lineage_manifest_sha256": hashlib.sha256(selected_manifest.read_bytes()).hexdigest() if selected_manifest.is_file() else None,
        "errors": errors,
    }


def main() -> int:
    root = Path("/opt/hes-trade-agent")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(root))
    parser.add_argument("--system-root", default="/")
    parser.add_argument("--log", default=str(root / "data/forward/gateio_feed_soak_24h_v2.jsonl"))
    parser.add_argument("--manifest", default=str(root / "forward/gateio_soak_runtime_lineage_v1.json"))
    args = parser.parse_args()
    result = audit_log(args.log, root=args.root, system_root=args.system_root, manifest_path=args.manifest)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else (2 if result["status"] == "IN_PROGRESS" else 3)


if __name__ == "__main__":
    raise SystemExit(main())
