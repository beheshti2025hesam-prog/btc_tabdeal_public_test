"""Execution safety contracts for HES Trade Agent.

This package defines execution boundaries only. It does not connect to venues,
submit orders, mutate capital, or enable live trading.
"""

from .idempotency import IdempotencyKey, IdempotencyRecord, IdempotencyRegistry

__all__ = [
    "IdempotencyKey",
    "IdempotencyRecord",
    "IdempotencyRegistry",
]

from .order_state import OrderEvent, OrderState, OrderStateMachine

__all__ += ["OrderEvent", "OrderState", "OrderStateMachine"]

from .reconciliation import (
    ExpectedOrder,
    ObservedOrder,
    OrderReconciler,
    ReconciliationResult,
    ReconciliationStatus,
)

__all__ += [
    "ExpectedOrder",
    "ObservedOrder",
    "OrderReconciler",
    "ReconciliationResult",
    "ReconciliationStatus",
]
