#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("/opt/hes-trade-agent")
EVIDENCE = Path("/srv/hes-evidence")
STAGE = Path("/var/backups/hes-trade-agent/offsite-staging")
META = STAGE / "recovery-metadata"
DELTA = META / "differential-v1-20261116"
OVERLAYS = META / "pr320-evidence-overlays-v1"
OUTPUT = STAGE / "compact-core-files.nul"
ACTIVE = Path(os.path.realpath(ROOT / "current"))
ROLLBACK = Path(os.path.realpath(ROOT / "current-before-4329a3df"))
EXPECTED_ACTIVE = ROOT / "releases/f5d505567522555ee1be9c260e83085347515721"
EXPECTED_ROLLBACK = ROOT / "releases/737d0555f9348f1e2584714a988d0751bb4448d4"

ROOT_EXCLUDES = {
    ".worktrees", ".venv",
    ".isolated-main-20261105", ".isolated-pr448-20261105",
    ".pr398-exact-head-268fa7524c12e085d010437bf50bdb163fa7277a",
}
CACHE_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}
SRV_CLONE_EXCLUDES = {
    "gateio-persisted-feed-signal-agent-20261026",
    "isolated-pr320", "isolated-pr320-final",
    "isolated-pr320-final-acceptance", "isolated-pr320-verified",
}

