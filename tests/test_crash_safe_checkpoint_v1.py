import pytest
from forward.crash_safe_checkpoint_v1 import CrashSafeCheckpointV1
def test_checkpoint_is_deterministic_and_write_once():
    c=CrashSafeCheckpointV1()
    a=c.write_once(segment_id=1,checkpoint_id="cp1",last_sequence=10)
    b=c.write_once(segment_id=1,checkpoint_id="cp1",last_sequence=10)
    assert a==b and len(a.digest)==64
def test_conflicting_checkpoint_rejected():
    c=CrashSafeCheckpointV1(); c.write_once(segment_id=1,checkpoint_id="cp1",last_sequence=10)
    with pytest.raises(ValueError,match="CHECKPOINT_CONFLICT"):
        c.write_once(segment_id=1,checkpoint_id="cp1",last_sequence=11)
def test_resume_is_metadata_only():
    c=CrashSafeCheckpointV1(); c.write_once(segment_id=1,checkpoint_id="cp1",last_sequence=10)
    assert c.resume("cp1") is None
def test_unknown_checkpoint_fails_closed():
    with pytest.raises(ValueError,match="CHECKPOINT_NOT_FOUND"):
        CrashSafeCheckpointV1().resume("missing")
def test_invalid_identity_rejected():
    with pytest.raises(ValueError):
        CrashSafeCheckpointV1().write_once(segment_id=0,checkpoint_id="cp",last_sequence=1)
def test_digest_changes_with_sequence():
    c=CrashSafeCheckpointV1()
    a=c.write_once(segment_id=1,checkpoint_id="a",last_sequence=10)
    b=c.write_once(segment_id=1,checkpoint_id="b",last_sequence=11)
    assert a.digest != b.digest
