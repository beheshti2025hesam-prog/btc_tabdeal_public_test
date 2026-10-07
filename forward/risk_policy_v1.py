"""Explicit observation-only risk policy: evidence completeness and gate integrity."""
from __future__ import annotations
from .risk_gate_v1 import RiskGateResult

class RiskPolicyV1:
    REQUIRED=("confirmation_valid","risk_context_available","execution_disabled")

    def evaluate(self, *, observed_at, confirmation, checks=()):
        checks=tuple(checks); by={c.name:c for c in checks}
        cs=getattr(confirmation,"state","UNKNOWN")
        if cs not in ("CONFIRMED_LONG","CONFIRMED_SHORT"):
            return RiskGateResult(observed_at,cs,checks,"RISK_REJECTED",("CONFIRMATION_NOT_VALID",))
        missing=tuple(n for n in self.REQUIRED if n not in by)
        if missing:
            return RiskGateResult(observed_at,cs,checks,"RISK_REJECTED",("MISSING_RISK_EVIDENCE",)+missing)
        if any(c.state=="UNKNOWN" for c in checks):
            return RiskGateResult(observed_at,cs,checks,"RISK_REJECTED",("UNKNOWN_RISK_EVIDENCE",))
        if any(by[n].state!="PASS" for n in self.REQUIRED):
            return RiskGateResult(observed_at,cs,checks,"RISK_REJECTED",("RISK_CHECK_FAILED",))
        return RiskGateResult(observed_at,cs,checks,"RISK_APPROVED",("ALL_RISK_GATES_PASSED",))
