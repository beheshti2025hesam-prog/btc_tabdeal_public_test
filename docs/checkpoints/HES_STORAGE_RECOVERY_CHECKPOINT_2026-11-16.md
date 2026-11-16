# HES Trade Agent — Storage & Recovery Checkpoint — 2026-11-16

## Disposition

**PARTIAL / FULL ARCHIVE RESTORE PROVEN / DROPBOX MIGRATION BLOCKED / CLEANUP NOT AUTHORIZED.**

The draft implementation and full isolated archive restore are complete. Production migration and the <=10 GiB footprint target are not complete. Do not represent this as a production rollout.

## GitHub

- PR #506: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/506
- Branch: feat/hes-smart-storage-manager-v1
- Latest commit: 78e5b3405307d83fc06b3274cd26c796b9d2dcc9
- PR remains OPEN / DRAFT / unmerged.
- Latest focused regression: 54 tests passed; candidate shell scripts pass bash -n; git diff --check passes.

## Implemented draft candidates

- scripts/ops/hes_encrypted_local_backup_v2.sh: expanded encrypted local archive scope; retention defaults to report-only. Deletion-list processing requires explicit HES_BACKUP_RETENTION_APPLY=1.
- scripts/ops/hes_dropbox_offsite_build_v2.sh: expanded offsite archive scope aligned with local v2.
- Both include the same 33 additional recovery-critical host paths: UFW, netplan, APT, SentinelX/HES config and runtime state, sudoers, cron, logrotate, security/environment/cloud/network settings, cloud-init state, package state, HES operational state, SentinelX audit/runtime/release evidence, root SSH and rclone config.
- AES-256 encryption remains; the backup passphrase is deliberately excluded and must be escrowed separately.
- Both scripts remain draft-only. Neither was installed or executed against production data.

## Verification evidence

- All 33 added host paths exist; explicit tar stream/listing passed without creating a persistent archive.
- Disposable Restic 0.16.4 format-2 repository processed 4,475,455,640 source bytes and occupied 787,010,021 bytes with compression max.
- restic check --read-data passed all 45/45 packs.
- Full isolated restore to a temporary directory passed: 32,927 files verified by Restic, 4,131 directories, 129 symlinks, 4.168 GiB restored; 18/18 required recovery paths present; eight static configuration/content comparisons matched.
- Disposable Restic repo and test password were removed after verification. No Restic repository was installed or retained for production.
- Latest local gzip archive hes-full-20261116T023147Z.tar.gz.gpg verified: 2,454,418,968 bytes, SHA-256 2df8ec077bc77029e611b42dca0d6c2973de08d5dedc28ec4378c0ed4943d9a6; GPG AES-256 decrypt and gzip integrity PASS; 60,801 members; zero unsafe paths; active and rollback releases present.
- Existing Dropbox archive hes-offsite-latest.tar.zst.gpg: remote hash matched sidecar and identical local staging copy; GPG decrypt, zstd integrity and full tar listing PASS (35,004 entries). It predates expanded recovery scope and lacks UFW, netplan, APT, SentinelX, sudoers, dpkg state, root SSH and rclone configuration.

## Capacity and operational state

- Core project + independent evidence: 7.357 GB (~6.85 GiB), within the 10 GiB core target.
- Complete local footprint including backups: 30.596 GB (~28.495 GiB), still above the 10 GiB total target.
- Local encrypted archives: 8 files, 17,735,966,720 bytes.
- Offsite staging: 2 archives, 2,728,108,032 bytes.
- Root filesystem: 52,721,094,656 bytes total; 6,589,943,808 bytes free (12.5%). Operational healthcheck returns UNHEALTHY solely for disk free below 15% / usage 87% above 85% threshold.
- Local and Dropbox backup timers remain active. Production backup script hashes unchanged. No production service/timer, release pointer, backup format, retention, or market/trading configuration changed.
- Dropbox Basic free quota: 780,861,940 bytes. Restic prototype 787,010,021 bytes plus 64 MiB reserve requires 854,118,885 bytes; shortfall 73,256,945 bytes. The current capacity gate correctly blocks upload while the old remote archive occupies quota.

## Security and destructive-operation gates

