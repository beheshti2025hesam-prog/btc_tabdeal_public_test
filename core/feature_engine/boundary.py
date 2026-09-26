"""HES Trade Agent - Feature Boundary Gate v1.1.

Final descriptive-data safety boundary before downstream Strategy.
"""
from dataclasses import dataclass
from typing import Iterable

from core.feature_engine.adapter import DataIntelligenceFeatureAdapter, IntelligenceFeatureInput
from core.feature_engine.coverage import CoverageGap
from core.feature_engine.quality import FeatureQualityGate, FeatureQualityResult, FeatureSnapshot


@dataclass(frozen=True)
class FeatureBoundaryResult:
    passed: bool
    snapshot: FeatureSnapshot | None
    quality: FeatureQualityResult


class FeatureBoundaryGate:
    """Build, coverage-check, and quality-check one feature boundary."""

    def __init__(self, quality_gate: FeatureQualityGate | None = None):
        self.adapter = DataIntelligenceFeatureAdapter()
        self.quality_gate = quality_gate or FeatureQualityGate()

    def evaluate(self, item: IntelligenceFeatureInput, coverage_gaps: Iterable[CoverageGap] = ()) -> FeatureBoundaryResult:
        try:
            snapshot = self.adapter.build(item)
        except ValueError as exc:
            return FeatureBoundaryResult(False, None, FeatureQualityResult(False, (f"alignment:{exc}",)))

        for gap in coverage_gaps:
            if gap.overlaps(symbol=snapshot.symbol, start=item.candle.start, end=item.candle.end):
                return FeatureBoundaryResult(False, None, FeatureQualityResult(False, (f"coverage_gap:{gap.reason}",)))

        quality = self.quality_gate.evaluate(snapshot)
        return FeatureBoundaryResult(quality.passed, snapshot if quality.passed else None, quality)
