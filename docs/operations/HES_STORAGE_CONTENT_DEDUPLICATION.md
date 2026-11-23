# HES Storage Content Deduplication v1

## Purpose

Reduce physical VPS storage consumed by repeated, byte-identical payloads in immutable HES offsite recovery snapshots without deleting any path or backup generation.

## Scope

- Timestamped `differential-v2-YYYYMMDDTHHMMSSZ` and `live-data-snapshot-YYYYMMDDTHHMMSSZ` directories under `/var/backups/hes-trade-agent/offsite-staging/recovery-metadata`.
- Selected immutable root-level HES archive payloads with approved filename prefixes.
- Only regular files at least 1 MiB, older than the configured age, with identical SHA-256, size, device, owner, group and mode.
- Failed-builds, mutable dependency snapshots, live source data, active project worktrees, model weights, Restic repositories and Dropbox objects are excluded.

## Safety properties

- No file or directory path is deleted.
- A duplicate path is atomically replaced by a hardlink to a byte-identical canonical file on the same filesystem.
- Symlinks, open files, already-hardlinked files, metadata-mismatched files, young snapshots and unknown paths are skipped.
- The offsite builder lock is held while deduplication runs, preventing a race with snapshot creation.
- A root-owned evidence manifest is fsynced before any link changes. It records SHA-256, original inode, size, allocated bytes, owner/group, mode, per-path mtime and atime, canonical path, and every planned duplicate.
- The undo mode checks available space before making independent copies and restores per-path metadata. It never removes paths.
- The daily systemd timer is a storage optimization only; it does not authorize backup retention or project-data deletion.

## Run / inspect

Dry run:

```bash
python3 /usr/local/lib/hes-storage-v1/hes_storage_content_dedupe_v1.py \
  --root /var/backups/hes-trade-agent/offsite-staging/recovery-metadata
```

Apply (normally via the daily systemd timer):

```bash
systemctl start --wait hes-storage-content-dedupe.service
```

Undo a specific manifest (requires enough free disk space to recreate independent copies):

```bash
python3 /usr/local/lib/hes-storage-v1/hes_storage_content_dedupe_v1.py \
  --undo-manifest /srv/hes-evidence/operations/storage-lifecycle/content-dedupe-YYYYMMDDTHHMMSSZ.json
```

A hardlink is not a second backup copy. It preserves all snapshot paths and bytes while sharing one physical inode. Do not modify files inside timestamped recovery snapshots in place; build a new timestamped snapshot instead.