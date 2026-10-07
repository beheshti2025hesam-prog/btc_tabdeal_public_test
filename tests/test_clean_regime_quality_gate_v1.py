import pytest
from forward.clean_regime_quality_gate_v1 import CleanRegimeQualityGateV1


def test_high_observation_safe():
    r=CleanRegimeQualityGateV1().evaluate("HIGH")
    assert r.safe_for_observation and r.reason=="HIGH_QUALITY_STRUCTURE"


def test_medium_not_promoted():
    r=CleanRegimeQualityGateV1().evaluate("MEDIUM")
    assert not r.safe_for_observation


def test_low_not_promoted():
    r=CleanRegimeQualityGateV1().evaluate("LOW")
    assert not r.safe_for_observation


def test_unknown_rejected():
    with pytest.raises(ValueError): CleanRegimeQualityGateV1().evaluate("SIGNAL_READY")
