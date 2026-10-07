from datetime import datetime, timezone
import pytest
from forward.observation_session_manager_v1 import ObservationSessionManagerV1

def test_session_is_unique_and_scoped():
    m=ObservationSessionManagerV1(policy_id="HES_FORWARD_OBSERVATION_POLICY_V1",policy_version="1.0.0")
    a=m.start(started_at=datetime(2026,10,7,6,0,tzinfo=timezone.utc))
    b=m.start(started_at=datetime(2026,10,7,6,0,tzinfo=timezone.utc))
    assert a.run_id != b.run_id
    assert a.symbol=="BTC_USDT" and a.timeframe=="15m"
    assert a.execution_enabled is False
    assert a.historical_inputs_allowed is False
    assert len(a.digest())==64

def test_naive_time_rejected():
    m=ObservationSessionManagerV1(policy_id="P",policy_version="1")
    with pytest.raises(ValueError,match="timezone"):
        m.start(started_at=datetime(2026,10,7,6,0))

def test_scope_and_source_are_fail_closed():
    with pytest.raises(ValueError):
        ObservationSessionManagerV1(policy_id="P",policy_version="1",symbol="ETH_USDT").start(
            started_at=datetime.now(timezone.utc))
    with pytest.raises(ValueError):
        ObservationSessionManagerV1(policy_id="P",policy_version="1",source="historical").start(
            started_at=datetime.now(timezone.utc))
