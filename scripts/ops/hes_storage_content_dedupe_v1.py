#!/usr/bin/env python3
"""Safely deduplicate immutable HES offsite snapshot payloads with hardlinks.

No paths are deleted. Only byte-identical regular files under completed,
time-stamped recovery snapshots (and immutable root-level archive payloads) are
eligible. File metadata needed to reconstruct independent copies is recorded
before the first link is changed.
"""
from __future__ import annotations
import argparse
import fcntl
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import shutil
from typing import Any

SCHEMA = "hes_storage_content_dedupe_v1"
SNAPSHOT_DIR_RE = re.compile(r"^(?:differential-v2|live-data-snapshot)-\d{8}T\d{6}Z$")
ARCHIVE_NAMES = ("hes-offsite-core-", "hes-offsite-recovery-core-", "verified-previous-core-")
ARCHIVE_SUFFIXES = (".tar.zst.gpg", ".bundle")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_roots(root: Path, now: datetime, min_age_seconds: int) -> list[Path]:
    roots: list[Path] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and SNAPSHOT_DIR_RE.fullmatch(child.name):
            try:
                stamp = datetime.strptime(child.name.rsplit("-", 1)[-1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if (now - stamp).total_seconds() >= min_age_seconds:
                roots.append(child)
    return roots


def _eligible_paths(root: Path, now: datetime, min_age_seconds: int, min_size_bytes: int) -> list[Path]:
    paths: list[Path] = []
    for snapshot_root in _snapshot_roots(root, now, min_age_seconds):
        for base, dirs, files in os.walk(snapshot_root, followlinks=False):
            dirs[:] = [d for d in dirs if d != "failed-builds" and not (Path(base) / d).is_symlink()]
            for name in files:
                path = Path(base) / name
                try:
                    st = path.lstat()
                except OSError:
                    continue
                if stat.S_ISREG(st.st_mode) and st.st_size >= min_size_bytes:
                    paths.append(path)
    # A small, explicit allowlist for immutable archive payloads at the staging root.
    for path in root.parent.iterdir():
        if not path.is_file() or path.is_symlink():
            continue
        if not path.name.endswith(ARCHIVE_SUFFIXES):
            continue
        if not path.name.startswith(ARCHIVE_NAMES):
            continue
        try:
            st = path.lstat()
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode) and st.st_size >= min_size_bytes:
            if (now.timestamp_ns() if hasattr(now, "timestamp_ns") else int(now.timestamp() * 1e9)) - st.st_mtime_ns >= min_age_seconds * 1_000_000_000:
                paths.append(path)
    return paths


def open_inodes(proc_root: Path = Path("/proc")) -> set[tuple[int, int]]:
    """Return regular-file inodes currently open by any visible process."""
    result: set[tuple[int, int]] = set()
    if not proc_root.is_dir():
        return result
    for proc in proc_root.iterdir():
        if not proc.name.isdigit():
            continue
        fd_dir = proc / "fd"
        try:
            fds = list(fd_dir.iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                st = fd.stat()
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                result.add((st.st_dev, st.st_ino))
    return result


def plan_dedupe(
    root: Path,
    *,
    now: datetime | None = None,
    min_age_seconds: int = 3600,
    min_size_bytes: int = 1024 * 1024,
    open_inode_set: set[tuple[int, int]] | None = None,
) -> dict[str, Any]:
    root = root.resolve(strict=True)
    now = now or datetime.now(timezone.utc)
    if not root.is_dir() or root.name != "recovery-metadata":
        raise ValueError("root must be the exact HES recovery-metadata directory")
    opened = open_inode_set if open_inode_set is not None else open_inodes()
    candidates = _eligible_paths(root, now, min_age_seconds, min_size_bytes)
    groups: dict[tuple[int, int, str, int, int, int], list[dict[str, Any]]] = defaultdict(list)
    errors: list[str] = []
    for path in candidates:
        try:
            st = path.lstat()
            if (st.st_dev, st.st_ino) in opened or st.st_nlink != 1:
                continue
            digest = sha256_file(path)
            key = (st.st_dev, st.st_size, digest, st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode))
            groups[key].append({
                "path": str(path), "size_bytes": st.st_size,
                "allocated_bytes": st.st_blocks * 512,
                "sha256": digest, "uid": st.st_uid, "gid": st.st_gid,
                "mode": stat.S_IMODE(st.st_mode), "mtime_ns": st.st_mtime_ns,
                "atime_ns": st.st_atime_ns, "original_inode": st.st_ino,
                "device": st.st_dev, "nlink": st.st_nlink,
            })
        except OSError as exc:
            errors.append(f"{path}:{type(exc).__name__}")
    groups_out: list[dict[str, Any]] = []
    for (device, size, digest, uid, gid, mode), rows in groups.items():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda row: row["path"])
        canonical = rows[0]
        duplicates = rows[1:]
        groups_out.append({
            "device": device, "size_bytes": size, "sha256": digest,
            "uid": uid, "gid": gid, "mode": mode,
            "canonical_path": canonical["path"],
            "canonical_metadata": canonical,
            "duplicates": duplicates,
            "potential_saved_bytes": sum(row["allocated_bytes"] for row in duplicates),
        })
    groups_out.sort(key=lambda row: row["potential_saved_bytes"], reverse=True)
    return {
        "schema": SCHEMA, "generated_at_utc": now.isoformat(),
        "root": str(root), "min_age_seconds": min_age_seconds,
        "min_size_bytes": min_size_bytes, "candidate_file_count": len(candidates),
        "duplicate_group_count": len(groups_out),
        "duplicate_path_count": sum(len(g["duplicates"]) for g in groups_out),
        "potential_saved_bytes": sum(g["potential_saved_bytes"] for g in groups_out),
        "errors": errors, "groups": groups_out,
        "mutation_policy": "HARDLINK_IDENTICAL_FILES_ONLY_NO_PATH_DELETION",
    }


