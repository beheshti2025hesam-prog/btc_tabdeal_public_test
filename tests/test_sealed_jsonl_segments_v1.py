import json
from pathlib import Path
import threading

import pytest

from forward.forward_journal_v1 import ForwardJournalV1
from forward.sealed_jsonl_segments_v1 import (
    JsonlSegmentError, read_jsonl_records, seal_hot_file, seal_if_over,
)


def row(event_id, n):
    return {"event_id": event_id, "observed_at": f"2026-11-24T00:00:{n:02d}Z", "n": n}


def test_seal_moves_hot_prefix_to_verified_compressed_segment_and_keeps_order(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    for n in range(3):
        assert writer.append_event(row(f"e{n}", n))
    original = path.read_bytes()
    entry = writer.seal()
    assert entry["record_count"] == 3
    assert entry["source_bytes"] == len(original)
    assert path.read_bytes() == b""
    assert [r["event_id"] for r in read_jsonl_records(path)] == ["e0", "e1", "e2"]
    assert (path.parent / (path.name + ".segments") / "manifest.json").is_file()


def test_writer_duplicate_detection_includes_sealed_segments(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    writer.append_event(row("same", 1))
    writer.seal()
    assert writer.append_event(row("new", 2))
    assert writer.append_event(row("same", 1)) is False
    assert [r["event_id"] for r in read_jsonl_records(path)] == ["same", "new"]


def test_reader_recovers_manifest_committed_but_hot_not_truncated_state(tmp_path):
    import forward.sealed_jsonl_segments_v1 as segments
    path = tmp_path / "journal.jsonl"
    path.write_bytes(b"".join((json.dumps(row(f"e{i}", i)) + "\n").encode() for i in range(2)))
    with segments._locked(path, exclusive=True):
        entry = segments._seal_hot_file_unlocked(path, truncate_hot=False)
    assert entry
    assert len(read_jsonl_records(path)) == 2
    # A later append is retained after the exact sealed prefix is skipped.
    with path.open("ab") as handle:
        handle.write((json.dumps(row("e2", 2)) + "\n").encode())
    assert [r["event_id"] for r in read_jsonl_records(path)] == ["e0", "e1", "e2"]


def test_corrupt_compressed_segment_fails_closed(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    writer.append_event(row("e0", 0))
    entry = writer.seal()
    compressed = path.parent / (path.name + ".segments") / entry["file"]
    compressed.write_bytes(b"not zstandard")
    with pytest.raises(JsonlSegmentError):
        read_jsonl_records(path)


def test_manifest_hash_tamper_fails_closed(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    writer.append_event(row("e0", 0))
    writer.seal()
    manifest_path = path.parent / (path.name + ".segments") / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["segments"][0]["source_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(JsonlSegmentError):
        read_jsonl_records(path)


def test_hot_file_mismatch_after_manifest_commit_fails_closed(tmp_path):
    import forward.sealed_jsonl_segments_v1 as segments
    path = tmp_path / "journal.jsonl"
    path.write_bytes((json.dumps(row("e0", 0)) + "\n").encode())
    with segments._locked(path, exclusive=True):
        entry = segments._seal_hot_file_unlocked(path, truncate_hot=False)
    path.write_bytes(b'{"event_id":"different"}\n' + b" " * (entry["source_bytes"]))
    with pytest.raises(JsonlSegmentError, match="HOT_PREFIX_DOES_NOT_MATCH"):
        read_jsonl_records(path)


def test_seal_threshold_is_opt_in_and_does_not_seal_below_threshold(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    writer.append_event(row("e0", 0))
    assert seal_if_over(path, max_hot_bytes=10_000) is None
    assert path.stat().st_size > 0
    assert seal_if_over(path, max_hot_bytes=1)["record_count"] == 1


def test_concurrent_appends_and_seal_preserve_all_events(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    errors = []
    def append(n):
        try:
            writer.append_event(row(f"e{n}", n))
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=append, args=(n,)) for n in range(24)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors
    writer.seal()
    ids = [r["event_id"] for r in read_jsonl_records(path)]
    assert len(ids) == 24
    assert len(set(ids)) == 24


def test_logical_hash_and_size_match_original_bytes_after_multiple_generations(tmp_path):
    from forward.sealed_jsonl_segments_v1 import logical_sha256, logical_size_bytes
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    expected = bytearray()
    for n in range(4):
        item = row(f"e{n}", n)
        line = (json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n").encode()
        assert writer.append_event(item)
        expected.extend(line)
        if n in (1, 3):
            writer.seal()
    assert logical_sha256(path) == __import__("hashlib").sha256(expected).hexdigest()
    assert logical_size_bytes(path) == len(expected)
    assert read_jsonl_records(path) == [row(f"e{n}", n) for n in range(4)]


def test_sealing_preserves_last_real_append_mtime(tmp_path):
    import os
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    writer.append_event(row("e0", 0))
    before = path.stat().st_mtime_ns
    writer.seal()
    assert path.stat().st_mtime_ns == before


def test_seal_recovers_committed_prefix_before_sealing_new_hot_tail(tmp_path):
    import forward.sealed_jsonl_segments_v1 as segments
    path = tmp_path / "journal.jsonl"
    path.write_bytes(b"".join((json.dumps(row(f"e{i}", i)) + "\n").encode() for i in range(2)))
    with segments._locked(path, exclusive=True):
        segments._seal_hot_file_unlocked(path, truncate_hot=False)
    with path.open("ab") as handle:
        handle.write((json.dumps(row("e2", 2)) + "\n").encode())
    writer = ForwardJournalV1(path)
    second = writer.seal()
    assert second["record_count"] == 1
    manifest = json.loads((path.parent / (path.name + ".segments") / "manifest.json").read_text())
    assert [item["seq"] for item in manifest["segments"]] == [1, 2]
    assert [item["record_count"] for item in manifest["segments"]] == [2, 1]
    assert [item["event_id"] for item in read_jsonl_records(path)] == ["e0", "e1", "e2"]


def test_orphan_segment_from_interrupted_publish_does_not_block_retry(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    writer.append_event(row("e0", 0))
    segment_dir = path.parent / (path.name + ".segments")
    segment_dir.mkdir()
    (segment_dir / "segment-00000001-deadbeef-orphan.jsonl.zst").write_bytes(b"orphan")
    entry = writer.seal()
    assert entry["seq"] == 1
    assert [r["event_id"] for r in read_jsonl_records(path)] == ["e0"]


def test_bounded_tail_reads_latest_rows_across_multiple_segments_and_hot_file(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    for n in range(2):
        writer.append_event(row(f"e{n}", n))
    writer.seal()
    for n in range(2, 4):
        writer.append_event(row(f"e{n}", n))
    writer.seal()
    for n in range(4, 6):
        writer.append_event(row(f"e{n}", n))
    assert [r["event_id"] for r in read_jsonl_records(path, limit=3)] == ["e3", "e4", "e5"]
    assert [r["event_id"] for r in read_jsonl_records(path, limit=5)] == ["e1", "e2", "e3", "e4", "e5"]


def test_bounded_tail_skips_unread_cold_segments_but_full_audit_detects_tampering(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    for n in range(2):
        writer.append_event(row(f"e{n}", n))
    first = writer.seal()
    for n in range(2, 4):
        writer.append_event(row(f"e{n}", n))
    writer.seal()
    segment = path.parent / (path.name + ".segments") / first["file"]
    segment.write_bytes(b"tampered")
    assert [item["event_id"] for item in read_jsonl_records(path, limit=1)] == ["e3"]
    with pytest.raises(JsonlSegmentError, match="COMPRESSED_SEGMENT_HASH_MISMATCH"):
        read_jsonl_records(path)


def test_bounded_tail_fails_closed_when_selected_segment_is_corrupt(tmp_path):
    path = tmp_path / "journal.jsonl"
    writer = ForwardJournalV1(path)
    for n in range(2):
        writer.append_event(row(f"e{n}", n))
    entry = writer.seal()
    segment = path.parent / (path.name + ".segments") / entry["file"]
    segment.write_bytes(b"tampered")
    with pytest.raises(JsonlSegmentError, match="COMPRESSED_SEGMENT_HASH_MISMATCH"):
        read_jsonl_records(path, limit=1)


def test_read_only_jsonl_uses_read_only_source_lock_fallback(tmp_path):
    import os
    from forward.sealed_jsonl_segments_v1 import read_jsonl_records

    path = tmp_path / "immutable" / "evidence.jsonl"
    path.parent.mkdir()
    path.write_bytes(bytes.fromhex("7b226576656e745f6964223a22696d6d757461626c652d31227d0a"))
    path.chmod(0o444)
    path.parent.chmod(0o555)
    try:
        assert read_jsonl_records(path) == [{"event_id": "immutable-1"}]
        assert not path.with_name(path.name + ".lock").exists()
    finally:
        path.parent.chmod(0o755)