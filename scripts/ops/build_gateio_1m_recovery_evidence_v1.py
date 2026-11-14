#!/usr/bin/env python3
"""Build durable evidence from the official PR #498 release-bound 24h soak."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_ROOT = Path(os.environ.get("HES_GLOBAL_MARKET_DATA_ROOT", "/opt/hes-trade-agent"))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.paper.strategy_v2_execution_gate import (
    EXPECTED_RECOVERY_CANDIDATE_HEAD,
    RECOVERY_CANDIDATE_1M_SERVICE,
    RECOVERY_MARKET_DATA_ROOT,
    RECOVERY_REQUIRED_SERVICES,
    RECOVERY_SCHEMA,
    _candidate_collector_manifest_error,
    _candidate_soak_wrapper_error,
    _canonical_hash,
    _file_sha256,
    verify_gateio_1m_recovery_evidence,
)


def _parse_time(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone_required")
    return result.astimezone(timezone.utc)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"jsonl_record_not_object:{line_number}")
        rows.append(value)
    return rows


def _release_provenance_and_reader(release_root: Path):
    manifest_path = release_root / "HES_RELEASE_MANIFEST_v1.json"
    sidecar_path = release_root / "HES_RELEASE_MANIFEST_v1.sha256"
    soak_script_path = release_root / "scripts/soak_gateio_feed_24h_v2.py"
    reader_path = release_root / "forward/global_market_data_reader_v1.py"
    collector_script_path = release_root / "scripts/run_global_market_data_gateio_service.py"
    collector_module_path = release_root / "forward/global_market_data_gateio_v1.py"
    if (
        release_root.is_symlink()
        or not release_root.is_dir()
        or release_root.stat().st_mode & 0o222
        or manifest_path.is_symlink()
        or sidecar_path.is_symlink()
        or soak_script_path.is_symlink()
        or reader_path.is_symlink()
        or collector_script_path.is_symlink()
        or collector_module_path.is_symlink()
        or not manifest_path.is_file()
        or not sidecar_path.is_file()
        or not soak_script_path.is_file()
        or not reader_path.is_file()
        or not collector_script_path.is_file()
        or not collector_module_path.is_file()
        or soak_script_path.stat().st_mode & 0o222
        or reader_path.stat().st_mode & 0o222
        or collector_script_path.stat().st_mode & 0o222
        or collector_module_path.stat().st_mode & 0o222
    ):
        raise ValueError("candidate_release_missing_or_writable")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    sidecar = sidecar_path.read_text(encoding="utf-8").strip().split()
    if (
        manifest.get("commit_sha") != EXPECTED_RECOVERY_CANDIDATE_HEAD
        or release_root.name != EXPECTED_RECOVERY_CANDIDATE_HEAD
        or not isinstance(manifest.get("files"), list)
        or manifest.get("file_count") != len(manifest["files"])
        or sidecar != [manifest_sha, "HES_RELEASE_MANIFEST_v1.json"]
    ):
        raise ValueError("candidate_release_manifest_provenance_mismatch")
    file_hashes = {item.get("path"): item.get("sha256") for item in manifest["files"] if isinstance(item, dict)}
    soak_sha = _file_sha256(soak_script_path)
    reader_sha = _file_sha256(reader_path)
    collector_script_sha = _file_sha256(collector_script_path)
    collector_module_sha = _file_sha256(collector_module_path)
    if file_hashes.get("scripts/soak_gateio_feed_24h_v2.py") != soak_sha:
        raise ValueError("candidate_soak_script_manifest_hash_mismatch")
    if file_hashes.get("forward/global_market_data_reader_v1.py") != reader_sha:
        raise ValueError("candidate_market_reader_manifest_hash_mismatch")
    if file_hashes.get("scripts/run_global_market_data_gateio_service.py") != collector_script_sha:
        raise ValueError("candidate_collector_script_manifest_hash_mismatch")
    if file_hashes.get("forward/global_market_data_gateio_v1.py") != collector_module_sha:
        raise ValueError("candidate_collector_module_manifest_hash_mismatch")
    spec = importlib.util.spec_from_file_location("hes_pr498_release_market_reader", reader_path)
    if spec is None or spec.loader is None:
        raise ValueError("candidate_market_reader_import_failed")
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    return {
        "code_release_id": manifest["commit_sha"],
        "release_manifest_sha256": manifest_sha,
        "soak_script_sha256": soak_sha,
        "collector_script_sha256": collector_script_sha,
        "collector_module_sha256": collector_module_sha,
    }, reader


def build_evidence(
    *,
    data_root: Path,
    release_root: Path,
    market_data_root: Path,
    soak_log: Path,
    soak_wrapper_path: Path,
    candidate_collector_manifest_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    inputs = (data_root, release_root, market_data_root, soak_log, soak_wrapper_path, candidate_collector_manifest_path, output_path)
    if any(path.is_symlink() for path in inputs):
        raise ValueError("input_or_output_symlink_rejected")
    data_root = data_root.resolve()
    release_root = release_root.resolve()
    market_data_root = market_data_root.resolve()
    soak_log = soak_log.resolve()
    soak_wrapper_path = soak_wrapper_path.resolve()
    candidate_collector_manifest_path = candidate_collector_manifest_path.resolve()
    output_path = output_path.resolve()
    expected_release = data_root / "releases" / EXPECTED_RECOVERY_CANDIDATE_HEAD
    expected_market_root = data_root / RECOVERY_MARKET_DATA_ROOT
    if release_root != expected_release:
        raise ValueError("release_root_must_be_exact_pr498_candidate")
    if market_data_root != expected_market_root or not market_data_root.is_dir():
        raise ValueError("candidate_market_data_root_must_be_exact_isolated_root")
    expected_soak_log = market_data_root / "data/forward/gateio_feed_soak_24h_pr498_candidate.jsonl"
    expected_wrapper = market_data_root / "run_candidate_soak.py"
    expected_collector_manifest = market_data_root / "candidate_collector_unit_manifest.json"
    if (
        soak_log != expected_soak_log
        or not soak_log.is_file()
        or soak_wrapper_path != expected_wrapper
        or not soak_wrapper_path.is_file()
        or candidate_collector_manifest_path != expected_collector_manifest
        or not candidate_collector_manifest_path.is_file()
    ):
        raise ValueError("candidate_soak_or_collector_runtime_artifact_missing_or_unsafe")
    artifact_dir = data_root / "data/forward/gateio_1m_recovery_24h"
    if artifact_dir.exists() or artifact_dir.is_symlink():
        raise FileExistsError("recovery_artifact_directory_already_exists")
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError("recovery_evidence_file_already_exists")

    release, reader = _release_provenance_and_reader(release_root)
    if release.get("code_release_id") != EXPECTED_RECOVERY_CANDIDATE_HEAD:
        raise ValueError("candidate_release_provenance_mismatch")
    collector_manifest = json.loads(candidate_collector_manifest_path.read_text(encoding="utf-8"))
    wrapper_text = soak_wrapper_path.read_text(encoding="utf-8")
    manifest_error = _candidate_collector_manifest_error(
        collector_manifest, market_data_root=market_data_root, release_dir=release_root
    )
    if manifest_error:
        raise ValueError(manifest_error)
    wrapper_error = _candidate_soak_wrapper_error(wrapper_text, release_dir=release_root)
    if wrapper_error:
        raise ValueError(wrapper_error)

    records = _read_jsonl(soak_log)
    samples = [row for row in records if row.get("schema") == "hes_gateio_soak_sample_v3"]
    summaries = [row for row in records if row.get("schema") == "hes_gateio_soak_summary_v3"]
    if len(summaries) != 1 or not records or records[-1] is not summaries[0]:
        raise ValueError("official_soak_summary_missing_or_duplicated")
    summary = summaries[0]
    if (
        summary.get("passed") is not True
        or summary.get("execution_enabled") is not False
        or summary.get("orders_placed") is not False
        or summary.get("code_release_id") != release["code_release_id"]
        or summary.get("release_manifest_sha256") != release["release_manifest_sha256"]
        or summary.get("soak_script_sha256") != release["soak_script_sha256"]
        or not isinstance(summary.get("services"), list)
        or set(summary.get("services", [])) != RECOVERY_REQUIRED_SERVICES
        or summary.get("samples") != len(samples)
        or len(samples) < 1400
        or int(summary.get("duration_seconds", 0)) < 86400
    ):
        raise ValueError("official_soak_summary_not_accepted")

    for index, sample in enumerate(samples, 1):
        services = sample.get("services")
        if not isinstance(services, dict) or set(services) != RECOVERY_REQUIRED_SERVICES or any(value != "active" for value in services.values()):
            raise ValueError(f"candidate_soak_service_state_invalid:{index}")
    started_at = _parse_time(samples[0]["observed_at"])
    finished_at = _parse_time(summary["finished_at"])
    first_close = int(samples[0]["timeframes"]["1m"]["last_close_time"])
    last_close = int(samples[-1]["timeframes"]["1m"]["last_close_time"])
    new_closed_candles = (last_close - first_close) // 60
    max_age = max(float(row["timeframes"]["1m"]["age_seconds"]) for row in samples)
    if new_closed_candles < 1400 or max_age > 120:
        raise ValueError("official_soak_1m_coverage_or_freshness_failed")

    candle_rows = reader.read_closed_candles(
        "1m", root=market_data_root, now=int(finished_at.timestamp()), min_bars=200
    )
    if not candle_rows or int(candle_rows[-1]["close_time"]) != last_close:
        raise ValueError("final_canonical_1m_snapshot_does_not_match_soak")

    journal = subprocess.run(
        [
            "journalctl", "-u", RECOVERY_CANDIDATE_1M_SERVICE,
            f"--since=@{max(0, int(started_at.timestamp()) - 300)}",
            f"--until=@{int(finished_at.timestamp())}",
            "--no-pager", "-o", "short-iso",
        ],
        capture_output=True, text=True, timeout=180,
    )
    if journal.returncode != 0 or not journal.stdout.strip():
        raise RuntimeError("one_minute_collector_journal_unavailable:" + journal.stderr[-500:])

    artifact_dir.mkdir(parents=True, mode=0o700)
    sample_path = artifact_dir / "soak.jsonl"
    candle_path = artifact_dir / "candles_1m.jsonl"
    collector_path = artifact_dir / "collector_1m.log"
    wrapper_artifact_path = artifact_dir / "soak_wrapper.py"
    collector_manifest_artifact_path = artifact_dir / "candidate_collector_manifest.json"
    shutil.copyfile(soak_log, sample_path)
    shutil.copyfile(soak_wrapper_path, wrapper_artifact_path)
    shutil.copyfile(candidate_collector_manifest_path, collector_manifest_artifact_path)
    candle_path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in candle_rows),
        encoding="utf-8",
    )
    collector_path.write_text(journal.stdout, encoding="utf-8")

    artifacts = {
        "sample_ledger": {
            "path": "data/forward/gateio_1m_recovery_24h/soak.jsonl",
            "sha256": _file_sha256(sample_path),
        },
        "candle_ledger": {
            "path": "data/forward/gateio_1m_recovery_24h/candles_1m.jsonl",
            "sha256": _file_sha256(candle_path),
        },
        "collector_log": {
            "path": "data/forward/gateio_1m_recovery_24h/collector_1m.log",
            "sha256": _file_sha256(collector_path),
        },
        "soak_wrapper": {
            "path": "data/forward/gateio_1m_recovery_24h/soak_wrapper.py",
            "sha256": _file_sha256(wrapper_artifact_path),
        },
        "candidate_collector_manifest": {
            "path": "data/forward/gateio_1m_recovery_24h/candidate_collector_manifest.json",
            "sha256": _file_sha256(collector_manifest_artifact_path),
        },
    }
    final_age = finished_at.timestamp() - int(candle_rows[-1]["close_time"])
    payload = {
        "schema": RECOVERY_SCHEMA,
        "status": "PASS",
        "candidate_head": EXPECTED_RECOVERY_CANDIDATE_HEAD,
        "run_id": summary["run_id"],
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": int(summary["duration_seconds"]),
        "samples": int(summary["samples"]),
        "new_closed_candles": int(new_closed_candles),
        "max_observed_candle_age_seconds": max_age,
        "release_manifest_sha256": release["release_manifest_sha256"],
        "soak_script_sha256": release["soak_script_sha256"],
        "collector_script_sha256": release["collector_script_sha256"],
        "collector_module_sha256": release["collector_module_sha256"],
        "candidate_market_data_root": RECOVERY_MARKET_DATA_ROOT,
        "candidate_collector_service": RECOVERY_CANDIDATE_1M_SERVICE,
        "final_stats": {
            "rows": len(candle_rows),
            "last_open_time": int(candle_rows[-1]["open_time"]),
            "last_close_time": int(candle_rows[-1]["close_time"]),
            "age_seconds": final_age,
            "gaps": 0,
            "duplicates": 0,
            "sha256": artifacts["candle_ledger"]["sha256"],
        },
        "artifacts": artifacts,
    }
    payload["evidence_sha256"] = _canonical_hash(payload)

    for artifact in artifact_dir.iterdir():
        if artifact.is_file():
            os.chmod(artifact, 0o444)
    os.chmod(artifact_dir, 0o555)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".gateio-recovery-evidence.", dir=output_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o444)
        os.replace(temporary, output_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    verified = verify_gateio_1m_recovery_evidence(
        output_path, data_root=data_root, now=datetime.now(timezone.utc)
    )
    if verified.get("status") != "VERIFIED":
        try:
            output_path.chmod(0o644)
            output_path.unlink()
        except OSError:
            pass
        raise RuntimeError("recovery_evidence_self_verification_failed:" + str(verified))
    return {
        "status": verified["status"],
        "evidence_path": str(output_path),
        "evidence_sha256": verified["evidence_sha256"],
        "run_id": verified["run_id"],
        "samples": verified["samples"],
        "duration_seconds": verified["duration_seconds"],
        "new_closed_candles": verified["new_closed_candles"],
        "max_observed_candle_age_seconds": verified["max_observed_candle_age_seconds"],
        "release_manifest_sha256": verified["release_manifest_sha256"],
        "soak_script_sha256": verified["soak_script_sha256"],
        "artifact_hashes": verified["artifacts"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument(
        "--release-root",
        type=Path,
        default=DEFAULT_DATA_ROOT / "releases" / EXPECTED_RECOVERY_CANDIDATE_HEAD,
    )
    parser.add_argument("--market-data-root", type=Path, default=DEFAULT_DATA_ROOT / RECOVERY_MARKET_DATA_ROOT)
    parser.add_argument(
        "--soak-log",
        type=Path,
        default=DEFAULT_DATA_ROOT / RECOVERY_MARKET_DATA_ROOT / "data/forward/gateio_feed_soak_24h_pr498_candidate.jsonl",
    )
    parser.add_argument(
        "--soak-wrapper", type=Path,
        default=DEFAULT_DATA_ROOT / RECOVERY_MARKET_DATA_ROOT / "run_candidate_soak.py",
    )
    parser.add_argument(
        "--candidate-collector-manifest", type=Path,
        default=DEFAULT_DATA_ROOT / RECOVERY_MARKET_DATA_ROOT / "candidate_collector_unit_manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_DATA_ROOT / "data/forward/gateio_1m_recovery_24h_evidence.json",
    )
    args = parser.parse_args()
    result = build_evidence(
        data_root=args.data_root,
        release_root=args.release_root,
        market_data_root=args.market_data_root,
        soak_log=args.soak_log,
        soak_wrapper_path=args.soak_wrapper,
        candidate_collector_manifest_path=args.candidate_collector_manifest,
        output_path=args.output,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
