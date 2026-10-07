import pytest
from forward.clean_regime_persistence_v1 import CleanRegimePersistenceV1


def test_up_persistent():
    r=CleanRegimePersistenceV1().observe(["UPTREND","UPTREND","UPTREND"])
    assert r.dominant_regime=="UPTREND" and r.persistence_ratio==1.0 and r.stable


def test_down_persistent():
    r=CleanRegimePersistenceV1().observe(["DOWNTREND","DOWNTREND"])
    assert r.dominant_regime=="DOWNTREND" and r.stable


def test_transition_not_stable():
    r=CleanRegimePersistenceV1().observe(["TRANSITION_UNCERTAIN","TRANSITION_UNCERTAIN"])
    assert r.stable is False


def test_mixed_not_stable():
    r=CleanRegimePersistenceV1().observe(["UPTREND","DOWNTREND","UPTREND"])
    assert r.dominant_regime=="UPTREND" and r.persistence_ratio < 1 and not r.stable


def test_empty_rejected():
    with pytest.raises(ValueError): CleanRegimePersistenceV1().observe([])


def test_unknown_rejected():
    with pytest.raises(ValueError): CleanRegimePersistenceV1().observe(["UPTREND","LONG_SIGNAL"])
