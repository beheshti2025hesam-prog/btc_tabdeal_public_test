#!/usr/bin/env python3
"""Deterministic, read-only OHLCV parity checker for two independently captured sources.

Accepts TradingView UDF-style JSON (t/o/h/l/c/v arrays) or a JSON list of
normalized candle objects with timestamp/time/t and open/o, high/h, low/l,
close/c, volume/v fields. Uses Decimal; never rescales or repairs source data.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

FIELDS = ("open", "high", "low", "close", "volume")
ALIASES = {
    "timestamp": ("timestamp", "time", "t"),
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c"),
    "volume": ("volume", "v"),
}


class InputError(ValueError):
    pass


def _decimal(value: Any, where: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise InputError(f"{where}: expected a numeric value, got {value!r}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise InputError(f"{where}: invalid numeric value {value!r}") from None
    if not result.is_finite():
        raise InputError(f"{where}: non-finite numeric value {value!r}")
    return result


def _first(obj: dict, names: tuple[str, ...], where: str) -> Any:
    for name in names:
        if name in obj:
            return obj[name]
    raise InputError(f"{where}: missing field (accepted: {', '.join(names)})")


def load_candles(path: str) -> tuple[list[dict], dict]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"{path}: cannot read valid JSON: {exc}") from None

    metadata: dict = {}
    if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict):
        metadata = payload["metadata"]

    # UDF history payload: parallel arrays keyed t/o/h/l/c/v.
    if isinstance(payload, dict) and all(k in payload for k in ("t", "o", "h", "l", "c", "v")):
        arrays = {k: payload[k] for k in ("t", "o", "h", "l", "c", "v")}
        if not all(isinstance(v, list) for v in arrays.values()):
            raise InputError(f"{path}: UDF fields t/o/h/l/c/v must all be arrays")
        lengths = {k: len(v) for k, v in arrays.items()}
        if len(set(lengths.values())) != 1:
            raise InputError(f"{path}: UDF array lengths differ: {lengths}")
        if payload.get("s") not in (None, "ok"):
            raise InputError(f"{path}: UDF status is not ok: {payload.get('s')!r}")
        rows = [
            {"timestamp": arrays["t"][i], "open": arrays["o"][i],
             "high": arrays["h"][i], "low": arrays["l"][i],
             "close": arrays["c"][i], "volume": arrays["v"][i]}
            for i in range(len(arrays["t"]))
        ]
    elif isinstance(payload, dict) and isinstance(payload.get("candles"), list):
        rows = payload["candles"]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise InputError(f"{path}: expected UDF t/o/h/l/c/v object, a candles list, or a JSON list")

    normalized = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise InputError(f"{path}: candle[{i}] must be an object")
        stamp = _first(row, ALIASES["timestamp"], f"{path} candle[{i}] timestamp")
        # Timestamps must be integer Unix seconds; don't silently round or infer units.
        try:
            stamp_decimal = _decimal(stamp, f"{path} candle[{i}] timestamp")
        except InputError:
            raise
        if stamp_decimal != stamp_decimal.to_integral_value() or stamp_decimal <= 0:
            raise InputError(f"{path}: candle[{i}] timestamp must be a positive integer Unix timestamp in seconds")
        candle = {"timestamp": int(stamp_decimal)}
        for field in FIELDS:
            candle[field] = _decimal(_first(row, ALIASES[field], f"{path} candle[{i}] {field}"),
                                     f"{path} candle[{i}] {field}")
        normalized.append(candle)
    return normalized, metadata


def compare_candles(left: list[dict], right: list[dict],
                    abs_tolerance: Decimal = Decimal("0")) -> dict:
    if not left or not right:
        raise InputError("both sources must contain at least one candle; empty-input equality is not a valid pass")
    if not isinstance(abs_tolerance, Decimal) or not abs_tolerance.is_finite() or abs_tolerance < 0:
        raise InputError("absolute tolerance must be a finite non-negative Decimal")

    def index(rows: list[dict], label: str) -> tuple[dict[int, dict], list[int]]:
        by_time: dict[int, dict] = {}
        duplicates = []
        for row in rows:
            ts_value = _decimal(row["timestamp"], f"{label} timestamp")
            if ts_value != ts_value.to_integral_value():
                raise InputError(f"{label}: timestamp must be integer Unix seconds")
            ts = int(ts_value)
            normalized = {"timestamp": ts}
            for field in FIELDS:
                normalized[field] = _decimal(row[field], f"{label} {field} at {ts}")
            if ts in by_time:
                duplicates.append(ts)
            else:
                by_time[ts] = normalized
        return by_time, sorted(set(duplicates))

    a, dup_a = index(left, "A")
    b, dup_b = index(right, "B")
    ta, tb = set(a), set(b)
    common = sorted(ta & tb)
    missing_b = sorted(ta - tb)
    missing_a = sorted(tb - ta)
    mismatches = []
    exact_volume_double = []
    for ts in common:
        differences = {}
        for field in FIELDS:
            av, bv = a[ts][field], b[ts][field]
            delta = abs(av - bv)
            if delta > abs_tolerance:
                differences[field] = {
                    "source_a": str(av), "source_b": str(bv), "absolute_delta": str(delta)
                }
        if differences:
            item = {"timestamp": ts, "fields": differences}
            va, vb = a[ts]["volume"], b[ts]["volume"]
            if va != 0 and vb == va * 2:
                item["volume_ratio_observation"] = "source_b_is_exactly_2x_source_a"
                exact_volume_double.append(ts)
            elif vb != 0 and va == vb * 2:
                item["volume_ratio_observation"] = "source_a_is_exactly_2x_source_b"
                exact_volume_double.append(ts)
            mismatches.append(item)

    return {
        "schema_version": "1.0",
        "mode": "read_only_exact_timestamp_ohlcv_comparison",
        "source_a_count": len(left),
        "source_b_count": len(right),
        "matched_timestamp_count": len(common),
        "source_a_only_timestamps": missing_b,
        "source_b_only_timestamps": missing_a,
        "duplicate_timestamps": {"source_a": dup_a, "source_b": dup_b},
        "ohlcv_mismatch_count": len(mismatches),
        "ohlcv_mismatches": mismatches,
        "exact_2x_volume_mismatch_timestamps": exact_volume_double,
        "abs_tolerance": str(abs_tolerance),
        "pass": not (missing_a or missing_b or dup_a or dup_b or mismatches),
        "limitations": [
            "A match proves equality of supplied captures only, not the truth or completeness of either source.",
            "No timestamp shifting, gap filling, volume rescaling, or data repair is performed.",
            "Volume semantics and source-market identity must be validated outside this numeric comparator."
        ]
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-a", required=True, help="JSON file captured independently from source A")
    parser.add_argument("--source-b", required=True, help="JSON file captured independently from source B")
    parser.add_argument("--label-a", default="source_a")
    parser.add_argument("--label-b", default="source_b")
    parser.add_argument("--symbol", help="Expected market symbol; recorded, never inferred")
    parser.add_argument("--resolution", help="Expected candle resolution; recorded, never inferred")
    parser.add_argument("--abs-tolerance", default="0", help="Explicit absolute numeric tolerance (default: exact)")
    parser.add_argument("--output", help="Write JSON report to this path; stdout if omitted")
    args = parser.parse_args(argv)
    try:
        tolerance = _decimal(args.abs_tolerance, "--abs-tolerance")
        if tolerance < 0:
            raise InputError("--abs-tolerance must be non-negative")
        left, meta_a = load_candles(args.source_a)
        right, meta_b = load_candles(args.source_b)
        report = compare_candles(left, right, tolerance)
        report["sources"] = {
            "a": {"label": args.label_a, "file": args.source_a, "metadata": meta_a},
            "b": {"label": args.label_b, "file": args.source_b, "metadata": meta_b},
        }
        report["requested_market"] = {"symbol": args.symbol, "resolution": args.resolution}
        # Metadata mismatch is a blocking comparability warning, never auto-corrected.
        for key, requested in (("symbol", args.symbol), ("resolution", args.resolution)):
            if requested is not None:
                for side, meta in (("a", meta_a), ("b", meta_b)):
                    if key not in meta:
                        report["pass"] = False
                        report.setdefault("metadata_errors", []).append(
                            f"source {side} metadata is missing required {key!r}; cannot verify market/timeframe identity"
                        )
                    elif str(meta[key]) != str(requested):
                        report["pass"] = False
                        report.setdefault("metadata_errors", []).append(
                            f"source {side} metadata {key}={meta[key]!r} differs from requested {requested!r}"
                        )
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        return 0 if report["pass"] else 1
    except InputError as exc:
        print(json.dumps({"pass": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
