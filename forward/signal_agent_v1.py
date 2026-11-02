"""Fail-closed, forward-only Signal Agent composition.

This composes the existing opportunity, confirmation, risk and decision layers.
It does not calculate indicators, fetch market data, tune thresholds, or execute orders.
All policy evidence must be supplied by the validated upstream feature pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Sequence

from .confirmation_engine_v1 import ConfirmationCheck, ConfirmationEngineV1
from .confirmation_policy_v1 import ConfirmationPolicyV1
from .decision_engine_v1 import DecisionEngineV1, DecisionResult
from .opportunity_detector_v1 import OpportunityCandidate, OpportunityDetectorV1
from .opportunity_policy_v1 import OpportunityPolicyV1
from .risk_gate_v1 import RiskCheck, RiskGateV1, RiskGateResult
from .risk_policy_v1 import RiskPolicyV1
from .strategy_policy_v1 import StrategyEvidenceCheckV1, StrategyPolicyV1, StrategyQualityResultV1


@dataclass(frozen=True)
class RiskGeometryV1:
    """Explicit, independently checked entry/stop/target geometry.

    The project's existing baseline uses a minimum 3:1 reward-to-risk target.
    Values may be Decimal-compatible numbers or strings; binary floats are
    converted through their string representation before Decimal arithmetic.
    """

    entry: Decimal | str | int | float
    stop_loss: Decimal | str | int | float
    take_profit: Decimal | str | int | float


@dataclass(frozen=True)
class SignalAgentResult:
    observed_at: datetime
    candidate: OpportunityCandidate
    confirmation: object
    risk: RiskGateResult
    decision: DecisionResult
    blocked_reasons: tuple[str, ...]
    strategy_quality: StrategyQualityResultV1 | None = None


class SignalAgentV1:
    """Deterministic Signal -> Confirmation -> Risk -> Decision chain.

    The default analysis profile is the approved canonical Gate.io Spot BTCUSDT / 15m source.
    Other venue/product/symbol/timeframe scopes fail closed until a separately
    configured and versioned policy approves them. No orders are submitted.
    """

    VERSION = "hes-signal-agent-v1"
    MIN_REWARD_RISK = Decimal("3")
    REQUIRED_PRECHECKS = ("structure_direction_aligned", "signal_quality_gate_passed")

    def __init__(self, *, allowed_scopes=(("gateio", "spot", "BTCUSDT", "15m"),)) -> None:
        self.allowed_scopes = tuple(tuple(scope) for scope in allowed_scopes)
        if not self.allowed_scopes or any(len(scope) != 4 or any(not isinstance(v, str) or not v for v in scope) for scope in self.allowed_scopes):
            raise ValueError("allowed_scopes must contain explicit venue/product/symbol/timeframe tuples")
        self.strategy_policy = StrategyPolicyV1()
        self.detector = OpportunityDetectorV1(
            policy=OpportunityPolicyV1(
                allowed_scopes=tuple((scope[2], scope[3]) for scope in self.allowed_scopes)
            )
        )
        self.confirmation_engine = ConfirmationEngineV1(policy=ConfirmationPolicyV1())
        self.risk_gate = RiskGateV1(policy=RiskPolicyV1())
        self.decision_engine = DecisionEngineV1()

    @staticmethod
    def _validate_observation(observed_at: datetime, checks: Sequence[object]) -> tuple[str, ...]:
        reasons: list[str] = []
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
            return ("OBSERVED_AT_MUST_BE_TIMEZONE_AWARE",)
        names = [getattr(check, "name", None) for check in checks]
        if any(not isinstance(name, str) or not name.strip() for name in names):
            reasons.append("EVIDENCE_CHECK_NAME_MISSING")
        valid_names = [name for name in names if isinstance(name, str) and name.strip()]
        if len(valid_names) != len(set(valid_names)):
            reasons.append("DUPLICATE_EVIDENCE_CHECK_NAME")
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

    @classmethod
    def _validate_risk_geometry(cls, geometry: RiskGeometryV1 | None, direction: str) -> tuple[str, ...]:
        if geometry is None:
            return ("RISK_GEOMETRY_MISSING",)
        try:
            if any(isinstance(v, bool) for v in (geometry.entry, geometry.stop_loss, geometry.take_profit)):
                return ("RISK_GEOMETRY_INVALID_NUMBER",)
            entry, stop, target = (
                Decimal(str(geometry.entry)),
                Decimal(str(geometry.stop_loss)),
                Decimal(str(geometry.take_profit)),
            )
        except (InvalidOperation, TypeError, ValueError):
            return ("RISK_GEOMETRY_INVALID_NUMBER",)
        if not all(v.is_finite() and v > 0 for v in (entry, stop, target)):
            return ("RISK_GEOMETRY_INVALID_NUMBER",)
        if direction == "BULLISH":
            if not stop < entry < target:
                return ("LONG_RISK_GEOMETRY_ORDER_INVALID",)
            risk, reward = entry - stop, target - entry
        elif direction == "BEARISH":
            if not target < entry < stop:
                return ("SHORT_RISK_GEOMETRY_ORDER_INVALID",)
            risk, reward = stop - entry, entry - target
        else:
            return ("RISK_GEOMETRY_DIRECTION_UNKNOWN",)
        if risk <= 0 or reward <= 0:
            return ("RISK_GEOMETRY_NON_POSITIVE_DISTANCE",)
        if reward / risk < cls.MIN_REWARD_RISK:
            return ("RISK_REWARD_BELOW_MINIMUM_3_TO_1",)
        return ()

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
        venue: str = "",
        product: str = "",
        strategy_checks: Sequence[StrategyEvidenceCheckV1] = (),
        structure_labels: Sequence[str] = (),
        structure_events: Sequence[str] = (),
        structure_direction: str = "UNKNOWN",
        confirmation_checks: Sequence[ConfirmationCheck] = (),
        risk_checks: Sequence[RiskCheck] = (),
        risk_geometry: RiskGeometryV1 | None = None,
    ) -> SignalAgentResult:
        """Evaluate one contemporaneous observation and return LONG/SHORT/NO_TRADE.

        structure_direction must be explicit (BULLISH/BEARISH); BOS/CHOCH alone
        is insufficient. Actual entry/stop/target geometry is independently checked
        against the existing 3:1 minimum reward-to-risk baseline.
        """
        confirmation_checks = tuple(confirmation_checks)
        risk_checks = tuple(risk_checks)
        strategy_checks = tuple(strategy_checks)
        caller_quality_checks = tuple(c for c in confirmation_checks if getattr(c, "name", None) == "signal_quality_gate_passed")
        confirmation_checks = tuple(c for c in confirmation_checks if getattr(c, "name", None) != "signal_quality_gate_passed")
        strategy_quality = self.strategy_policy.evaluate(
            observed_at=observed_at, venue=venue, product=product, symbol=symbol,
            timeframe=timeframe, direction=structure_direction, checks=strategy_checks,
        )
        quality_ref = ("strategy-policy-v1:sha256:" + strategy_quality.evidence_sha256
                       if strategy_quality.evidence_sha256 else "strategy-policy-v1:unavailable")
        confirmation_checks = confirmation_checks + (
            ConfirmationCheck("signal_quality_gate_passed", strategy_quality.state, quality_ref, observed_at),
        )
        all_checks = confirmation_checks + risk_checks + strategy_checks
        invalid = list(self._validate_observation(observed_at, all_checks))
        if caller_quality_checks:
            invalid.append("EXTERNAL_STRATEGY_QUALITY_OVERRIDE_REJECTED")
        invalid = tuple(dict.fromkeys(invalid))
        geometry_reasons = self._validate_risk_geometry(risk_geometry, structure_direction)
        direction_matches = (
            (regime == "UPTREND" and structure_direction == "BULLISH")
            or (regime == "DOWNTREND" and structure_direction == "BEARISH")
        )
        scope_matches = (venue, product, symbol, timeframe) in self.allowed_scopes
        precheck_by_name = {c.name: c for c in confirmation_checks if isinstance(getattr(c, "name", None), str)}
        missing_prechecks = tuple(n for n in self.REQUIRED_PRECHECKS if n not in precheck_by_name)
        failed_prechecks = tuple(
            n for n in self.REQUIRED_PRECHECKS
            if n in precheck_by_name and getattr(precheck_by_name[n], "state", None) != "PASS"
        )
        if invalid or geometry_reasons or not direction_matches or not scope_matches or missing_prechecks or failed_prechecks:
            reasons = list(invalid) + list(geometry_reasons)
            if not direction_matches:
                reasons.append("STRUCTURE_DIRECTION_NOT_ALIGNED")
            if not scope_matches:
                reasons.append("STRATEGY_SCOPE_UNSUPPORTED")
            if strategy_quality.state != "PASS":
                reasons.extend(strategy_quality.reason_codes)
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
            return SignalAgentResult(observed_at, candidate, confirmation, risk, decision, tuple(dict.fromkeys(reasons)), strategy_quality)

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
        return SignalAgentResult(observed_at, candidate, confirmation, risk, decision, tuple(dict.fromkeys(blocked)), strategy_quality)
