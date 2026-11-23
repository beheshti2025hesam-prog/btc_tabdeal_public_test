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

## 6. Verified compaction update — 2026-11-20 13:35 UTC

- 18 unreferenced release snapshots retired after manifest or exact Git-tree byte-for-byte verification, GitHub commit availability, and no active symlink/deployment/systemd/process/open-file references: 1,383,575,552 bytes.
- Two exact-Git-tree candidate snapshots with no live references retired: 148,008,960 bytes.
- 77 stale `/tmp/pip-*` build/install/unpack directories retired: 848,449,536 bytes.
- Total verified HES temporary/release/candidate reclamation: 2,380,034,048 bytes, plus APT cache and journald retention reductions.
- Latest measured complete HES footprint: **17,970,057,216 bytes (17.97 GB)**; over the 5 GB target by **12,970,057,216 bytes**. Project checkout: 12,204,572,672 bytes; evidence: 442,011,648; local backups/staging: 5,469,429,760.
- Root filesystem: 74% used, 13 GB free; HES operational healthcheck HEALTHY.
- All current/rollback pointers and newest-five release snapshots remain; deployment-record references retained. Dirty/registered worktrees, active models, Gate.io data, journals, evidence and backup archives untouched.
- Full 43-root Restic restore drill from exact Nov20 snapshot is in progress in isolated `/var/tmp`; remote Dropbox restore and replacement-host recovery are still separate gates.

The 5 GB objective is not yet met. Remaining footprint is not disposable cache; any further reduction needs a reviewed cold-storage/recovery plan for protected candidates, worktrees, runtime/model assets and backups.

## 7. Recovery validation update — 2026-11-20 13:50 UTC

- Local full Restic recovery: `restic check --read-data` passed (205/205 packs, zero errors); full 43-root snapshot restored in isolation (65,047 files/directories, 9.089 GiB), 12/12 required roots and four static configuration hashes passed. Test tree removed.
- Dropbox compact core remote recovery: exact remote object copied back, SHA-256/size matched its sidecar (`f4702fff3275f828706e081c4f4b3e4dc937058b958bd54f8dbefa599e3d01ec`, 398,216,865 bytes); GPG, Zstandard and safe tar listing passed (8,897 entries); full extraction passed; active release 620/620 and rollback release 582/582 manifest files verified; main Git object connectivity passed. Test tree and downloaded object removed.
- Remote restore evidence is stored at `.../2026-11-20T1323Z/dropbox-core-remote-restore.json`; local full restore evidence is stored at `.../2026-11-20T1323Z/full-restore-drill.json`.
- The Smart Storage Manager now reports local and remote restore independently. Replacement-host boot/recovery remains NOT_PROVEN; no backup pruning or destructive cleanup is authorized.

## Dashboard contract update — 2026-11-23

### Hard budget and accounting
- Target: complete local HES footprint **strictly below 5,000,000,000 allocated bytes (decimal 5 GB)**.
- Scope: project checkout/releases/candidates/worktrees, independent evidence, local backups/offsite staging, HES-owned temporary/restore artifacts, and HES runtime state/logs.
- Use the exact IDLM snapshot and global (st_dev, st_ino) deduplication. Show:
  - total_local_hes_bytes_including_backups — conservative physical allocation;
  - total_local_hes_logical_path_bytes — path-summed allocation;
  - shared_inode_path_bytes_not_double_counted — duplicate inode paths not counted twice;
  - component bytes for project, evidence, backups, HES temp/restore, HES runtime, and unclassified temp.
- allocated_bytes is the logical path sum; unique_allocated_bytes is the unique physical value used for the hard budget. Never sum hardlinked paths as separate disk use.
- HES-owned /tmp and /var/tmp plus /var/lib/hes-*, /var/log/hes-*, and /var/cache/hes-* must be included. Platform-private temp roots are excluded. Unclassified temp paths are counted conservatively and block acceptance.

### Status semantics
- WITHIN_BUDGET: complete/error-free scope and physical total below the target.
- OVER_BUDGET: complete/error-free scope but physical total exceeds the target.
- SCOPE_INCOMPLETE: unknown temp ownership or incomplete scope; no compliance claim.
- SCOPE_INCOMPLETE_OVER_BUDGET: scope is incomplete and the known/conservative total already exceeds the target.
- Display scan errors, missing roots, unclassified temp item count/bytes, and last successful daily audit. Do not show a green/pass state unless scope_complete=true and complete_footprint_within_target=true.

### Safety and operations
- The daily hes-smart-storage-maintenance.timer runs the existing IDLM → Smart Cleanup → Smart Storage chain.
- Automatic cleanup is cache-only and bounded. Release/worktree, model, dataset, evidence, and backup deletion/pruning remain disabled.
- Preserve active/rollback releases and every dirty, unpushed, open, referenced, or unverified path.
- Backup pruning stays blocked until remote restore, replacement-host recovery, and external key escrow are proven.
- The 5 GB objective is currently **NOT MET**; a previous manager path-sum is not acceptance-grade until global inode-aware accounting and full HES scope are in place.

### Worktree reference semantics — 2026-11-23

The dashboard must distinguish the primary repository root from child worktrees. The primary repo root itself must not make every project directory appear referenced. A child worktree path and any parent container that would remove that worktree remain blocked; unrelated sibling paths can proceed to dependency-aware review. The correction is covered by regression tests.

### Temporary-path safety classification — 2026-11-23

The dashboard must separate:
- KEEP_UNREGISTERED_GIT_WORKSPACE: temporary path contains .git metadata; retain until clean/dirty/ignored state and remote provenance are verified.
- KEEP_TEMP_EVIDENCE: archive, backup, restore, recovery, model/data, candidate/release, test/soak/smoke, audit/review, Restic or similar evidence artifact.
- REVIEW_STALE_TEMP / REVIEW_TEMP: generic temporary paths only; review status is not deletion authorization.

Show counts and allocated bytes for each class. No automated deletion of Git workspaces, archives, recovery data, model/data snapshots or test evidence.
