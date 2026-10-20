"""Test-only analysis/risk/adapter boundary harness; never connects to a venue."""
from unittest.mock import Mock

from core.execution.contract import ExecutionAction, ExecutionMode, ExecutionRequest, ExecutionResult
from core.risk.boundary import RiskDecision, RiskInput, RiskPolicy
from core.strategy.baseline import BaselineDecision


class FakeTestAdapter:
    """In-memory adapter double. It cannot perform network or exchange I/O."""
    def __init__(self):
        self.submit = Mock(side_effect=lambda request: ExecutionResult(
            request_id=request.request_id, accepted=False, reason="test_adapter_no_execution"
        ))


def route_through_risk_only_for_test(decision, risk_input, adapter):
    risk = RiskPolicy().evaluate(risk_input)
    if risk is not RiskDecision.ALLOW_SIGNAL:
        return "NO_TRADE"
    # This branch exists only in this test harness. Production execution remains disabled.
    if decision is BaselineDecision.NO_TRADE:
        return "NO_TRADE"
    request = ExecutionRequest(
        request_id="test-only-request-001",
        action=ExecutionAction.ENTER_LONG if decision is BaselineDecision.LONG else ExecutionAction.ENTER_SHORT,
        symbol="BTC_USDT",
        price=100.0,
        mode=ExecutionMode.SHADOW,
    )
    adapter.submit(request)
    return "SHADOW_REQUESTED"


def test_risk_veto_prevents_test_adapter_invocation():
    adapter = FakeTestAdapter()
    result = route_through_risk_only_for_test(
        BaselineDecision.LONG,
        RiskInput(BaselineDecision.LONG, equity=10000.0, current_drawdown_fraction=0.20),
        adapter,
    )
    assert result == "NO_TRADE"
    adapter.submit.assert_not_called()


def test_approved_signal_reaches_only_in_memory_test_adapter():
    adapter = FakeTestAdapter()
    result = route_through_risk_only_for_test(
        BaselineDecision.LONG,
        RiskInput(BaselineDecision.LONG, equity=10000.0, current_drawdown_fraction=0.01),
        adapter,
    )
    assert result == "SHADOW_REQUESTED"
    adapter.submit.assert_called_once()
    request = adapter.submit.call_args.args[0]
    assert request.mode is ExecutionMode.SHADOW
    assert request.symbol == "BTC_USDT"
