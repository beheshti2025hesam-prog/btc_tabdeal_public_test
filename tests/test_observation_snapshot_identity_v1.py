import pytest
from datetime import datetime, timezone, timedelta
from forward.observation_snapshot_identity_v1 import ObservationSnapshotIdentityV1


def test_identity_is_deterministic():
    t=datetime(2026,10,7,12,0,tzinfo=timezone.utc)
    p={"regime":"UPTREND","quality":"HIGH"}
    a=ObservationSnapshotIdentityV1().create(forward_run_id="RUN-1",observed_at=t,symbol="BTC_USDT",timeframe="15m",payload=p)
    b=ObservationSnapshotIdentityV1().create(forward_run_id="RUN-1",observed_at=t,symbol="BTC_USDT",timeframe="15m",payload=p)
    assert a.snapshot_id==b.snapshot_id and a.digest==b.digest


def test_payload_change_changes_digest():
    t=datetime(2026,10,7,12,0,tzinfo=timezone.utc)
    a=ObservationSnapshotIdentityV1().create(forward_run_id="RUN-1",observed_at=t,symbol="BTC_USDT",timeframe="15m",payload={"x":1})
    b=ObservationSnapshotIdentityV1().create(forward_run_id="RUN-1",observed_at=t,symbol="BTC_USDT",timeframe="15m",payload={"x":2})
    assert a.digest!=b.digest


def test_naive_time_rejected():
    with pytest.raises(ValueError):
        ObservationSnapshotIdentityV1().create(forward_run_id="RUN-1",observed_at=datetime(2026,10,7,12),symbol="BTC_USDT",timeframe="15m",payload={"x":1})


def test_future_rejected():
    with pytest.raises(ValueError):
        ObservationSnapshotIdentityV1().create(forward_run_id="RUN-1",observed_at=datetime.now(timezone.utc)+timedelta(minutes=1),symbol="BTC_USDT",timeframe="15m",payload={"x":1})


def test_scope_rejected():
    t=datetime(2026,10,7,12,0,tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        ObservationSnapshotIdentityV1().create(forward_run_id="RUN-1",observed_at=t,symbol="ETH_USDT",timeframe="15m",payload={"x":1})
