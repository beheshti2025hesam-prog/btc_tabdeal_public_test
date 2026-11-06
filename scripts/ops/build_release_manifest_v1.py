#!/usr/bin/env python3
"""Build and verify the immutable-release manifest from an exact Git commit.

Run after extracting the commit archive into releases/<commit-sha> and before
making the release directory read-only or switching the current symlink.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
from typing import Any

MANIFEST_NAME = "HES_RELEASE_MANIFEST_v1.json"
SIDECAR_NAME = "HES_RELEASE_MANIFEST_v1.sha256"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class ReleaseManifestError(RuntimeError):
    """Raised when the release cannot be proven to match its Git commit."""


def _git(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ReleaseManifestError(f"GIT_COMMAND_FAILED:{args[0]}:{detail[:240]}")
    return result.stdout


def _validate_roots(repo_root: Path, release_dir: Path, commit_sha: str) -> tuple[Path, Path]:
    repo = repo_root.resolve(strict=True)
    release = release_dir.resolve(strict=True)
    if not COMMIT_RE.fullmatch(commit_sha):
        raise ReleaseManifestError("COMMIT_SHA_INVALID")
    releases = (repo / "releases").resolve(strict=True)
    if release.parent != releases or release.name != commit_sha:
        raise ReleaseManifestError("RELEASE_PATH_OR_ID_MISMATCH")
    if not release.is_dir():
        raise ReleaseManifestError("RELEASE_DIRECTORY_MISSING")
    _git(repo, "cat-file", "-e", f"{commit_sha}^{{commit}}")
    return repo, release


def build_manifest(repo_root: Path, release_dir: Path, commit_sha: str) -> dict[str, Any]:
    """Hash only files tracked by the exact commit; reject missing or altered files."""
    repo, release = _validate_roots(repo_root, release_dir, commit_sha)
    raw_tree = _git(repo, "ls-tree", "-r", "-z", "--full-tree", commit_sha)
    files: list[dict[str, str]] = []

    for entry in raw_tree.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, path_bytes = entry.split(b"\t", 1)
            mode, kind, object_id = metadata.decode("ascii").split()
            relative = path_bytes.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ReleaseManifestError("GIT_TREE_ENTRY_INVALID") from exc

        if kind == "commit" or mode == "160000":
            raise ReleaseManifestError(f"GIT_SUBMODULE_UNSUPPORTED:{relative}")
        if kind != "blob":
            raise ReleaseManifestError(f"GIT_ENTRY_UNSUPPORTED:{relative}")
        rel = PurePosixPath(relative)
        if rel.is_absolute() or not rel.parts or ".." in rel.parts or "." in rel.parts:
            raise ReleaseManifestError(f"RELEASE_PATH_UNSAFE:{relative}")

        target = release.joinpath(*rel.parts)
        if target.is_symlink() or not target.is_file():
            raise ReleaseManifestError(f"RELEASE_FILE_MISSING_OR_SYMLINK:{relative}")
        try:
            resolved_target = target.resolve(strict=True)
            resolved_target.relative_to(release)
        except (OSError, ValueError) as exc:
            raise ReleaseManifestError(f"RELEASE_FILE_MISSING_OR_ESCAPED:{relative}") from exc

        actual = target.read_bytes()
        committed = _git(repo, "cat-file", "blob", object_id)
        if actual != committed:
            raise ReleaseManifestError(f"RELEASE_FILE_GIT_MISMATCH:{relative}")

        files.append({
            "mode": oct(stat.S_IMODE(target.stat().st_mode)),
            "path": relative,
            "sha256": hashlib.sha256(actual).hexdigest(),
        })

    if not files:
        raise ReleaseManifestError("RELEASE_HAS_NO_TRACKED_FILES")

    files.sort(key=lambda row: row["path"])
    return {
        "commit_sha": commit_sha,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "files": files,
    }


def _manifest_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def verify_manifest(release_dir: Path) -> dict[str, Any]:
    release = release_dir.resolve(strict=True)
    manifest_path = release / MANIFEST_NAME
    sidecar_path = release / SIDECAR_NAME
    if manifest_path.is_symlink() or sidecar_path.is_symlink():
        raise ReleaseManifestError("RELEASE_MANIFEST_PAIR_SYMLINK")
    if not manifest_path.is_file() or not sidecar_path.is_file():
        raise ReleaseManifestError("RELEASE_MANIFEST_PAIR_MISSING")

    raw = manifest_path.read_bytes()
    manifest = json.loads(raw)
    if manifest.get("commit_sha") != release.name:
        raise ReleaseManifestError("RELEASE_ID_MISMATCH")
    files = manifest.get("files")
    if not isinstance(files, list) or not files or manifest.get("file_count") != len(files):
        raise ReleaseManifestError("RELEASE_FILE_COUNT_MISMATCH")

    seen: set[str] = set()
    checked = 0
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ReleaseManifestError("RELEASE_ENTRY_INVALID")
        relative = item["path"]
        rel = PurePosixPath(relative)
        if rel.is_absolute() or not rel.parts or ".." in rel.parts or "." in rel.parts or relative in seen:
            raise ReleaseManifestError(f"RELEASE_PATH_UNSAFE_OR_DUPLICATE:{relative}")
        seen.add(relative)
        target = release.joinpath(*rel.parts)
        if target.is_symlink() or not target.is_file() or not target.resolve(strict=True).is_relative_to(release):
            raise ReleaseManifestError(f"RELEASE_FILE_MISSING_OR_ESCAPED:{relative}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != item.get("sha256"):
            raise ReleaseManifestError(f"RELEASE_FILE_HASH_MISMATCH:{relative}")
        checked += 1

    expected = hashlib.sha256(raw).hexdigest()
    fields = sidecar_path.read_text(encoding="utf-8").strip().split()
    if len(fields) != 2 or fields[0] != expected or fields[1] != MANIFEST_NAME:
        raise ReleaseManifestError("RELEASE_MANIFEST_HASH_MISMATCH")
    return {
        "release_id": release.name,
        "manifest_sha256": expected,
        "files_checked": checked,
    }


def _write_temp(directory: Path, prefix: str, payload: bytes) -> Path:
    fd, name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o444)
        return path
    except Exception:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def write_manifest(release_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Create the manifest pair atomically; never overwrite existing evidence."""
    release = release_dir.resolve(strict=True)
    manifest_path = release / MANIFEST_NAME
    sidecar_path = release / SIDECAR_NAME
    if manifest_path.exists() or sidecar_path.exists():
        if manifest_path.exists() and sidecar_path.exists():
            existing = verify_manifest(release)
            existing_manifest = json.loads(manifest_path.read_bytes())
            expected_identity = (manifest.get("commit_sha"), manifest.get("file_count"), manifest.get("files"))
            existing_identity = (
                existing_manifest.get("commit_sha"),
                existing_manifest.get("file_count"),
                existing_manifest.get("files"),
            )
            if existing_identity != expected_identity:
                raise ReleaseManifestError("EXISTING_MANIFEST_DIFFERS")
            return existing
        raise ReleaseManifestError("PARTIAL_MANIFEST_PAIR_EXISTS")

    raw = _manifest_bytes(manifest)
    digest = hashlib.sha256(raw).hexdigest()
    sidecar = f"{digest}  {MANIFEST_NAME}\n".encode("ascii")
    temp_manifest = _write_temp(release, f".{MANIFEST_NAME}.", raw)
    temp_sidecar = _write_temp(release, f".{SIDECAR_NAME}.", sidecar)
    created: list[Path] = []
    try:
        os.replace(temp_manifest, manifest_path)
        created.append(manifest_path)
        os.replace(temp_sidecar, sidecar_path)
        created.append(sidecar_path)
        directory_fd = os.open(release, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        for path in created:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for path in (temp_manifest, temp_sidecar):
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    return verify_manifest(release)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--commit-sha", default=None)
    args = parser.parse_args()
    commit_sha = args.commit_sha or args.release_dir.name
    try:
        manifest = build_manifest(args.repo_root, args.release_dir, commit_sha)
        result = write_manifest(args.release_dir, manifest)
    except (OSError, ValueError, ReleaseManifestError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}:{str(exc)[:240]}"}))
        return 2
    print(json.dumps({"status": "PASS", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
