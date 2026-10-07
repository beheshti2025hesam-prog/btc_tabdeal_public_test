"""Observation-only forward regime transition detection."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RegimeTransition:
    status: str
    previous_regime: str
    current_regime: str
    transition: str


class CleanRegimeTransitionV1:
    ALLOWED={"UPTREND","DOWNTREND","TRANSITION_UNCERTAIN"}

    def observe(self, previous_regime: str, current_regime: str) -> RegimeTransition:
        if previous_regime not in self.ALLOWED or current_regime not in self.ALLOWED:
            raise ValueError("invalid regime")
        if previous_regime == current_regime:
            transition="NO_CHANGE"
        elif current_regime == "TRANSITION_UNCERTAIN":
            transition="ENTERED_UNCERTAIN"
        elif previous_regime == "TRANSITION_UNCERTAIN":
            transition="EXITED_UNCERTAIN"
        elif previous_regime == "UPTREND" and current_regime == "DOWNTREND":
            transition="UP_TO_DOWN"
        elif previous_regime == "DOWNTREND" and current_regime == "UPTREND":
            transition="DOWN_TO_UP"
        else:
            transition="REGIME_CHANGE"
        return RegimeTransition("REGIME_TRANSITION_OBSERVED",previous_regime,current_regime,transition)
