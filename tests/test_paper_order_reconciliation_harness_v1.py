"""Test-only paper lifecycle harness; no network or venue execution is possible."""
from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
import json

from core.execution.contract import ExecutionAction, ExecutionMode, ExecutionRequest, ExecutionResult
from core.feature_engine.quality import FeatureSnapshot
from core.risk.boundary import RiskDecision, RiskInput, RiskPolicy
from core.strategy.baseline import BaselineDecision, BaselineStrategy, BaselineStrategyInput


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
    def filled_quantity(self):
        return sum((f.quantity for f in self.fills.values()), Decimal("0"))

    @property
    def average_fill_price(self):
        qty = self.filled_quantity
        if not qty:
            return None
        notional = sum((f.quantity * f.price for f in self.fills.values()), Decimal("0"))
        return notional / qty

    @property
    def fees(self):
        return sum((f.fee for f in self.fills.values()), Decimal("0"))


class InMemoryPaperLedger:
    """Deterministic test double; it has no transport, credentials, or exchange calls."""

    def __init__(self):
        self.orders: dict[str, PaperOrder] = {}
        self._fingerprints: dict[str, str] = {}

    @staticmethod
    def _fingerprint(request, quantity):
        fields = {
            "request_id": request.request_id, "action": request.action.value,
            "symbol": request.symbol, "price": str(Decimal(str(request.price))),
            "mode": request.mode.value, "quantity": str(quantity),
        }
        return sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()

    def submit(self, request, *, quantity: Decimal) -> ExecutionResult:
        if request.mode is not ExecutionMode.SHADOW:
            return ExecutionResult(request.request_id, False, "paper_mode_required")
        if not request.request_id or not request.symbol:
            return ExecutionResult(request.request_id, False, "missing_request_identity")
        if not quantity.is_finite() or quantity <= 0:
            return ExecutionResult(request.request_id, False, "invalid_quantity")
        fingerprint = self._fingerprint(request, quantity)
        old = self._fingerprints.get(request.request_id)
        if old is not None:
            if old != fingerprint:
                return ExecutionResult(request.request_id, False, "idempotency_conflict")
            return ExecutionResult(request.request_id, True, "idempotent_replay")
        self._fingerprints[request.request_id] = fingerprint
        self.orders[request.request_id] = PaperOrder(request, quantity)
        return ExecutionResult(request.request_id, True, "paper_order_recorded")

    def record_fill(self, order_id, *, fill_id, quantity, price, fee):
        order = self.orders[order_id]
        if order.state in ("FILLED", "REJECTED", "CANCELLED"):
            raise ValueError("order_not_fillable")
        if (not fill_id or not all(v.is_finite() for v in (quantity, price, fee))
                or quantity <= 0 or price <= 0 or fee < 0):
            raise ValueError("invalid_fill")
        fill = PaperFill(fill_id, quantity, price, fee)
        previous = order.fills.get(fill_id)
        if previous is not None:
            if previous != fill:
                raise ValueError("fill_id_conflict")
            return "EXACT_REPLAY"
        if order.filled_quantity + quantity > order.quantity:
            raise ValueError("overfill")
        order.fills[fill_id] = fill
        order.state = "FILLED" if order.filled_quantity == order.quantity else "PARTIALLY_FILLED"
        return order.state

    def reconcile(self, order_id):
        order = self.orders[order_id]
        filled = order.filled_quantity
        return {
            "order_id": order_id, "state": order.state,
            "requested_quantity": order.quantity, "filled_quantity": filled,
            "remaining_quantity": order.quantity - filled,
            "average_fill_price": order.average_fill_price, "fees": order.fees,
            "reconciled": filled == order.quantity and order.state == "FILLED",
        }


def _decision():
    # Synthetic feature fixture: plumbing test only, not provider-derived market data.
    features = FeatureSnapshot(
        symbol="BTC_USDT", timeframe_seconds=60,
        close=102.0, ema=100.0, vwap=101.0, buy_ratio=0.7,
    )
    return BaselineStrategy().evaluate(BaselineStrategyInput(features=features))