def run(args: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(f"command failed: {args!r}: {p.stderr[-1200:]}")
    return p.stdout

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def git_fingerprint_check() -> tuple[int, int]:
    fp_path = DELTA / "fingerprint.json"
    fp = json.loads(fp_path.read_text())
    live = 0
    snapshot_only = 0
    for rec in fp["repositories"]:
        path = Path(rec["path"])
        if rec["validation_mode"] != "live" or not path.exists():
            snapshot_only += 1
            continue
        live += 1
        gitbase = ["git", "-c", f"safe.directory={path}"]
        head = run(gitbase + ["rev-parse", "HEAD"], path).strip()
        branch = run(gitbase + ["branch", "--show-current"], path).strip()
        if head != rec["head"] or branch != rec["branch"]:
            raise RuntimeError(f"WORKTREE_BASE_CHANGED: {path}")
        diff_proc = subprocess.run(gitbase + ["diff", "HEAD", "--binary"], cwd=str(path), capture_output=True)
        if diff_proc.returncode:
            raise RuntimeError(f"WORKTREE_DIFF_READ_FAILED: {path}")
        diff = diff_proc.stdout
        if len(diff) != rec["tracked_diff_bytes"] or hashlib.sha256(diff).hexdigest() != rec["tracked_diff_sha256"]:
            raise RuntimeError(f"WORKTREE_TRACKED_DIFF_CHANGED: {path}")
        raw_proc = subprocess.run(gitbase + ["ls-files", "--others", "--exclude-standard", "-z"], cwd=str(path), capture_output=True)
        if raw_proc.returncode:
            raise RuntimeError(f"WORKTREE_UNTRACKED_READ_FAILED: {path}")
        current_untracked = [x.decode(errors="surrogateescape") for x in raw_proc.stdout.split(b"\0") if x]
        expected_untracked = [x["path"] for x in rec["untracked"]]
        if sorted(current_untracked) != sorted(expected_untracked):
            raise RuntimeError(f"WORKTREE_UNTRACKED_SET_CHANGED: {path}")
        for item in rec["untracked"]:
            target = path / item["path"]
            if not target.is_file() or target.stat().st_size != item["size"] or sha256_file(target) != item["sha256"]:
                raise RuntimeError(f"WORKTREE_UNTRACKED_CONTENT_CHANGED: {target}")
    return live, snapshot_only

def add_tree(files: set[str], root: Path, *, prune_names: set[str] | None = None,
             prune_paths: set[str] | None = None, exclude_pyc: bool = True) -> None:
    if not root.exists() and not root.is_symlink():
        raise RuntimeError(f"REQUIRED_BACKUP_ROOT_MISSING: {root}")
    if root.is_symlink() or root.is_file():
        files.add(str(root))
        return
    prune_names = prune_names or set()
    prune_paths = prune_paths or set()
    for base, dirs, names in os.walk(root, topdown=True, followlinks=False):
        bp = Path(base)
        keep = []
        for d in dirs:
            p = bp / d
            rel = str(p)
            if d in prune_names or rel in prune_paths:
                continue
            if p.is_symlink():
                files.add(str(p))
            else:
                keep.append(d)
        dirs[:] = keep
        for name in names:
            p = bp / name
            if p.is_symlink() or p.is_file():
                if exclude_pyc and name.endswith(".pyc"):
                    continue
                files.add(str(p))

def main() -> int:
    if ACTIVE != EXPECTED_ACTIVE or ROLLBACK != EXPECTED_ROLLBACK:
        raise RuntimeError(f"RELEASE_POINTER_CHANGED active={ACTIVE} rollback={ROLLBACK}")
    if not ACTIVE.is_dir() or not ROLLBACK.is_dir() or ACTIVE == ROLLBACK:
        raise RuntimeError("RELEASE_POINTER_INVALID")
    if not (DELTA / "manifest.json").is_file() or not (DELTA / "fingerprint.json").is_file():
        raise RuntimeError("DIFFERENTIAL_SNAPSHOT_METADATA_MISSING")
    if not (OVERLAYS / "manifest.json").is_file():
        raise RuntimeError("PR320_EVIDENCE_OVERLAYS_MISSING")

    live, snapshot_only = git_fingerprint_check()
    files: set[str] = set()

    add_tree(files, ROOT, prune_names=ROOT_EXCLUDES | CACHE_NAMES,
             prune_paths={
                 str(ROOT / "candidates"),
                 str(ROOT / "releases"),
                 str(ROOT / "archive/primary_pre_main_alignment_20261007"),
             })
    add_tree(files, ACTIVE, prune_names=CACHE_NAMES)
    add_tree(files, ROLLBACK, prune_names=CACHE_NAMES)
    add_tree(files, ROOT / "releases/deployment-records", prune_names=CACHE_NAMES)

    # Quarantined source is preserved; its Git DB and data duplicate are excluded.
    quarantine = ROOT / "candidates/quarantine/rc-merged-7ae1afcb4a65d1a3ddec0c1a7c9f35fffadfdf66-invalid-manifest-20261107"
    add_tree(files, quarantine, prune_names={".git", "data"} | CACHE_NAMES)

    # Small candidate manifests/attestations only; old tarballs remain in local archives.
    for p in (ROOT / "candidates").glob("*"):
        if p.is_file() and p.suffix not in {".gz", ".tgz"}:
            files.add(str(p))

    # Evidence is immutable source material: preserve cache-named directories and
    # .pyc payloads there. Only known duplicate clone roots are excluded.
    add_tree(files, EVIDENCE, prune_names=SRV_CLONE_EXCLUDES, exclude_pyc=False)
    for base in (
        EVIDENCE / "gateio-persisted-feed-signal-agent-20261026",
        EVIDENCE / "isolated-pr320-final-acceptance",
    ):
        for sub in ("docs", "evidence", "archive", "README.md", "HES_RELEASE_MANIFEST_v1.json"):
            p = base / sub
            if p.exists() or p.is_symlink():
                add_tree(files, p, exclude_pyc=False)

    fixed = [
        Path("/etc/ssh"), Path("/etc/nftables.conf"), Path("/etc/systemd/system"),
        Path("/etc/ufw"), Path("/etc/netplan"), Path("/etc/apt"), Path("/etc/hes-trade-agent"),
        Path("/etc/sentinelx"), Path("/etc/sysctl.d"), Path("/etc/modules-load.d"),
        Path("/etc/fstab"), Path("/etc/hosts"), Path("/etc/hostname"), Path("/etc/sudoers"),
        Path("/etc/sudoers.d"), Path("/etc/cron.d"), Path("/etc/logrotate.d"),
        Path("/var/lib/cloud"), Path("/var/lib/dpkg/status"), Path("/var/lib/apt/extended_states"),
        Path("/var/lib/hes-operational-health"), Path("/var/lib/sentinelx/audit.jsonl"),
        Path("/var/lib/sentinelx/hes-runtime-snapshots"), Path("/var/lib/sentinelx/hes-release-manifests"),
        Path("/var/lib/systemd"), Path("/var/spool/cron/crontabs"),
        Path("/root/.ssh"), Path("/root/.config/rclone"),
        Path("/usr/local/sbin/hes-operational-healthcheck"),
        Path("/usr/local/sbin/hes-runtime-healthcheck"),
        Path("/usr/local/sbin/hes-encrypted-local-backup"),
        Path("/usr/local/sbin/hes-restic-incremental-backup"),
        Path("/usr/local/sbin/hes-restic-dropbox-sync"),
        Path("/usr/local/sbin/hes-restic-compact-filelist"),
        DELTA, OVERLAYS, META / "offsite-dependency-snapshot",
        META / "RECOVERY-RUNBOOK-HES-OFFSITE-CORE-V1.md",
        META / "hes-offsite-recovery-core-20261116T143052Z.manifest.txt",
        STAGE / "hes-recovery-core-latest.tar.zst.gpg.sha256",
        STAGE / "hes-recovery-core-latest.tar.zst.gpg.manifest.json",
        STAGE / "hes-recovery-core-latest.tar.zst.gpg.manifest.txt",
        STAGE / "hes-recovery-core-latest.tar.zst.gpg.runbook.md",
        Path("/var/backups/hes-trade-agent/restic-compact-v1/README.md"),
    ]
    for p in fixed:
        if p.exists() or p.is_symlink():
            add_tree(files, p, prune_names=CACHE_NAMES)

    # Exclude the Restic repositories themselves, local encrypted archive generations,
    # temporary restore drills, and all backup staging payloads.
    forbidden = (
        "/var/backups/hes-trade-agent/restic-production-v1/repo/",
        "/var/backups/hes-trade-agent/restic-compact-v1/repo/",
        "/var/backups/hes-trade-agent/offsite-staging/hes-offsite-recovery-core-",
        "/var/tmp/hes-restic-",
        "/var/tmp/hes-offsite-",
    )
    files = {p for p in files if not any(p.startswith(x) for x in forbidden)}
    if not (EVIDENCE / "wallex").is_dir() or not (EVIDENCE / "gateio").is_dir():
        raise RuntimeError("REQUIRED_EVIDENCE_ROOT_MISSING")
    for required in (
        str(ROOT / "current"), str(ROOT / "current-before-4329a3df"),
        str(ACTIVE / "HES_RELEASE_MANIFEST_v1.json"),
        str(ROLLBACK / "RELEASE_MANIFEST_737d0555.json"),
        "/etc/systemd/system/hes-restic-dropbox-sync.service",
        "/etc/systemd/system/hes-restic-dropbox-sync.timer",
        "/usr/local/sbin/hes-restic-incremental-backup",
        "/usr/local/sbin/hes-restic-dropbox-sync",
        str(DELTA / "manifest.json"), str(DELTA / "fingerprint.json"),
        str(OVERLAYS / "manifest.json"),
    ):
        if required not in files and not Path(required).is_file() and not Path(required).is_symlink():
            raise RuntimeError(f"REQUIRED_BACKUP_FILE_MISSING: {required}")

    ordered = sorted(files)
    if len(ordered) < 7000:
        raise RuntimeError(f"COMPACT_SCOPE_TOO_SMALL: {len(ordered)}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("wb") as f:
        for p in ordered:
            f.write(os.fsencode(p) + b"\0")
    os.chmod(OUTPUT, 0o600)
    print(f"COMPACT_FILELIST_OK files={len(ordered)} live_worktrees={live} snapshot_only={snapshot_only} bytes={OUTPUT.stat().st_size}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COMPACT_FILELIST_FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
