# IDLM read-only discovery checkpoint — 2026-11-08

**Mode:** read-only. No files were deleted, moved, compressed, rotated, or pruned. No service was restarted and no production retention setting was changed.

## Filesystem baseline

- Sole VPS root filesystem: 50G; approximately 40G used; `df` reported 85% used and 7.4G available at the initial privileged scan. A later IDLM scan measured 15.23% free by `shutil.disk_usage` and 87.04% free inodes. The small free-space percentage difference is due to `df` available blocks versus filesystem free blocks/reserved space; retain both metrics.
- Root directory usage, privileged scan: `/var` about 20G, `/opt` about 6.4G, `/tmp` about 5.4G, `/home` about 2.5G, `/usr` about 3.4G, `/boot` about 200M.
- `/var/backups/hes-trade-agent` occupies about 18G. Its `encrypted-local` tier occupies about 16.0G allocated.
- `/var/log/journal` occupies about 286.6M.
- `/var/cache/apt` occupies about 604M.
- `/home/hes-remote/.npm` is about 1.03G and `/home/hes-remote/.cache` about 968M.
- `/opt/sentinelx-cloud-core/.cache` is about 1.03G.
- `/tmp` includes many dated test/replay workspaces; `/tmp/hes-playwright-browsers` is about 924M. All are review-only until their job/evidence dependencies are established.

## Read-only IDLM scanner result

- The scanner inventoried 702 top-level filesystem entries across its configured roots with zero scan errors.
- Report mode: `READ_ONLY_DRY_RUN`; `automatic_action=NONE`.
- Disk: 15.23% free; inodes: 87.04% free.
- Backup scan: 11 encrypted full snapshots across 7 UTC dates; four older same-day additional snapshots were identified (two on 2026-11-02 and two on 2026-11-06). These are **not proven content duplicates** and remain protected.
- Review classifications: 172 stale temporary-workspace entries, 306 other temporary entries, 22 regenerable-cache review entries, one system-journal policy review, and one log-policy review. Unknown entries remain KEEP.
- The report is stored on the VPS at `/root/hes-idlm-audit-20261108-v3.json`. It is a review artifact, not authorization to delete anything.

## Backup findings

- Eleven encrypted full backup archives were present in `/var/backups/hes-trade-agent/encrypted-local`, ranging from about 1.2G to 2.0G each.
- All eleven sidecar SHA-256 checks passed.
- The active `hes-encrypted-local-backup.timer` runs daily around 02:30 UTC.
- The backup script checks health and requires at least 5G free before starting. It encrypts the full project/system scope, verifies decryption/gzip integrity/tar listing, writes a SHA-256 sidecar, then applies retention.
- Existing retention keeps all snapshots younger than seven days, Sunday snapshots under 28 days, and first-of-month snapshots under 180 days. It does not cap multiple snapshots made on the same UTC day.
- The four older same-day snapshots are only additional full backups by timestamp. Their contents are not proven identical. No full restore drill or verified independent offsite restore was established in this audit. Keep all backups until that gate passes.

## Existing controls to reuse

- The existing HES runtime check reports disk-free percentage: at least 15% is OK, 10–15% is WARN, below 10% is CRITICAL.
- The host-level operational check reports root-disk pressure as CRITICAL at 85% used.
- The last recorded health-state issue at the time of inspection was `disk-free:14.8%`; a later read-only scan measured 15.23% free. Reconcile this through the next scheduled health sample rather than manually running a recovery-capable check.
- Extend the existing checks with inode availability, growth rate, and time-to-capacity forecasting; do not create a duplicate monitor.
- Generic `logrotate.timer` is enabled and daily. No HES-specific logrotate rule was found in the inspected configuration.
- `systemd-tmpfiles` currently gives `/tmp` a 30-day cleanup age. This is not a substitute for HES data-retention policy.
- Root-level privileged inspection was required for complete accounting; the unprivileged `du` scan understated `/var/backups`.

## Repository/runtime preservation

- Local checkout: `/opt/hes-trade-agent`; branch `feat/gateio-global-market-data-v1`; HEAD `060d0d36ae6140a03d9a74495bb3899637ed3827`.
- The checkout is heavily dirty and contains many untracked files, worktrees, candidate/release trees, and evidence. Preserve all of them; do not reset, clean, overwrite, or delete.
- The local untracked `docs/HES_DNA_AND_ROADMAP.md` was append-only updated with the accepted IDLM architecture; original bytes were preserved at `/tmp/HES_DNA_AND_ROADMAP.md.pre-idlm-20261108`.
- `current` resolves to release `f5d505567522555ee1be9c260e83085347515721`; `current-before-4329a3df` resolves to `737d0555f9348f1e2584714a988d0751bb4448d4`.
- Nine HES services were observed active. Their runtime data, journals, and feed files remain protected.

## Code review status

- Isolated GitHub branch: `feat/hes-intelligent-data-lifecycle-audit-v1`.
- Draft PR #485 adds the read-only scanner, six focused tests, architecture documentation, and this discovery checkpoint.
- Local isolated prototype validation: six tests passed and the module compiled successfully. Repository CI remains pending; no merge or deployment has occurred.
- The PR is independent of the dirty VPS checkout; the production checkout was not changed by this code work.

## Disposition and next gates

1. Complete CI and code review for the read-only scanner.
2. Reconcile scanner path-level output with active process descriptors, systemd unit read/write paths, Git/worktree references, and backup provenance.
3. Test a proposed same-day backup retention policy against synthetic archives and prove the newest valid daily backup is always retained.
4. Complete an independent restore drill and offsite coverage review before changing backup retention or deleting any backup.
5. Extend the existing health monitor with inode/growth/forecast signals after focused tests and review.
6. Only after independent review may an allowlisted cache/temp canary be considered.

**Current disposition:** Phase A discovery and read-only implementation are in progress. No destructive operation is authorized or performed.
