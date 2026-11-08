# IDLM read-only discovery checkpoint — 2026-11-08

**Mode:** read-only. No files were deleted, moved, compressed, rotated, or pruned. No service was restarted and no production retention setting was changed.

## Filesystem baseline

- Sole VPS root filesystem: 50G; approximately 40G used; 7.4G available; `df` reported 85% used at the initial privileged scan. A later IDLM scan measured 15.23% free by `shutil.disk_usage` and 87.04% free inodes. The small free-space percentage difference is due to `df` available blocks versus filesystem free blocks/reserved space; retain both metrics.
- Root directory usage, privileged scan: `/var` about 20G, `/opt` about 6.4G, `/tmp` about 5.4G, `/home` about 2.5G, `/usr` about 3.4G, `/boot` about 200M.
- `/var/backups/hes-trade-agent` occupies about 18G. Its `encrypted-local` tier occupies about 16.0G allocated.
- `/var/log/journal` occupies about 286.6M.
- `/var/cache/apt` occupies about 604M.
- `/home/hes-remote/.npm` is about 1.03G and `/home/hes-remote/.cache` about 968M.
- `/opt/sentinelx-cloud-core/.cache` is about 1.03G.
- `/tmp` includes many dated test/replay workspaces; `/tmp/hes-playwright-browsers` is about 924M. All are review-only until their job/evidence dependencies are established.

## Read-only IDLM scanner result

- The scanner inventoried 702 top-level filesystem entries across configured roots with zero scan errors.
- Report mode: `READ_ONLY_DRY_RUN`; `automatic_action=NONE`.
- Disk: 15.23% free; inodes: 87.04% free.
- Backup scan: 11 encrypted full snapshots across 7 UTC dates; four older same-day additional snapshots were identified (two on 2026-11-02 and two on 2026-11-06). These are **not proven content duplicates** and remain protected.
- Git worktree registry loaded successfully: 24 registered worktree paths were reported; 11 existing scanned paths were classified `KEEP_REGISTERED_WORKTREE`. This includes current sequence-safe, journal-provenance, dashboard-contract/i18n, and precision-entry worktrees. A path registered by Git is never a stale-temp candidate.
- Review classifications after worktree protection: 172 stale temporary-workspace entries, 297 other temporary entries, 22 regenerable-cache entries, one system-journal policy review, and one log-policy review. Unknown entries remain KEEP.
- The report is stored on VPS at `/root/hes-idlm-audit-20261108-v5.json`. It is a review artifact, not authorization to delete anything.

## Backup findings

- Eleven encrypted full backup archives were present in `/var/backups/hes-trade-agent/encrypted-local`, ranging from about 1.2G to 2.0G each.
- All eleven sidecar SHA-256 checks passed.
- The active `hes-encrypted-local-backup.timer` runs daily around 02:30 UTC.
- The backup script checks health and requires at least 5G free before starting. It encrypts the full project/system scope, verifies decryption/gzip integrity/tar listing, writes a SHA-256 sidecar, then applies retention.
- Existing retention keeps all snapshots younger than seven days, Sunday snapshots under 28 days, and first-of-month snapshots under 180 days. It does not cap multiple snapshots made on the same UTC day.
- The four older same-day snapshots are only additional full backups by timestamp. Their contents are not proven identical. No full restore drill or verified independent offsite restore was established in this audit. Keep all backups until that gate passes.

## Existing controls and active service dependencies

- Existing HES runtime check: at least 15% free = OK, 10–15% = WARN, below 10% = CRITICAL. Host operational check: root-disk pressure is CRITICAL at 85% used.
- The last stored health-state issue was `disk-free:14.8%`; a later scanner measured 15.23% free. Reconcile through the next scheduled monitor sample rather than manually running a recovery-capable check.
- Extend the existing checks with inode availability, growth rate, and time-to-capacity forecasting; do not create a duplicate monitor.
- Generic daily `logrotate.timer` is active. No HES-specific logrotate rule was found in inspected configuration. `systemd-tmpfiles` gives `/tmp` a 30-day cleanup age; this is not a substitute for HES-specific retention policy.
- Active market-data services run from `/opt/hes-trade-agent/current` and write to `/opt/hes-trade-agent/data/forward`. The learning loop, paper evaluator, and precision-entry journal write to `data/forward` and `logs`. The dashboard is read-only on releases and forward data. The one-minute integrity service is a successful oneshot with a dedicated StateDirectory. The encrypted backup service writes only to its encrypted-local backup path and was inactive at inspection.
- A privileged `lsof +D /tmp` scan returned no open-file rows, but this is not proof of disuse. Git's worktree registry revealed 11 existing worktree paths under scanned temporary locations; those are now explicitly protected.

## Repository/runtime preservation

