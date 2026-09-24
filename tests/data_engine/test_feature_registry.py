import pytest

from core.features.registry import FeatureDefinition, FeatureRegistry


def test_registry_registers_and_returns_metadata():
    registry = FeatureRegistry()
    registry.register(FeatureDefinition("ema", "1.0", 900, True))
    assert registry.get("ema").required
    assert registry.definitions()[0].name == "ema"


def test_duplicate_feature_is_rejected():
    registry = FeatureRegistry((FeatureDefinition("ema", "1.0"),))
    with pytest.raises(ValueError):
        registry.register(FeatureDefinition("ema", "2.0"))


def test_invalid_timeframe_is_rejected():
    with pytest.raises(ValueError):
        FeatureRegistry((FeatureDefinition("ema", "1.0", 0),))