def apply_dedupe(plan: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    if plan.get("schema") != SCHEMA or plan.get("errors"):
        raise ValueError("invalid or incomplete dedupe plan")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = dict(plan)
    manifest.update({"status": "PREPARED", "linked_paths": [], "failed_paths": []})
    fd, raw_tmp = tempfile.mkstemp(prefix=manifest_path.name + ".", suffix=".tmp", dir=manifest_path.parent)
    tmp_manifest = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp_manifest, 0o600)
        os.replace(tmp_manifest, manifest_path)
    finally:
        if tmp_manifest.exists():
            tmp_manifest.unlink()

    for group in plan["groups"]:
        canonical = Path(group["canonical_path"])
        for row in group["duplicates"]:
            duplicate = Path(row["path"])
            try:
                cst = canonical.lstat()
                dst = duplicate.lstat()
                if (not stat.S_ISREG(cst.st_mode) or not stat.S_ISREG(dst.st_mode)
                        or cst.st_dev != dst.st_dev or dst.st_nlink != 1
                        or cst.st_size != dst.st_size
                        or sha256_file(canonical) != group["sha256"]
                        or sha256_file(duplicate) != group["sha256"]):
                    raise ValueError("source changed after preflight")
                link_tmp = duplicate.with_name("." + duplicate.name + ".dedupe-link-tmp")
                if link_tmp.exists():
                    raise FileExistsError(link_tmp)
                os.link(canonical, link_tmp, follow_symlinks=False)
                os.replace(link_tmp, duplicate)
                linked_st = duplicate.lstat()
                if (linked_st.st_dev, linked_st.st_ino) != (cst.st_dev, cst.st_ino):
                    raise ValueError("hardlink verification failed")
                manifest["linked_paths"].append({
                    "path": str(duplicate), "canonical_path": str(canonical),
                    "original_mtime_ns": row["mtime_ns"],
                    "original_atime_ns": row["atime_ns"],
                    "original_inode": row["original_inode"],
                    "sha256": group["sha256"], "size_bytes": row["size_bytes"],
                    "mode": row["mode"], "uid": row["uid"], "gid": row["gid"],
                    "allocated_bytes": row["allocated_bytes"],
                })
            except Exception as exc:
                manifest["failed_paths"].append({"path": str(duplicate), "error": f"{type(exc).__name__}:{exc}"})
    manifest["status"] = ("APPLIED_WITH_ERRORS" if manifest["failed_paths"] else ("APPLIED" if manifest["linked_paths"] else "NO_DUPLICATES"))
    manifest["linked_path_count"] = len(manifest["linked_paths"])
    manifest["actual_saved_bytes"] = sum(
        int(next(row["allocated_bytes"] for group in plan["groups"] for row in group["duplicates"] if row["path"] == item["path"]))
        for item in manifest["linked_paths"]
    )
    tmp = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, manifest_path)
    return manifest


