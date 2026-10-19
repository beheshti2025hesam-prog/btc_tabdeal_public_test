"""Execution-free reconciliation contract for HES Trade Agent.

This module compares expected execution state with observed execution state.
It performs no venue connection, order submission, capital mutation, or live
trading.
"""

from dataclasses import dataclass
from enum import Enum

from .contract import ExecutionAction
from .order_state import OrderState


class ReconciliationStatus(str, Enum):
    MATCHED = "MATCHED"
    MISSING = "MISSING"
    UNEXPECTED = "UNEXPECTED"
    MISMATCH = "MISMATCH"


@dataclass(frozen=True)
class ExpectedOrder:
    """Immutable expected order identity and lifecycle state."""

    request_id: str
    action: ExecutionAction
    symbol: str
    state: OrderState


@dataclass(frozen=True)
class ObservedOrder:
    """Immutable externally observed order identity and lifecycle state."""

    request_id: str
    action: ExecutionAction
    symbol: str
    state: OrderState


@dataclass(frozen=True)
class ReconciliationResult:
    """Deterministic comparison result for one expected/observed order pair."""

    status: ReconciliationStatus
    request_id: str
    reason: str


class OrderReconciler:
    """Compare expected and observed order records without executing anything."""

    def reconcile(
        self,
        expected: ExpectedOrder,
        observed: ObservedOrder | None,
    ) -> ReconciliationResult:
        if observed is None:
            return ReconciliationResult(
                status=ReconciliationStatus.MISSING,
                request_id=expected.request_id,
                reason="expected order is not observed",
            )

        if observed.request_id != expected.request_id:
            return ReconciliationResult(
                status=ReconciliationStatus.UNEXPECTED,
                request_id=expected.request_id,
                reason="observed order identity does not match expected request",
            )

        if (
            observed.action != expected.action
            or observed.symbol != expected.symbol
            or observed.state != expected.state
        ):
            return ReconciliationResult(
                status=ReconciliationStatus.MISMATCH,
                request_id=expected.request_id,
                reason="observed order differs from expected order",
            )

        return ReconciliationResult(
            status=ReconciliationStatus.MATCHED,
            request_id=expected.request_id,
            reason="expected and observed order match",
        )
