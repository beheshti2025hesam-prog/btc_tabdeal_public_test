"""Mother Agent - Strategy Decision Orchestrator v1.0."""

from dataclasses import dataclass

from core.data_engine.feature_engine import FeatureSnapshot
from core.data_engine.feature_quality import FeatureQualityGate
from core.strategy.baseline import BaselineStrategy, Decision
from core.strategy.confirmation import ConfirmationEngine
from core.strategy.risk import RiskVeto


@dataclass(frozen=True)
class FinalDecision:
    decision: Decision
    reasons: tuple[str, ...]


class StrategyDecisionEngine:
    """Quality -> baseline -> confirmation -> risk veto."""

    def __init__(
        self,
        *,
        quality_gate: FeatureQualityGate | None = None,
        strategy: BaselineStrategy | None = None,
        confirmation: ConfirmationEngine | None = None,
        risk_veto: RiskVeto | None = None,
    ):
        self.quality_gate = quality_gate or FeatureQualityGate()
        self.strategy = strategy or BaselineStrategy(self.quality_gate)
        self.confirmation = confirmation or ConfirmationEngine()
        self.risk_veto = risk_veto or RiskVeto()

    def evaluate(self, snapshot: FeatureSnapshot) -> FinalDecision:
        quality = self.quality_gate.evaluate(snapshot)
        if not quality.passed:
            return FinalDecision(
                Decision.NO_TRADE,
                ("quality_gate_rejected", *quality.violations),
            )

        baseline = self.strategy.evaluate(snapshot)
        if baseline.decision == Decision.NO_TRADE:
            return FinalDecision(Decision.NO_TRADE, baseline.reasons)

        confirmation = self.confirmation.evaluate(snapshot)
        if not confirmation.confirmed:
            return FinalDecision(
                Decision.NO_TRADE,
                ("confirmation_failed", *confirmation.reasons),
            )

        risk = self.risk_veto.evaluate(snapshot, baseline.decision)
        if not risk.allowed:
            return FinalDecision(
                Decision.NO_TRADE,
                ("risk_veto", *risk.reasons),
            )

        return FinalDecision(
            baseline.decision,
            (*baseline.reasons, *confirmation.reasons, "risk_allowed"),
        )
