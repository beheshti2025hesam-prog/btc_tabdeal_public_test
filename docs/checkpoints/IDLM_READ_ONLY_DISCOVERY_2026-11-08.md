# IDLM read-only discovery checkpoint — 2026-11-08

**Mode:** read-only. No files were deleted, moved, compressed, rotated, or pruned. No service was restarted and no production retention setting was changed.

## Filesystem baseline

- Sole VPS root filesystem: 50G; approximately 40G used; 7.4G available; `df` reports 85% used. Inode use is approximately 14%.
- Root directory usage, privileged scan: `/var` about 20G, `/opt` about 6.4G, `/tmp` about 5.4G, `/home` about 2.5G, `/usr` about 3.4G, `/boot` about 200M.
- `/var/backups/hes-trade-agent` occupies about 18G. Its `encrypted-local` tier is about 15G.
- `/var/log/journal` occupies about 286.6M.
- `/var/cache/apt` occupies about 604M.
- `/home/hes-remote/.npm` is about 1.1G and `/home/hes-remote/.cache` about 924M.
- `/opt/sentinelx-cloud-core/.cache` is about 985M.
- `/tmp` includes many dated test/replay workspaces; `/tmp/hes-playwright-browsers` is about 924M. All are review-only until their job/evidence dependencies are established.

## Backup findings

- Eleven encrypted full backup archives were present in `/var/backups/hes-trade-agent/encrypted-local`, ranging from about 1.2G to 2.0G each.
- All eleven sidecar SHA-256 checks passed.
- The active `hes-encrypted-local-backup.timer` runs daily around 02:30 UTC.
- The backup script checks health and requires at least 5G free before starting. It encrypts the full project/system scope, verifies decryption/gzip integrity/tar listing, writes a SHA-256 sidecar, then applies retention.
- Existing retention keeps all snapshots younger than seven days, Sunday snapshots under 28 days, and first-of-month snapshots under 180 days. It does not cap multiple snapshots made on the same UTC day. Three backups were found on 2026-11-02 and three on 2026-11-06.
- This is a same-day duplicate review opportunity, not deletion permission. No full restore drill or verified independent offsite restore was established in this audit. Keep all backups until that gate passes.

## Existing controls to reuse

- The existing HES runtime check reports disk-free percentage: at least 15% is OK, 10–15% is WARN, below 10% is CRITICAL.
- The host-level operational check reports root-disk pressure as CRITICAL at 85% used.
- Current recorded health issue: `disk-free:14.8%`. Extend these existing checks with inode availability, growth rate, and time-to-capacity forecasting; do not create a duplicate monitor.
- Generic `logrotate.timer` is enabled and daily. No HES-specific logrotate rule was found in the inspected configuration.
- `systemd-tmpfiles` currently gives `/tmp` a 30-day cleanup age. This is not a substitute for HES data-retention policy.
- Root-level privileged inspection was required for complete accounting; the unprivileged `du` scan understated `/var/backups`.

## Repository/runtime preservation

- Local checkout: `/opt/hes-trade-agent`; branch `feat/gateio-global-market-data-v1`; HEAD `060d0d36ae6140a03d9a74495bb3899637ed3827`.
- The checkout is heavily dirty and contains many untracked files, worktrees, candidate/release trees, and evidence. Preserve all of them; do not reset, clean, overwrite, or delete.
- `current` resolves to release `f5d505567522555ee1be9c260e83085347515721`; `current-before-4329a3df` resolves to `737d0555f9348f1e2584714a988d0751bb4448d4`.
- Nine HES services were observed active. Their runtime data, journals, and feed files remain protected.

## Disposition and next gates

1. Add and test the read-only IDLM inventory/candidate-manifest tool on an isolated branch.
2. Run it against the VPS in read-only mode and reconcile its path-level output with the privileged disk baseline.
3. Map active process descriptors, systemd unit read/write paths, Git/worktree references, backup provenance, and restore dependencies.
4. Test a proposed same-day backup retention policy against synthetic archives and prove that the newest verified daily backup is always retained.
5. Complete an independent restore drill and offsite coverage review before changing backup retention or deleting any backup.
6. Only after independent review may an allowlisted cache/temp canary be considered.

**Current disposition:** Phase A discovery is in progress. No destructive operation is authorized or performed.
