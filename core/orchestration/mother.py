"""Mother Agent Orchestrator v1.

Coordinates quality -> strategy -> signal without performing exchange execution.
Execution is an explicit downstream capability and is disabled by default.
"""
from datetime import datetime

from core.data_engine.feature_engine import FeatureSnapshot
from core.risk.engine import CapitalRiskEngine, RiskSide
from core.signal.adapter import DecisionSignalAdapter
from core.signal.contract import SignalMode
from core.strategy.baseline import Decision
from core.strategy.decision import StrategyDecisionEngine
from core.orchestration.contract import ExecutionMode, OrchestrationResult


class MotherOrchestrator:
    """Deterministic top-level decision coordinator for one market snapshot."""

    def __init__(
        self,
        *,
        decision_engine: StrategyDecisionEngine | None = None,
        risk_engine: CapitalRiskEngine | None = None,
        signal_adapter: DecisionSignalAdapter | None = None,
    ) -> None:
        self.decision_engine = decision_engine or StrategyDecisionEngine()
        self.risk_engine = risk_engine
        self.signal_adapter = signal_adapter or DecisionSignalAdapter()

    def evaluate(
        self,
        snapshot: FeatureSnapshot,
        *,
        mode: ExecutionMode = ExecutionMode.SIGNAL_ONLY,
        entry_price: float | None = None,
        stop_price: float | None = None,
        target_price: float | None = None,
    ) -> OrchestrationResult:
        if snapshot.timestamp is None or snapshot.timestamp.tzinfo is None:
            raise ValueError("snapshot timestamp must be timezone-aware")

        decision = self.decision_engine.evaluate(snapshot)
        reasons = list(decision.reasons)

        if self.risk_engine is not None and decision.decision != Decision.NO_TRADE:
            if None in (entry_price, stop_price, target_price):
                decision = type(decision)(Decision.NO_TRADE, (*reasons, "risk_geometry_missing"))
                reasons = list(decision.reasons)
            else:
                side = RiskSide.LONG if decision.decision == Decision.LONG else RiskSide.SHORT
                assessment = self.risk_engine.assess(
                    entry_price=entry_price,
                    stop_price=stop_price,
                    target_price=target_price,
                    side=side,
                )
                if not assessment.allowed:
                    decision = type(decision)(Decision.NO_TRADE, (*reasons, *assessment.reasons))
                    reasons = list(decision.reasons)
                else:
                    reasons.extend(("capital_risk_allowed",))

        signal_mode = SignalMode(mode.value)
        signal = self.signal_adapter.build(
            symbol=snapshot.symbol,
            timeframe_seconds=snapshot.timeframe_seconds,
            timestamp=snapshot.timestamp,
            decision=decision,
            mode=signal_mode,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
        )

        # No mode grants execution from this layer. An execution adapter must
        # explicitly consume the signal downstream and enforce its own gates.
        execution_allowed = False
        if mode == ExecutionMode.ANALYSIS_ONLY:
            reasons.append("analysis_only")
        elif mode == ExecutionMode.SIGNAL_ONLY:
            reasons.append("signal_only")
        elif mode == ExecutionMode.ASSISTIVE:
            reasons.append("assistive_no_execution")
        else:
            reasons.append("auto_trading_requires_execution_adapter")

        return OrchestrationResult(
            signal=signal,
            execution_allowed=execution_allowed,
            reasons=tuple(reasons),
        )
