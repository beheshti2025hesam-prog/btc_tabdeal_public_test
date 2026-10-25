from copy import deepcopy
from datetime import datetime, timedelta, timezone

from core.orchestration.mother_v1 import AgentResult, MotherOrchestratorV1

ORDER = ("data_quality", "market_structure", "signal", "confirmation", "risk", "decision", "evaluation")
NOW = datetime.now(timezone.utc)
CONTEXT = {
    "scope": {"venue": "binance", "product": "spot", "symbol": "BTCUSDT", "timeframe": "15m"},
    "observed_at": NOW.isoformat(),
    "snapshot_sha256": "a" * 64,
    "evidence_sha256": "b" * 64,
    "request_id": "test-run-1",
}
STATES = {
    "data_quality": "PASS", "market_structure": "PASS", "signal": "PASS",
    "confirmation": "CONFIRMED", "risk": "APPROVED", "decision": "DECIDED",
    "evaluation": "OBSERVED",
}


class Stub:
    def __init__(self, name, state=None, payload=None, raises=False, mutate=False, reasons=(), refs=("a" * 64,)):
        self.name = name
        self.state = STATES[name] if state is None else state
        self.payload = ({"decision": "LONG"} if name == "decision" else {}) if payload is None else payload
        self.raises = raises
        self.mutate = mutate
        self.reasons = reasons
        self.refs = refs
        self.seen = []

    def evaluate(self, context):
        self.seen.append(context)
        if self.mutate:
            context["scope"]["symbol"] = "INJECTED"
        if self.raises:
            raise RuntimeError("simulated")
        return AgentResult(self.name, self.state, tuple(self.reasons), tuple(self.refs), self.payload)


def agents(**overrides):
    return {name: overrides.get(name, Stub(name)) for name in ORDER}


def test_missing_specialist_fails_closed():
    a = agents()
    a.pop("risk")
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.decision == "NO_TRADE" and not r.execution_authorized
    assert r.status == "BLOCKED_CONFIGURATION"


def test_extra_specialist_fails_closed_to_prevent_shadow_agents():
    a = agents()
    a["execution"] = Stub("execution")
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.status == "BLOCKED_CONFIGURATION"
    assert "UNREGISTERED_SPECIALISTS:execution" in r.reason_codes


def test_risk_veto_stops_downstream():
    a = agents(risk=Stub("risk", "REJECTED", reasons=("RISK_BUDGET_UNKNOWN",)))
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.decision == "NO_TRADE" and r.status == "BLOCKED_RISK_VETO"
    assert len(r.stages) == 5 and not a["decision"].seen


def test_agent_exception_fails_closed():
    a = agents(signal=Stub("signal", raises=True))
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.status == "BLOCKED_AGENT_ERROR" and r.decision == "NO_TRADE"


def test_unknown_state_fails_closed():
    a = agents(confirmation=Stub("confirmation", "UNKNOWN"))
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.status == "BLOCKED_GATE" and r.decision == "NO_TRADE"


def test_success_is_observation_only_and_auditable():
    r = MotherOrchestratorV1(agents()).run(CONTEXT)
    assert r.status == "OBSERVATION_ONLY" and r.decision == "LONG"
    assert r.execution_authorized is False
    assert tuple(x.agent for x in r.stages) == ORDER
    assert len(r.trace_id) == len(r.audit_sha256) == 64
    assert r.as_dict()["execution_authorized"] is False


def test_short_decision_mapping_is_preserved():
    a = agents(decision=Stub("decision", payload={"decision": "SHORT"}))
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.status == "OBSERVATION_ONLY" and r.decision == "SHORT"


def test_no_trade_is_a_valid_decision_not_a_successful_trade():
    a = agents(decision=Stub("decision", payload={"decision": "NO_TRADE"}))
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.status == "OBSERVATION_ONLY" and r.decision == "NO_TRADE"


def test_invalid_decision_payload_fails_closed():
    a = agents(decision=Stub("decision", payload={"decision": "BUY_MORE"}))
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.status == "BLOCKED_INVALID_DECISION" and r.decision == "NO_TRADE"


def test_wrong_result_identity_blocks():
    a = agents(signal=Stub("other"))
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.status == "BLOCKED_INVALID_RESULT" and r.decision == "NO_TRADE"


def test_result_contract_rejects_unexpected_state_for_stage():
    a = agents(confirmation=Stub("confirmation", "PASS"))
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.status == "BLOCKED_GATE" and r.decision == "NO_TRADE"


def test_context_scope_and_provenance_are_mandatory():
    for key in ("scope", "observed_at", "snapshot_sha256", "evidence_sha256"):
        bad = deepcopy(CONTEXT)
        bad.pop(key)
        r = MotherOrchestratorV1(agents()).run(bad)
        assert r.status == "BLOCKED_CONTEXT" and r.decision == "NO_TRADE"


def test_future_and_naive_timestamps_fail_closed():
    future = dict(CONTEXT, observed_at=(datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat())
    assert MotherOrchestratorV1(agents()).run(future).status == "BLOCKED_CONTEXT"
    naive = dict(CONTEXT, observed_at="2026-10-25T12:00:00")
    assert MotherOrchestratorV1(agents()).run(naive).status == "BLOCKED_CONTEXT"


def test_mutating_specialist_cannot_poison_following_context():
    a = agents(data_quality=Stub("data_quality", mutate=True))
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.decision == "LONG"
    assert a["market_structure"].seen[0]["scope"]["symbol"] == "BTCUSDT"


def test_duplicate_and_malformed_evidence_refs_fail_closed():
    a = agents(signal=Stub("signal", refs=("bad-hash",)))
    # References are opaque source identifiers at this layer; they are still
    # type/length checked, while canonical SHA-256 provenance is in the context.
    r = MotherOrchestratorV1(a).run(CONTEXT)
    assert r.decision == "LONG"
    a = agents(signal=Stub("signal", refs=("x" * 513,)))
    assert MotherOrchestratorV1(a).run(CONTEXT).status == "BLOCKED_INVALID_RESULT"


def test_trace_is_stable_for_identical_context_and_stage_outputs():
    first = MotherOrchestratorV1(agents()).run(CONTEXT)
    second = MotherOrchestratorV1(agents()).run(CONTEXT)
    assert first.trace_id == second.trace_id
    assert first.audit_sha256 == second.audit_sha256
