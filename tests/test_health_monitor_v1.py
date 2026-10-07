import pytest
from forward.health_monitor_v1 import ForwardHealthMonitorV1
def test_live_requires_reason_and_is_safe():
    m=ForwardHealthMonitorV1(); m.record("LIVE","VALID_TRADE")
    assert m.is_safe()
def test_stale_is_not_safe():
    m=ForwardHealthMonitorV1(); m.record("LIVE","VALID_TRADE"); m.record("STALE","STALE_SOURCE_DATA")
    assert not m.is_safe()
def test_no_events_not_safe():
    assert not ForwardHealthMonitorV1().is_safe()
def test_reason_is_required():
    with pytest.raises(ValueError): ForwardHealthMonitorV1().record("ERROR","")
def test_unknown_status_rejected():
    with pytest.raises(ValueError): ForwardHealthMonitorV1().record("BOGUS","X")
def test_counts_are_deterministic():
    m=ForwardHealthMonitorV1(); m.record("REJECT","FUTURE_OBSERVATION"); m.record("REJECT","FUTURE_OBSERVATION")
    assert m.counts()=={"FUTURE_OBSERVATION":2}
def test_error_is_not_safe():
    m=ForwardHealthMonitorV1(); m.record("ERROR","TRANSPORT_FAILURE")
    assert not m.is_safe()
