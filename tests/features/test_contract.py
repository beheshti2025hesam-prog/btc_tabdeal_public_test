from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from core.features.contract import FeatureValue


def test_feature_value_contract():
    timestamp = datetime(2026, 9, 20, 17, 0, tzinfo=timezone.utc)

    feature = FeatureValue(
        name="EMA_50",
        timestamp=timestamp,
        value=100.5,
    )

    assert feature.name == "EMA_50"
    assert feature.timestamp == timestamp
    assert feature.value == 100.5


def test_feature_value_allows_missing_value():
    timestamp = datetime(2026, 9, 20, 17, 0, tzinfo=timezone.utc)

    feature = FeatureValue(
        name="RSI_14",
        timestamp=timestamp,
        value=None,
    )

    assert feature.value is None


def test_feature_value_is_frozen():
    timestamp = datetime(2026, 9, 20, 17, 0, tzinfo=timezone.utc)

    feature = FeatureValue(
        name="EMA_50",
        timestamp=timestamp,
        value=100.5,
    )

    with pytest.raises(FrozenInstanceError):
        feature.value = 101.0
