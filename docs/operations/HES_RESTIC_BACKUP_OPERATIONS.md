# HES Trade Agent — encrypted incremental backup and offsite recovery

## Recovery layout

- Local full-scope Restic repository: `/var/backups/hes-trade-agent/restic-production-v1/repo`.
- The 43-root set explicitly includes the operational healthcheck and both backup runner scripts, so a restored system can re-establish its own backup automation.
- Dropbox Restic repository: `hesdropbox:HES Trade Agent Backups/restic-production-v1`.
- Independent compact recovery archive: `hesdropbox:HES Trade Agent Backups/hes-recovery-core-latest.tar.zst.gpg`, with adjacent `.sha256` and `.manifest.json` files.
- Restic repository encryption and compact-archive GPG AES-256 use the operator-held recovery passphrase. The secret is not embedded in the repository, archive, Dropbox, or source control. A root-only working copy exists on the VPS for unattended jobs and is excluded from all backup roots.

The former 1.37 GB daily full-archive Dropbox job is retired. The full-scope Restic repository and the independently encrypted compact recovery archive provide separate offsite recovery paths. The temporary compact-only Restic repository was retired after the full-scope repository passed remote verification.

## Automation

| Job | Schedule | Behavior |
|---|---|---|
| `hes-encrypted-local-backup.timer` | Daily 02:30 UTC, up to 20 min random delay | Incremental Restic backup of 43 recovery roots; health and free-space gates; exact full-scope verification; scope-aware retention; partial read-data integrity check |
| `hes-restic-production-dropbox-sync.timer` | Daily 03:30 UTC, up to 5 min random delay | Quota-guarded `rclone sync`, 128 MiB reserve, then bidirectional `rclone check` |

The legacy `hes-dropbox-offsite.timer` and temporary compact-only `hes-restic-production-dropbox-sync.timer` are disabled. The full-scope production sync timer is enabled.

## Retention safety

Restic retention is 7 daily, 4 weekly, 6 monthly, and 2 yearly snapshots, grouped explicitly by `host,paths`. Full 43-root snapshots and evidence-only snapshots therefore belong to separate groups. An evidence-only snapshot cannot replace or cause deletion of the full-system recovery group. Future-dated snapshots are rejected by the full-scope selector.

## Recovery

1. Copy `hesdropbox:HES Trade Agent Backups/restic-production-v1` to an isolated recovery host using `rclone copy`.
2. Supply the operator-held passphrase through a root-only file outside the restored backup tree.
3. Set `RESTIC_REPOSITORY` to the copied repository and `RESTIC_PASSWORD_FILE` to that secret file; run `restic snapshots` and `restic check --read-data`.
4. Select a snapshot with host `hes-vps-recovery-v1`, tag `hes-full-recovery-v1`, and all 43 required roots. Do not rely on the unqualified `latest` alias because partial evidence-only snapshots may exist.
5. Restore to an isolated target first; never overwrite a running production root.

The compact archive can independently be verified and listed with GPG and Zstandard before extraction. Its JSON manifest identifies active/rollback releases, included recovery scope, and exclusions.

## Guardrails

- Dropbox upload is blocked unless current free capacity plus any existing remote repository size can accommodate the complete local repository and a 128 MiB reserve.
- Remote repository sync is checked after transfer; mismatch fails the job.
- Local backup stops if disk free space falls below 512 MiB or operational health is not healthy.
- Backup jobs do not modify trading execution, strategies, market-data sources, release pointers, or order settings.
