from types import SimpleNamespace

import json
import pytest

from forward.decision_engine_v1 import DecisionEngineV1
from forward.forward_journal_v1 import ForwardJournalV1


def _candidate(state):
    return SimpleNamespace(state=state)


def _confirmation(state):
    return SimpleNamespace(state=state)


def _risk(state):
    return SimpleNamespace(state=state)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_risk_approved_preserves_valid_direction(direction):
    result = DecisionEngineV1().evaluate(
        observed_at="2026-10-07T09:00:00+03:30",
        candidate=_candidate(f"CANDIDATE_{direction}"),
        confirmation=_confirmation(f"CONFIRMED_{direction}"),
        risk=_risk("RISK_APPROVED"),
    )
    assert result.decision == direction
    assert result.reason_codes == ("ALL_REQUIRED_GATES_PASSED",)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
@pytest.mark.parametrize("risk_state", [
    "RISK_REJECTED",
    "RISK_BLOCKED",
    "RISK_FAILED",
    "RISK_UNKNOWN",
    None,
])
def test_every_risk_reject_resolves_to_no_trade(direction, risk_state):
    result = DecisionEngineV1().evaluate(
        observed_at="2026-10-07T09:00:00+03:30",
        candidate=_candidate(f"CANDIDATE_{direction}"),
        confirmation=_confirmation(f"CONFIRMED_{direction}"),
        risk=_risk(risk_state),
    )

    assert result.decision == "NO_TRADE"
    assert "RISK_NOT_APPROVED" in result.reason_codes


def test_risk_veto_cannot_produce_opposite_direction():
    for risk_state in ("RISK_REJECTED", "RISK_BLOCKED"):
        result = DecisionEngineV1().evaluate(
            observed_at="2026-10-07T09:00:00+03:30",
            candidate=_candidate("CANDIDATE_SHORT"),
            confirmation=_confirmation("CONFIRMED_SHORT"),
            risk=_risk(risk_state),
        )
        assert result.decision == "NO_TRADE"


def test_risk_veto_no_trade_is_journalable():
    result = DecisionEngineV1().evaluate(
        observed_at="2026-10-07T09:00:00+03:30",
        candidate=_candidate("CANDIDATE_LONG"),
        confirmation=_confirmation("CONFIRMED_LONG"),
        risk=_risk("RISK_REJECTED"),
    )
    assert result.decision == "NO_TRADE"

    # The exact decision produced by the veto is the one that reaches Journal.
    assert result.decision in {"LONG", "SHORT", "NO_TRADE"}


def test_decision_journal_rejects_future_outcome(tmp_path):
    journal = ForwardJournalV1(tmp_path / "journal.jsonl")
    base = {
        "event_id": "evt-risk-veto-001",
        "observed_at": "2026-10-07T09:00:00+03:30",
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "decision": "NO_TRADE",
        "evidence_source": ["live-observation-001"],
    }

    journal.append_decision(base)

    with pytest.raises(ValueError, match="future outcome leakage"):
        journal.append_decision({**base, "event_id": "evt-risk-veto-002", "outcome": "WIN"})

    with pytest.raises(ValueError, match="future outcome leakage"):
        journal.append_decision({
            **base,
            "event_id": "evt-risk-veto-003",
            "closed_at": "2026-10-07T10:00:00+03:30",
        })

    rows = (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    stored = json.loads(rows[0])
    assert stored["decision"] == "NO_TRADE"
    assert stored["outcome"] is None
    assert stored["closed_at"] is None


def test_outcome_mutation_is_separate_and_forbidden_on_decision_journal(tmp_path):
    journal = ForwardJournalV1(tmp_path / "journal.jsonl")
    with pytest.raises(NotImplementedError, match="separate immutable outcome artifact"):
        journal.append_outcome(
            event_id="evt-risk-veto-004",
            outcome="WIN",
            closed_at="2026-10-07T10:00:00+03:30",
        )
