"""Forward pipeline composition boundary.

Pure orchestration only: normalized market data -> structure -> opportunity ->
confirmation -> risk -> decision -> append-only journal. Policies must be
explicitly supplied by callers; this module never tunes them.
"""
from dataclasses import dataclass
from typing import Any

from .forward_runtime_validation_v1 import validate_decision_record

@dataclass(frozen=True)
class PipelineResult:
    decision: Any
    journal_record: dict

def run_once(*, market_input, structure_engine, opportunity_engine,
             confirmation_engine, risk_gate, decision_engine, journal,
             event_id: str, evidence_source: str):
    structure = structure_engine(market_input)
    candidate = opportunity_engine(structure, market_input)
    confirmation = confirmation_engine(candidate, market_input, structure)
    risk = risk_gate(candidate, confirmation, market_input)
    decision = decision_engine(candidate, confirmation, risk, market_input)
    record = decision.as_journal_record(event_id, evidence_source)
    validation_errors = validate_decision_record(record)
    if validation_errors:
        raise ValueError("invalid forward decision record: " + ",".join(validation_errors))
    journal.append_decision(record)
    return PipelineResult(decision=decision, journal_record=record)


class ForwardPipelineV1:
    """Explicit pipeline adapter used by the runtime bridge.

    The runner is injected by the caller; no policy, strategy, or execution
    behavior is hidden here. This keeps the runtime boundary branch-safe.
    """
    def __init__(self, runner=None):
        self._runner = runner

    def run_once(self, **kwargs):
        if self._runner is None:
            raise RuntimeError("NO_PIPELINE_RUNNER_CONFIGURED")
        return self._runner(**kwargs)
