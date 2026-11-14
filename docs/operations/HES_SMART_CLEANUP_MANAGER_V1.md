# HES Smart Cleanup Manager v1

**Status:** isolated implementation candidate; dependency-aware read-only dry-run only. Not deployed, not enabled as a service, and contains no destructive executor.

## Purpose

Extend the existing IDLM v1 scanner without creating a second inventory engine. Consume `hes_data_lifecycle_audit_v1` JSON, enrich its records with live process file-descriptor/CWD/root references, running systemd unit path declarations, active/rollback release targets, and registered Git worktree relationships. Add local encrypted-backup checksum, Dropbox quota, remote object size, and Dropbox content-hash checks.

## Safety contract

- The manager rejects source manifests with the wrong schema/mode, a missing or unverified Git worktree registry, or an audit timestamp older than 15 minutes. It has no delete, move, truncate, compress, rotate, prune, or service-mutation implementation.
- `KEEP_*`, `KEEP_UNKNOWN`, any active process/unit reference, active/rollback release relation, registered worktree relation, or incomplete dependency scan fails closed to `KEEP`.
- A clean live-reference scan yields at most `REVIEW_ONLY`; it is not permission to delete.
- A selective restore is not a full-system restore. `full_restore_gate` remains `BLOCKED_NOT_PROVEN` until a separately isolated full recovery drill is evidenced.
- `delete_authorized` is always zero; `automatic_action` is always `NONE`.
- No new service, timer, daemon, monitor, or market-data path is created. Existing IDLM inventory and health checks are reused.

## Backup and capacity checks

The manager checks the newest local encrypted full backup sidecar, newest local offsite bundle sidecar, Dropbox Basic quota through the existing `hesdropbox:` rclone remote, remote stable-object size, and remote content hash against the newest local offsite bundle. It does not print credentials or read the encryption passphrase into the report. Dropbox quota is observational; the existing offsite cycle remains the only upload/retention mechanism and retains its 1.5 GiB archive cap plus 128 MiB reserve.

Disk and inode metrics are taken from the source IDLM audit. Pressure is reported as OK at >=15% free, WARN at 10–15%, and CRITICAL below 10%; this is a manager summary, not a replacement for the existing operational health monitor.

## Invocation

Run the existing IDLM inventory first, writing outside scanned roots, then:

```bash
python3 scripts/ops/hes_smart_cleanup_manager_v1.py \
  --audit-manifest /var/tmp/hes-idlm-audit.json \
  --output /var/tmp/hes-smart-cleanup-manager.json
```

The command reads the existing report, inspects `/proc` and active systemd declarations, checks backup hashes/quota/remote content hash, and writes a JSON review report. It does not mutate project files or services.

## Acceptance boundary

The scanner now reads standard cron files, enabled user-systemd unit symlinks, tmpfiles, logrotate and apt maintenance declarations. It does not query every transient or dynamically launched per-user systemd manager; active process references are still scanned, and any unresolved source must remain KEEP. This candidate is suitable for further review and repeated dry-run soak only. Before any canary cleanup can be considered, require exact-SHA CI/full regression, independent review, a separately isolated full restore drill, per-path owner/retention/dependency approval, stale-manifest protection, concurrent-writer and interrupted-operation tests, and an explicit human-approved bounded canary. Unknown remains KEEP. The three-signals-per-day limit and Gate.io canonical market-data architecture are unaffected; IDLM has no trading authority.


## Encrypted local backup manager — 2026-11-14

The existing local encrypted backup service is now versioned with its deployable systemd unit and timer:

- Source: scripts/ops/hes_encrypted_local_backup_v1.sh
- Unit/timer: deploy/systemd/hes-encrypted-local-backup.service and .timer
- The archive input set is frozen from an explicit NUL-delimited path list; tar --no-recursion avoids false failures caused by live directory-entry changes while collectors continue running. A file-content race still fails closed.
- Each archive is AES-256 GPG encrypted, then verified by GPG decryption, gzip -t, tar -tzf, and a SHA-256 sidecar before it is accepted.
- A failed run removes only its own incomplete .partial artifacts. The 5 GiB free-space floor and operational healthcheck remain mandatory.
- Retention is 7 daily snapshots, 4 weekly snapshots, and 6 monthly snapshots; same-day duplicates keep only the newest. A deterministic date override exists only for tests and is unset in production.
- The local backup service is network-isolated. Dropbox remains a separate encrypted offsite path with its existing 1.5 GiB archive cap, 128 MiB reserve, quota check, remote content verification, and metadata verification.

Live verification on 2026-11-14: local archive hes-full-20261114T030547Z.tar.gz.gpg is 2,271,413,402 bytes; SHA-256 fc791eb373f2d3a7088f7c37858c61f3f51e8e7ef2e44604483412aa8b7e1948 verified against its sidecar. The daily backup service completed successfully. Disk usage fell to 80% (9.7 GiB free) after removing only a completed isolated restore extraction and a superseded failed .partial after the replacement archive passed integrity checks. The operational healthcheck returned overall=OK, disk-free=19.6%.

The cleanup manager itself remains read-only and fail-closed; this backup change does not authorize automatic deletion of application data or activation of a cleanup timer.
