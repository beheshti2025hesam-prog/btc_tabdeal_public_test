import pytest
from forward.clean_regime_quality_v1 import CleanRegimeQualityV1


def test_high_quality_stable_persistent():
    r=CleanRegimeQualityV1().observe(regime="UPTREND",persistence_ratio=1.0,transition="NO_CHANGE")
    assert r.quality=="HIGH"


def test_medium_when_not_fully_persistent():
    r=CleanRegimeQualityV1().observe(regime="DOWNTREND",persistence_ratio=0.75,transition="NO_CHANGE")
    assert r.quality=="MEDIUM"


def test_medium_after_transition():
    r=CleanRegimeQualityV1().observe(regime="UPTREND",persistence_ratio=1.0,transition="UP_TO_DOWN")
    assert r.quality=="MEDIUM"


def test_uncertain_is_low():
    r=CleanRegimeQualityV1().observe(regime="TRANSITION_UNCERTAIN",persistence_ratio=1.0,transition="NO_CHANGE")
    assert r.quality=="LOW"


def test_invalid_ratio_rejected():
    with pytest.raises(ValueError):
        CleanRegimeQualityV1().observe(regime="UPTREND",persistence_ratio=1.2,transition="NO_CHANGE")
