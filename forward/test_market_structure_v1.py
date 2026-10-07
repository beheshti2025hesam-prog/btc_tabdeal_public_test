from datetime import datetime, timezone
from decimal import Decimal

import pytest

from forward.market_structure_v1 import (
    SwingPoint,
    StructureEvent,
    build_snapshot,
    classify_swing_labels,
    infer_regime,
)


T0 = datetime(2026, 10, 7, 1, 45, tzinfo=timezone.utc)
T1 = datetime(2026, 10, 7, 2, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 10, 7, 2, 15, tzinfo=timezone.utc)


def test_swing_labels_are_relative_to_prior_same_kind():
    high1 = SwingPoint("SWING_HIGH", Decimal("100"), T0, 1)
    high2 = SwingPoint("SWING_HIGH", Decimal("105"), T1, 2)
    low1 = SwingPoint("SWING_LOW", Decimal("90"), T0, 1)
    low2 = SwingPoint("SWING_LOW", Decimal("95"), T1, 2)

    assert classify_swing_labels([high1], high2) == ("HH",)
    assert classify_swing_labels([low1], low2) == ("HL",)


def test_regime_fails_closed_with_insufficient_or_ambiguous_labels():
    assert infer_regime(["HH"]) == "UNKNOWN"
    assert infer_regime(["HH", "HL"]) == "UPTREND"
    assert infer_regime(["LL", "LH"]) == "DOWNTREND"
    assert infer_regime(["HH", "LL"]) == "RANGE"


def test_snapshot_rejects_future_swing_timestamp():
    future_swing = SwingPoint("SWING_HIGH", Decimal("110"), T2, 3)

    with pytest.raises(ValueError, match="after observed_at"):
        build_snapshot(T1, [future_swing], ["HH"], [])


def test_snapshot_rejects_future_event_timestamp():
    event = StructureEvent(
        event="BOS",
        direction="BULLISH",
        observed_at=T2,
        reference_candle_time=T1,
        reference_price=Decimal("105"),
        reason="test",
    )

    with pytest.raises(ValueError, match="after observed_at"):
        build_snapshot(T1, [], ["HH", "HL"], [event])


def test_snapshot_accepts_only_observed_or_earlier_structure():
    high = SwingPoint("SWING_HIGH", Decimal("105"), T0, 1)
    low = SwingPoint("SWING_LOW", Decimal("95"), T1, 2)

    snapshot = build_snapshot(T1, [high, low], ["HH", "HL"], [])

    assert snapshot.observed_at == T1
    assert snapshot.last_high == high
    assert snapshot.last_low == low
    assert snapshot.regime == "UPTREND"
