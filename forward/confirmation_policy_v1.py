"""Explicit forward-only confirmation policy for structure-derived candidates."""
from __future__ import annotations
from .confirmation_engine_v1 import ConfirmationCheck, ConfirmationResult

class ConfirmationPolicyV1:
    """Requires contemporaneous PASS evidence for candidate, direction, regime and event."""

    REQUIRED = ("candidate_valid", "direction_regime_alignment", "structural_event_present")

    def evaluate(self, *, observed_at, candidate, checks=()):
        checks=tuple(checks)
        by_name={c.name:c for c in checks}
        state=getattr(candidate,"state","UNKNOWN")
        if state not in ("CANDIDATE_LONG","CANDIDATE_SHORT"):
            return ConfirmationResult(observed_at,state,checks,0,len(self.REQUIRED),"UNCONFIRMED",("NO_VALID_CANDIDATE",))
        missing=tuple(n for n in self.REQUIRED if n not in by_name)
        if missing:
            return ConfirmationResult(observed_at,state,checks,sum(c.state=="PASS" for c in checks),len(self.REQUIRED),"UNCONFIRMED",("MISSING_EVIDENCE",)+missing)
        if any(c.state=="UNKNOWN" for c in checks):
            return ConfirmationResult(observed_at,state,checks,sum(c.state=="PASS" for c in checks),len(self.REQUIRED),"UNCONFIRMED",("UNKNOWN_EVIDENCE",))
        if any(by_name[n].state!="PASS" for n in self.REQUIRED):
            return ConfirmationResult(observed_at,state,checks,sum(c.state=="PASS" for c in checks),len(self.REQUIRED),"UNCONFIRMED",("REQUIRED_CHECK_FAILED",))
        confirmed="CONFIRMED_LONG" if state=="CANDIDATE_LONG" else "CONFIRMED_SHORT"
        return ConfirmationResult(observed_at,state,checks,len(self.REQUIRED),len(self.REQUIRED),confirmed,("ALL_REQUIRED_CONFIRMATIONS_PASSED",))