def _request(decision):
    actions = {
        BaselineDecision.LONG: ExecutionAction.ENTER_LONG,
        BaselineDecision.SHORT: ExecutionAction.ENTER_SHORT,
    }
    if decision not in actions:
        raise ValueError("no_trade_has_no_order")
    return ExecutionRequest(
        request_id="paper-test-request-001", action=actions[decision],
        symbol="BTC_USDT", price=102.0, mode=ExecutionMode.SHADOW,
    )


def test_strategy_risk_paper_partial_fills_and_reconciliation():
    decision = _decision()
    assert decision is BaselineDecision.LONG
    assert RiskPolicy().evaluate(
        RiskInput(decision, equity=10_000, current_drawdown_fraction=0.01)
    ) is RiskDecision.ALLOW_SIGNAL

    ledger = InMemoryPaperLedger()
    request = _request(decision)
    assert ledger.submit(request, quantity=Decimal("1.0")).reason == "paper_order_recorded"
    assert ledger.record_fill(request.request_id, fill_id="f1", quantity=Decimal("0.4"),
                              price=Decimal("100"), fee=Decimal("0.04")) == "PARTIALLY_FILLED"
    assert ledger.record_fill(request.request_id, fill_id="f2", quantity=Decimal("0.6"),
                              price=Decimal("101"), fee=Decimal("0.0606")) == "FILLED"
    assert ledger.reconcile(request.request_id) == {
        "order_id": request.request_id, "state": "FILLED",
        "requested_quantity": Decimal("1.0"), "filled_quantity": Decimal("1.0"),
        "remaining_quantity": Decimal("0.0"), "average_fill_price": Decimal("100.6"),
        "fees": Decimal("0.1006"), "reconciled": True,
    }


def test_risk_veto_prevents_any_paper_order():
    decision = _decision()
    assert RiskPolicy().evaluate(
        RiskInput(decision, equity=10_000, current_drawdown_fraction=0.20)
    ) is RiskDecision.VETO
    assert InMemoryPaperLedger().orders == {}


def test_order_request_retry_is_idempotent_but_conflicting_reuse_fails():
    ledger = InMemoryPaperLedger()
    request = _request(BaselineDecision.LONG)
    assert ledger.submit(request, quantity=Decimal("1")).accepted
    assert ledger.submit(request, quantity=Decimal("1")).reason == "idempotent_replay"
    conflict = ExecutionRequest(
        request_id=request.request_id, action=ExecutionAction.ENTER_SHORT,
        symbol=request.symbol, price=request.price, mode=ExecutionMode.SHADOW,
    )
    result = ledger.submit(conflict, quantity=Decimal("1"))
    assert not result.accepted and result.reason == "idempotency_conflict"
    assert len(ledger.orders) == 1


def test_fill_replay_is_idempotent_and_overfill_is_rejected():
    ledger = InMemoryPaperLedger()
    request = _request(BaselineDecision.LONG)
    ledger.submit(request, quantity=Decimal("1"))
    fill = dict(fill_id="f1", quantity=Decimal("0.7"), price=Decimal("100"), fee=Decimal("0"))
    assert ledger.record_fill(request.request_id, **fill) == "PARTIALLY_FILLED"
    assert ledger.record_fill(request.request_id, **fill) == "EXACT_REPLAY"
    try:
        ledger.record_fill(request.request_id, fill_id="f2", quantity=Decimal("0.4"),
                           price=Decimal("100"), fee=Decimal("0"))
    except ValueError as exc:
        assert str(exc) == "overfill"
    else:
        raise AssertionError("overfill accepted")


def test_non_shadow_mode_is_rejected():
    ledger = InMemoryPaperLedger()
    request = ExecutionRequest(
        request_id="live-must-not-pass", action=ExecutionAction.ENTER_LONG,
        symbol="BTC_USDT", price=100.0, mode=ExecutionMode.DISABLED,
    )
    result = ledger.submit(request, quantity=Decimal("1"))
    assert not result.accepted and result.reason == "paper_mode_required"
    assert ledger.orders == {}
