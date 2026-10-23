import pytest
from core.orchestration.mother_v1 import AgentResult, MotherOrchestratorV1

ORDER = ("data_quality", "market_structure", "signal", "confirmation", "risk", "decision", "evaluation")

class Stub:
    def __init__(self, name, state="PASS", payload=None, raises=False):
        self.name, self.state, self.payload, self.raises = name, state, payload, raises
        self.seen = []
    def evaluate(self, context):
        self.seen.append(context)
        if self.raises: raise RuntimeError("simulated")
        return AgentResult(self.name, self.state, payload=self.payload)

def agents(**overrides):
    return {name: overrides.get(name, Stub(name, "APPROVED" if name=="risk" else "PASS", {"decision":"LONG"} if name=="decision" else None)) for name in ORDER}

def test_missing_specialist_fails_closed():
    a=agents(); a.pop("risk")
    r=MotherOrchestratorV1(a).run({})
    assert r.decision=="NO_TRADE" and not r.execution_authorized and r.status=="BLOCKED_CONFIGURATION"

def test_risk_veto_stops_downstream():
    a=agents(risk=Stub("risk","REJECTED"))
    r=MotherOrchestratorV1(a).run({})
    assert r.decision=="NO_TRADE" and r.status=="BLOCKED_GATE"
    assert len(r.stages)==5 and not a["decision"].seen

def test_agent_exception_fails_closed():
    a=agents(signal=Stub("signal",raises=True))
    r=MotherOrchestratorV1(a).run({})
    assert r.status=="BLOCKED_AGENT_ERROR" and r.decision=="NO_TRADE"

def test_unknown_state_fails_closed():
    a=agents(confirmation=Stub("confirmation","UNKNOWN"))
    r=MotherOrchestratorV1(a).run({})
    assert r.status=="BLOCKED_GATE" and r.decision=="NO_TRADE"

def test_success_is_still_observation_only():
    r=MotherOrchestratorV1(agents()).run({"symbol":"BTCUSDT"})
    assert r.status=="OBSERVATION_ONLY" and r.decision=="LONG"
    assert r.execution_authorized is False
    assert tuple(x.agent for x in r.stages)==ORDER

def test_short_decision_mapping_is_preserved():
    a=agents(decision=Stub("decision", "PASS", {"decision":"SHORT"}))
    r=MotherOrchestratorV1(a).run({})
    assert r.status=="OBSERVATION_ONLY" and r.decision=="SHORT"
    assert r.execution_authorized is False

def test_invalid_decision_payload_fails_closed():
    a=agents(decision=Stub("decision", "PASS", {"decision":"BUY_MORE"}))
    r=MotherOrchestratorV1(a).run({})
    assert r.status=="BLOCKED_INVALID_DECISION" and r.decision=="NO_TRADE"
    assert r.execution_authorized is False

def test_wrong_result_identity_blocks():
    a=agents(signal=Stub("other","PASS"))
    r=MotherOrchestratorV1(a).run({})
    assert r.status=="BLOCKED_INVALID_RESULT" and r.decision=="NO_TRADE"
