import pytest
from forward.clean_structure_stability_v1 import CleanStructureStabilityV1


def test_up_stable():
    r=CleanStructureStabilityV1().observe(["UP_CONTEXT","UP_CONTEXT","UP_CONTEXT"])
    assert r.stable_bias=="UP_STABLE" and r.up_contexts==3


def test_down_stable():
    r=CleanStructureStabilityV1().observe(["DOWN_CONTEXT","DOWN_CONTEXT"])
    assert r.stable_bias=="DOWN_STABLE"


def test_mixed_is_unstable():
    r=CleanStructureStabilityV1().observe(["UP_CONTEXT","MIXED_CONTEXT","UP_CONTEXT"])
    assert r.stable_bias=="UNSTABLE"


def test_empty_rejected():
    with pytest.raises(ValueError): CleanStructureStabilityV1().observe([])


def test_unknown_rejected():
    with pytest.raises(ValueError): CleanStructureStabilityV1().observe(["UP_CONTEXT","BOS_SIGNAL"])
