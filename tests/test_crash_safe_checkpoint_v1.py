from datetime import datetime, timezone
import json
import pytest

from forward.crash_safe_checkpoint_v1 import CrashSafeCheckpointV1

STAMP = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)


def create(store, checkpoint_id="cp-1", state=None):
    return store.create(
        checkpoint_id=checkpoint_id,
        segment_id=1,
        created_at=STAMP,
        state={"status": "HEALTHY"} if state is None else state,
    )


def test_checkpoint_survives_store_recreation(tmp_path):
    first = CrashSafeCheckpointV1(tmp_path)
    written = create(first, state={"status": "HEALTHY", "reason_count": 0})
    recovered = CrashSafeCheckpointV1(tmp_path).read("cp-1")
    assert recovered == written
    assert len(recovered.digest) == 64
    assert recovered.state == {"status": "HEALTHY", "reason_count": 0}


def test_duplicate_checkpoint_id_always_rejects_without_overwrite(tmp_path):
    store = CrashSafeCheckpointV1(tmp_path)
    original = create(store)
    with pytest.raises(ValueError, match="CHECKPOINT_ALREADY_EXISTS"):
        create(store)
    with pytest.raises(ValueError, match="CHECKPOINT_ALREADY_EXISTS"):
        create(store, state={"status": "DIFFERENT"})
    assert CrashSafeCheckpointV1(tmp_path).read("cp-1") == original


def test_sequence_continuity_fields_are_forbidden_even_when_nested(tmp_path):
    store = CrashSafeCheckpointV1(tmp_path)
    with pytest.raises(ValueError, match="CONTINUITY_PROOF_FORBIDDEN"):
        create(store, state={"nested": [{"last_sequence": 123}]})


def test_naive_timestamp_rejected(tmp_path):
    with pytest.raises(ValueError, match="TIMEZONE_REQUIRED"):
        CrashSafeCheckpointV1(tmp_path).create(
            checkpoint_id="cp-1", segment_id=1,
            created_at=datetime(2026, 10, 7, 9, 0), state={},
        )


def test_invalid_segment_rejected(tmp_path):
    with pytest.raises(ValueError, match="SEGMENT_INVALID"):
        CrashSafeCheckpointV1(tmp_path).create(
            checkpoint_id="cp-1", segment_id=0, created_at=STAMP, state={},
        )


def test_tampered_payload_fails_digest_check(tmp_path):
    store = CrashSafeCheckpointV1(tmp_path)
    create(store)
    path = next(tmp_path.glob("*.json"))
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["payload"]["state"]["status"] = "ALTERED"
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        store.read("cp-1")


def test_partial_or_corrupt_checkpoint_fails_closed(tmp_path):
    store = CrashSafeCheckpointV1(tmp_path)
    store.root.mkdir(parents=True, exist_ok=True)
    path = store._path("cp-1")
    path.write_text("{partial", encoding="utf-8")
    with pytest.raises(ValueError, match="RECORD_INVALID"):
        store.read("cp-1")
    with pytest.raises(ValueError, match="ALREADY_EXISTS"):
        create(store)


def test_missing_checkpoint_is_not_repaired_or_inferred(tmp_path):
    with pytest.raises(FileNotFoundError):
        CrashSafeCheckpointV1(tmp_path).read("missing")


def test_checkpoint_id_cannot_escape_storage_root(tmp_path):
    store = CrashSafeCheckpointV1(tmp_path / "checkpoints")
    create(store, checkpoint_id="../../outside")
    assert list((tmp_path / "checkpoints").glob("*.json"))
    assert not (tmp_path / "outside").exists()
