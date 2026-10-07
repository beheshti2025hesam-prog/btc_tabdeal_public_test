from datetime import datetime, timezone, timedelta
import pytest
from forward.clock_integrity_v1 import ForwardClockIntegrityV1
T=datetime(2026,10,7,8,0,tzinfo=timezone.utc)
def test_normal_skew_ok():
    e=ForwardClockIntegrityV1(max_clock_skew_seconds=5).validate(source_time=T,receive_time=T+timedelta(seconds=2))
    assert e.status=="OK" and e.age_seconds==2
def test_excessive_skew_is_drift():
    e=ForwardClockIntegrityV1(max_clock_skew_seconds=5).validate(source_time=T,receive_time=T+timedelta(seconds=6))
    assert e.status=="DRIFT" and e.reason=="SOURCE_RECEIVE_CLOCK_SKEW"
def test_source_after_receive_rejected():
    e=ForwardClockIntegrityV1().validate(source_time=T+timedelta(seconds=1),receive_time=T)
    assert e.status=="REJECT" and e.reason=="SOURCE_TIME_AFTER_RECEIVE_TIME"
def test_naive_source_rejected():
    with pytest.raises(ValueError):
        ForwardClockIntegrityV1().validate(source_time=datetime(2026,10,7,8,0),receive_time=T)
def test_naive_receive_rejected():
    with pytest.raises(ValueError):
        ForwardClockIntegrityV1().validate(source_time=T,receive_time=datetime(2026,10,7,8,0))
def test_zero_skew_allowed():
    e=ForwardClockIntegrityV1(max_clock_skew_seconds=0).validate(source_time=T,receive_time=T)
    assert e.status=="OK"
