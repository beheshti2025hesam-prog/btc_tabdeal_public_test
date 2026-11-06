from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.ops.build_release_manifest_v1 import (
    ReleaseManifestError,
    build_manifest,
    verify_manifest,
    write_manifest,
)


def make_git_release(tmp_path: Path, *, symlink: bool = False):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "HES tests"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "hes-tests@example.invalid"], check=True)

    (repo / "app.py").write_text("print('immutable')\n", encoding="utf-8")
    if symlink:
        (repo / "target.txt").write_text("target\n", encoding="utf-8")
        os.symlink("target.txt", repo / "linked.txt")

    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    release = repo / "releases" / commit
    release.mkdir(parents=True)
    shutil.copy2(repo / "app.py", release / "app.py")
    if symlink:
        shutil.copy2(repo / "target.txt", release / "target.txt")
        os.symlink("target.txt", release / "linked.txt")
    return repo, release, commit


def test_manifest_uses_only_exact_git_tracked_files_and_verifies(tmp_path):
    repo, release, commit = make_git_release(tmp_path)
    cache = release / "__pycache__"
    cache.mkdir()
    (cache / "runtime.pyc").write_bytes(b"generated runtime cache")

    manifest = build_manifest(repo, release, commit)
    assert manifest["commit_sha"] == commit
    assert manifest["file_count"] == 1
    assert [row["path"] for row in manifest["files"]] == ["app.py"]
    assert manifest["files"][0]["sha256"] == hashlib.sha256((release / "app.py").read_bytes()).hexdigest()

    result = write_manifest(release, manifest)
    assert result["files_checked"] == 1
    assert verify_manifest(release) == result


def test_manifest_write_is_idempotent_and_never_overwrites(tmp_path):
    repo, release, commit = make_git_release(tmp_path)
    manifest = build_manifest(repo, release, commit)
    first = write_manifest(release, manifest)
    second = write_manifest(release, manifest)
    assert first == second

    changed = dict(manifest)
    changed["files"] = [{**manifest["files"][0], "sha256": "0" * 64}]
    with pytest.raises(ReleaseManifestError, match="EXISTING_MANIFEST_DIFFERS"):
        write_manifest(release, changed)


def test_missing_tracked_file_fails_closed(tmp_path):
    repo, release, commit = make_git_release(tmp_path)
    (release / "app.py").unlink()
    with pytest.raises(ReleaseManifestError, match="RELEASE_FILE_MISSING_OR_SYMLINK"):
        build_manifest(repo, release, commit)


def test_modified_tracked_file_fails_closed(tmp_path):
    repo, release, commit = make_git_release(tmp_path)
    (release / "app.py").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ReleaseManifestError, match="RELEASE_FILE_GIT_MISMATCH"):
        build_manifest(repo, release, commit)


def test_symlinked_tracked_file_fails_closed(tmp_path):
    repo, release, commit = make_git_release(tmp_path, symlink=True)
    with pytest.raises(ReleaseManifestError, match="RELEASE_FILE_MISSING_OR_SYMLINK"):
        build_manifest(repo, release, commit)


def test_partial_manifest_pair_is_not_overwritten(tmp_path):
    repo, release, commit = make_git_release(tmp_path)
    manifest = build_manifest(repo, release, commit)
    (release / "HES_RELEASE_MANIFEST_v1.sha256").write_text("partial\n", encoding="ascii")
    with pytest.raises(ReleaseManifestError, match="PARTIAL_MANIFEST_PAIR_EXISTS"):
        write_manifest(release, manifest)

def test_symlinked_parent_directory_cannot_escape_release(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "HES tests"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "hes-tests@example.invalid"], check=True)
    nested = repo / "nested"
    nested.mkdir()
    (nested / "app.py").write_text("print('immutable')\\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "nested fixture"], check=True)
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    release = repo / "releases" / commit
    release.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "app.py").write_text("print('immutable')\\n", encoding="utf-8")
    os.symlink(outside, release / "nested", target_is_directory=True)

    with pytest.raises(ReleaseManifestError, match="RELEASE_FILE_MISSING_OR_ESCAPED"):
        build_manifest(repo, release, commit)


def test_manifest_symlink_is_rejected(tmp_path):
    repo, release, commit = make_git_release(tmp_path)
    write_manifest(release, build_manifest(repo, release, commit))
    outside = tmp_path / "manifest.json"
    outside.write_bytes((release / "HES_RELEASE_MANIFEST_v1.json").read_bytes())
    (release / "HES_RELEASE_MANIFEST_v1.json").unlink()
    os.symlink(outside, release / "HES_RELEASE_MANIFEST_v1.json")

    with pytest.raises(ReleaseManifestError, match="RELEASE_MANIFEST_PAIR_SYMLINK"):
        verify_manifest(release)


def test_sidecar_symlink_is_rejected(tmp_path):
    repo, release, commit = make_git_release(tmp_path)
    write_manifest(release, build_manifest(repo, release, commit))
    outside = tmp_path / "manifest.sha256"
    outside.write_bytes((release / "HES_RELEASE_MANIFEST_v1.sha256").read_bytes())
    (release / "HES_RELEASE_MANIFEST_v1.sha256").unlink()
    os.symlink(outside, release / "HES_RELEASE_MANIFEST_v1.sha256")

    with pytest.raises(ReleaseManifestError, match="RELEASE_MANIFEST_PAIR_SYMLINK"):
        verify_manifest(release)
