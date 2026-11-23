#!/usr/bin/env python3
"""Fail-closed validator for the exact Mother supervisor 24-hour soak."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess

EXPECTED_AGENTS = {
    "market_bootstrap", "data_quality", "market_structure", "signal",
    "confirmation", "risk", "decision", "evaluation",
}
EXPECTED_SOURCE_COMMIT = "42b50cd1cda4dd3a3196b86578ca50505e6243ce"
EXPECTED_SOURCE_TREE = "f93583b7ab960fd84b4ebdac088f8966c1788345"
EXPECTED_DURATION_SECONDS = 86400
EXPECTED_INTERVAL_SECONDS = 300
MIN_RUNS = 288


def validate_summary(summary: dict, *, source_commit: str, source_tree: str, source_clean: bool) -> dict:
    errors = []
    if summary.get("schema") != "hes.mother_supervisor_readonly_soak.v1": errors.append("SUMMARY_SCHEMA_INVALID")
    if summary.get("status") != "PASS": errors.append("SOAK_STATUS_NOT_PASS")
    if summary.get("complete") is not True: errors.append("SOAK_NOT_COMPLETE")
    if summary.get("requested_duration_seconds") != EXPECTED_DURATION_SECONDS: errors.append("SOAK_DURATION_NOT_24H")
    try:
        if float(summary.get("elapsed_seconds", 0)) < EXPECTED_DURATION_SECONDS: errors.append("SOAK_ELAPSED_BELOW_24H")
    except (TypeError, ValueError): errors.append("SOAK_ELAPSED_INVALID")
    if summary.get("interval_seconds") != EXPECTED_INTERVAL_SECONDS: errors.append("SOAK_INTERVAL_INVALID")
    try:
        if int(summary.get("runs", 0)) < MIN_RUNS: errors.append("SOAK_SAMPLE_COUNT_BELOW_MINIMUM")
    except (TypeError, ValueError): errors.append("SOAK_SAMPLE_COUNT_INVALID")
    if summary.get("failures") != []: errors.append("SOAK_FAILURES_PRESENT")
    if summary.get("production_journal_used_for_soak") is not False: errors.append("PRODUCTION_JOURNAL_USED")
    if summary.get("soak_journal_snapshot_unchanged") is not True: errors.append("SOAK_SNAPSHOT_CHANGED")
    before = summary.get("soak_journal_snapshot_sha256_before")
    after = summary.get("soak_journal_snapshot_sha256_after")
    if not isinstance(before, str) or len(before) != 64 or before != after: errors.append("SOAK_SNAPSHOT_HASH_MISMATCH")
    if summary.get("production_journal_sha256_at_start") != before: errors.append("SOAK_BASELINE_COPY_MISMATCH")
    last = summary.get("last_observation") if isinstance(summary.get("last_observation"), dict) else {}
    if last.get("failures") != []: errors.append("LAST_OBSERVATION_FAILURES_PRESENT")
    if last.get("journal_unchanged") is not True: errors.append("LAST_OBSERVATION_JOURNAL_CHANGED")
    if last.get("journal_sha256") != before: errors.append("LAST_OBSERVATION_JOURNAL_HASH_MISMATCH")
    if last.get("witness_verified") is not True: errors.append("LAST_OBSERVATION_WITNESS_INVALID")
    states = last.get("stage_states")
    if not isinstance(states, list) or len(states) != 7 or "UNKNOWN" in states: errors.append("LAST_OBSERVATION_STAGE_STATE_INVALID")
    supervisor = last.get("supervisor") if isinstance(last.get("supervisor"), dict) else {}
    health = supervisor.get("health") if isinstance(supervisor.get("health"), dict) else {}
    if supervisor.get("bootstrap_status") != "SUCCEEDED": errors.append("SUPERVISOR_BOOTSTRAP_INVALID")
    if health.get("version") != "hes-specialist-supervisor-v1": errors.append("SUPERVISOR_VERSION_INVALID")
    if health.get("inflight_requests") != 0 or health.get("active_counts") != {}: errors.append("SUPERVISOR_NOT_QUIESCENT")
    if health.get("execution_authorized") is not False: errors.append("SUPERVISOR_EXECUTION_AUTHORIZED")
    if health.get("active_agents") != []: errors.append("SUPERVISOR_ACTIVE_AGENTS_PRESENT")
    agents = health.get("agents") if isinstance(health.get("agents"), dict) else {}
    if set(agents) != EXPECTED_AGENTS: errors.append("SUPERVISOR_AGENT_SET_INVALID")
    for name, state in agents.items():
        if state.get("circuit") != "CLOSED" or state.get("consecutive_failures") != 0:
            errors.append("SUPERVISOR_AGENT_NOT_HEALTHY:" + name)
    if source_commit != EXPECTED_SOURCE_COMMIT: errors.append("SOAK_SOURCE_COMMIT_MISMATCH")
    if source_tree != EXPECTED_SOURCE_TREE: errors.append("SOAK_SOURCE_TREE_MISMATCH")
    if source_clean is not True: errors.append("SOAK_SOURCE_WORKTREE_DIRTY")
    if errors:
        raise ValueError(";".join(errors))
    return {"status": "PASS", "runs": summary["runs"], "elapsed_seconds": summary["elapsed_seconds"],
            "source_commit": source_commit, "source_tree": source_tree}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    if not args.summary.is_file():
        raise SystemExit("SOAK_SUMMARY_MISSING_OR_NOT_COMPLETE")
    try:
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("SOAK_SUMMARY_UNREADABLE_OR_INVALID") from exc
    commit = subprocess.run(["git", "-C", str(args.source_root), "rev-parse", "HEAD"],
                            check=True, capture_output=True, text=True).stdout.strip()
    tree = subprocess.run(["git", "-C", str(args.source_root), "rev-parse", "HEAD^{tree}"],
                          check=True, capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "-C", str(args.source_root), "status", "--porcelain", "--untracked-files=no"],
                            check=True, capture_output=True, text=True).stdout.strip()
    result = validate_summary(summary, source_commit=commit, source_tree=tree, source_clean=not status)
    print(json.dumps(result, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
