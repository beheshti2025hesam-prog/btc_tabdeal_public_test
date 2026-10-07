from datetime import datetime, timezone, timedelta
import pytest
from forward.forward_reliability_guard_v1 import ReliabilityGuardV1

G=ReliabilityGuardV1()
NOW=datetime(2026,10,7,8,0,tzinfo=timezone.utc)

def test_timestamp_requires_timezone():
    with pytest.raises(ValueError, match="timezone-aware"):
        G.validate_timestamp(NOW.replace(tzinfo=None), as_of=NOW)

def test_future_timestamp_rejected():
    with pytest.raises(ValueError, match="future"):
        G.validate_timestamp(NOW+timedelta(seconds=1), as_of=NOW)

def test_sequence_is_nonnegative():
    assert G.validate_sequence("12")==12
    with pytest.raises(ValueError): G.validate_sequence("-1")

def test_identical_duplicate_is_idempotent_noop():
    row={"sequence":1,"price":"100"}
    assert G.validate_duplicate(row,row) is None

def test_conflicting_duplicate_is_fail_closed():
    with pytest.raises(ValueError, match="conflicting"):
        G.validate_duplicate({"sequence":1,"price":"100"},{"sequence":1,"price":"101"})

def test_rejection_reason_required():
    with pytest.raises(ValueError, match="reason"):
        G.require_reason(" ")
