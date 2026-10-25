# SQLite Execution Journal Backup/Restore v1

This procedure applies only to the existing file-backed execution journal. It does not activate execution, contact a venue, or alter the source database during backup. Run it only from the authorized project runtime and use an access-controlled backup directory.

## Create a verified backup

```bash
python -m scripts.backup_execution_journal_v1 --backup /path/to/execution.sqlite /secure/backup/execution-YYYYMMDD.sqlite
```

The command fails if the source is missing/unsafe or the destination already exists. On success it writes the SQLite backup and adjacent `.manifest.json` containing the backup SHA-256, byte size, UTC creation time, and integrity result. Store the database and manifest together; the manifest is required for restore verification.

## Verify and restore

Restore to a **new path** first:

```bash
python -m scripts.backup_execution_journal_v1 --restore /secure/backup/execution-YYYYMMDD.sqlite /tmp/execution-restore-check.sqlite
```

The command verifies manifest schema, SHA-256, size, and SQLite integrity before writing the destination. It then rechecks the restored database. Existing destinations are protected; `--overwrite` is required to replace one. Prefer restoring to a new path, comparing expected record counts/state, and only then scheduling an operator-controlled cutover.

## Required operational controls

- Keep the SQLite database and manifest access-controlled; do not print or upload database contents.
- Schedule backups only after the deployment/runtime owner approves the path and retention policy.
- Periodically restore into a separate path and record the exact backup hash, restored hash, `PRAGMA integrity_check`, record counts, date, and operator.
- Never use a backup with a missing or mismatched manifest. Any error means the restore is blocked.
- This utility is tested in CI, but a scheduled backup and successful recovery on the authorized production runtime have **not** been demonstrated by this code change.
