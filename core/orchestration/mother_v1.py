"""Mother orchestrator v1: typed, fail-closed coordination of existing specialist contracts.

This layer coordinates injected specialist agents. It deliberately does not
instantiate data providers, activate services, or execute orders.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

@dataclass(frozen=True)
class AgentResult:
    agent: str
    state: str
    reason_codes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    payload: Any = None

@dataclass(frozen=True)
class OrchestrationResult:
    status: str
    decision: str
    stages: tuple[AgentResult, ...]
    reason_codes: tuple[str, ...]
    execution_authorized: bool = False

class SpecialistAgent(Protocol):
    name: str
    def evaluate(self, context: Mapping[str, Any]) -> AgentResult: ...

def _decision_value(payload: Any) -> Any:
    """Read decision from either typed result objects or mapping payloads."""
    if isinstance(payload, Mapping):
        return payload.get("decision")
    return getattr(payload, "decision", None)


class MotherOrchestratorV1:
    """Run configured specialists in a fixed order; any unknown/error blocks downstream."""
    REQUIRED = ("data_quality", "market_structure", "signal", "confirmation", "risk", "decision", "evaluation")

    def __init__(self, agents: Mapping[str, SpecialistAgent]):
        self.agents = dict(agents)

    def run(self, context: Mapping[str, Any]) -> OrchestrationResult:
        missing = [name for name in self.REQUIRED if name not in self.agents]
        if missing:
            return OrchestrationResult("BLOCKED_CONFIGURATION", "NO_TRADE", (),
                ("MISSING_SPECIALISTS:" + ",".join(missing),), False)
        stages: list[AgentResult] = []
        shared = dict(context)
        for name in self.REQUIRED:
            agent = self.agents[name]
            try:
                result = agent.evaluate(dict(shared))
            except Exception:
                return OrchestrationResult("BLOCKED_AGENT_ERROR", "NO_TRADE", tuple(stages),
                    ("AGENT_EXCEPTION:" + name,), False)
            if not isinstance(result, AgentResult) or result.agent != name:
                return OrchestrationResult("BLOCKED_INVALID_RESULT", "NO_TRADE", tuple(stages),
                    ("INVALID_AGENT_RESULT:" + name,), False)
            stages.append(result)
            shared[name] = result
            if result.state not in {"PASS", "READY", "CONFIRMED", "APPROVED", "OBSERVED"}:
                reasons = result.reason_codes or ("AGENT_NOT_READY:" + name,)
                return OrchestrationResult("BLOCKED_GATE", "NO_TRADE", tuple(stages), tuple(reasons), False)
            if name == "risk" and result.state != "APPROVED":
                return OrchestrationResult("BLOCKED_RISK_VETO", "NO_TRADE", tuple(stages),
                    result.reason_codes or ("RISK_VETO",), False)
            if name == "decision":
                candidate = _decision_value(result.payload)
                if candidate not in {"LONG", "SHORT", "NO_TRADE"}:
                    return OrchestrationResult("BLOCKED_INVALID_DECISION", "NO_TRADE", tuple(stages),
                        ("INVALID_DECISION",), False)
        decision_result = stages[-2] if len(stages) >= 2 else None
        decision = _decision_value(decision_result.payload) if decision_result else None
        if decision not in {"LONG", "SHORT", "NO_TRADE"}:
            decision = "NO_TRADE"
        # Orchestrator is an analysis boundary only; execution requires a separate future gate.
        return OrchestrationResult("OBSERVATION_ONLY", decision, tuple(stages),
            ("EXECUTION_NOT_AUTHORIZED",), False)
