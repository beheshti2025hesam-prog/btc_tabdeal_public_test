# HES Dashboard — Smart Memory & Storage Management

**Policy version:** 1.1 — 2026-11-20  
**Target:** less than **5,000,000,000 bytes (5 decimal GB)** complete local HES footprint.  
**Current state:** OVER BUDGET; no claim of target achievement.

## 1. Scope and baseline

The HES budget includes the project checkout (including releases, candidates and worktrees), independent `/srv/hes-evidence`, and local backup/offsite-staging roots. Ubuntu and SentinelX platform files are reported separately. Do not conflate this HES budget with the Dropbox Basic 400,000,000-byte folder cap.

Latest complete IDLM + dependency-aware Smart Cleanup + Smart Storage snapshot (2026-11-20 13:04 UTC):

| Component | Allocated bytes |
|---|---:|
| Project checkout, releases, candidates, worktrees | 13,583,405,056 |
| Independent evidence store | 436,072,448 |
| Local backups and offsite staging | 5,469,429,760 |
| **Complete local HES footprint** | **19,488,907,264 (~19.49 GB)** |
| Agent core excluding backup copies | 14,019,477,504 |
| Hard target | **5,000,000,000 bytes** |

IDLM inventoried 1,291 rows with zero scan errors. Smart Cleanup: 378 KEEP, 913 REVIEW_ONLY, 337 live-referenced, zero dependency-unknown, zero deletion authorization. The full archive/replacement-host/remote restore gate is NOT_PROVEN.

## 2. Automated safe maintenance

Daily pipeline: IDLM inventory → exact-snapshot Smart Cleanup dependency analysis → Smart Storage budget/compression/Dropbox report → narrowly scoped safe cache maintenance.

Automatic maintenance is limited to:
- Direct-child `/tmp/pip-*` temporary build/install/unpack directories older than 24 hours, only if no active pip/build process and no open file handle are observed; exact path/type/age are revalidated before removal.
- APT download cache (`apt-get clean`); installed packages and package database are untouched.
- systemd journal retention via journald policy: 256 MiB cap, keep at least 1 GiB free, 30-day maximum age, compression enabled.

A first cleanup on 2026-11-20 removed 77 stale pip temporary directories (848,449,536 bytes). APT archives cache was reduced to ~68 KiB. Journal usage is ~232.6 MiB. Root filesystem after maintenance: ~36 GB used of 50 GB, ~12 GB available (77%).

## 3. Protected data / no-touch rules

Never automatically delete, move, truncate, compress in place, or prune:
- Active or rollback releases, deployment pointers, release manifests.
- Registered or dirty Git worktrees, unmerged branches, unverified candidate branches.
- Gate.io canonical market data, trades/candles, strategy journals, evaluation evidence and audit records.
- Hoshyar/local inference models or binaries referenced by systemd/runtime configuration.
- Encrypted local backups, Restic repository, Dropbox staging archives, unique historical backups, recovery manifests or keys.
- Unknown paths, incomplete scans, open files, process/service/scheduled-job references, dependency errors.

Unknown or uncertain means KEEP. No full-restore proof means no backup-retention change. The 400,000,000-byte Dropbox cap remains a separate hard guard.

## 4. Next controlled compaction gates

1. Build a release registry: active/rollback symlinks, deployment records, service/process references, manifests and commit provenance.
2. For each unreferenced release/candidate/worktree, prove clean Git state or preserve dirty patch/untracked content; verify commit is available in the remote GitHub repository and can be reconstructed; verify manifest and selective restore before proposing removal.
3. Preserve current release and rollback set; retain a bounded number of proven restorable releases, with evidence for every retired item.
4. Consolidate only redundant candidate copies after branch/PR status and remote commit verification. Do not delete registered worktrees by age.
5. Keep backup retention unchanged until full local archive restore, remote Dropbox restore and replacement-host recovery are proven.
6. Re-run IDLM and Smart Storage after every approved batch; stop if any dependency/scan error appears or the disk healthcheck degrades.

## 5. Acceptance criteria

- Complete local HES footprint below 5,000,000,000 allocated bytes, independently calculated from the exact IDLM snapshot with no double counting.
- Active and rollback deployment pointers still resolve; required services pass health checks.
- Git branches/commits and all retained evidence remain recoverable.
- Gate.io data continuity, journals and model service are unchanged.
- Full backup restore and remote recovery evidence pass before any backup archive pruning.
- Daily maintenance timer succeeds; each cleanup has a machine-readable manifest and exact byte accounting.

**Status:** safe temporary/cache/log maintenance is active; 5 GB budget is not yet met. Release/worktree/candidate compaction and full backup recovery are separate blocked gates, not authorized by this report.