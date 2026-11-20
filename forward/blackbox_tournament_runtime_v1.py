"""Continuous, fail-closed Blackbox evidence collection and hypothesis tournament runtime."""
from __future__ import annotations
import fcntl, hashlib, json, math
from collections import defaultdict
from pathlib import Path
from typing import Any
from .blackbox_experience_memory_v1 import (
    canonical_sha256, evaluate_hypothesis_tournament,
    build_hypothesis_transition_event, append_hypothesis_events,
)

AUDIT_SCHEMA = "hes_blackbox_family_evidence_audit_v1"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"JSONL_ROW_NOT_OBJECT:{path.name}:{line_no}")
        rows.append(row)
    return rows


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _append_immutable(path: Path, rows: list[dict[str, Any]]) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"appended": 0, "exact_replays": 0}
    with path.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0)
        existing = {}
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            old = json.loads(line)
            if old.get("schema") != AUDIT_SCHEMA or not old.get("event_id"):
                raise ValueError(f"FAMILY_AUDIT_LEDGER_CORRUPT:{line_no}")
            digest = canonical_sha256(old)
            if old["event_id"] in existing and existing[old["event_id"]] != digest:
                raise ValueError("FAMILY_AUDIT_EVENT_COLLISION")
            existing[old["event_id"]] = digest
        for row in rows:
            digest = canonical_sha256(row)
            prior = existing.get(row["event_id"])
            if prior is not None:
                if prior != digest:
                    raise ValueError("FAMILY_AUDIT_EVENT_CONTENT_CONFLICT")
                counts["exact_replays"] += 1
                continue
            stream.seek(0, 2)
            stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
            existing[row["event_id"]] = digest
            counts["appended"] += 1
        stream.flush()
    return counts


