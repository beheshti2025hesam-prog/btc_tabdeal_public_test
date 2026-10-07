from datetime import datetime, timezone, timedelta
import pytest
from forward.liveness_stale_guard_v1 import ForwardLivenessGuardV1

T0=datetime(2026,10,7,8,0,tzinfo=timezone.utc)

def test_fresh_observation_is_live():
    g=ForwardLivenessGuardV1(max_staleness_seconds=30)
    assert g.observe(T0,now=T0+timedelta(seconds=5)).status=="LIVE"

def test_stale_observation_fails_closed():
    g=ForwardLivenessGuardV1(max_staleness_seconds=30)
    e=g.observe(T0,now=T0+timedelta(seconds=31))
    assert e.status=="STALE"
    assert e.reason=="STALE_SOURCE_DATA"

def test_heartbeat_detects_dead_data_without_new_frames():
    g=ForwardLivenessGuardV1(max_staleness_seconds=30)
    g.observe(T0,now=T0+timedelta(seconds=1))
    assert g.heartbeat(now=T0+timedelta(seconds=31)).status=="STALE"

def test_no_data_is_not_reported_as_live():
    g=ForwardLivenessGuardV1()
    assert g.heartbeat(now=T0).status=="NO_DATA"

def test_future_observation_rejected():
    g=ForwardLivenessGuardV1()
    e=g.observe(T0+timedelta(seconds=1),now=T0)
    assert e.status=="REJECT"
    assert e.reason=="FUTURE_OBSERVATION"

def test_naive_timestamp_rejected():
    g=ForwardLivenessGuardV1()
    with pytest.raises(ValueError):
        g.observe(datetime(2026,10,7,8,0),now=T0)
