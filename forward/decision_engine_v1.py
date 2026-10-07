"""Forward-only final decision resolver. No order execution."""
from dataclasses import dataclass
from typing import Literal
Decision = Literal["LONG","SHORT","NO_TRADE"]

@dataclass(frozen=True)
class DecisionResult:
    observed_at: object
    decision: Decision
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    quality_score: float | None = None

class DecisionEngineV1:
    def evaluate(self, *, observed_at, candidate, confirmation, risk) -> DecisionResult:
        cs, fs, rs = (getattr(candidate,"state",None), getattr(confirmation,"state",None), getattr(risk,"state",None))
        if cs=="CANDIDATE_LONG" and fs=="CONFIRMED_LONG" and rs=="RISK_APPROVED":
            return DecisionResult(observed_at,"LONG",("ALL_REQUIRED_GATES_PASSED",),())
        if cs=="CANDIDATE_SHORT" and fs=="CONFIRMED_SHORT" and rs=="RISK_APPROVED":
            return DecisionResult(observed_at,"SHORT",("ALL_REQUIRED_GATES_PASSED",),())
        reasons=[]
        if cs not in ("CANDIDATE_LONG","CANDIDATE_SHORT"): reasons.append("NO_VALID_CANDIDATE")
        if fs not in ("CONFIRMED_LONG","CONFIRMED_SHORT"): reasons.append("CONFIRMATION_NOT_CONFIRMED")
        if rs!="RISK_APPROVED": reasons.append("RISK_NOT_APPROVED")
        return DecisionResult(observed_at,"NO_TRADE",tuple(reasons) or ("FAIL_CLOSED",),())