def undo_dedupe(manifest_path: Path, *, min_free_bytes: int = 0) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or manifest.get("status") not in {"PREPARED", "APPLIED", "APPLIED_WITH_ERRORS"}:
        raise ValueError("dedupe manifest is not a prepared/applied manifest")
    rows = []
    for group in manifest.get("groups", []):
        canonical = Path(group["canonical_path"])
        for item in group.get("duplicates", []):
            row = dict(item)
            row["canonical_path"] = str(canonical)
            row["sha256"] = group["sha256"]
            path = Path(row["path"])
            try:
                if (path.lstat().st_dev, path.lstat().st_ino) == (canonical.lstat().st_dev, canonical.lstat().st_ino):
                    rows.append(row)
            except OSError:
                continue
    required = sum(int(row.get("allocated_bytes", row["size_bytes"])) for row in rows)
    free = os.statvfs(manifest_path.parent).f_bavail * os.statvfs(manifest_path.parent).f_frsize
    if free < max(min_free_bytes, required):
        raise OSError(f"insufficient space to undo dedupe: free={free} required={max(min_free_bytes, required)}")
    restored = []
    failed = []
    for row in rows:
        path = Path(row["path"])
        canonical = Path(row["canonical_path"])
        try:
            st = path.lstat()
            cst = canonical.lstat()
            if (st.st_dev, st.st_ino) != (cst.st_dev, cst.st_ino):
                continue
            if sha256_file(path) != row["sha256"]:
                raise ValueError("linked content hash changed")
            fd, raw_tmp = tempfile.mkstemp(prefix=path.name + ".undo.", dir=path.parent)
            os.close(fd)
            tmp = Path(raw_tmp)
            shutil.copyfile(path, tmp)
            os.chown(tmp, int(row["uid"]), int(row["gid"]))
            os.chmod(tmp, int(row["mode"]))
            os.utime(tmp, ns=(int(row["original_atime_ns"]), int(row["original_mtime_ns"])))
            if sha256_file(tmp) != row["sha256"]:
                raise ValueError("restored copy hash mismatch")
            os.replace(tmp, path)
            restored.append(str(path))
        except Exception as exc:
            failed.append({"path": str(path), "error": f"{type(exc).__name__}:{exc}"})
    manifest["undo_status"] = "UNDONE_WITH_ERRORS" if failed else "UNDONE"
    manifest["undo_restored_paths"] = restored
    manifest["undo_failed_paths"] = failed
    tmp_manifest = manifest_path.with_suffix(manifest_path.suffix + ".undo.tmp")
    tmp_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(tmp_manifest, 0o600)
    os.replace(tmp_manifest, manifest_path)
    return {"undo_status": manifest["undo_status"], "restored_path_count": len(restored), "failed_paths": failed, "required_free_bytes": required, "free_bytes": free}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/var/backups/hes-trade-agent/offsite-staging/recovery-metadata"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-dir", type=Path, default=Path("/srv/hes-evidence/operations/storage-lifecycle"))
    parser.add_argument("--undo-manifest", type=Path)
    parser.add_argument("--min-age-seconds", type=int, default=3600)
    parser.add_argument("--min-size-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--lock-file", type=Path, default=Path("/run/hes-storage-content-dedupe/lock"))
    parser.add_argument("--writer-lock-file", type=Path, default=Path("/run/lock/hes-dropbox-offsite-build.lock"))
    parser.add_argument("--apply", action="store_true", help="replace exact duplicate files with hardlinks; no paths are deleted")
    ns = parser.parse_args()
    ns.lock_file.parent.mkdir(parents=True, exist_ok=True)
    with ns.lock_file.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("HES_CONTENT_DEDUPE_ALREADY_RUNNING")
            return 0
        writer_lock = ns.writer_lock_file.open("a+")
        try:
            fcntl.flock(writer_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("HES_OFFSITE_BUILD_ACTIVE_DEDUPE_DEFERRED")
            return 0
        if ns.undo_manifest:
            result = undo_dedupe(ns.undo_manifest)
            print(json.dumps(result, sort_keys=True))
            return 0 if result["undo_status"] == "UNDONE" else 2
        plan = plan_dedupe(ns.root, min_age_seconds=ns.min_age_seconds, min_size_bytes=ns.min_size_bytes)
        if ns.apply:
            manifest_path = ns.manifest or (ns.manifest_dir / ("content-dedupe-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"))
            result = apply_dedupe(plan, manifest_path)
            print(json.dumps({k: result.get(k) for k in ("status", "candidate_file_count", "duplicate_group_count", "duplicate_path_count", "potential_saved_bytes", "actual_saved_bytes", "linked_path_count", "failed_paths")}, sort_keys=True))
            return 0 if result["status"] in {"APPLIED", "NO_DUPLICATES"} else 2
        print(json.dumps({k: plan.get(k) for k in ("candidate_file_count", "duplicate_group_count", "duplicate_path_count", "potential_saved_bytes", "errors")}, sort_keys=True))
        return 0 if not plan["errors"] else 2

if __name__ == "__main__":
    raise SystemExit(main())