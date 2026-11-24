"""Verified, crash-aware Zstandard segments for append-only JSONL artifacts.

The active writer path remains plain JSONL. Explicit sealing compresses only the
writer-locked closed prefix, records a hash-bound manifest, then removes that
prefix from the hot file. Readers take the same advisory lock and merge verified
segments followed by the hot tail. Requires the existing system zstd CLI.
"""
from __future__ import annotations

from collections import deque
import errno
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import pwd
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import uuid
from typing import Any, Iterator

SCHEMA = "hes_jsonl_segment_manifest_v1"
VERSION = 1
MAX_LINE_BYTES = 1024 * 1024


class JsonlSegmentError(ValueError):
    """A segmented JSONL artifact is incomplete, corrupt, or ambiguous."""


def _lock_path(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


@contextmanager
def _locked(path: Path, *, exclusive: bool) -> Iterator[None]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise JsonlSegmentError("SOURCE_PATH_SYMLINK")
    lock_path = _lock_path(path)
    if lock_path.is_symlink():
        raise JsonlSegmentError("LOCK_PATH_SYMLINK")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if not lock_path.exists():
        try:
            create_fd = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | nofollow,
                0o640,
            )
            os.close(create_fd)
        except FileExistsError:
            pass
        except OSError as exc:
            # Immutable/read-only JSONL evidence cannot host a sidecar lock.
            # In that case only, lock the read-only source (or manifest when
            # the hot file is absent). Writers cannot mutate that directory.
            if exc.errno not in (errno.EACCES, errno.EPERM, errno.EROFS):
                raise
            fallback = path if path.is_file() else _manifest_path(path)
            if fallback.is_symlink() or not fallback.is_file():
                raise
            fd = os.open(fallback, os.O_RDONLY | nofollow)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                try:
                    yield
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
            return
    fd = os.open(lock_path, os.O_RDONLY | nofollow)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)

def _segment_dir(path: Path) -> Path:
    return path.with_name(path.name + ".segments")


def _manifest_path(path: Path) -> Path:
    return _segment_dir(path) / "manifest.json"


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def _parse_jsonl(raw: bytes, *, line_no: int, allow_final_no_newline: bool = False, skip_blank_lines: bool = False) -> dict[str, Any] | None:
    if len(raw) > MAX_LINE_BYTES:
        raise JsonlSegmentError(f"record size limit exceeded at line {line_no}")
    if not raw.endswith(b"\n") and not allow_final_no_newline:
        raise JsonlSegmentError(f"journal has incomplete trailing record at line {line_no}")
    if raw in (b"\n", b"\r\n"):
        if skip_blank_lines:
            return None
        raise JsonlSegmentError(f"journal contains blank record at line {line_no}")
    try:
        row = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JsonlSegmentError(f"journal contains malformed JSON at line {line_no}") from exc
    if not isinstance(row, dict):
        raise JsonlSegmentError(f"journal record is not an object at line {line_no}")
    return row


