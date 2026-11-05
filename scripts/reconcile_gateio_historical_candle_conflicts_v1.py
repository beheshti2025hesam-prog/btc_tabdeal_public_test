#!/usr/bin/env python3
"""Evidence-gated one-time reconciliation of six known Gate.io BTC Spot candles.

Default mode only stages a complete-history candidate and raw REST evidence.
--apply requires both affected collectors to be stopped and exact source hashes
to remain unchanged. Original files are retained byte-for-byte for rollback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

RELEASE_ROOT = Path(__file__).resolve().parents[1]
if str(RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_ROOT))
from forward.native_ohlcv_gateio_v1 import GateioSpotKlineSource


def resolve_runtime_root(release_root: Path) -> Path:
    configured = os.environ.get("HES_GLOBAL_MARKET_DATA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    if release_root.parent.name == "releases":
        return release_root.parent.parent.resolve()
    return release_root.resolve()


ROOT = RELEASE_ROOT
RUNTIME_ROOT = resolve_runtime_root(RELEASE_ROOT)
DATA = RUNTIME_ROOT / "data/forward"
ARCHIVES = RUNTIME_ROOT / "data/archives"
SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"
FIELDS = ("open", "high", "low", "close", "volume", "quote_volume")
TIMEFRAMES = {
    "1h": {"seconds": 3600, "path": "global_market_candles_1h_v1.jsonl"},
    "4h": {"seconds": 14400, "path": "global_market_candles_4h_v1.jsonl"},
}
SERVICES = {
    "1h": "hes-global-market-data-gateio-1h.service",
    "4h": "hes-global-market-data-gateio-4h.service",
}
# Old values are the byte-archived values observed in the live persisted feeds.
# New values are pinned from the 2026-11-04 90d capture, 2026-11-05 05:57Z
# REST probe, and three independent REST reads made on 2026-11-05.
APPROVED = {
    "1h": {
        1793170800: {
            "old": {"open":"80875.4","high":"81088.4","low":"80875.4","close":"81088.3","volume":"110.024764","quote_volume":"8908101.66188"},
            "new": {"open":"80875.4","high":"81088.4","low":"80875.4","close":"81088.4","volume":"110.35663800","quote_volume":"8935012.79354160"},
        },
        1793174400: {
            "old": {"open":"81088.4","high":"81820.9","low":"81088.3","close":"81477.5","volume":"487.814789","quote_volume":"39741365.1442493"},
            "new": {"open":"81088.4","high":"81820.9","low":"81088.3","close":"81477.3","volume":"487.81502600","quote_volume":"39741384.45436940"},
        },
    },
    "4h": {
        1793044800: {
            "old": {"open":"80008.6","high":"80203.9","low":"79731.6","close":"80145.9","volume":"596.265096","quote_volume":"47689368.7464576"},
            "new": {"open":"80008.6","high":"80203.9","low":"79731.6","close":"80145.9","volume":"596.26539900","quote_volume":"47689393.03066530"},
        },
        1793073600: {
            "old": {"open":"79820.8","high":"80044.9","low":"79578.7","close":"79813.7","volume":"944.103512","quote_volume":"75329025.468588"},
            "new": {"open":"79820.8","high":"80044.9","low":"79578.7","close":"79813.8","volume":"944.53875200","quote_volume":"75363763.62690000"},
        },
        1793664000: {
            "old": {"open":"76806.6","high":"77312.1","low":"76547.7","close":"76925","volume":"1451.709234","quote_volume":"111766532.8962977"},
            "new": {"open":"76806.6","high":"77312.1","low":"76547.7","close":"76924.9","volume":"1451.92289800","quote_volume":"111782968.97813130"},
        },
        1793678400: {
            "old": {"open":"76924.9","high":"77149.3","low":"76386.8","close":"76823.8","volume":"1171.452426","quote_volume":"89883524.615219"},
            "new": {"open":"76924.9","high":"77149.3","low":"76386.8","close":"76823.8","volume":"1171.45327200","quote_volume":"89883589.60815380"},
        },
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decimal_values(row: dict[str, Any]) -> dict[str, Decimal]:
    values = {}
    for field in FIELDS:
        value = Decimal(str(row[field]))
        if not value.is_finite():
            raise ValueError(f"non-finite candle field {field}")
        values[field] = value
    if min(values["open"], values["high"], values["low"], values["close"]) <= 0:
        raise ValueError("candle prices must be positive")
    if min(values["volume"], values["quote_volume"]) < 0:
        raise ValueError("candle volumes must be non-negative")
    if values["high"] < max(values["open"], values["close"], values["low"]):
        raise ValueError("candle high violates OHLC bounds")
    if values["low"] > min(values["open"], values["close"], values["high"]):
        raise ValueError("candle low violates OHLC bounds")
    return values


def numeric_values(row: dict[str, Any]) -> dict[str, str]:
    return {field: str(value) for field, value in decimal_values(row).items()}


def identity_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("schema"), row.get("source"), row.get("symbol"),
        row.get("timeframe"), row.get("open_time"), row.get("close_time"),
        row.get("closed"),
    )


def semantic_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return identity_key(row) + (tuple((field, Decimal(str(row[field]))) for field in FIELDS),)


def native_to_record(candle, timeframe: str, fetched_at_ms: int) -> dict[str, Any]:
    seconds = TIMEFRAMES[timeframe]["seconds"]
    return {
        "schema": "hes_global_candle_v1",
        "source": SOURCE,
        "symbol": SYMBOL,
        "timeframe": timeframe,
        "open_time": candle.open_time_ms // 1000,
        "close_time": (candle.close_time_ms + 1) // 1000,
        "open": str(candle.open),
        "high": str(candle.high),
        "low": str(candle.low),
        "close": str(candle.close),
        "volume": str(candle.volume),
        "quote_volume": str(candle.quote_volume),
        "closed": candle.closed is True,
        "observed_at": datetime.fromtimestamp(fetched_at_ms / 1000, timezone.utc).isoformat(),
    }


def fetch_three_snapshots(timeframe: str, raw_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    snapshots = []
    evidence = []
    for index in range(1, 4):
        captured: list[bytes] = []

        def transport(url: str, timeout: int) -> bytes:
            request = Request(
                url,
                headers={"Accept": "application/json", "User-Agent": "HES-Gateio-History-Reconciliation/1.0"},
                method="GET",
            )
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
            captured.append(body)
            return body

        source = GateioSpotKlineSource(transport=transport)
        batch = source.fetch(symbol="BTCUSDT", interval=timeframe, limit=500)
        if len(captured) != 1 or batch.gaps:
            raise ValueError(f"{timeframe} REST snapshot {index} is incomplete or gapped")
        rows = [native_to_record(candle, timeframe, batch.fetched_at_ms) for candle in batch.candles]
        if len(rows) < 200:
            raise ValueError(f"{timeframe} REST snapshot {index} has insufficient closed candles")
        snapshots.append(rows)
        raw_path = raw_dir / f"{timeframe}_probe_{index}.json"
        raw_path.write_bytes(captured[0])
        evidence.append({
            "probe": index,
            "rows": len(rows),
            "first_open_time": rows[0]["open_time"],
            "last_open_time": rows[-1]["open_time"],
            "response_sha256": sha256_bytes(captured[0]),
            "raw_path": str(raw_path),
            "gaps": len(batch.gaps),
        })
    try:
        validate_three_snapshots(snapshots)
    except ValueError as exc:
        raise ValueError(f"{timeframe} REST snapshot validation failed: {exc}") from exc
    return snapshots[0], evidence


def validate_three_snapshots(snapshots: list[list[dict[str, Any]]]) -> None:
    if len(snapshots) != 3:
        raise ValueError("exactly three independent REST snapshots are required")
    signatures = [
        {row["open_time"]: semantic_key(row) for row in snapshot}
        for snapshot in snapshots
    ]
    if signatures[0] != signatures[1] or signatures[1] != signatures[2]:
        raise ValueError("Gate.io REST semantic rows changed between the three probes")


def read_jsonl(path: Path, timeframe: str) -> list[dict[str, Any]]:
    rows = []
    seconds = TIMEFRAMES[timeframe]["seconds"]
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if (
                row.get("schema") != "hes_global_candle_v1"
                or row.get("source") != SOURCE
                or row.get("symbol") != SYMBOL
                or row.get("timeframe") != timeframe
                or row.get("closed") is not True
            ):
                raise ValueError(f"{timeframe} persisted identity/state invalid at line {line_number}")
            ts = row.get("open_time")
            if type(ts) is not int or ts < 0 or ts % seconds:
                raise ValueError(f"{timeframe} persisted timestamp invalid at line {line_number}")
            if row.get("close_time") != ts + seconds:
                raise ValueError(f"{timeframe} persisted close_time invalid at line {line_number}")
            numeric_values(row)
            rows.append(row)
    if not rows:
        raise ValueError(f"{timeframe} persisted history is empty")
    if any(a["open_time"] >= b["open_time"] for a, b in zip(rows, rows[1:])):
        raise ValueError(f"{timeframe} persisted history is unordered or duplicated")
    return rows


def reconcile_rows(timeframe: str, existing: list[dict[str, Any]], rest: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[int]]:
    approved = APPROVED[timeframe]
    old_by_ts = {row["open_time"]: row for row in existing}
    rest_by_ts = {row["open_time"]: row for row in rest}
    if len(rest_by_ts) != len(rest):
        raise ValueError(f"{timeframe} REST snapshot contains duplicate open_time")
    if len(old_by_ts) != len(existing):
        raise ValueError(f"{timeframe} persisted file contains duplicate open_time")
    for ts, pinned in approved.items():
        if ts not in old_by_ts:
            raise ValueError(f"Required pinned {timeframe} conflict candle is missing at {ts}")
        current_values = decimal_values(old_by_ts[ts])
        allowed_old = {key: Decimal(value) for key, value in pinned["old"].items()}
        allowed_new = {key: Decimal(value) for key, value in pinned["new"].items()}
        if current_values not in (allowed_old, allowed_new):
            raise ValueError(f"Persisted {timeframe} candle at {ts} matches neither pinned old nor corrected evidence")

    # Within the REST coverage window, every persisted timestamp must be present.
    first_rest, last_rest = rest[0]["open_time"], rest[-1]["open_time"]
    for ts in old_by_ts:
        if first_rest <= ts <= last_rest and ts not in rest_by_ts:
            raise ValueError(f"{timeframe} REST snapshot omitted persisted timestamp {ts}")

    merged = dict(old_by_ts)
    changes = []
    for ts, old_row in old_by_ts.items():
        current = rest_by_ts.get(ts)
        if current is None:
            continue
        if identity_key(old_row) != identity_key(current):
            raise ValueError(f"Gate.io {timeframe} candle identity mismatch at {ts}")
        if decimal_values(old_row) == decimal_values(current):
            continue
        approved_item = approved.get(ts)
        if approved_item is None:
            raise ValueError(f"Unapproved {timeframe} historical candle conflict at {ts}")
        old_values = numeric_values(old_row)
        rest_values = numeric_values(current)
        expected_old = {key: Decimal(value) for key, value in approved_item["old"].items()}
        expected_new = {key: Decimal(value) for key, value in approved_item["new"].items()}
        if decimal_values(old_row) != expected_old:
            raise ValueError(f"Persisted {timeframe} candle at {ts} no longer matches the pinned old evidence")
        if decimal_values(current) != expected_new:
            raise ValueError(f"Gate.io REST {timeframe} candle at {ts} no longer matches the pinned three-probe evidence")
        merged[ts] = current
        changes.append({
            "open_time": ts,
            "old": old_values,
            "new": rest_values,
            "reason": "three matching current Gate.io REST probes plus independent prior captures",
        })

    added = []
    for ts, row in rest_by_ts.items():
        if ts not in merged:
            merged[ts] = row
            added.append(ts)

    ordered = [merged[ts] for ts in sorted(merged)]
    seconds = TIMEFRAMES[timeframe]["seconds"]
    for previous, current in zip(ordered, ordered[1:]):
        if current["open_time"] - previous["open_time"] != seconds:
            raise ValueError(
                f"{timeframe} merged history is not contiguous: "
                f"{previous['open_time']} -> {current['open_time']}"
            )
    if len(ordered) < len(existing):
        raise AssertionError("reconciliation must never remove persisted rows")
    return ordered, changes, sorted(added)


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def stage() -> Path:
    created = datetime.now(timezone.utc)
    stage_dir = ARCHIVES / f"gateio-historical-candle-reconciliation-{created.strftime('%Y%m%dT%H%M%SZ')}"
    if stage_dir.exists():
        raise FileExistsError(stage_dir)
    original_dir = stage_dir / "original"
    candidate_dir = stage_dir / "candidate_root" / "data" / "forward"
    raw_dir = stage_dir / "raw_rest"
    for directory in (original_dir, candidate_dir, raw_dir):
        directory.mkdir(parents=True, exist_ok=False)

    manifest: dict[str, Any] = {
        "schema": "hes_gateio_historical_candle_reconciliation_v1",
        "created_at": created.isoformat(),
        "source": SOURCE,
        "symbol": SYMBOL,
        "status": "STAGED_NOT_APPLIED",
        "live_files_modified": False,
        "services_restarted": False,
        "timeframes": {},
    }

    for timeframe, spec in TIMEFRAMES.items():
        live_path = DATA / spec["path"]
        original_bytes = live_path.read_bytes()
        original_rows = read_jsonl(live_path, timeframe)
        archive_path = original_dir / spec["path"]
        archive_path.write_bytes(original_bytes)
        if sha256_file(archive_path) != sha256_bytes(original_bytes):
            raise ValueError(f"{timeframe} original archive hash verification failed")

        rest_rows, probes = fetch_three_snapshots(timeframe, raw_dir)
        candidate_rows, changes, added = reconcile_rows(timeframe, original_rows, rest_rows)
        candidate_path = candidate_dir / spec["path"]
        candidate_path.write_text(
            "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in candidate_rows),
            encoding="utf-8",
        )
        candidate_bytes = candidate_path.read_bytes()
        manifest["timeframes"][timeframe] = {
            "live_path": str(live_path),
            "original_archive": str(archive_path),
            "original_sha256": sha256_bytes(original_bytes),
            "original_bytes": len(original_bytes),
            "original_rows": len(original_rows),
            "candidate_path": str(candidate_path),
            "candidate_sha256": sha256_bytes(candidate_bytes),
            "candidate_bytes": len(candidate_bytes),
            "candidate_rows": len(candidate_rows),
            "rows_added_from_rest": added,
            "corrected_conflicts": changes,
            "rest_probes": probes,
            "rest_gaps": 0,
            "first_open_time": candidate_rows[0]["open_time"],
            "last_open_time": candidate_rows[-1]["open_time"],
            "history_rows_preserved": len(candidate_rows) >= len(original_rows),
        }

    write_json_atomic(stage_dir / "manifest.json", manifest)
    return stage_dir


def atomic_replace(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "wb") as handle, source.open("rb") as src:
            shutil.copyfileobj(src, handle)
            handle.flush()
            os.fsync(handle.fileno())
        if destination.exists():
            os.chmod(temp_name, stat.S_IMODE(destination.stat().st_mode))
        os.replace(temp_name, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def apply(stage_dir: Path) -> dict[str, Any]:
    stage_dir = stage_dir.resolve()
    if not stage_dir.is_relative_to(ARCHIVES.resolve()):
        raise ValueError("stage directory must remain under the runtime archive root")
    manifest_path = stage_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "hes_gateio_historical_candle_reconciliation_v1":
        raise ValueError("unsupported reconciliation manifest")
    if manifest.get("status") != "STAGED_NOT_APPLIED" or manifest.get("live_files_modified") is not False:
        raise ValueError("reconciliation stage is not in a clean STAGED_NOT_APPLIED state")

    for timeframe, service in SERVICES.items():
        status = subprocess.run(
            ["systemctl", "is-active", service], capture_output=True, text=True, timeout=10
        )
        if status.returncode == 0 and status.stdout.strip() in {"active", "activating", "reloading"}:
            raise RuntimeError(f"stop {service} before applying the staged candle rebase")

    replacements = []
    for timeframe, spec in TIMEFRAMES.items():
        item = manifest["timeframes"][timeframe]
        live_path = Path(item["live_path"])
        original_path = Path(item["original_archive"])
        candidate_path = Path(item["candidate_path"])
        if sha256_file(live_path) != item["original_sha256"]:
            raise RuntimeError(f"{timeframe} live file changed after staging; refusing apply")
        if sha256_file(original_path) != item["original_sha256"]:
            raise RuntimeError(f"{timeframe} archived original hash mismatch")
        if sha256_file(candidate_path) != item["candidate_sha256"]:
            raise RuntimeError(f"{timeframe} candidate hash mismatch")
        candidate_rows = read_jsonl(candidate_path, timeframe)
        if len(candidate_rows) != item["candidate_rows"]:
            raise RuntimeError(f"{timeframe} candidate row-count mismatch")
        replacements.append((timeframe, live_path, original_path, candidate_path))

    applied = []
    try:
        for timeframe, live_path, original_path, candidate_path in replacements:
            atomic_replace(candidate_path, live_path)
            applied.append((timeframe, live_path, original_path))
            if sha256_file(live_path) != manifest["timeframes"][timeframe]["candidate_sha256"]:
                raise RuntimeError(f"{timeframe} post-replacement hash mismatch")
        from forward.global_market_data_reader_v1 import read_closed_candles
        for timeframe in TIMEFRAMES:
            accepted = read_closed_candles(timeframe, root=RUNTIME_ROOT)
            if len(accepted) < 200:
                raise RuntimeError(f"{timeframe} reader rejected the applied candidate")
    except Exception:
        for _, live_path, original_path in reversed(applied):
            atomic_replace(original_path, live_path)
        raise

    manifest["status"] = "APPLIED"
    manifest["live_files_modified"] = True
    manifest["applied_at"] = datetime.now(timezone.utc).isoformat()
    for timeframe, item in manifest["timeframes"].items():
        item["applied_sha256"] = sha256_file(Path(item["live_path"]))
    write_json_atomic(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="apply an existing staged candidate; default only stages")
    parser.add_argument("--stage-dir", type=Path, help="existing stage directory required with --apply")
    args = parser.parse_args()
    if args.apply:
        if args.stage_dir is None:
            parser.error("--apply requires --stage-dir")
        result = apply(args.stage_dir)
        print(json.dumps({"status": result["status"], "stage_dir": str(args.stage_dir)}, sort_keys=True))
    else:
        result = stage()
        print(json.dumps({"status": "STAGED_NOT_APPLIED", "stage_dir": str(result)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
