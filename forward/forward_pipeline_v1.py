"""Forward pipeline composition boundary.

Pure orchestration only: normalized market data -> structure -> opportunity ->
confirmation -> risk -> decision -> append-only journal. Policies must be
explicitly supplied by callers; this module never tunes them.
"""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class PipelineResult:
    decision: Any
    journal_record: dict

def run_once(*, market_input, structure_engine, opportunity_engine,
             confirmation_engine, risk_gate, decision_engine, journal):
    structure = structure_engine(market_input)
    candidate = opportunity_engine(structure, market_input)
    confirmation = confirmation_engine(candidate, market_input, structure)
    risk = risk_gate(candidate, confirmation, market_input)
    decision = decision_engine(candidate, confirmation, risk, market_input)
    record = decision.as_journal_record()
    journal.append_decision(record)
    return PipelineResult(decision=decision, journal_record=record)
