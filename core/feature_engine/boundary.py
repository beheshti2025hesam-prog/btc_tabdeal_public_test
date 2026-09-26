"""HES Trade Agent - Feature Boundary Gate v1.

Final descriptive-data safety boundary before downstream Strategy.
It composes temporal/window alignment, Data Intelligence adaptation, and
Feature Quality validation. It never creates, ranks, or executes signals.
"""
from dataclasses import dataclass

from core.feature_engine.adapter import DataIntelligenceFeatureAdapter, IntelligenceFeatureInput
from core.feature_engine.quality import FeatureQualityGate, FeatureQualityResult, FeatureSnapshot


@dataclass(frozen=True)
class FeatureBoundaryResult:
    passed: bool
    snapshot: FeatureSnapshot | None
    quality: FeatureQualityResult


class FeatureBoundaryGate:
    """Build and quality-check one complete feature boundary."""

    def __init__(self, quality_gate: FeatureQualityGate | None = None):
        self.adapter = DataIntelligenceFeatureAdapter()
        self.quality_gate = quality_gate or FeatureQualityGate()

    def evaluate(self, item: IntelligenceFeatureInput) -> FeatureBoundaryResult:
        try:
            snapshot = self.adapter.build(item)
        except ValueError as exc:
            return FeatureBoundaryResult(
                passed=False,
                snapshot=None,
                quality=FeatureQualityResult(False, (f"alignment:{exc}",)),
            )

        quality = self.quality_gate.evaluate(snapshot)
        return FeatureBoundaryResult(
            passed=quality.passed,
            snapshot=snapshot if quality.passed else None,
            quality=quality,
        )