def _load_manifest_unlocked(path: Path) -> dict[str, Any]:
    manifest_path = _manifest_path(path)
    directory = _segment_dir(path)
    if directory.is_symlink():
        raise JsonlSegmentError("SEGMENT_DIRECTORY_SYMLINK")
    if manifest_path.is_symlink():
        raise JsonlSegmentError("MANIFEST_SYMLINK")
    if not manifest_path.exists():
        return {"schema": SCHEMA, "version": VERSION, "source_name": path.name, "segments": []}
    if not manifest_path.is_file():
        raise JsonlSegmentError("MANIFEST_NOT_REGULAR_FILE")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JsonlSegmentError("MANIFEST_UNREADABLE") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or data.get("version") != VERSION:
        raise JsonlSegmentError("MANIFEST_SCHEMA_MISMATCH")
    if data.get("source_name") != path.name or not isinstance(data.get("segments"), list):
        raise JsonlSegmentError("MANIFEST_SOURCE_MISMATCH")
    previous_seq = 0
    seen_names: set[str] = set()
    for item in data["segments"]:
        if not isinstance(item, dict):
            raise JsonlSegmentError("MANIFEST_SEGMENT_INVALID")
        seq, name = item.get("seq"), item.get("file")
        if type(seq) is not int or seq != previous_seq + 1:
            raise JsonlSegmentError("MANIFEST_SEQUENCE_INVALID")
        if item.get("compression") != "zstd" or type(item.get("level")) is not int or item.get("level") != 9:
            raise JsonlSegmentError("MANIFEST_COMPRESSION_PROFILE_INVALID")
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".jsonl.zst") or name in seen_names:
            raise JsonlSegmentError("MANIFEST_FILENAME_INVALID")
        for key in ("source_sha256", "compressed_sha256"):
            value = item.get(key)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise JsonlSegmentError("MANIFEST_HASH_INVALID")
        for key in ("source_bytes", "compressed_bytes", "record_count"):
            if type(item.get(key)) is not int or item[key] < 1:
                raise JsonlSegmentError("MANIFEST_SIZE_INVALID")
        for key in ("source_dev", "source_ino"):
            if type(item.get(key)) is not int or item[key] < 0:
                raise JsonlSegmentError("MANIFEST_SOURCE_FILE_ID_INVALID")
        previous_seq = seq
        seen_names.add(name)
    return data


def has_sealed_segments(path: str | Path) -> bool:
    source = Path(path)
    # This API describes sealed JSONL ledgers only. Do not create sidecar
    # locks for reports, source files, or absent ledgers during a read-only probe.
    if source.suffix.lower() != ".jsonl":
        return False
    directory = _segment_dir(source)
    if not directory.exists():
        return False
    with _locked(source, exclusive=False):
        return bool(_load_manifest_unlocked(source)["segments"])

