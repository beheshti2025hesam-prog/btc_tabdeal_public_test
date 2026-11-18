import hashlib
import json
from pathlib import Path

from forward.blackbox_experience_memory_v1 import (
    append_hypothesis_events, build_hypothesis_event, build_hypothesis_transition_event,
    canonical_sha256,
)
from forward.blackbox_tournament_runtime_v1 import run_competition_cycle


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_family_fixture(root, outcomes, candidates):
    base = root / "data" / "forward"
    base.mkdir(parents=True, exist_ok=True)
    family_id = "trend_breakout"
    journal = base / "strategy_family_trend_breakout_results_v1.jsonl"
    journal.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in candidates + outcomes))
    report = {
        "schema": "hes_strategy_family_results_report_v1",
        "execution_enabled": False, "orders_placed": False,
        "families": {
            family_id: {
                "family_id": family_id, "family_version": "family-v1",
                "journal_file": journal.name, "journal_sha256": _sha(journal),
                "journal_event_count": len(candidates) + len(outcomes),
                "candidate_count": len(candidates), "outcome_count": len(outcomes),
                "performance_eligible_resolved": sum(x.get("performance_eligible") is True for x in outcomes),
                "execution_enabled": False, "orders_placed": False,
            }
        },
    }
    (base / "strategy_family_results_report_v1.json").write_text(json.dumps(report, sort_keys=True))
    return base, journal


def test_continuous_cycle_collects_unverified_family_rows_but_never_promotes(tmp_path):
    candidates = [{"event_type": "PAPER_CANDIDATE", "event_id": "c1", "family_id": "trend_breakout",
                   "final_gate_decision": "NO_TRADE"}]
    outcomes = [{"event_type": "PAPER_OUTCOME", "event_id": "o1", "family_id": "trend_breakout",
                 "candidate_event_id": "c1", "performance_eligible": False, "costs_verified": False}]
    base, _ = _write_family_fixture(tmp_path, outcomes, candidates)
    first = run_competition_cycle(tmp_path)
    second = run_competition_cycle(tmp_path)
    assert first["status"] == "WAITING_FOR_PREREGISTERED_INDEPENDENT_OOS_EVIDENCE"
    assert first["hypotheses_tested"] == 0
    assert first["family_evidence_audit"]["eligible_outcomes"] == 0
    assert first["family_evidence_audit"]["families"]["trend_breakout"]["candidate_count"] == 1
    assert "trend_breakout:INSUFFICIENT_VERIFIED_TRAIN_AND_OOS_OUTCOMES" in first["family_evidence_audit"]["blockers"]
    assert second["family_evidence_audit"]["append_result"]["exact_replays"] == 1
    assert first["safety"]["execution_enabled"] is False
    assert first["safety"]["policy_mutation_enabled"] is False


def test_paired_oos_tournament_accepts_only_preregistered_verified_evidence(tmp_path):
    base = tmp_path / "data" / "forward"
    base.mkdir(parents=True)
    sha = "a" * 64
    manifest_sha = "b" * 64
    hypothesis_id = "HES-BBX-TEST-001"
    discovery = build_hypothesis_event(
        hypothesis_id=hypothesis_id, family_id="trend_breakout",
        statement="Test frozen breakout hypothesis against baseline.",
        discovery_window={"start": "2026-01-01T00:00:00+00:00", "end": "2026-06-30T00:00:00+00:00"},
        source_hashes={"discovery": sha},
        feature_definition={"feature": "test_feature", "threshold": 1.0},
        null_hypothesis="No net-R improvement over baseline.",
        alternative_hypothesis="Positive paired net-R improvement over baseline.",
        primary_metric="oos_mean_net_r_minus_baseline",
        falsification_rule="Reject on significant paired underperformance.",
        multiple_testing_family="family-v1",
    )
    ledger = base / "blackbox_hypothesis_events_v1.jsonl"
    append_hypothesis_events(ledger, [discovery])
    append_hypothesis_events(ledger, [
        build_hypothesis_transition_event(hypothesis_id=hypothesis_id, previous_status="DISCOVERED",
                                          next_status="PREREGISTERED"),
        build_hypothesis_transition_event(hypothesis_id=hypothesis_id, previous_status="PREREGISTERED",
                                          next_status="TESTING"),
    ])
    candidates, outcomes = [], []
    for role, count in (("TRAIN", 100), ("OOS", 100)):
        for i in range(count):
            cid = f"{role.lower()}-c{i}"
            candidates.append({"event_type": "PAPER_CANDIDATE", "event_id": cid,
                               "family_id": "trend_breakout", "family_version": "family-v1",
                               "final_gate_decision": "LONG", "run_id": "run-1",
                               "source_record_sha256": "c" * 64})
            row = {
                "event_type": "PAPER_OUTCOME", "event_id": f"{role.lower()}-o{i}",
                "family_id": "trend_breakout", "family_version": "family-v1", "run_id": "run-1",
                "candidate_event_id": cid, "candidate_source_sha256": "c" * 64,
                "source_record_sha256": "d" * 64,
                "performance_eligible": True, "costs_verified": True,
                "net_R": 1.0 if role == "TRAIN" else 1.2,
                "baseline_net_R": 0.2 if role == "OOS" else None,
                "independent_oos": role == "OOS", "chronological_purged": True,
                "provenance_complete": True, "sample_role": role,
                "preregistered": True, "hypothesis_status": "TESTING",
                "preregistration_sha256": sha, "source_manifest_sha256": manifest_sha,
                "source_hashes": {"source": sha}, "hypothesis_id": hypothesis_id,
                "multiple_testing_family": "family-v1", "direction": "LONG",
                "regime": ("BULLISH" if i % 2 else "BEARISH") if role == "OOS" else "BULLISH",
                "unmatched": 0, "unscorable": 0,
            }
            outcomes.append(row)
    _write_family_fixture(tmp_path, outcomes, candidates)
    report = run_competition_cycle(tmp_path)
    assert report["status"] == "TOURNAMENT_EVALUATED"
    assert report["hypotheses_tested"] == 1
    assert report["family_evidence_audit"]["families"]["trend_breakout"]["candidate_count"] == 200
    result = report["tournament"]["results"][0]
    assert result["status"] == "ACCEPTED"
    assert result["holm_adjusted_p_value"] <= 0.05
    rows = [json.loads(x) for x in ledger.read_text().splitlines()]
    assert rows[-1]["event_type"] == "STATUS_TRANSITION"
    assert rows[-1]["status"] == "ACCEPTED"
    assert report["safety"]["execution_enabled"] is False
    assert report["safety"]["policy_mutation_enabled"] is False