def collect_family_evidence_audit(data_root: str | Path) -> dict[str, Any]:
    """Continuously snapshot family journals; only fully verified independent outcomes qualify."""
    root = Path(data_root).resolve()
    base = root / "data" / "forward"
    report_path = base / "strategy_family_results_report_v1.json"
    if not report_path.exists():
        return {"status": "BLOCKED_MISSING_FAMILY_REPORT", "families": {}, "eligible_outcomes": 0,
                "blockers": ["CANONICAL_FAMILY_REPORT_MISSING"]}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") != "hes_strategy_family_results_report_v1":
        raise ValueError("CANONICAL_FAMILY_REPORT_SCHEMA_MISMATCH")
    report_sha = _sha(report_path)
    snapshots = []
    families = {}
    all_blockers = []
    total_eligible = 0
    for family_id, family in sorted(report.get("families", {}).items()):
        filename = family.get("journal_file")
        if not filename or Path(filename).name != filename:
            raise ValueError("FAMILY_JOURNAL_PATH_INVALID")
        journal = base / filename
        journal_sha = _sha(journal)
        sha_ok = bool(journal_sha and journal_sha == family.get("journal_sha256"))
        blockers = []
        if not sha_ok:
            blockers.append("FAMILY_JOURNAL_HASH_MISMATCH")
        rows = _read_jsonl(journal) if sha_ok else []
        candidate_rows = [r for r in rows if r.get("event_type") == "PAPER_CANDIDATE"]
        candidates = {}
        for candidate_row in candidate_rows:
            if candidate_row.get("event_type") != "PAPER_CANDIDATE":
                continue
            for candidate_key in (candidate_row.get("event_id"), candidate_row.get("candidate_event_id"),
                                  candidate_row.get("source_event_id")):
                if candidate_key:
                    key = str(candidate_key)
                    if key in candidates and canonical_sha256(candidates[key]) != canonical_sha256(candidate_row):
                        raise ValueError("FAMILY_CANDIDATE_ID_COLLISION")
                    candidates[key] = candidate_row
        outcomes = [r for r in rows if r.get("event_type") == "PAPER_OUTCOME"]
        report_count_blockers = []
        if len(rows) != int(family.get("journal_event_count", len(rows)) or 0):
            report_count_blockers.append("JOURNAL_EVENT_COUNT_MISMATCH")
        if len(candidate_rows) != int(family.get("candidate_count", len(candidate_rows)) or 0):
            report_count_blockers.append("CANDIDATE_COUNT_MISMATCH")
        if len(outcomes) != int(family.get("outcome_count", len(outcomes)) or 0):
            report_count_blockers.append("OUTCOME_COUNT_MISMATCH")
        if sum(r.get("performance_eligible") is True for r in outcomes) != int(family.get("performance_eligible_resolved", 0) or 0):
            report_count_blockers.append("PERFORMANCE_ELIGIBLE_COUNT_MISMATCH")
        eligible = []
        reason_counts: dict[str, int] = {}
        for outcome in outcomes:
            reasons = []
            if outcome.get("family_id") != family_id:
                reasons.append("FAMILY_ID_MISMATCH")
            candidate_id = str(outcome.get("candidate_event_id") or "")
            candidate = candidates.get(candidate_id)
            if candidate is None:
                reasons.append("CANDIDATE_LINK_MISSING")
            elif candidate.get("final_gate_decision") not in ("LONG", "SHORT"):
                reasons.append("CANDIDATE_NOT_GATE_APPROVED")
            elif not _valid_sha(candidate.get("source_record_sha256")) or outcome.get("candidate_source_sha256") != candidate.get("source_record_sha256"):
                reasons.append("CANDIDATE_SOURCE_HASH_LINK_INVALID")
            if not _valid_sha(outcome.get("source_record_sha256")):
                reasons.append("OUTCOME_SOURCE_RECORD_HASH_INVALID")
            if outcome.get("family_version") != family.get("family_version"):
                reasons.append("FAMILY_VERSION_MISMATCH")
            if candidate is not None and outcome.get("run_id") != candidate.get("run_id"):
                reasons.append("CANDIDATE_OUTCOME_RUN_MISMATCH")
            if outcome.get("performance_eligible") is not True:
                reasons.append("PERFORMANCE_NOT_GATE_APPROVED")
            if outcome.get("costs_verified") is not True:
                reasons.append("EXECUTION_COSTS_UNVERIFIED")
            if outcome.get("cost_model_status") != "VERIFIED":
                reasons.append("COST_MODEL_NOT_VERIFIED")
            if not _valid_sha(outcome.get("fee_schedule_sha256")):
                reasons.append("FEE_SCHEDULE_PROVENANCE_INVALID")
            if not _valid_sha(outcome.get("slippage_evidence_sha256")):
                reasons.append("SLIPPAGE_PROVENANCE_INVALID")
            if not _finite_number(outcome.get("net_R")):
                reasons.append("NET_R_MISSING_OR_INVALID")
            if outcome.get("sample_role") == "OOS" and not _finite_number(outcome.get("baseline_net_R")):
                reasons.append("MATCHED_BASELINE_NET_R_MISSING")
            if outcome.get("sample_role") == "OOS" and not _valid_sha(outcome.get("baseline_source_sha256")):
                reasons.append("BASELINE_SOURCE_PROVENANCE_INVALID")
            if outcome.get("sample_role") == "OOS" and outcome.get("independent_oos") is not True:
                reasons.append("OOS_NOT_INDEPENDENT")
            if outcome.get("chronological_purged") is not True:
                reasons.append("PURGED_CHRONOLOGY_NOT_PROVEN")
            if outcome.get("provenance_complete") is not True:
                reasons.append("PROVENANCE_INCOMPLETE")
            if outcome.get("sample_role") not in ("TRAIN", "OOS"):
                reasons.append("TRAIN_OOS_ROLE_MISSING")
            if outcome.get("preregistered") is not True or outcome.get("hypothesis_status") != "TESTING":
                reasons.append("HYPOTHESIS_NOT_PREREGISTERED_FOR_TESTING")
            if not _valid_sha(outcome.get("preregistration_sha256")):
                reasons.append("PREREGISTRATION_HASH_INVALID")
            if not _valid_sha(outcome.get("source_manifest_sha256")):
                reasons.append("SOURCE_MANIFEST_HASH_INVALID")
            hashes = outcome.get("source_hashes")
            if not isinstance(hashes, dict) or not hashes or not all(_valid_sha(v) for v in hashes.values()):
                reasons.append("SOURCE_HASH_SET_INVALID")
            if outcome.get("direction") == "SHORT" and outcome.get("short_economics_validated") is not True:
                reasons.append("SHORT_ECONOMICS_NOT_VALIDATED")
            for reason in reasons:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            if not reasons:
                eligible.append(outcome)
        total_eligible += len(eligible)
        family_blockers = list(report_count_blockers)
        if not sha_ok:
            family_blockers.append("FAMILY_JOURNAL_HASH_MISMATCH")
        if len(eligible) < 200:
            family_blockers.append("INSUFFICIENT_VERIFIED_TRAIN_AND_OOS_OUTCOMES")
        if not any(r.get("sample_role") == "TRAIN" for r in eligible):
            family_blockers.append("NO_VERIFIED_TRAIN_OUTCOMES")
        if not any(r.get("sample_role") == "OOS" for r in eligible):
            family_blockers.append("NO_VERIFIED_INDEPENDENT_OOS_OUTCOMES")
        blockers.extend(family_blockers)
        snapshot = {
            "schema": AUDIT_SCHEMA,
            "event_type": "FAMILY_EVIDENCE_SNAPSHOT",
            "event_id": "HES-FAM-AUDIT-" + canonical_sha256({
                "family_id": family_id, "family_version": family.get("family_version"),
                "report_sha256": report_sha, "journal_sha256": journal_sha,
            })[:24],
            "family_id": family_id, "family_version": family.get("family_version"),
            "report_sha256": report_sha, "journal_sha256": journal_sha,
            "journal_sha256_verified": sha_ok, "candidate_count": len(candidate_rows),
            "outcome_count": len(outcomes), "verified_eligible_outcome_count": len(eligible),
            "verified_train_count": sum(r.get("sample_role") == "TRAIN" for r in eligible),
            "verified_oos_count": sum(r.get("sample_role") == "OOS" for r in eligible),
            "verified_eligible_outcome_ids": sorted(str(r.get("event_id")) for r in eligible if r.get("event_id")),
            "rejection_reason_counts": reason_counts, "blockers": family_blockers,
            "execution_enabled": False, "orders_placed": False,
            "policy_mutation_enabled": False,
        }
        snapshots.append(snapshot)
        families[family_id] = snapshot
        all_blockers.extend(f"{family_id}:{x}" for x in blockers)
    append_result = _append_immutable(base / "blackbox_family_evidence_audit_v1.jsonl", snapshots)
    return {
        "status": "VERIFIED_FAMILY_EVIDENCE_COLLECTING" if total_eligible else "WAITING_FOR_VERIFIED_FAMILY_EVIDENCE",
        "families": families, "family_count": len(families), "eligible_outcomes": total_eligible,
        "append_result": append_result, "blockers": all_blockers,
        "source_report_sha256": report_sha,
        "execution_enabled": False, "orders_placed": False, "policy_mutation_enabled": False,
    }


