from datetime import datetime, timezone
import pytest
from forward.crash_safe_checkpoint_v1 import CrashSafeCheckpointV1
T=datetime(2026,10,7,9,0,tzinfo=timezone.utc)
def test_checkpoint_is_immutable_metadata():
    c=CrashSafeCheckpointV1().create(checkpoint_id="CP-1",segment_id=1,created_at=T,state={"status":"HEALTHY"})
    assert c.checkpoint_id=="CP-1" and len(c.digest)==64
def test_duplicate_checkpoint_rejected():
    g=CrashSafeCheckpointV1(); g.create(checkpoint_id="CP-1",segment_id=1,created_at=T,state={})
    with pytest.raises(ValueError): g.create(checkpoint_id="CP-1",segment_id=1,created_at=T,state={})
def test_sequence_resume_proof_forbidden():
    with pytest.raises(ValueError):
        CrashSafeCheckpointV1().create(checkpoint_id="CP-1",segment_id=1,created_at=T,state={"last_sequence":123})
def test_nonpositive_segment_rejected():
    with pytest.raises(ValueError):
        CrashSafeCheckpointV1().create(checkpoint_id="CP-1",segment_id=0,created_at=T,state={})
def test_naive_time_rejected():
    with pytest.raises(ValueError):
        CrashSafeCheckpointV1().create(checkpoint_id="CP-1",segment_id=1,created_at=datetime(2026,10,7,9),state={})
