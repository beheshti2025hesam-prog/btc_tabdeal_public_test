"""HES Trade Agent - Feature Engine exports."""
from core.feature_engine.ema import EMASnapshot, EMACalculator
from core.feature_engine.momentum import MomentumSnapshot, MomentumCalculator
from core.feature_engine.price_vwap import PriceVWAPRelationship, PriceVWAPRelationshipCalculator
from core.feature_engine.structure import StructureSnapshot, StructureCalculator
from core.feature_engine.quality import FeatureSnapshot, FeatureQualityResult, FeatureQualityGate
from core.feature_engine.temporal import FeatureTemporalInput, FeatureTemporalAlignment
from core.feature_engine.adapter import IntelligenceFeatureInput, DataIntelligenceFeatureAdapter
from core.feature_engine.boundary import FeatureBoundaryResult, FeatureBoundaryGate

__all__ = [
    "EMASnapshot", "EMACalculator",
    "MomentumSnapshot", "MomentumCalculator",
    "PriceVWAPRelationship", "PriceVWAPRelationshipCalculator",
    "StructureSnapshot", "StructureCalculator",
    "FeatureSnapshot", "FeatureQualityResult", "FeatureQualityGate",
    "FeatureTemporalInput", "FeatureTemporalAlignment",
    "IntelligenceFeatureInput", "DataIntelligenceFeatureAdapter",
    "FeatureBoundaryResult", "FeatureBoundaryGate",
]