- Local checkout: `/opt/hes-trade-agent`; branch `feat/gateio-global-market-data-v1`; HEAD `060d0d36ae6140a03d9a74495bb3899637ed3827`.
- The checkout is heavily dirty and contains many untracked files, worktrees, candidate/release trees, and evidence. Preserve all of them; do not reset, clean, overwrite, or delete.
- The local untracked `docs/HES_DNA_AND_ROADMAP.md` was append-only updated with the accepted IDLM architecture; original bytes were preserved in `/tmp/HES_DNA_AND_ROADMAP.md.pre-idlm-20261108`; append verification passed.
- `current` resolves to release `f5d505567522555ee1be9c260e83085347515721`; `current-before-4329a3df` resolves to `737d0555f9348f1e2584714a988d0751bb4448d4`.
- Nine HES services were observed active. Their runtime data, journals, and feed files remain protected.

## Code review status

- Isolated GitHub branch: `feat/hes-intelligent-data-lifecycle-audit-v1`.
- Draft PR #485 adds the read-only scanner, focused tests, architecture documentation, and this discovery checkpoint. It remains unmerged and undeployed.
- Local isolated prototype validation: nine tests passed and the module compiled successfully. Repository CI is being rechecked after the latest worktree-protection hardening.
- The PR is independent of the dirty VPS checkout; the production checkout was not changed by this code work.

## Disposition and next gates

1. Complete CI and code review for the read-only scanner.
2. Reconcile scanner output with all service read/write paths, process descriptors, Git/worktree references, evidence ownership, and backup provenance.
3. Test a proposed same-day backup retention policy against synthetic archives and prove the newest valid daily backup is always retained.
4. Complete an independent encrypted-backup restore drill and verify offsite coverage before changing backup retention or deleting any backup.
5. Extend the existing operational monitor with inode, disk-growth, and time-to-capacity metrics after focused tests and review.
6. Keep cleanup in read-only mode until all gates are satisfied; then consider a narrowly allowlisted cache/temp canary.

**Current disposition:** Phase A scanner and dependency discovery are materially advanced. CI/review and restore proof remain open. Production deletion remains disabled.


## Backup retention fail-closed hardening — 2026-11-08

- A synthetic test of the live retention loop found a concrete edge case: a syntactically valid future-dated archive filename produced a negative age, left `keep=0`, and was deleted together with its sidecar. This was reproduced with a synthetic 2026-11-09 archive while evaluating policy date 2026-11-08.
- A minimal fail-closed guard was applied to `/usr/local/sbin/hes-encrypted-local-backup`: if `age < 0`, log `RETENTION_KEEP_FUTURE_DATED` and continue without pruning that archive or its sidecar.
- The original script was preserved at `/root/hes-encrypted-local-backup.pre-idlm-20261108`.
- Original SHA-256: `829f29e4625acf870fd3a2cf5320af5cfa88a60bdd457fe067c87255d5843b4f`.
- Patched SHA-256: `3601316ee10c56589281de3c1dfaf6a7aab073d12b061a03d92f821e9892586d`.
- `bash -n` passed. A synthetic retention-loop regression passed: future-dated archive and sidecar kept; malformed filename kept; same-day snapshots retained under current policy; expired non-anchor snapshot removed in the synthetic fixture.
- No backup run was triggered, no service was restarted, no existing archive/sidecar was changed, and the same-day/age retention policy itself was not changed. The next scheduled backup remains the first production execution of this guard.

## Updated CI status

- Latest PR head: `1f43bd214ce0ff25a8323b64ef11a5dea75c1595`.
- All **32/32** GitHub Actions workflow runs completed successfully.
- HES Full Regression Gate: **1,195 passed, 82 subtests passed**; `HES_REGRESSION_GATE=PASS`; `LIVE_EXECUTION=OFF`.
- PR #485 remains draft/open/unmerged; production deployment is not authorized by the PR.


## Selective encrypted-backup restore and offsite check — 2026-11-08

- Latest encrypted archive `hes-full-20261108T023146Z.tar.gz.gpg` passed its SHA-256 sidecar check; decryption and tar listing succeeded with 42,753 members.
- Three critical files were extracted to an isolated root-only scratch directory, not over live paths, and matched live SHA-256 byte-for-byte: the Gate.io market-data systemd unit (743 bytes), operational health wrapper (3,717 bytes), and immutable release healthcheck module (6,997 bytes). Total restored: 11,457 bytes.
- Restore manifest: `/root/hes-restore-drill-20261108/restore-drill-manifest.json`. Source archive SHA-256: `4ca5bd124ead428ee255f6198e80de4b3e143a9fcd50bf8235e4b30facf09940`.
- This is a **selective-file restore drill only**, not a full system restore or complete data recovery proof.
- Dropbox folder `/HES Trade Agent Backups` exists but direct listing returned zero entries. VPS `/var/backups/hes-trade-agent/dropbox-staging` was also empty. No independent offsite copy is verified.
- Do not transfer backups to Dropbox without explicit user authorization. If later authorized, transfer encrypted ciphertext and checksum manifest only; never transfer the passphrase/key file.
- Full restore and offsite coverage remain open acceptance gates. No backup pruning or production cleanup is authorized by this selective restore result.
