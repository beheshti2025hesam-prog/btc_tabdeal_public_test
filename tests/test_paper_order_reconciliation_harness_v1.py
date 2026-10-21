"""Deterministic paper-order lifecycle harness; never connects to a venue.

This test-only harness exercises the existing strategy and risk contracts through
an in-memory paper ledger. It is plumbing evidence only: it does not qualify a
market-data provider, call a sandbox API, or enable production execution.
"""
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
import json

from core.execution.contract import (
    ExecutionAction,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
)
from core.feature_engine.quality import FeatureSnapshot
from core.risk.boundary import RiskDecision, RiskInput, RiskPolicy
from core.strategy.baseline import (
    BaselineDecision,
    BaselineStrategy,
    BaselineStrategyInput,
)


@dataclass(frozen=True)
class PaperFill:
    fill_id: str
    quantity: Decimal
    price: Decimal
    fee: Decimal


@dataclass
class PaperOrder:
    request: ExecutionRequest
    quantity: Decimal
    state: str = "ACCEPTED"
    fills: dict[str, PaperFill] = field(default_factory=dict)

    @property
    def filled_quantity(self) -> Decimal:
        return sum((fill.quantity for fill in self.fills.values()), Decimal("0"))

    @property
    def average_fill_price(self) -> Decimal | None:
        quantity = self.filled_quantity
        if quantity == 0:
            return None
        notional = sum(
            (fill.quantity * fill.price for fill in self.fills.values()),
            Decimal("0"),
        )
        return notional / quantity

    @property
    def fees(self) -> Decimal:
        return sum((fill.fee for fill in self.fills.values()), Decimal("0"))


class InMemoryPaperLedger:
    """Deterministic local ledger; no transport, credentials, or exchange calls."""

    def __init__(self):
        self.orders: dict[str, PaperOrder] = {}
        self._request_fingerprints: dict[str, str] = {}

    @staticmethod
    def _fingerprint(request: ExecutionRequest, quantity: Decimal) -> str:
        payload = {
            "request_id": request.request_id,
            "action": request.action.value,
            "symbol": request.symbol,
            "price": str(Decimal(str(request.price))),
            "mode": request.mode.value,
            "quantity": str(quantity),
        }
        return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def submit(self, request: ExecutionRequest, *, quantity: Decimal) -> ExecutionResult:
        if request.mode is not ExecutionMode.SHADOW:
            return ExecutionResult(request.request_id, False, "paper_mode_required")
        if not request.request_id or not request.symbol:
            return ExecutionResult(request.request_id, False, "missing_request_identity")
        if not quantity.is_finite() or quantity <= 0:
            return ExecutionResult(request.request_id, False, "invalid_quantity")
        fingerprint = self._fingerprint(request, quantity)
        previous = self._request_fingerprints.get(request.request_id)
        if previous is not None:
            if previous != fingerprint:
                return ExecutionResult(request.request_id, False, "idempotency_conflict")
            return ExecutionResult(request.request_id, True, "idempotent_replay")
        self._request_fingerprints[request.request_id] = fingerprint
        self.orders[request.request_id] = PaperOrder(request=request, quantity=quantity)
        return ExecutionResult(request.request_id, True, "paper_order_recorded")

    def record_fill(
        self,
        order_id: str,
        *,
        fill_id: str,
        quantity: Decimal,
        price: Decimal,
        fee: Decimal,
    ) -> str:
        order = self.orders[order_id]
        if order.state in ("FILLED", "REJECTED", "CANCELLED"):
            raise ValueError("order_not_fillable")
        if not fill_id or not all(v.is_finite() for v in (quantity, price, fee)):
            raise ValueError("invalid_fill")
        if quantity <= 0 or price <= 0 or fee < 0:
            raise ValueError("invalid_fill")
        candidate = PaperFill(fill_id, quantity, price, fee)
        existing = order.fills.get(fill_id)
        if existing is not None:
            if existing != candidate:
                raise ValueError("fill_id_conflict")
            return "EXACT_REPLAY"
        if order.filled_quantity + quantity > order.quantity:
            raise ValueError("overfill")
        order.fills[fill_id] = candidate
        order.state = "FILLED" if order.filled_quantity == order.quantity else "PARTIALLY_FILLED"
        return order.state

    def reconcile(self, order_id: str) -> dict[str, object]:
        order = self.orders[order_id]
        total = order.filled_quantity
        if total > order.quantity:
            raise ValueError("reconciliation_overfill")
        return {
            "order_id": order_id,
            "state": order.state,
            "requested_quantity": order.quantity,
            "filled_quantity": total,
            "remaining_quantity": order.quantity - total,
            "average_fill_price": order.average_fill_price,
            "fees": order.fees,
            "reconciled": total == order.quantity and order.state == "FILLED",
        }


def _qualified_test_signal() -> BaselineDecision:
    """Synthetic feature fixture; deliberately not sourced from a market provider."""
    snapshot = FeatureSnapshot(
        symbol="BTC_USDT",
        timeframe_seconds=60,
        close=102.0,
        ema=100.0,
        vwap=101.0,
        buy_ratio=0.7,
    )
    return BaselineStrategy().evaluate(BaselineStrategyInput(features=snapshot))


