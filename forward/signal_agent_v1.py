"""Fail-closed, forward-only Signal Agent composition.

This composes the existing opportunity, confirmation, risk and decision layers.
It does not calculate indicators, fetch market data, tune thresholds, or execute orders.
All policy evidence must be supplied by the validated upstream feature pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .confirmation_engine_v1 import ConfirmationCheck, ConfirmationEngineV1
from .confirmation_policy_v1 import ConfirmationPolicyV1
from .decision_engine_v1 import DecisionEngineV1, DecisionResult
from .opportunity_detector_v1 import OpportunityCandidate, OpportunityDetectorV1
from .opportunity_policy_v1 import OpportunityPolicyV1
from .risk_gate_v1 import RiskCheck, RiskGateV1, RiskGateResult
from .risk_policy_v1 import RiskPolicyV1


@dataclass(frozen=True)
class SignalAgentResult:
    observed_at: datetime
    candidate: OpportunityCandidate
    confirmation: object
    risk: RiskGateResult
    decision: DecisionResult
    blocked_reasons: tuple[str, ...]


class SignalAgentV1:
    """Deterministic Signal -> Confirmation -> Risk -> Decision chain.

    The default scope follows the already-established forward baseline:
    BTC_USDT / 15m. Any other scope is rejected by the existing opportunity policy.
    No orders or external side effects are performed.
    """

    VERSION = "hes-signal-agent-v1"
    REQUIRED_PRECHECKS = ("structure_direction_aligned", "signal_quality_gate_passed")

    def __init__(self) -> None:
        self.detector = OpportunityDetectorV1(policy=OpportunityPolicyV1())
        self.confirmation_engine = ConfirmationEngineV1(policy=ConfirmationPolicyV1())
        self.risk_gate = RiskGateV1(policy=RiskPolicyV1())
        self.decision_engine = DecisionEngineV1()

    @staticmethod
    def _validate_observation(observed_at: datetime, checks: Sequence[object]) -> tuple[str, ...]:
        reasons: list[str] = []
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
            return ("OBSERVED_AT_MUST_BE_TIMEZONE_AWARE",)
        for check in checks:
            stamp = getattr(check, "observed_at", None)
            if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
                reasons.append("EVIDENCE_TIMESTAMP_INVALID")
                continue
            if stamp > observed_at:
                reasons.append("FUTURE_EVIDENCE_REJECTED")
            ref = getattr(check, "evidence_ref", None)
            if not isinstance(ref, str) or not ref.strip():
                reasons.append("EVIDENCE_REFERENCE_MISSING")
            state = getattr(check, "state", None)
            if state not in ("PASS", "FAIL", "UNKNOWN"):
                reasons.append("EVIDENCE_STATE_INVALID")
        return tuple(dict.fromkeys(reasons))

    @staticmethod
    def _blocked_candidate(observed_at, symbol, timeframe, regime, labels, events, reason):
        return OpportunityCandidate(
            observed_at, symbol, timeframe, "NO_CANDIDATE", regime,
            tuple(labels), tuple(events), (reason,),
        )

    def evaluate(
        self,
        *,
        observed_at: datetime,
        symbol: str,
        timeframe: str,
        regime: str,
        structure_labels: Sequence[str] = (),
        structure_events: Sequence[str] = (),
        structure_direction: str = "UNKNOWN",
        confirmation_checks: Sequence[ConfirmationCheck] = (),
        risk_checks: Sequence[RiskCheck] = (),
    ) -> SignalAgentResult:
        """Evaluate one contemporaneous observation and return LONG/SHORT/NO_TRADE.

        structure_direction must be an explicit upstream result (BULLISH/BEARISH);
        a generic BOS/CHOCH token alone is not sufficient directional evidence.
        """
        confirmation_checks = tuple(confirmation_checks)
        risk_checks = tuple(risk_checks)
        all_checks = confirmation_checks + risk_checks
        invalid = self._validate_observation(observed_at, all_checks)
        direction_matches = (
            (regime == "UPTREND" and structure_direction == "BULLISH")
            or (regime == "DOWNTREND" and structure_direction == "BEARISH")
        )
        precheck_by_name = {c.name: c for c in confirmation_checks if isinstance(getattr(c, "name", None), str)}
        missing_prechecks = tuple(n for n in self.REQUIRED_PRECHECKS if n not in precheck_by_name)
        failed_prechecks = tuple(
            n for n in self.REQUIRED_PRECHECKS
            if n in precheck_by_name and getattr(precheck_by_name[n], "state", None) != "PASS"
        )
        if invalid or not direction_matches or missing_prechecks or failed_prechecks:
            reasons = list(invalid)
            if not direction_matches:
                reasons.append("STRUCTURE_DIRECTION_NOT_ALIGNED")
            if missing_prechecks:
                reasons.extend("MISSING_" + n.upper() for n in missing_prechecks)
            if failed_prechecks:
                reasons.extend("FAILED_" + n.upper() for n in failed_prechecks)
            candidate = self._blocked_candidate(
                observed_at, symbol, timeframe, regime, structure_labels,
                structure_events, reasons[0] if reasons else "PRECHECK_FAILED",
            )
            confirmation = self.confirmation_engine.evaluate(
                observed_at=observed_at, candidate=candidate, checks=confirmation_checks
            )
            risk = self.risk_gate.evaluate(observed_at=observed_at, confirmation=confirmation, checks=risk_checks)
            decision = self.decision_engine.evaluate(
                observed_at=observed_at, candidate=candidate, confirmation=confirmation, risk=risk
            )
            return SignalAgentResult(observed_at, candidate, confirmation, risk, decision, tuple(dict.fromkeys(reasons)))

        candidate = self.detector.evaluate(
            observed_at=observed_at,
            symbol=symbol,
            timeframe=timeframe,
            regime=regime,
            structure_labels=structure_labels,
            structure_events=structure_events,
        )
        confirmation = self.confirmation_engine.evaluate(
            observed_at=observed_at, candidate=candidate, checks=confirmation_checks
        )
        risk = self.risk_gate.evaluate(
            observed_at=observed_at, confirmation=confirmation, checks=risk_checks
        )
        decision = self.decision_engine.evaluate(
            observed_at=observed_at, candidate=candidate, confirmation=confirmation, risk=risk
        )
        blocked = tuple(
            list(candidate.reason_codes)
            + list(getattr(confirmation, "reason_codes", ()))
            + list(risk.reason_codes)
            + list(decision.reason_codes if decision.decision == "NO_TRADE" else ())
        )
        return SignalAgentResult(observed_at, candidate, confirmation, risk, decision, tuple(dict.fromkeys(blocked)))
