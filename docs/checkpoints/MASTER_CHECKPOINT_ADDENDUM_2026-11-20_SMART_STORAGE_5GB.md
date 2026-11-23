# Master Checkpoint Addendum — Smart Memory / Storage Control — 2026-11-20

## User objective

Hard target: complete local HES footprint below 5,000,000,000 allocated bytes (5 decimal GB), excluding Ubuntu/SentinelX platform files. This supersedes the earlier 10 GiB planning target. The target is not yet achieved.

## Implemented

- Smart Storage Manager upgraded to decimal 5 GB budget; archives now inventory `.tar.zst.gpg`, `.tar.gz.gpg` and Git bundles; local Restic repo is separately reported.
- Daily IDLM → dependency-aware Smart Cleanup → Smart Storage pipeline installed under `/usr/local/sbin/hes-smart-storage-maintenance-v1.py`; systemd timer `hes-smart-storage-maintenance.timer` enabled for 03:45 UTC daily.
- Safe automatic cleanup only: direct-child `/tmp/pip-*` directories older than 24h with no active pip/build process and no open handles; APT download cache; journald max 256 MiB / 30 days. Unknown paths remain KEEP.
- PR #557 remains draft from current mainline; branch `feat/hes-smart-storage-5gb-20261120`. Includes manager, runner, systemd units, dashboard docs, Project DNA update, and separate local/remote restore evidence support. CI/status pending; do not merge before review.

## Verified cleanup

- 77 stale pip temp directories removed: 848,449,536 bytes.
- 18 old release snapshots removed: 1,383,575,552 bytes, after manifest or exact Git-tree byte comparison, GitHub commit availability, and no symlink/deployment/systemd/process/open-file references. All active/rollback pointers, newest-five releases and deployment-record targets retained.
- Two exact-Git-tree candidate snapshots removed: 148,008,960 bytes, no active candidate path or live refs.
- Total HES temp/release/candidate reclamation: 2,380,034,048 bytes, plus APT cache and journald retention reductions.
- Preserved all release manifests and retirement/reconstruction records in `/srv/hes-evidence/operations/storage-lifecycle/`.

## Latest measured baseline

From exact IDLM/Smart Cleanup snapshot 2026-11-20 13:33 UTC:
- Complete local HES footprint: 17,970,057,216 bytes (17.97 GB).
- Hard target: 5,000,000,000 bytes.
- Remaining overage: 12,970,057,216 bytes.
- Project checkout: 12,204,572,672 bytes.
- Independent evidence: 442,011,648 bytes.
- Local backups/offsite staging: 5,469,429,760 bytes.
- Local Restic repo: 3,409,702,912 bytes.
- Offsite staging archives: 1,347,412,546 bytes.
- Dropbox HES folder: 2,004,006,371 / 2,147,483,648 bytes (93.32%); the independent 400,000,000-byte upload cap remains enforced.
- Root filesystem: 74% used, 13 GB free; operational healthcheck HEALTHY.

## Protected / not deleted

No active or dirty worktree, dirty candidate, Hoshyar model/runtime, Gate.io data, trade journal, evidence record, local Restic repo, encrypted backup archive, or Dropbox object was deleted. The remaining candidates/worktrees/runtime/models/backups are not generic cache. Unknown means KEEP.

## Recovery gates — updated 2026-11-20 13:50 UTC

- Local full Restic restore: PASS. `restic check --read-data` verified 205/205 packs with zero errors; exact 43-root snapshot `6518cb4854b9253a7b14730d60ab04d8db09881ff31742a37cc5cfc15ef14c68` fully restored in isolated `/var/tmp` (65,047 files/directories, 9.089 GiB), 12/12 required roots and four static configuration hashes passed. Test tree removed. Evidence: `/srv/hes-evidence/operations/storage-lifecycle/2026-11-20T1323Z/full-restore-drill.json`.
- Dropbox remote core restore: PASS. Exact remote object `HES Trade Agent Backups/hes-recovery-core-latest.tar.zst.gpg` copied back, SHA/size matched sidecar (`f4702fff3275f828706e081c4f4b3e4dc937058b958bd54f8dbefa599e3d01ec`, 398,216,865 bytes), GPG/Zstandard/tar validation passed (8,897 members, zero unsafe paths), full isolated extraction passed, active release 620/620 and rollback release 582/582 files verified, main Git connectivity passed. Test tree and downloaded object removed. Evidence: `/srv/hes-evidence/operations/storage-lifecycle/2026-11-20T1323Z/dropbox-core-remote-restore.json`.
- Replacement-host boot/recovery remains NOT_PROVEN. No backup pruning authorized.

## Next architectural decision

To reach 5 GB, the remaining 12.97 GB cannot be removed safely as cache. It requires a separately approved cold-storage/recovery plan for inactive worktrees/candidates and backup assets, or a changed target/scope. Box is currently a connected document workspace only; it is not yet an approved VPS archive/backup target.