def _aggregate_hypothesis_evidence(
    data_root: Path, *, verified_outcome_keys: set[tuple[str, str]]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    base = data_root / "data" / "forward"
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts = {"outcomes_seen": 0, "outcomes_qualified": 0, "outcomes_rejected": 0}
    for path in sorted(base.glob("strategy_family_*_results_v1.jsonl")):
        for row in _read_jsonl(path):
            if row.get("event_type") != "PAPER_OUTCOME":
                continue
            counts["outcomes_seen"] += 1
            # The family audit is the single source of truth for candidate linkage,
            # journal hashes, fee/slippage evidence, run/version provenance and OOS gates.
            # Never let the tournament use a weaker parallel eligibility check.
            evidence_key = (str(row.get("family_id") or ""), str(row.get("event_id") or ""))
            if evidence_key not in verified_outcome_keys:
                counts["outcomes_rejected"] += 1
                continue
            required_true = ("performance_eligible", "costs_verified",
                             "chronological_purged", "provenance_complete", "preregistered")
            ok = all(row.get(k) is True for k in required_true)
            ok = ok and row.get("hypothesis_status") == "TESTING"
            ok = ok and row.get("sample_role") in ("TRAIN", "OOS")
            if row.get("sample_role") == "OOS":
                ok = ok and row.get("independent_oos") is True
            ok = ok and _valid_sha(row.get("preregistration_sha256")) and _valid_sha(row.get("source_manifest_sha256"))
            ok = ok and _finite_number(row.get("net_R"))
            if row.get("sample_role") == "OOS":
                ok = ok and _finite_number(row.get("baseline_net_R"))
                ok = ok and _valid_sha(row.get("baseline_source_sha256"))
            ok = ok and isinstance(row.get("hypothesis_id"), str) and bool(row.get("hypothesis_id"))
            if row.get("direction") == "SHORT":
                ok = ok and row.get("short_economics_validated") is True
            if not ok:
                counts["outcomes_rejected"] += 1
                continue
            grouped[row["hypothesis_id"]].append(row)
            counts["outcomes_qualified"] += 1
    evidence_rows = []
    for hid, rows in sorted(grouped.items()):
        train = [r for r in rows if r["sample_role"] == "TRAIN"]
        oos = [r for r in rows if r["sample_role"] == "OOS"]
        if not train or not oos:
            continue
        directions = {r.get("direction") for r in rows}
        if any(r.get("regime") not in ("BULLISH", "BEARISH", "RANGE") for r in oos):
            continue
        if len({r.get("event_id") for r in rows}) != len(rows):
            continue
        families = {r.get("multiple_testing_family") for r in rows}
        prereg_hashes = {r.get("preregistration_sha256") for r in rows}
        manifest_hashes = {r.get("source_manifest_sha256") for r in rows}
        if len(directions) != 1 or len(families) != 1 or len(prereg_hashes) != 1 or len(manifest_hashes) != 1:
            continue
        train_values = [float(r["net_R"]) for r in train]
        oos_values = [float(r["net_R"]) for r in oos]
        baseline_values = [float(r["baseline_net_R"]) for r in oos]
        evidence_rows.append({
            "hypothesis_id": hid, "direction": next(iter(directions)),
            "train_n": len(train), "train_wins": sum(v > 0 for v in train_values),
            "oos_n": len(oos), "oos_wins": sum(v > 0 for v in oos_values),
            "train_mean_net_r": sum(train_values) / len(train_values),
            "oos_mean_net_r": sum(oos_values) / len(oos_values),
            "baseline_oos_mean_net_r": sum(baseline_values) / len(baseline_values),
            "train_net_r_values": train_values, "oos_net_r_values": oos_values,
            "baseline_oos_net_r_values": baseline_values,
            "oos_regime_count": len({str(r.get("regime")) for r in oos}),
            "costs_verified": all(r.get("costs_verified") is True for r in rows),
            "independent_oos": all(r.get("independent_oos") is True for r in oos),
            "chronological_purged": all(r.get("chronological_purged") is True for r in oos),
            "unmatched": sum(int(r.get("unmatched", 0) or 0) for r in rows),
            "unscorable": sum(int(r.get("unscorable", 0) or 0) for r in rows),
            "provenance_complete": all(r.get("provenance_complete") is True for r in rows),
            "preregistered": all(r.get("preregistered") is True for r in rows),
            "hypothesis_status": "TESTING",
            "preregistration_sha256": next(iter(prereg_hashes)),
            "source_manifest_sha256": next(iter(manifest_hashes)),
            "multiple_testing_family": next(iter(families)),
            "short_economics_validated": all(r.get("short_economics_validated") is True for r in rows),
            "source_event_hashes": sorted(canonical_sha256(r) for r in rows),
        })
    return evidence_rows, counts


def _latest_hypothesis_states(path: Path) -> dict[str, dict[str, Any]]:
    latest = {}
    for row in _read_jsonl(path):
        hid = row.get("hypothesis_id")
        if not hid:
            continue
        if row.get("event_type") == "DISCOVERY":
            latest[hid] = {"status": "DISCOVERED", "evidence_sha256": None}
        elif row.get("event_type") == "STATUS_TRANSITION":
            latest[hid] = {"status": row.get("status"), "evidence_sha256": row.get("evidence_sha256")}
    return latest


def run_competition_cycle(data_root: str | Path) -> dict[str, Any]:
    """Run evidence audit and paired OOS tournament; never synthesizes or relaxes evidence."""
    root = Path(data_root).resolve()
    base = root / "data" / "forward"
    family_audit = collect_family_evidence_audit(root)
    verified_outcome_keys = {
        (family_id, event_id)
        for family_id, family in family_audit.get("families", {}).items()
        for event_id in family.get("verified_eligible_outcome_ids", [])
    }
    evidence_rows, evidence_counts = _aggregate_hypothesis_evidence(
        root, verified_outcome_keys=verified_outcome_keys
    )
    hypothesis_ledger = base / "blackbox_hypothesis_events_v1.jsonl"
    states = _latest_hypothesis_states(hypothesis_ledger)
    eligible_rows = [r for r in evidence_rows if states.get(r["hypothesis_id"], {}).get("status") in ("TESTING", "INCONCLUSIVE")]
    transitions = []
    if eligible_rows:
        for row in eligible_rows:
            state = states[row["hypothesis_id"]]
            if state["status"] == "INCONCLUSIVE" and state.get("evidence_sha256") != canonical_sha256(row):
                event = build_hypothesis_transition_event(
                    hypothesis_id=row["hypothesis_id"], previous_status="INCONCLUSIVE",
                    next_status="TESTING", rationale="New independently verified evidence snapshot; reopen testing.")
                transitions.append(event)
        if transitions:
            append_hypothesis_events(hypothesis_ledger, transitions)
            states = _latest_hypothesis_states(hypothesis_ledger)
        testing = [r for r in eligible_rows if states.get(r["hypothesis_id"], {}).get("status") == "TESTING"]
        results = evaluate_hypothesis_tournament(testing) if testing else {"results": [], "safety": {"execution_enabled": False, "orders_placed": False, "policy_mutation_enabled": False}}
        final_events = []
        for result in results.get("results", []):
            if result["status"] in ("ACCEPTED", "REJECTED", "INCONCLUSIVE"):
                final_events.append(build_hypothesis_transition_event(
                    hypothesis_id=result["hypothesis_id"], previous_status="TESTING",
                    next_status=result["status"], evidence_sha256=result["evidence_sha256"],
                    rationale="Automated paired exact OOS net-R sign test with Holm correction; see immutable tournament report."))
        if final_events:
            append_hypothesis_events(hypothesis_ledger, final_events)
        status = "TOURNAMENT_EVALUATED"
    else:
        results = {"results": [], "safety": {"execution_enabled": False, "orders_placed": False, "policy_mutation_enabled": False}}
        status = "WAITING_FOR_PREREGISTERED_INDEPENDENT_OOS_EVIDENCE"
    report = {
        "schema": "hes_blackbox_continuous_tournament_v1",
        "status": status, "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "family_evidence_audit": family_audit, "evidence_collection": evidence_counts,
        "hypotheses_with_eligible_evidence": len(evidence_rows),
        "hypotheses_tested": len(results.get("results", [])),
        "tournament": results,
        "safety": {"execution_enabled": False, "orders_placed": False,
                   "policy_mutation_enabled": False, "production_approved": False,
                   "risk_gate_bypass": False},
    }
    out = base / "blackbox_continuous_tournament_v1_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
