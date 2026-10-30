from copy import deepcopy
from datetime import datetime, timezone

from core.orchestration.mother_v1 import AgentResult, MotherOrchestratorV1
from core.orchestration.witness_v1 import MotherAuditWitnessV1


ORDER = ("data_quality", "market_structure", "signal", "confirmation", "risk", "decision", "evaluation")
STATES = {
    "data_quality": "PASS",
    "market_structure": "PASS",
    "signal": "PASS",
    "confirmation": "CONFIRMED",
    "risk": "APPROVED",
    "decision": "DECIDED",
    "evaluation": "OBSERVED",
}
CONTEXT = {
    "scope": {"venue": "binance", "product": "spot", "symbol": "BTCUSDT", "timeframe": "15m"},
    "observed_at": datetime.now(timezone.utc).isoformat(),
    "snapshot_sha256": "a" * 64,
    "evidence_sha256": "b" * 64,
}


class Stub:
    def __init__(self, name, state=None, payload=None, reasons=()):
        self.name = name
        self.state = STATES[name] if state is None else state
        self.payload = ({"decision": "LONG"} if name == "decision" else {}) if payload is None else payload
        self.reasons = reasons

    def evaluate(self, context):
        return AgentResult(self.name, self.state, self.reasons, ("a" * 64,), self.payload, "witness-test-v1")


def agent_map(**overrides):
    return {name: overrides.get(name, Stub(name)) for name in ORDER}


def test_witness_independently_verifies_successful_observation_audit():
    output = MotherOrchestratorV1(agent_map()).run(CONTEXT).as_dict()
    witness = MotherAuditWitnessV1().verify(output)
    assert witness.verified is True
    assert witness.reason_codes == ("WITNESS_VERIFIED",)
    assert witness.audit_sha256 == output["audit_sha256"]
    assert witness.as_dict()["execution_authorized"] is False


def test_witness_accepts_fail_closed_risk_veto_with_partial_stage_chain():
    agents = agent_map(risk=Stub("risk", "REJECTED", reasons=("RISK_BUDGET_UNKNOWN",)))
    output = MotherOrchestratorV1(agents).run(CONTEXT).as_dict()
    witness = MotherAuditWitnessV1().verify(output)
    assert output["decision"] == "NO_TRADE"
    assert output["status"] == "BLOCKED_RISK_VETO"
    assert witness.verified is True


def test_witness_rejects_tampered_audit_fields():
    output = MotherOrchestratorV1(agent_map()).run(CONTEXT).as_dict()
    tampered = deepcopy(output)
    tampered["reason_codes"].append("FABRICATED_REASON")
    result = MotherAuditWitnessV1().verify(tampered)
    assert result.verified is False
    assert result.reason_codes == ("WITNESS_AUDIT_DIGEST_MISMATCH",)


def test_witness_rejects_execution_authorization_even_with_original_hash():
    output = MotherOrchestratorV1(agent_map()).run(CONTEXT).as_dict()
    output["execution_authorized"] = True
    result = MotherAuditWitnessV1().verify(output)
    assert result.verified is False
    assert result.reason_codes == ("WITNESS_EXECUTION_BOUNDARY_VIOLATION",)


def test_witness_rejects_reordered_or_incomplete_observation_stages():
    output = MotherOrchestratorV1(agent_map()).run(CONTEXT).as_dict()
    reordered = deepcopy(output)
    reordered["stages"][0], reordered["stages"][1] = reordered["stages"][1], reordered["stages"][0]
    assert MotherAuditWitnessV1().verify(reordered).verified is False
    incomplete = deepcopy(output)
    incomplete["stages"].pop()
    assert MotherAuditWitnessV1().verify(incomplete).verified is False
