from pathlib import Path
import pytest
from scripts.ops.hes_backup_archive_verify_v1 import compression_for_archive, validate_members

def test_detects_legacy_gzip_archive():
    assert compression_for_archive(Path("backup.tar.gz.gpg"))=="gzip"

def test_detects_versioned_zstd_archive():
    assert compression_for_archive(Path("backup.tar.zst.gpg"))=="zstd"

def test_rejects_unknown_archive_suffix():
    with pytest.raises(ValueError,match="unsupported archive suffix"):
        compression_for_archive(Path("backup.gpg"))

def test_member_validation_requires_active_and_rollback():
    result=validate_members(["opt/hes/releases/a/","opt/hes/releases/b/","opt/hes/config.yml"],
                            "opt/hes/releases/a","opt/hes/releases/b")
    assert result["members"]==3
    assert result["unsafe_paths"]==0

def test_member_validation_rejects_path_traversal():
    with pytest.raises(ValueError,match="unsafe"):
        validate_members(["../etc/passwd","opt/hes/releases/a","opt/hes/releases/b"],
                         "opt/hes/releases/a","opt/hes/releases/b")

def test_member_validation_rejects_absolute_paths():
    with pytest.raises(ValueError,match="unsafe"):
        validate_members(["/etc/passwd","opt/hes/releases/a","opt/hes/releases/b"],
                         "opt/hes/releases/a","opt/hes/releases/b")

def test_member_validation_requires_both_release_paths():
    with pytest.raises(ValueError,match="active or rollback"):
        validate_members(["opt/hes/releases/a"],"opt/hes/releases/a","opt/hes/releases/b")

def test_member_validation_rejects_empty_archive():
    with pytest.raises(ValueError,match="no members"):
        validate_members([],"a","b")