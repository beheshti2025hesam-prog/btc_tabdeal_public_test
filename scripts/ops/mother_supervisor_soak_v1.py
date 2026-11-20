#!/usr/bin/env python3
"""Read-only 24-hour acceptance soak for the supervised live Mother runtime."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path("/opt/hes-trade-agent")
EXPECTED_STAGES = (
    "data_quality", "market_structure", "signal", "confirmation",
    "risk", "decision", "evaluation",
)
EXPECTED_SUPERVISOR_AGENTS = ("market_bootstrap", *EXPECTED_STAGES)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_jsonl(path: Path, value: dict) -> None:
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _one_observation(journal_snapshot: Path) -> dict:
    from web.mother_runtime_dashboard_view import read_mother_runtime_dashboard

    journal_before = _sha256(journal_snapshot)
    started = time.monotonic()
    result = read_mother_runtime_dashboard(
        data_root=ROOT, journal_path=journal_snapshot, supervised=True
    )
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    journal_after = _sha256(journal_snapshot)

    stages = result.get("stages")
    stage_names = tuple(row.get("agent") for row in stages) if isinstance(stages, list) else ()
    stage_states = tuple(row.get("state") for row in stages) if isinstance(stages, list) else ()
    supervisor = result.get("specialist_supervisor")
    supervisor = supervisor if isinstance(supervisor, dict) else {}
    health = supervisor.get("health")
    health = health if isinstance(health, dict) else {}
    agents = health.get("agents")
    agents = agents if isinstance(agents, dict) else {}

    failures = []
    if result.get("schema") != "hes.mother_runtime_dashboard.v1":
        failures.append("MOTHER_SCHEMA_INVALID")
    if result.get("executed_count") != 7 or stage_names != EXPECTED_STAGES:
        failures.append("SEVEN_SPECIALIST_SEQUENCE_INCOMPLETE")
    if "UNKNOWN" in stage_states:
        failures.append("SPECIALIST_UNKNOWN_STATE")
    if result.get("witness", {}).get("verified") is not True:
        failures.append("MOTHER_WITNESS_NOT_VERIFIED")
    for key in ("execution_authorized", "execution_enabled", "orders_placed", "journal_write"):
        if result.get(key) is not False:
            failures.append("READ_ONLY_INVARIANT_BROKEN:" + key)
    if supervisor.get("bootstrap_status") != "SUCCEEDED":
        failures.append("MARKET_BOOTSTRAP_NOT_SUPERVISED_SUCCESS")
    if health.get("version") != "hes-specialist-supervisor-v1":
        failures.append("SUPERVISOR_VERSION_MISMATCH")
    if health.get("inflight_requests") != 0 or health.get("active_counts") != {}:
        failures.append("SUPERVISOR_WORKER_NOT_QUIESCENT")
    if set(agents) != set(EXPECTED_SUPERVISOR_AGENTS):
        failures.append("SUPERVISOR_AGENT_SET_MISMATCH")
    for name, state in agents.items():
        if state.get("consecutive_failures") != 0 or state.get("circuit") != "CLOSED":
            failures.append("SUPERVISOR_CIRCUIT_NOT_CLOSED:" + name)
    if journal_before != journal_after:
        failures.append("TRADE_JOURNAL_CHANGED")

    return {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": elapsed_ms,
        "mother_status": result.get("status"),
        "decision": result.get("decision"),
        "stage_states": list(stage_states),
        "witness_verified": result.get("witness", {}).get("verified"),
        "supervisor": supervisor,
        "journal_sha256": journal_after,
        "journal_unchanged": journal_before == journal_after,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=int, default=24 * 60 * 60)
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--max-runs", type=int, default=0, help="optional cap for controlled smoke tests")
    parser.add_argument("--journal", type=Path, default=ROOT / "data/forward/trade_journal_v2.jsonl")
    args = parser.parse_args()
    if args.duration_seconds < 1 or args.interval_seconds < 1 or args.max_runs < 0:
        parser.error("duration/interval must be positive and max-runs cannot be negative")
    if not args.journal.is_file():
        parser.error("canonical trade journal is unavailable")

    state_dir = Path(os.environ.get("STATE_DIRECTORY", "/var/tmp/hes-mother-supervisor-soak"))
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "mother-supervisor-soak.jsonl"
    summary_path = state_dir / "mother-supervisor-soak-summary.json"
    start_wall = datetime.now(timezone.utc)
    start_mono = time.monotonic()
    deadline = start_mono + args.duration_seconds
    production_journal_at_start = _sha256(args.journal)
    journal_snapshot = state_dir / "trade_journal_soak_snapshot.jsonl"
    shutil.copyfile(args.journal, journal_snapshot)
    os.chmod(journal_snapshot, 0o400)
    baseline_journal = _sha256(journal_snapshot)
    runs = 0
    failures = []
    last = None
    next_run = start_mono

    while time.monotonic() <= deadline:
        try:
            last = _one_observation(journal_snapshot)
        except BaseException as exc:
            last = {
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "failures": ["OBSERVATION_EXCEPTION:" + type(exc).__name__ + ":" + str(exc)[:180]],
            }
        runs += 1
        _append_jsonl(log_path, {"run": runs, **last})
        if last.get("failures"):
            failures.extend(last["failures"])
            break
        if args.max_runs and runs >= args.max_runs:
            break
        next_run += args.interval_seconds
        remaining = min(next_run, deadline) - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

    end_wall = datetime.now(timezone.utc)
    final_journal = _sha256(journal_snapshot)
    elapsed = time.monotonic() - start_mono
    complete = elapsed >= args.duration_seconds or bool(args.max_runs and runs >= args.max_runs)
    status = "PASS" if complete and not failures and final_journal == baseline_journal else "FAIL"
    summary = {
        "schema": "hes.mother_supervisor_readonly_soak.v1",
        "status": status,
        "started_at": start_wall.isoformat(),
        "finished_at": end_wall.isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "requested_duration_seconds": args.duration_seconds,
        "interval_seconds": args.interval_seconds,
        "runs": runs,
        "complete": complete,
        "failures": failures,
        "production_journal_sha256_at_start": production_journal_at_start,
        "soak_journal_snapshot_sha256_before": baseline_journal,
        "soak_journal_snapshot_sha256_after": final_journal,
        "soak_journal_snapshot_unchanged": baseline_journal == final_journal,
        "production_journal_used_for_soak": False,
        "last_observation": last,
        "log_path": str(log_path),
    }
    _atomic_json(summary_path, summary)
    print(json.dumps(summary, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