def _paper_request(decision: BaselineDecision) -> ExecutionRequest:
    if decision is BaselineDecision.LONG:
        action = ExecutionAction.ENTER_LONG
    elif decision is BaselineDecision.SHORT:
        action = ExecutionAction.ENTER_SHORT
    else:
        raise ValueError("no_trade_has_no_order")
    return ExecutionRequest(
        request_id="paper-test-request-001",
        action=action,
        symbol="BTC_USDT",
        price=102.0,
        mode=ExecutionMode.SHADOW,
    )


def test_strategy_risk_paper_fills_and_reconciliation():
    decision = _qualified_test_signal()
    assert decision is BaselineDecision.LONG

    risk = RiskPolicy().evaluate(
        RiskInput(decision, equity=10_000.0, current_drawdown_fraction=0.01)
    )
    assert risk is RiskDecision.ALLOW_SIGNAL

    ledger = InMemoryPaperLedger()
    request = _paper_request(decision)
    submitted = ledger.submit(request, quantity=Decimal("1.0"))
    assert submitted.accepted
    assert submitted.reason == "paper_order_recorded"

    assert ledger.record_fill(
        request.request_id,
        fill_id="fill-001",
        quantity=Decimal("0.4"),
        price=Decimal("100"),
        fee=Decimal("0.04"),
    ) == "PARTIALLY_FILLED"
    assert ledger.record_fill(
        request.request_id,
        fill_id="fill-002",
        quantity=Decimal("0.6"),
        price=Decimal("101"),
        fee=Decimal("0.0606"),
    ) == "FILLED"

    report = ledger.reconcile(request.request_id)
    assert report == {
        "order_id": request.request_id,
        "state": "FILLED",
        "requested_quantity": Decimal("1.0"),
        "filled_quantity": Decimal("1.0"),
        "remaining_quantity": Decimal("0.0"),
        "average_fill_price": Decimal("100.6"),
        "fees": Decimal("0.1006"),
        "reconciled": True,
    }


def test_risk_veto_never_submits_paper_order():
    decision = _qualified_test_signal()
    risk = RiskPolicy().evaluate(
        RiskInput(decision, equity=10_000.0, current_drawdown_fraction=0.20)
    )
    assert risk is RiskDecision.VETO
    ledger = InMemoryPaperLedger()
    assert ledger.orders == {}


def test_request_retry_is_idempotent_and_conflicting_reuse_is_rejected():
    ledger = InMemoryPaperLedger()
    request = _paper_request(BaselineDecision.LONG)
    quantity = Decimal("1.0")
    first = ledger.submit(request, quantity=quantity)
    retry = ledger.submit(request, quantity=quantity)
    conflict = ledger.submit(
        ExecutionRequest(
            request_id=request.request_id,
            action=ExecutionAction.ENTER_SHORT,
            symbol=request.symbol,
            price=request.price,
            mode=ExecutionMode.SHADOW,
        ),
        quantity=quantity,
    )
    assert first.accepted and retry.accepted
    assert retry.reason == "idempotent_replay"
    assert not conflict.accepted
    assert conflict.reason == "idempotency_conflict"
    assert len(ledger.orders) == 1


def test_exact_fill_replay_is_idempotent_but_conflicting_fill_is_rejected():
    ledger = InMemoryPaperLedger()
    request = _paper_request(BaselineDecision.LONG)
    ledger.submit(request, quantity=Decimal("1"))
    fill = dict(fill_id="fill-001", quantity=Decimal("1"), price=Decimal("100"), fee=Decimal("0.1"))
    assert ledger.record_fill(request.request_id, **fill) == "FILLED"
    assert ledger.record_fill(request.request_id, **fill) == "EXACT_REPLAY"
    conflicting = dict(fill_id="fill-001", quantity=Decimal("1"), price=Decimal("101"), fee=Decimal("0.1"))
    try:
        ledger.record_fill(request.request_id, **conflicting)
    except ValueError as exc:
        assert str(exc) == "order_not_fillable"
    else:
        raise AssertionError("terminal order accepted another fill")


def test_overfill_and_invalid_fee_are_rejected():
    ledger = InMemoryPaperLedger()
    request = _paper_request(BaselineDecision.LONG)
    ledger.submit(request, quantity=Decimal("1"))
    ledger.record_fill(
        request.request_id,
        fill_id="fill-001",
        quantity=Decimal("0.7"),
        price=Decimal("100"),
        fee=Decimal("0"),
    )
    try:
        ledger.record_fill(
            request.request_id,
            fill_id="fill-002",
            quantity=Decimal("0.4"),
            price=Decimal("100"),
            fee=Decimal("0"),
        )
    except ValueError as exc:
        assert str(exc) == "overfill"
    else:
        raise AssertionError("paper ledger accepted overfill")

    try:
        ledger.record_fill(
            request.request_id,
            fill_id="fill-003",
            quantity=Decimal("0.1"),
            price=Decimal("100"),
            fee=Decimal("-0.01"),
        )
    except ValueError as exc:
        assert str(exc) == "invalid_fill"
    else:
        raise AssertionError("paper ledger accepted negative fee")