- Existing backup passphrase file is present only on the VPS, root:root mode 0600. No external escrow file was found in Dropbox. The user must store the passphrase securely outside the VPS before any production migration.
- Existing Dropbox archive must be retained until the new remote Restic repository passes remote integrity and restore checks.
- No Dropbox upload, overwrite, rename, or delete occurred.
- No local archive, staging file, cache, journal, Git object, release, or worktree was deleted or moved.
- Git repack experiments were performed only on temporary copies. A quarantined candidate repo had 12,315 unreachable Git objects; preserving unreachable objects removed almost all apparent repack savings. No production Git object database was modified.
- Full restore was an isolated archive restore on the same VPS, not a replacement-host boot or bare-metal OS rebuild.

## Next gates

1. User stores the existing backup passphrase in a secure password manager or other off-VPS escrow; never paste the secret into ChatGPT.
2. Obtain explicit approval to replace the older Dropbox archive after the new production repository is built from the verified scope.
3. Install/use a stable Restic version, create the production repository with a durable external recovery secret, upload to Dropbox, then run remote check --read-data and a remote restore validation.
4. Only after remote restore passes, obtain explicit approval for retention cleanup: replace the eight old local archives and prune redundant staging while preserving at least the agreed fallback. Re-run IDLM/Smart Cleanup and healthcheck.
5. Re-measure full local footprint and confirm <=10 GiB and disk health before calling the storage work complete.

**Safety:** no live trading or capital mutation; execution state unchanged.


## Fresh storage-manager reconciliation — 2026-11-16 10:29 UTC

- Fresh read-only IDLM scan: 928 items. Exact dependency-aware Smart Cleanup pass: 327 KEEP, 601 REVIEW_ONLY, 88 live-referenced, zero dependency-unknown, delete authorization false.
- Integrated storage manager report: HES core 7,357,534,208 bytes (~6.85 GiB); complete local footprint 30,596,861,952 bytes (~28.496 GiB); root disk 12.5% free / WARN.
- Storage Manager now consumes the full-scope Restic restore evidence and reports FULL_ARCHIVE_RESTORE_VERIFIED (32,927 files; 18/18 required paths) separately from replacement-host restore NOT_PROVEN and remote restore NOT_RUN. Cleanup authorization remains false.
- Latest focused storage/backup regression: 54 passed; shell syntax and git diff checks pass.
- Evidence: evidence/operations/hes_smart_storage_manager_20261116.json.


## Fresh production progress — 2026-11-16 14:08 UTC

- **Dropbox stable backup replaced and remotely verified.** The prior `HES Trade Agent Backups/hes-offsite-latest.tar.zst.gpg` object was overwritten in place by the expanded-scope v2 archive `hes-offsite-core-20261116T135324Z.tar.zst.gpg`. Remote rclone content hash, size, GPG decrypt, Zstandard/tar listing, 33/33 recovery-critical paths, active/rollback release presence, and 3,744 independent evidence entries all passed. New SHA-256: `16a1c3ced6be0723dd80494eb4b7b2b8a02cbe661ca94430b13b3777b927da52`. Dropbox free space after replacement: 777,460,340 bytes; 128 MiB reserve remains available. Old archive's local staging copy retained.
- **Production local Restic repository created and verified.** Restic 0.16.4 repository `/var/backups/hes-trade-agent/restic-production-v1/repo`, current size 815,136,818 bytes. Full snapshot ID `26c6d6acad02bbc88b8408bf6a26f2633eeb9dd43e3227962e1ccfaa5a634a7b`, tag `hes-full-recovery-v1`, host `hes-vps-recovery-v1`, 40 recovery roots. `restic check --read-data`: 50/50 packs, 3 snapshots, zero errors. Selective restore from the exact full snapshot ID: 13 required roots and 11 static content comparisons passed.
- **Critical Restic restore/retention bug found and fixed in the draft PR:** two later snapshots contain only `/srv/hes-evidence`; blindly using `latest` would restore only that partial scope, and the previous retention planner could have treated a partial snapshot as superseding a full one. Planner v2 now matches the actual host/tag, requires all 40 full-scope paths, selects `latest_full_snapshot_id`, and keeps partial snapshots outside deletion eligibility. Live run: 1 full + 2 partial, zero deletion candidates.
- No local full archives were deleted; no staging was pruned; no service/timer, release pointer, or trading execution setting changed. The local full-backup footprint remains above the 10 GiB complete-footprint target pending a separate explicit cleanup approval.
- Evidence: `evidence/operations/hes_restic_production_snapshot_20261116.json`, `evidence/operations/hes_restic_scope_aware_retention_20261116.json`, `evidence/operations/hes_dropbox_offsite_replacement_20261116.json`.
