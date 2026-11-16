# HES storage and recovery checkpoint — 2026-11-16

## Final disposition

- Local HES footprint after cleanup: **9.3088 GiB**, under the 10 GiB target.
- Filesystem usage after cleanup: **51%**, with approximately 22.9 GiB free at the measured point.
- Dropbox holds the independently verified compact recovery archive and the encrypted Restic repository; the previous large full archive object was retired to make room for incremental offsite recovery.
- Local Restic repository retains full-scope recovery snapshots and scope-aware retention. Daily local backup and Dropbox sync timers are enabled; the old full-archive Dropbox timer is disabled.

## Cleanup evidence

- 2,137 files representing **25,336,307,115 bytes** were removed after verification and explicit operator approval.
- The eight legacy local full archives all passed their SHA-256 sidecar checks before deletion.
- The prior full Dropbox archive hash matched local staging and had already passed GPG decryption, Zstandard/tar listing, 33/33 recovery-root coverage, active/rollback release coverage, and 3,744 evidence-entry validation.
- The compact recovery archive is **398,216,865 bytes**, SHA-256 `f4702fff3275f828706e081c4f4b3e4dc937058b958bd54f8dbefa599e3d01ec`; remote and local tar listings are byte-for-byte identical with 8,897 entries.
- The full Restic snapshot has 40 roots. `restic check --read-data` passed 50/50 packs before cleanup; after new snapshots, integrity checks also passed.
- Cleanup inventory and deletion reasons are recorded in `/srv/hes-evidence/operations/backup-retention/cleanup-20261116.json`.

## Automation

- Local daily Restic backup runs through `hes-encrypted-local-backup.timer` at 02:30 UTC, with 7 daily / 4 weekly / 6 monthly / 2 yearly retention grouped by `host,paths`.
- Dropbox incremental Restic repository sync runs through `hes-restic-dropbox-sync.timer` at 03:30 UTC, with a 128 MiB quota reserve and post-sync `rclone check`.
- The old `hes-dropbox-offsite.timer` full-archive builder is disabled.
- Recovery passphrase remains operator-held and memorized off-VPS; the VPS root-only working file is excluded from all backup roots and remote artifacts.

No trading or execution settings, market-data configuration, release pointers, or order paths were changed.

## Backup automation self-recovery hardening — 2026-11-16 15:09 UTC

The full-scope Restic root set was expanded from 40 to **43** by adding the exact operational scripts referenced by systemd: `/usr/local/sbin/hes-operational-healthcheck`, `/usr/local/sbin/hes-restic-incremental-backup`, and `/usr/local/sbin/hes-restic-production-dropbox-sync`. This closes a self-recovery gap: restoring `/etc/systemd/system` without the referenced `/usr/local/sbin` executables would not re-establish unattended backup. The local backup runner now verifies the exact 43-root path set and rejects future-dated full snapshots. The Dropbox sync runner requires a 43-root full snapshot before syncing.

A new full snapshot `007f75a02f7a5c199d3ff5265f3bceb338cc1440e3e0983743ec82429bb43cc5` was created at `2026-11-16T15:08:15Z`. The local Restic check read 4/4 packs in its selected 1/20 data subset with zero errors. Dropbox sync passed with 74 matching files and no differences. Full remote read-data verification is running before obsolete 40-root and evidence-only snapshots are retired.

## Final verified state — 2026-11-16 15:13 UTC

- Complete local HES footprint: **9.0382 GiB**, below the 10 GiB limit; root filesystem 52% used with about 23 GiB free.
- Dropbox: full-scope encrypted Restic repository `HES Trade Agent Backups/restic-production-v1` (63 files, 977,921,737 bytes) plus independent compact encrypted recovery archive (398,216,865 bytes, 8,897 archive entries). Dropbox free capacity: **771,258,473 bytes**; 128 MiB reserve is preserved.
- Latest full Restic snapshot contains **43 recovery roots**. The three added roots are the operational healthcheck and the two backup runner scripts referenced by systemd. Only the current 43-root full snapshot remains after old 40-root and evidence-only snapshots were retired.
- Local and downloaded remote `restic check --read-data`: **59/59 packs, zero errors**. Selective restore: **13/13 files**, Restic `--verify` and all 13 independent SHA-256 comparisons passed.
- Local backup timer 02:30 UTC and full-scope Dropbox sync timer 03:30 UTC are enabled. Legacy full-archive and compact-only sync timers are disabled/retired. Retention: 7 daily / 4 weekly / 6 monthly / 2 yearly, grouped by `host,paths`.
- Recovery passphrase is held/memorized by the operator outside the VPS; the root-only working copy is excluded from the 43 backup roots and Dropbox objects.
- Cleanup inventory and per-file evidence: `/srv/hes-evidence/operations/backup-retention/cleanup-20261116.json`; final validation evidence: `/srv/hes-evidence/operations/backup-retention/final-storage-recovery-20261116.json`.

No trading, strategy, market-data, release-pointer, or execution configuration changed.
