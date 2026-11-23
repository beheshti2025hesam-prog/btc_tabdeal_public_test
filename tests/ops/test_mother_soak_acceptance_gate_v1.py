from pathlib import Path
import pytest

from scripts.ops.mother_soak_acceptance_gate_v1 import (
    EXPECTED_SOURCE_COMMIT, EXPECTED_SOURCE_TREE, validate_summary,
)


def _summary():
    agents = {
        name: {"circuit": "CLOSED", "consecutive_failures": 0}
        for name in ("market_bootstrap", "data_quality", "market_structure", "signal",
                     "confirmation", "risk", "decision", "evaluation")
    }
    return {
        "schema": "hes.mother_supervisor_readonly_soak.v1", "status": "PASS",
        "complete": True, "requested_duration_seconds": 86400, "elapsed_seconds": 86400.5,
        "interval_seconds": 300, "runs": 288, "failures": [],
        "production_journal_used_for_soak": False,
        "production_journal_sha256_at_start": "a" * 64,
        "soak_journal_snapshot_sha256_before": "a" * 64,
        "soak_journal_snapshot_sha256_after": "a" * 64,
        "soak_journal_snapshot_unchanged": True,
        "last_observation": {
            "failures": [], "journal_unchanged": True, "journal_sha256": "a" * 64, "witness_verified": True,
            "stage_states": ["PASS", "PASS", "PASS", "UNCONFIRMED", "REJECTED", "DECIDED", "OBSERVED"],
            "supervisor": {
                "bootstrap_status": "SUCCEEDED",
                "health": {"version": "hes-specialist-supervisor-v1", "inflight_requests": 0,
                           "active_counts": {}, "execution_authorized": False,
                           "active_agents": [], "agents": agents},
            },
        },
    }


def test_exact_complete_24h_soak_passes_only_with_frozen_source_and_journal():
    result = validate_summary(_summary(), source_commit=EXPECTED_SOURCE_COMMIT,
                              source_tree=EXPECTED_SOURCE_TREE, source_clean=True)
    assert result["status"] == "PASS" and result["runs"] == 288


@pytest.mark.parametrize("mutate,expected", [
    (lambda d: d.update(elapsed_seconds=86399), "SOAK_ELAPSED_BELOW_24H"),
    (lambda d: d.update(runs=287), "SOAK_SAMPLE_COUNT_BELOW_MINIMUM"),
    (lambda d: d.update(requested_duration_seconds=1), "SOAK_DURATION_NOT_24H"),
    (lambda d: d.update(soak_journal_snapshot_sha256_after="f" * 64), "SOAK_SNAPSHOT_HASH_MISMATCH"),
    (lambda d: d.update(production_journal_used_for_soak=True), "PRODUCTION_JOURNAL_USED"),
    (lambda d: d.update(complete=False), "SOAK_NOT_COMPLETE"),
    (lambda d: d["last_observation"].update(stage_states=["PASS", "UNKNOWN", "PASS", "PASS", "PASS", "PASS", "PASS"]), "LAST_OBSERVATION_STAGE_STATE_INVALID"),
    (lambda d: d["last_observation"].update(witness_verified=False), "LAST_OBSERVATION_WITNESS_INVALID"),
    (lambda d: d["last_observation"].update(journal_sha256="f" * 64), "LAST_OBSERVATION_JOURNAL_HASH_MISMATCH"),
    (lambda d: d["last_observation"]["supervisor"]["health"].update(execution_authorized=True), "SUPERVISOR_EXECUTION_AUTHORIZED"),
    (lambda d: d["last_observation"]["supervisor"]["health"].update(active_agents=["risk"]), "SUPERVISOR_ACTIVE_AGENTS_PRESENT"),
])
def test_soak_gate_rejects_short_or_unsafe_summaries(mutate, expected):
    summary = _summary(); mutate(summary)
    with pytest.raises(ValueError, match=expected):
        validate_summary(summary, source_commit=EXPECTED_SOURCE_COMMIT,
                         source_tree=EXPECTED_SOURCE_TREE, source_clean=True)


def test_soak_gate_rejects_wrong_or_dirty_source_tree():
    with pytest.raises(ValueError, match="SOAK_SOURCE_COMMIT_MISMATCH"):
        validate_summary(_summary(), source_commit="0" * 40,
                         source_tree=EXPECTED_SOURCE_TREE, source_clean=True)
    with pytest.raises(ValueError, match="SOAK_SOURCE_TREE_MISMATCH"):
        validate_summary(_summary(), source_commit=EXPECTED_SOURCE_COMMIT,
                         source_tree="0" * 40, source_clean=True)
    with pytest.raises(ValueError, match="SOAK_SOURCE_WORKTREE_DIRTY"):
        validate_summary(_summary(), source_commit=EXPECTED_SOURCE_COMMIT,
                         source_tree=EXPECTED_SOURCE_TREE, source_clean=False)


def test_activation_script_targets_the_current_soak_and_uses_strict_validator():
    script = (Path(__file__).resolve().parents[2] / "scripts" / "ops" /
              "activate_mother_decision_journal_writer_v1.sh").read_text()
    assert "hes-mother-supervisor-soak-20261122-v1.service" in script
    assert "/var/lib/hes-mother-supervisor-soak-20261122-v1/mother-supervisor-soak-summary.json" in script
    assert "mother_soak_acceptance_gate_v1.py" in script
    assert "--duration-seconds 86400" in script
    assert "--interval-seconds 300" in script
    assert "scripts/ops/mother_supervisor_soak_v1.py" in script
    assert "hes-mother-supervisor-soak-20261121-v2.service" not in script
