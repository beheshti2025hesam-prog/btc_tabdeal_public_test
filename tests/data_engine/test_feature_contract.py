from datetime import datetime, timezone

import pytest

from core.features.contract import FeatureValue


def test_feature_value_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError):
        FeatureValue("ema", datetime(2026, 1, 1), 100.0)


def test_feature_value_carries_timeframe_and_source():
    value = FeatureValue(
        "ema",
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        100.0,
        timeframe_seconds=900,
        source="ema_calculator",
    )
    assert value.timeframe_seconds == 900
    assert value.source == "ema_calculator"
