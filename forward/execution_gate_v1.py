"""Fail-closed live-execution boundary contract.

Defines the preflight between an approved decision and a venue adapter. No
concrete live adapter or order-submission side effect ships in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol
import hashlib


Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class ExecutionEvidenceV1:
    decision_id: str
    signal_agent_version: str
    side: Side
    source_sha256: str
    symbol_mapping_ref: str
    structure_evidence_ref: str
    strategy_quality_evidence_ref: str
    risk_policy_version: str
    risk_evidence_ref: str
    account_reconciliation_ref: str
    observed_at: datetime
    entry: Decimal | str | int | float
    stop_loss: Decimal | str | int | float
    take_profit: Decimal | str | int | float
    quantity: Decimal | str | int | float
    reward_risk_minimum: Decimal | str | int | float = "3"


@dataclass(frozen=True)
class ExecutionPermitV1:
    allowed: bool
    reason_codes: tuple[str, ...]
    client_order_id: str | None = None


@dataclass(frozen=True)
class ExecutionRuntimeStateV1:
    live_mode_enabled: bool = False
    kill_switch_clear: bool = False
    venue_adapter_approved: bool = False
    venue_health_ref: str = ""
    account_reconciled: bool = False
    operator_approval_ref: str = ""
    deployment_sha: str = ""
    environment: str = "development"


class ExecutionAdapterV1(Protocol):
    """Interface contract only; implementations require independent review."""

    def submit_order(self, *, client_order_id: str, side: Side,
                     quantity: Decimal, entry: Decimal,
                     stop_loss: Decimal, take_profit: Decimal) -> object: ...

    def get_order(self, *, client_order_id: str) -> object: ...


class ExecutionGateV1:
    """Deterministic, fail-closed preflight; never submits orders itself."""

    VERSION = "hes-execution-gate-v1"

    @staticmethod
    def _decimal(value: object) -> Decimal | None:
        if isinstance(value, bool):
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return result if result.is_finite() and result > 0 else None

    @staticmethod
    def _has_text(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def evaluate(
        self,
        *,
        evidence: ExecutionEvidenceV1 | None,
        runtime: ExecutionRuntimeStateV1,
        now: datetime,
        max_evidence_age_seconds: int = 90,
        duplicate_client_order_id: bool = False,
    ) -> ExecutionPermitV1:
        if evidence is None:
            return ExecutionPermitV1(False, ("EXECUTION_EVIDENCE_MISSING",))
        reasons: list[str] = []
        now_valid = isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset() is not None
        evidence_time_valid = (
            isinstance(evidence.observed_at, datetime)
            and evidence.observed_at.tzinfo is not None
            and evidence.observed_at.utcoffset() is not None
        )
        if not now_valid:
            reasons.append("CURRENT_TIME_MUST_BE_TIMEZONE_AWARE")
        if not evidence_time_valid:
            reasons.append("EVIDENCE_TIME_MUST_BE_TIMEZONE_AWARE")
        elif now_valid:
            age = (now - evidence.observed_at).total_seconds()
            if age < 0:
                reasons.append("FUTURE_EVIDENCE_REJECTED")
            elif not isinstance(max_evidence_age_seconds, int) or max_evidence_age_seconds < 0:
                reasons.append("MAX_EVIDENCE_AGE_POLICY_INVALID")
            elif age > max_evidence_age_seconds:
                reasons.append("EXECUTION_EVIDENCE_STALE")

        if not self._has_text(evidence.decision_id):
            reasons.append("DECISION_ID_MISSING")
        if not self._has_text(evidence.signal_agent_version):
            reasons.append("SIGNAL_AGENT_VERSION_MISSING")
        if evidence.side not in ("LONG", "SHORT"):
            reasons.append("SIDE_INVALID")
        digest = evidence.source_sha256
        if not isinstance(digest, str) or len(digest) != 64 or any(
            c not in "0123456789abcdef" for c in digest.lower()
        ):
            reasons.append("SOURCE_HASH_INVALID")

        for value, reason in (
            (evidence.symbol_mapping_ref, "SYMBOL_MAPPING_EVIDENCE_MISSING"),
            (evidence.structure_evidence_ref, "STRUCTURE_EVIDENCE_MISSING"),
            (evidence.strategy_quality_evidence_ref, "STRATEGY_QUALITY_EVIDENCE_MISSING"),
            (evidence.risk_policy_version, "RISK_POLICY_VERSION_MISSING"),
            (evidence.risk_evidence_ref, "RISK_EVIDENCE_MISSING"),
            (evidence.account_reconciliation_ref, "ACCOUNT_RECONCILIATION_EVIDENCE_MISSING"),
        ):
            if not self._has_text(value):
                reasons.append(reason)

        entry, stop, target, quantity, rr_min = (
            self._decimal(evidence.entry), self._decimal(evidence.stop_loss),
            self._decimal(evidence.take_profit), self._decimal(evidence.quantity),
            self._decimal(evidence.reward_risk_minimum),
        )
        if any(v is None for v in (entry, stop, target, quantity, rr_min)):
            reasons.append("ORDER_GEOMETRY_OR_QUANTITY_INVALID")
        elif evidence.side == "LONG":
            if not stop < entry < target:
                reasons.append("LONG_ORDER_GEOMETRY_INVALID")
            elif (target - entry) / (entry - stop) < rr_min:
                reasons.append("REWARD_RISK_BELOW_POLICY_MINIMUM")
        elif evidence.side == "SHORT":
            if not target < entry < stop:
                reasons.append("SHORT_ORDER_GEOMETRY_INVALID")
            elif (entry - target) / (stop - entry) < rr_min:
                reasons.append("REWARD_RISK_BELOW_POLICY_MINIMUM")

        if runtime.environment != "production":
            reasons.append("NON_PRODUCTION_ENVIRONMENT")
        if runtime.live_mode_enabled is not True:
            reasons.append("LIVE_MODE_NOT_EXPLICITLY_ENABLED")
        if runtime.kill_switch_clear is not True:
            reasons.append("KILL_SWITCH_ACTIVE_OR_UNKNOWN")
        if runtime.venue_adapter_approved is not True:
            reasons.append("VENUE_ADAPTER_NOT_APPROVED")
        if not self._has_text(runtime.venue_health_ref):
            reasons.append("VENUE_HEALTH_EVIDENCE_MISSING")
        if runtime.account_reconciled is not True:
            reasons.append("ACCOUNT_NOT_RECONCILED")
        if not self._has_text(runtime.operator_approval_ref):
            reasons.append("OPERATOR_APPROVAL_MISSING")
        if not self._has_text(runtime.deployment_sha):
            reasons.append("DEPLOYMENT_SHA_MISSING")
        if duplicate_client_order_id:
            reasons.append("DUPLICATE_ORDER_ID_REJECTED")

        reasons = list(dict.fromkeys(reasons))
        if reasons:
            return ExecutionPermitV1(False, tuple(reasons))
        client_id = "hes-" + hashlib.sha256(
            f"{self.VERSION}|{evidence.decision_id}|{evidence.source_sha256}".encode()
        ).hexdigest()[:32]
        return ExecutionPermitV1(True, ("ALL_EXECUTION_PRECHECKS_PASSED",), client_id)
