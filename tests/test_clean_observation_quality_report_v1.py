import pytest
from forward.clean_observation_quality_report_v1 import CleanObservationQualityReportV1


def test_high_qualified():
    r=CleanObservationQualityReportV1().build(regime="UPTREND",quality="HIGH",gate_safe=True)
    assert r.report_state=="OBSERVATION_QUALIFIED"


def test_medium_limited():
    r=CleanObservationQualityReportV1().build(regime="DOWNTREND",quality="MEDIUM",gate_safe=False)
    assert r.report_state=="OBSERVATION_LIMITED"


def test_low_unqualified():
    r=CleanObservationQualityReportV1().build(regime="TRANSITION_UNCERTAIN",quality="LOW",gate_safe=False)
    assert r.report_state=="OBSERVATION_UNQUALIFIED"


def test_high_without_gate_not_qualified():
    r=CleanObservationQualityReportV1().build(regime="UPTREND",quality="HIGH",gate_safe=False)
    assert r.report_state=="OBSERVATION_UNQUALIFIED"


def test_invalid_inputs():
    with pytest.raises(ValueError):
        CleanObservationQualityReportV1().build(regime="SIGNAL",quality="HIGH",gate_safe=True)
