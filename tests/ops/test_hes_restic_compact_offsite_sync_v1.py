from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "scripts" / "ops"
DEPLOY = ROOT / "deploy" / "systemd"


def test_compact_filelist_policy_is_explicit_and_fail_closed():
    source = (OPS / "hes_restic_compact_filelist_v1.py").read_text()
    for token in (
        'ROOT_EXCLUDES =',
        '".worktrees"',
        '"candidates"',
        '"releases"',
        '".venv"',
        'primary_pre_main_alignment_20261007',
        'fingerprint.json',
        'WORKTREE_TRACKED_DIFF_CHANGED',
        'WORKTREE_UNTRACKED_CONTENT_CHANGED',
        'COMPACT_SCOPE_TOO_SMALL',
        'b"\\0"',
        'hes-restic-dropbox-sync.service',
    ):
        assert token in source
    root_excludes = source.split("ROOT_EXCLUDES = {", 1)[1].split("}", 1)[0]
    assert '"releases"' not in root_excludes
    assert '"candidates"' not in root_excludes
    assert 'str(ROOT / "releases")' in source
    assert 'str(ROOT / "candidates")' in source
    assert "passphrase =" not in source.lower()
    assert "RESTIC_PASSWORD=" not in source


def test_sync_script_uses_compact_incremental_restic_and_remote_verification():
    script = OPS / "hes_restic_dropbox_sync_v1.sh"
    source = script.read_text()
    subprocess.run(["bash", "-n", str(script)], check=True)
    for token in (
        "restic-compact-v1/repo",
        "compact-core-files.nul",
        "hes-full-recovery-core-v1",
        "hes-restic-core-v1",
        "--files-from-raw",
        "--keep-last 2",
        "--group-by host",
        "--read-data-subset=1/20",
        "400 * 1024 * 1024",
        "64 * 1024 * 1024",
        "rclone sync",
        "rclone check",
        "rclone:",
        "RESTIC_REMOTE_SNAPSHOT_OK",
    ):
        assert token in source
    assert "hes-restic-production-v1" not in source
    assert "passphrase=" not in source.lower()


def test_systemd_unit_is_sandboxed_and_writable_paths_are_narrow():
    unit = (DEPLOY / "hes-restic-dropbox-sync.service").read_text()
    timer = (DEPLOY / "hes-restic-dropbox-sync.timer").read_text()
    assert "ProtectSystem=strict" in unit
    assert "PrivateTmp=true" in unit
    assert "ProtectHome=read-only" in unit
    assert "ReadOnlyPaths=/root/.config/hes-backup" in unit
    assert "restic-compact-v1/repo" in unit
    assert "offsite-staging" in unit
    assert "restic-production-v1/repo" not in unit
    assert "TimeoutStartSec=1800" in unit
    assert "OnCalendar=*-*-* 03:30:00 UTC" in timer
    assert "Persistent=true" in timer


def test_compact_filelist_preserves_cache_named_evidence_but_prunes_project_caches(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("compact_filelist", OPS / "hes_restic_compact_filelist_v1.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    project = tmp_path / "project"
    evidence = tmp_path / "evidence"
    (project / "src" / "__pycache__").mkdir(parents=True)
    (evidence / "reports" / "__pycache__").mkdir(parents=True)
    (evidence / "reports" / ".pytest_cache").mkdir(parents=True)
    (project / "src" / "__pycache__" / "module.pyc").write_bytes(b"project-cache")
    (evidence / "reports" / "__pycache__" / "artifact.pyc").write_bytes(b"evidence-cache")
    (evidence / "reports" / ".pytest_cache" / "manifest.json").write_text('{"evidence":true}')

    files = set()
    module.add_tree(files, project, prune_names=module.CACHE_NAMES)
    module.add_tree(files, evidence, prune_names=set(), exclude_pyc=False)

    assert not any("/project/" in item and "__pycache__" in item for item in files)
    assert str(evidence / "reports" / "__pycache__" / "artifact.pyc") in files
    assert str(evidence / "reports" / ".pytest_cache" / "manifest.json") in files
