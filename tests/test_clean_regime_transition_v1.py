import pytest
from forward.clean_regime_transition_v1 import CleanRegimeTransitionV1


def test_no_change():
    r=CleanRegimeTransitionV1().observe("UPTREND","UPTREND")
    assert r.transition=="NO_CHANGE"


def test_up_to_down():
    r=CleanRegimeTransitionV1().observe("UPTREND","DOWNTREND")
    assert r.transition=="UP_TO_DOWN"


def test_down_to_up():
    r=CleanRegimeTransitionV1().observe("DOWNTREND","UPTREND")
    assert r.transition=="DOWN_TO_UP"


def test_enter_uncertain():
    r=CleanRegimeTransitionV1().observe("UPTREND","TRANSITION_UNCERTAIN")
    assert r.transition=="ENTERED_UNCERTAIN"


def test_exit_uncertain():
    r=CleanRegimeTransitionV1().observe("TRANSITION_UNCERTAIN","DOWNTREND")
    assert r.transition=="EXITED_UNCERTAIN"


def test_invalid_rejected():
    with pytest.raises(ValueError):
        CleanRegimeTransitionV1().observe("UPTREND","LONG_SIGNAL")