def _iter_compressed_segment_raw(path: Path, item: dict[str, Any]) -> Iterator[bytes]:
    compressed = _segment_dir(path) / item["file"]
    if compressed.is_symlink() or not compressed.is_file():
        raise JsonlSegmentError("SEGMENT_FILE_MISSING_OR_SYMLINK")
    compressed_hash, compressed_size = _sha256_file(compressed)
    if compressed_hash != item["compressed_sha256"] or compressed_size != item["compressed_bytes"]:
        raise JsonlSegmentError("COMPRESSED_SEGMENT_HASH_MISMATCH")
    process = subprocess.Popen(
        ["zstd", "-q", "-d", "-c", str(compressed)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    digest = hashlib.sha256()
    total_bytes = 0
    try:
        for raw in process.stdout:
            digest.update(raw)
            total_bytes += len(raw)
            yield raw
    finally:
        process.stdout.close()
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    rc = process.wait()
    if rc != 0:
        raise JsonlSegmentError("ZSTD_DECOMPRESSION_FAILED:" + stderr[-200:])
    if digest.hexdigest() != item["source_sha256"] or total_bytes != item["source_bytes"]:
        raise JsonlSegmentError("SOURCE_SEGMENT_HASH_MISMATCH")


def _iter_compressed_segment_entries(path: Path, item: dict[str, Any]) -> Iterator[tuple[dict[str, Any], bytes]]:
    count = 0
    for line_no, raw in enumerate(_iter_compressed_segment_raw(path, item), start=1):
        count += 1
        yield _parse_jsonl(raw, line_no=line_no), raw
    if count != item["record_count"]:
        raise JsonlSegmentError("SEGMENT_RECORD_COUNT_MISMATCH")


def _iter_compressed_segment(path: Path, item: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for row, _raw in _iter_compressed_segment_entries(path, item):
        yield row


def _read_entries_unlocked(path: Path) -> list[tuple[dict[str, Any], bytes]]:
    manifest = _load_manifest_unlocked(path)
    entries: list[tuple[dict[str, Any], bytes]] = []
    for item in manifest["segments"]:
        entries.extend(_iter_compressed_segment_entries(path, item))
    skip = _hot_prefix_to_skip(path, manifest["segments"])
    if path.exists():
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise JsonlSegmentError("HOT_FILE_NOT_REGULAR")
        with path.open("rb") as handle:
            if skip:
                handle.seek(skip)
            for line_no, raw in enumerate(handle, start=1):
                entries.append((_parse_jsonl(raw, line_no=line_no), raw))
    return entries


def read_jsonl_entries(path: str | Path) -> list[tuple[dict[str, Any], bytes]]:
    """Read verified logical rows together with their original JSONL bytes."""
    source = Path(path)
    with _locked(source, exclusive=False):
        return _read_entries_unlocked(source)



def iter_jsonl_entries(path: str | Path) -> Iterator[tuple[dict[str, Any], bytes]]:
    """Stream verified logical JSONL rows without materializing all sealed records.

    Immutable segments are read outside the source lock. The manifest is snapshotted
    under a shared lock; before reading the hot tail, the manifest is rechecked under
    lock so a concurrent seal cannot create a mixed-generation view. The hot tail is
    read under a shared lock, preventing append/seal races while it is consumed.
    Plain, unsealed files retain the legacy streaming behavior.
    """
    source = Path(path)
    if not has_sealed_segments(source):
        if source.exists():
            if source.is_symlink() or not stat.S_ISREG(source.stat().st_mode):
                raise JsonlSegmentError("HOT_FILE_NOT_REGULAR")
            with source.open("rb") as handle:
                for line_no, raw in enumerate(handle, start=1):
                    yield _parse_jsonl(raw, line_no=line_no), raw
        return

    with _locked(source, exclusive=False):
        manifest = _load_manifest_unlocked(source)
        snapshot = json.loads(json.dumps(manifest, sort_keys=True))
        skip = _hot_prefix_to_skip(source, snapshot["segments"])

    # Segment payloads are immutable; checksum and record-count validation occurs
    # as each segment streams. No journal-sized list is built in memory.
    for item in snapshot["segments"]:
        yield from _iter_compressed_segment_entries(source, item)

    # Appends may have advanced the hot tail while segments were being read.
    # A seal changes the manifest and forces a fail-closed retry instead of mixing
    # generations. Hold the shared lock only while consuming the bounded hot tail.
    with _locked(source, exclusive=False):
        current = _load_manifest_unlocked(source)
        if current != snapshot:
            raise JsonlSegmentError("MANIFEST_CHANGED_DURING_STREAM")
        current_skip = _hot_prefix_to_skip(source, current["segments"])
        if current_skip != skip:
            raise JsonlSegmentError("HOT_PREFIX_CHANGED_DURING_STREAM")
        if source.exists():
            if source.is_symlink() or not stat.S_ISREG(source.stat().st_mode):
                raise JsonlSegmentError("HOT_FILE_NOT_REGULAR")
            with source.open("rb") as handle:
                if current_skip:
                    handle.seek(current_skip)
                for line_no, raw in enumerate(handle, start=1):
                    yield _parse_jsonl(raw, line_no=line_no), raw

def logical_sha256(path: str | Path) -> str:
    """SHA-256 of the logical uncompressed JSONL byte stream across segments + hot tail."""
    source = Path(path)
    with _locked(source, exclusive=False):
        manifest = _load_manifest_unlocked(source)
        return logical_sha256_unlocked(source, manifest)



def logical_size_bytes(path: str | Path) -> int:
    """Logical uncompressed byte count across verified segments and the hot tail."""
    source = Path(path)
    with _locked(source, exclusive=False):
        manifest = _load_manifest_unlocked(source)
        total = sum(item["source_bytes"] for item in manifest["segments"])
        skip = _hot_prefix_to_skip(source, manifest["segments"])
        if source.exists():
            total += max(0, source.stat().st_size - skip)
        return total


def _hot_prefix_to_skip(path: Path, segments: list[dict[str, Any]]) -> int:
    if not path.exists():
        return 0
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise JsonlSegmentError("HOT_FILE_NOT_REGULAR")
    if not segments:
        return 0
    last = segments[-1]
    prefix_size = last["source_bytes"]
    hot_stat = path.stat()
    same_source_inode = (
        hot_stat.st_dev == last["source_dev"]
        and hot_stat.st_ino == last["source_ino"]
    )
    if hot_stat.st_size < prefix_size:
        if same_source_inode:
            raise JsonlSegmentError("HOT_PREFIX_TRUNCATED")
        return 0
    digest = hashlib.sha256()
    remaining = prefix_size
    with path.open("rb") as handle:
        while remaining:
            block = handle.read(min(1024 * 1024, remaining))
            if not block:
                raise JsonlSegmentError("HOT_PREFIX_TRUNCATED")
            digest.update(block)
            remaining -= len(block)
    if digest.hexdigest() == last["source_sha256"]:
        return prefix_size
    if same_source_inode:
        raise JsonlSegmentError("HOT_PREFIX_DOES_NOT_MATCH_LAST_SEGMENT")
    return 0


def _read_hot_tail_unlocked(
    path: Path, *, skip_bytes: int, limit: int,
    allow_final_no_newline: bool = False, skip_blank_lines: bool = False,
) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise JsonlSegmentError("HOT_FILE_NOT_REGULAR")
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        if position <= skip_bytes:
            return []
        chunks: list[bytes] = []
        newline_count = 0
        while position > skip_bytes and newline_count <= limit:
            size = min(64 * 1024, position - skip_bytes)
            position -= size
            handle.seek(position)
            block = handle.read(size)
            chunks.insert(0, block)
            newline_count += block.count(b"\n")
    data = b"".join(chunks)
    if position > skip_bytes:
        first_newline = data.find(b"\n")
        if first_newline < 0:
            return []
        data = data[first_newline + 1:]
    lines = data.splitlines(keepends=True)
    if len(lines) > limit:
        lines = lines[-limit:]
    rows = []
    for line_no, raw in enumerate(lines, start=1):
        row = _parse_jsonl(
            raw, line_no=line_no,
            allow_final_no_newline=allow_final_no_newline,
            skip_blank_lines=skip_blank_lines,
        )
        if row is not None:
            rows.append(row)
    return rows[-limit:]


def _read_records_unlocked(
    path: Path, *, limit: int | None = None,
    allow_final_no_newline: bool = False, skip_blank_lines: bool = False,
) -> list[dict[str, Any]]:
    manifest = _load_manifest_unlocked(path)
    if limit is not None:
        # A bounded live read verifies only the newest sealed segments it
        # actually consumes. Full Smart Storage verification audits every
        # segment; hot-path reads must not scan decades of cold compressed data.
        skip = _hot_prefix_to_skip(path, manifest["segments"])
        hot_rows = _read_hot_tail_unlocked(
            path, skip_bytes=skip, limit=limit,
            allow_final_no_newline=allow_final_no_newline,
            skip_blank_lines=skip_blank_lines,
        )
        remaining = limit - len(hot_rows)
        selected: list[dict[str, Any]] = []
        for item in reversed(manifest["segments"]):
            if remaining <= 0:
                break
            segment_rows = list(_iter_compressed_segment(path, item))
            take = min(remaining, len(segment_rows))
            selected = segment_rows[-take:] + selected
            remaining -= take
        return selected + hot_rows

    rows: list[dict[str, Any]] = []
    for item in manifest["segments"]:
        rows.extend(_iter_compressed_segment(path, item))
    skip = _hot_prefix_to_skip(path, manifest["segments"])
    if path.exists():
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise JsonlSegmentError("HOT_FILE_NOT_REGULAR")
        with path.open("rb") as handle:
            if skip:
                handle.seek(skip)
            for line_no, raw in enumerate(handle, start=1):
                row = _parse_jsonl(raw, line_no=line_no, skip_blank_lines=skip_blank_lines)
                if row is not None:
                    rows.append(row)
    return rows


def read_jsonl_records(path: str | Path, *, limit: int | None = None, allow_final_no_newline: bool = False, skip_blank_lines: bool = False) -> list[dict[str, Any]]:
    source = Path(path)
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("limit must be a positive integer")
    with _locked(source, exclusive=False):
        return _read_records_unlocked(source, limit=limit, allow_final_no_newline=allow_final_no_newline, skip_blank_lines=skip_blank_lines)


def _write_manifest_atomic(path: Path, manifest: dict[str, Any]) -> None:
    directory = _segment_dir(path)
    directory.mkdir(parents=True, exist_ok=True, mode=0o750)
    temp_fd, temp_name = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=directory)
    source_stat = path.stat() if path.exists() else directory.stat()
    try:
        os.fchown(temp_fd, source_stat.st_uid, source_stat.st_gid)
        os.fchmod(temp_fd, 0o640)
        with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, _manifest_path(path))
        _fsync_dir(directory)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _seal_hot_file_unlocked(path: Path, *, truncate_hot: bool = True) -> dict[str, Any] | None:
    if path.is_symlink():
        raise JsonlSegmentError("HOT_FILE_SYMLINK")
    if not path.exists():
        return None
    if not stat.S_ISREG(path.stat().st_mode):
        raise JsonlSegmentError("HOT_FILE_NOT_REGULAR")
    manifest_before = _load_manifest_unlocked(path)
    committed_prefix = _hot_prefix_to_skip(path, manifest_before["segments"])
    if committed_prefix:
        current_stat = path.stat()
        fd, recovery_name = tempfile.mkstemp(prefix=f".{path.name}.recover-", dir=path.parent)
        try:
            with path.open("rb") as original, os.fdopen(fd, "wb") as recovered:
                original.seek(committed_prefix)
                shutil.copyfileobj(original, recovered, length=1024 * 1024)
                recovered.flush()
                os.fsync(recovered.fileno())
            os.chmod(recovery_name, stat.S_IMODE(current_stat.st_mode))
            os.replace(recovery_name, path)
            os.utime(path, ns=(current_stat.st_atime_ns, current_stat.st_mtime_ns))
            _fsync_dir(path.parent)
        finally:
            if os.path.exists(recovery_name):
                os.unlink(recovery_name)
    source_stat = path.stat()
    source_hash, source_bytes = _sha256_file(path)
    if source_bytes == 0:
        return None

    # Validate every record and collect only compact provenance metadata.
    record_count = 0
    first_event_id = last_event_id = first_timestamp = last_timestamp = None
    with path.open("rb") as handle:
        for line_no, raw in enumerate(handle, start=1):
            row = _parse_jsonl(raw, line_no=line_no)
            record_count += 1
            if record_count == 1:
                first_event_id = row.get("event_id")
                first_timestamp = row.get("observed_at") or row.get("close_time")
            last_event_id = row.get("event_id")
            last_timestamp = row.get("observed_at") or row.get("close_time")
    if record_count == 0:
        return None

    manifest = _load_manifest_unlocked(path)
    seq = manifest["segments"][-1]["seq"] + 1 if manifest["segments"] else 1
    directory = _segment_dir(path)
    directory.mkdir(parents=True, exist_ok=True, mode=0o2750)
    # Preserve runtime writer/dashboard group access even when root performs sealing.
    os.chown(directory, source_stat.st_uid, source_stat.st_gid)
    os.chmod(directory, 0o2750)
    filename = f"segment-{seq:08d}-{source_hash[:12]}-{uuid.uuid4().hex[:8]}.jsonl.zst"
    final_path = directory / filename
    if final_path.exists():
        raise JsonlSegmentError("ORPHAN_SEGMENT_FILE_EXISTS")
    fd, temp_name = tempfile.mkstemp(prefix=".segment-", suffix=".tmp", dir=directory)
    os.fchown(fd, source_stat.st_uid, source_stat.st_gid)
    os.fchmod(fd, 0o640)
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with temp_path.open("wb") as output:
            result = subprocess.run(["zstd", "-q", "-9", "-T1", "-c", str(path)], stdout=output, stderr=subprocess.PIPE)
            if result.returncode != 0:
                raise JsonlSegmentError("ZSTD_COMPRESSION_FAILED:" + result.stderr.decode("utf-8", errors="replace")[-200:])
            output.flush()
            os.fsync(output.fileno())
        compressed_hash, compressed_bytes = _sha256_file(temp_path)
        # Verify decompression byte-for-byte before the manifest can reference it.
        decoder = subprocess.Popen(["zstd", "-q", "-d", "-c", str(temp_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert decoder.stdout is not None
        with path.open("rb") as original:
            cmp = subprocess.run(["cmp", "-s", "-", str(path)], stdin=decoder.stdout)
        decoder.stdout.close()
        decoder_stderr = decoder.stderr.read().decode("utf-8", errors="replace") if decoder.stderr else ""
        decoder_rc = decoder.wait()
        if cmp.returncode != 0 or decoder_rc != 0:
            raise JsonlSegmentError("SEGMENT_ROUNDTRIP_FAILED:" + decoder_stderr[-200:])
        os.replace(temp_path, final_path)
        _fsync_dir(directory)
        entry = {
            "seq": seq, "file": filename, "compression": "zstd", "level": 9,
            "source_bytes": source_bytes, "compressed_bytes": compressed_bytes,
            "source_dev": int(source_stat.st_dev), "source_ino": int(source_stat.st_ino),
            "source_sha256": source_hash, "compressed_sha256": compressed_hash,
            "record_count": record_count, "first_event_id": first_event_id,
            "last_event_id": last_event_id, "first_timestamp": first_timestamp,
            "last_timestamp": last_timestamp,
        }
        manifest["segments"].append(entry)
        _write_manifest_atomic(path, manifest)

        if truncate_hot:
            temp_fd, hot_temp_name = tempfile.mkstemp(prefix=f".{path.name}.hot-", dir=path.parent)
            try:
                mode = stat.S_IMODE(source_stat.st_mode)
                os.fchown(temp_fd, source_stat.st_uid, source_stat.st_gid)
                os.fchmod(temp_fd, mode)
                with os.fdopen(temp_fd, "wb") as hot_temp:
                    hot_temp.flush()
                    os.fsync(hot_temp.fileno())
                os.replace(hot_temp_name, path)
                # Preserve the last actual append time; an empty rotated file
                # must never make a stale feed/journal look freshly updated.
                os.utime(path, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))
                _fsync_dir(path.parent)
            finally:
                if os.path.exists(hot_temp_name):
                    os.unlink(hot_temp_name)
        return entry
    finally:
        if temp_path.exists():
            temp_path.unlink()


def inspect_lock_access(path: str | Path, *, username: str = "sentinelx") -> dict[str, Any]:
    """Check whether the runtime service identity can open the shared flock file read-only."""
    source = Path(path)
    lock_path = _lock_path(source)
    if not lock_path.exists():
        return {"status": "NOT_CREATED", "service_user": username, "can_open_readonly": True}
    if lock_path.is_symlink() or not lock_path.is_file():
        return {"status": "BLOCKED", "service_user": username, "can_open_readonly": False}
    st = lock_path.stat()
    try:
        uid = pwd.getpwnam(username).pw_uid
    except KeyError:
        return {"status": "UNKNOWN_USER", "service_user": username, "can_open_readonly": False}
    readable = (
        (st.st_uid == uid and bool(st.st_mode & stat.S_IRUSR))
        or bool(st.st_mode & stat.S_IROTH)
    )
    # Resolve the user's primary and supplementary groups using the process
    # account database when available; group-read is sufficient for flock.
    try:
        import grp
        import subprocess
        groups = {grp.getgrgid(pwd.getpwuid(uid).pw_gid).gr_gid}
        try:
            raw = subprocess.check_output(["id", "-G", username], text=True, timeout=2)
            groups.update(int(value) for value in raw.split())
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        readable = readable or (st.st_gid in groups and bool(st.st_mode & stat.S_IRGRP))
    except (KeyError, OSError):
        pass
    return {
        "status": "PASS" if readable else "BLOCKED",
        "service_user": username,
        "can_open_readonly": readable,
        "owner_uid": st.st_uid,
        "group_gid": st.st_gid,
        "mode_octal": oct(stat.S_IMODE(st.st_mode)),
    }


def inspect_jsonl_segments(path: str | Path, *, verify: bool = True) -> dict[str, Any]:
    """Return read-only segment/storage facts; optionally verify every segment end-to-end."""
    source = Path(path)
    # Do not create lock files during a read-only capacity inventory when no
    # segment generation exists. Active readers/writers create the shared lock.
    if not _lock_path(source).exists() and not _segment_dir(source).exists():
        hot_bytes = source.stat().st_size if source.is_file() and not source.is_symlink() else 0
        return {
            "status": "NO_SEGMENTS", "source_name": source.name,
            "segment_count": 0, "last_segment_seq": 0,
            "compressed_segment_bytes": 0, "sealed_source_bytes": 0,
            "hot_bytes": hot_bytes, "logical_bytes": hot_bytes,
            "record_count": None, "compression_saving_percent": None,
            "logical_sha256": None, "manifest_sha256": None, "verified": False,
        }
    with _locked(source, exclusive=False):
        manifest = _load_manifest_unlocked(source)
        segments = manifest["segments"]
        compressed_bytes = 0
        source_bytes = 0
        records = 0
        for item in segments:
            compressed = _segment_dir(source) / item["file"]
            if compressed.is_symlink() or not compressed.is_file():
                raise JsonlSegmentError("SEGMENT_FILE_MISSING_OR_SYMLINK")
            actual_hash, actual_size = _sha256_file(compressed)
            if actual_hash != item["compressed_sha256"] or actual_size != item["compressed_bytes"]:
                raise JsonlSegmentError("COMPRESSED_SEGMENT_HASH_MISMATCH")
            compressed_bytes += actual_size
            source_bytes += item["source_bytes"]
            records += item["record_count"]
        skip = _hot_prefix_to_skip(source, segments)
        hot_bytes = max(0, source.stat().st_size - skip) if source.exists() else 0
        if verify:
            rows = _read_records_unlocked(source)
            records = len(rows)
            logical_hash = logical_sha256_unlocked(source, manifest)
        else:
            logical_hash = None
        logical_bytes = source_bytes + hot_bytes
        return {
            "status": "VERIFIED" if segments and verify else "NO_SEGMENTS" if not segments else "MANIFEST_AND_COMPRESSED_HASHES_VERIFIED",
            "source_name": source.name,
            "segment_count": len(segments),
            "last_segment_seq": segments[-1]["seq"] if segments else 0,
            "compressed_segment_bytes": compressed_bytes,
            "sealed_source_bytes": source_bytes,
            "hot_bytes": hot_bytes,
            "logical_bytes": logical_bytes,
            "record_count": records,
            "compression_saving_percent": round((1 - compressed_bytes / source_bytes) * 100, 2) if source_bytes else None,
            "logical_sha256": logical_hash,
            "manifest_sha256": hashlib.sha256(_manifest_path(source).read_bytes()).hexdigest() if segments else None,
            "verified": bool(verify and segments),
        }


def logical_sha256_unlocked(source: Path, manifest: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for item in manifest["segments"]:
        for raw in _iter_compressed_segment_raw(source, item):
            digest.update(raw)
    skip = _hot_prefix_to_skip(source, manifest["segments"])
    if source.exists():
        with source.open("rb") as handle:
            if skip:
                handle.seek(skip)
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def seal_hot_file(path: str | Path) -> dict[str, Any] | None:
    """Seal the current hot JSONL file under its shared writer/reader lock."""
    source = Path(path)
    with _locked(source, exclusive=True):
        return _seal_hot_file_unlocked(source)


def seal_if_over(path: str | Path, *, max_hot_bytes: int) -> dict[str, Any] | None:
    """Explicitly seal only when the hot file reaches a caller-chosen threshold."""
    if type(max_hot_bytes) is not int or max_hot_bytes < 1:
        raise ValueError("max_hot_bytes must be a positive integer")
    source = Path(path)
    if not source.exists() or source.stat().st_size < max_hot_bytes:
        return None
    return seal_hot_file(source)