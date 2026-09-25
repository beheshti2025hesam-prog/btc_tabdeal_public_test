from datetime import datetime, timezone

from core.orchestration.contract import ExecutionMode
from core.orchestration.mother import MotherOrchestrator
from core.data_engine.feature_engine import FeatureSnapshot


def snapshot(close=101.0, ema=100.0, vwap=100.0, buy_ratio=0.7):
    return FeatureSnapshot(
        symbol="BTC_USDT",
        timeframe_seconds=900,
        close=close,
        ema=ema,
        vwap=vwap,
        buy_sell_delta=10.0,
        buy_ratio=buy_ratio,
        realized_volatility=0.01,
        average_true_range=100.0,
        volume_ratio=1.5,
        volume_spike=False,
        regime="TREND",
        timestamp=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )


def test_orchestrator_signal_only_never_executes():
    result = MotherOrchestrator().evaluate(snapshot())
    assert result.signal.intent.value == "LONG"
    assert result.signal.mode == result.signal.mode.SIGNAL_ONLY
    assert result.execution_allowed is False
    assert "signal_only" in result.reasons


def test_analysis_only_preserves_non_execution_boundary():
    result = MotherOrchestrator().evaluate(snapshot(), mode=ExecutionMode.ANALYSIS_ONLY)
    assert result.signal.intent.value == "LONG"
    assert result.signal.mode == result.signal.mode.ANALYSIS_ONLY
    assert result.execution_allowed is False
    assert "analysis_only" in result.reasons


def test_missing_risk_geometry_vetoes_when_capital_risk_is_enabled():
    from core.risk.engine import CapitalRiskEngine, RiskConfig

    risk = CapitalRiskEngine(RiskConfig(account_equity=1000, max_leverage=5))
    result = MotherOrchestrator(risk_engine=risk).evaluate(snapshot())
    assert result.signal.intent.value == "NO_TRADE"
    assert result.execution_allowed is False
    assert "risk_geometry_missing" in result.reasons


def test_capital_risk_accepts_valid_three_to_one_geometry():
    from core.risk.engine import CapitalRiskEngine, RiskConfig

    risk = CapitalRiskEngine(RiskConfig(account_equity=1000, max_leverage=5, min_reward_risk=3))
    result = MotherOrchestrator(risk_engine=risk).evaluate(
        snapshot(), entry_price=100, stop_price=99, target_price=103
    )
    assert result.signal.intent.value == "LONG"
    assert result.execution_allowed is False
    assert "capital_risk_allowed" in result.reasons
