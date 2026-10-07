import pytest
from forward.clean_regime_observation_v1 import CleanRegimeObservationV1


def test_uptrend():
    r=CleanRegimeObservationV1().observe("UP_STABLE")
    assert r.regime=="UPTREND" and r.confidence_state=="STRUCTURE_ALIGNED"


def test_downtrend():
    r=CleanRegimeObservationV1().observe("DOWN_STABLE")
    assert r.regime=="DOWNTREND"


def test_uncertain():
    r=CleanRegimeObservationV1().observe("UNSTABLE")
    assert r.regime=="TRANSITION_UNCERTAIN"


def test_unknown_rejected():
    with pytest.raises(ValueError): CleanRegimeObservationV1().observe("SIGNAL_LONG")
