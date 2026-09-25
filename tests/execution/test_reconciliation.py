from core.execution.contract import ExecutionAction
from core.execution.order_state import OrderState
from core.execution.reconciliation import (
    ExpectedOrder,
    ObservedOrder,
    OrderReconciler,
    ReconciliationStatus,
)


def _expected() -> ExpectedOrder:
    return ExpectedOrder(
        request_id="req-1",
        action=ExecutionAction.ENTER_LONG,
        symbol="BTC_USDT",
        state=OrderState.ACCEPTED,
    )


def test_matching_order_is_reconciled() -> None:
    expected = _expected()
    observed = ObservedOrder(
        request_id="req-1",
        action=ExecutionAction.ENTER_LONG,
        symbol="BTC_USDT",
        state=OrderState.ACCEPTED,
    )

    result = OrderReconciler().reconcile(expected, observed)

    assert result.status is ReconciliationStatus.MATCHED
    assert result.request_id == "req-1"


def test_missing_order_is_detected() -> None:
    result = OrderReconciler().reconcile(_expected(), None)

    assert result.status is ReconciliationStatus.MISSING


def test_unexpected_identity_is_detected() -> None:
    observed = ObservedOrder(
        request_id="req-other",
        action=ExecutionAction.ENTER_LONG,
        symbol="BTC_USDT",
        state=OrderState.ACCEPTED,
    )

    result = OrderReconciler().reconcile(_expected(), observed)

    assert result.status is ReconciliationStatus.UNEXPECTED


def test_state_or_order_fields_mismatch() -> None:
    observed = ObservedOrder(
        request_id="req-1",
        action=ExecutionAction.ENTER_SHORT,
        symbol="BTC_USDT",
        state=OrderState.ACCEPTED,
    )

    result = OrderReconciler().reconcile(_expected(), observed)

    assert result.status is ReconciliationStatus.MISMATCH


def test_reconciliation_is_execution_free() -> None:
    expected = _expected()
    observed = ObservedOrder(
        request_id="req-1",
        action=ExecutionAction.ENTER_LONG,
        symbol="BTC_USDT",
        state=OrderState.ACCEPTED,
    )

    result = OrderReconciler().reconcile(expected, observed)

    assert result.status is ReconciliationStatus.MATCHED
    assert result.reason
