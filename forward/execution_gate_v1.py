"""Fail-closed live-execution boundary contract.

This module defines the last safety boundary between an approved decision and a
venue adapter. It intentionally ships with no live venue adapter and no order
submission side effects. Production must inject a separately reviewed adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol


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
    """Contract only. A concrete venue adapter must be separately reviewed."""

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

    def evaluate(
        self,
        *,
        evidence: ExecutionEvidenceV1 | None,
        runtime: ExecutionRuntimeStateV1,
        now: datetime,
        max_evidence_age_seconds: int = 90,
        duplicate_client_order_id: bool = False,
    ) -> ExecutionPermitV1:
        reasons: list[str] = []
        if evidence is None:
            return ExecutionPermitV1(False, ("EXECUTION_EVIDENCE_MISSING",))
        if now.tzinfo is None or now.utcoffset() is None:
            reasons.append("CURRENT_TIME_MUST_BE_TIMEZONE_AWARE")
        if evidence.observed_at.tzinfo is None or evidence.observed_at.utcoffset() is None:
            reasons.append("EVIDENCE_TIME_MUST_BE_TIMEZONE_AWARE")
        elif now.tzinfo is not None and now.utcoffset() is not None:
            age = (now - evidence.observed_at).total_seconds()
            if age < 0:
                reasons.append("FUTURE_EVIDENCE_REJECTED")
            elif age > max_evidence_age_seconds:
                reasons.append("EXECUTION_EVIDENCE_STALE")
        if not evidence.decision_id.strip():
            reasons.append("DECISION_ID_MISSING")
        if not evidence.signal_agent_version.strip():
            reasons.append("SIGNAL_AGENT_VERSION_MISSING")
        if evidence.side not in ("LONG", "SHORT"):
            reasons.append("SIDE_INVALID")
        if len(evidence.source_sha256) != 64 or any(c not in "0123456789abcdef" for c in evidence.source_sha256.lower()):
            reasons.append("SOURCE_HASH_INVALID")
        for value, reason in (
            (evidence.symbol_mapping_ref, "SYMBOL_MAPPING_EVIDENCE_MISSING"),
            (evidence.structure_evidence_ref, "STRUCTURE_EVIDENCE_MISSING"),
            (evidence.strategy_quality_evidence_ref, "STRATEGY_QUALITY_EVIDENCE_MISSING"),
            (evidence.risk_policy_version, "RISK_POLICY_VERSION_MISSING"),
            (evidence.risk_evidence_ref, "RISK_EVIDENCE_MISSING"),
            (evidence.account_reconciliation_ref, "ACCOUNT_RECONCILIATION_EVIDENCE_MISSING"),
        ):
            if not isinstance(value, str) or not value.strip():
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
        if not runtime.live_mode_enabled:
            reasons.append("LIVE_MODE_NOT_EXPLICITLY_ENABLED")
        if not runtime.kill_switch_clear:
            reasons.append("KILL_SWITCH_ACTIVE_OR_UNKNOWN")
        if not runtime.venue_adapter_approved:
            reasons.append("VENUE_ADAPTER_NOT_APPROVED")
        if not runtime.venue_health_ref.strip():
            reasons.append("VENUE_HEALTH_EVIDENCE_MISSING")
        if not runtime.account_reconciled:
            reasons.append("ACCOUNT_NOT_RECONCILED")
        if not runtime.operator_approval_ref.strip():
            reasons.append("OPERATOR_APPROVAL_MISSING")
        if not runtime.deployment_sha.strip():
            reasons.append("DEPLOYMENT_SHA_MISSING")
        if duplicate_client_order_id:
            reasons.append("DUPLICATE_ORDER_ID_REJECTED")

        # Stable order and no silent success on unknown or absent prerequisites.
        reasons = list(dict.fromkeys(reasons))
        if reasons:
            return ExecutionPermitV1(False, tuple(reasons))
        # Deterministic client ID enables an external durable journal to dedupe.
        import hashlib
        client_id = "hes-" + hashlib.sha256(
            f"{self.VERSION}|{evidence.decision_id}|{evidence.source_sha256}".encode()
        ).hexdigest()[:32]
        return ExecutionPermitV1(True, ("ALL_EXECUTION_PRECHECKS_PASSED",), client_id)
