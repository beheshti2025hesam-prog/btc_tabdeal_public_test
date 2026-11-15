# HES evidence-store backup coverage — 2026-11-14

## Finding
- /srv/hes-evidence: 3,744 files, 414 MiB allocated, 421,318,869 logical bytes.
- Both /usr/local/sbin/hes-encrypted-local-backup and scripts/hes-dropbox-offsite-build.sh omitted this protected evidence store.
- Streaming tar-to-gzip estimate: 146,800,584 bytes.
- Dropbox Basic: 2 GiB total, 1,581,229,802 bytes used, 566,253,846 bytes free; current offsite object 1,581,153,470 bytes. Existing 128 MiB quota reserve is retained.

## Candidate implementation
Branch: fix/hes-evidence-backup-coverage-v1
Base: PR #496 exact head c875cb2ec4f96fd7cdc7c8b1f36b2a4c944edbf7.

- Include /srv/hes-evidence in local and Dropbox offsite archives.
- Require the store to exist and verify its directory entry and exact file/symlink count in the decrypted tar listing before accepting each archive.
- Emit local and offsite coverage manifests.
- Require both manifests to prove coverage in Smart Cleanup Manager's backup-integrity gate.
- Require matching remote size/hash and the same 128 MiB quota replacement reserve.
- Increase the offsite archive cap to 1.75 GiB in builder and cycle, consistently.

## Validation
- 102 focused operational tests passed.
- bash -n: local backup, offsite builder and offsite cycle passed.
- Python compile and git diff --check passed.
- No live backup, Dropbox upload, service mutation, deployment, cleanup, or deletion was performed.

## Acceptance gates
1. Exact-head GitHub Actions on the candidate.
2. Review retention sidecar and coverage-manifest behavior.
3. Controlled deploy of updated scripts only after CI/review.
4. New local backup must include /srv/hes-evidence; SHA sidecar and coverage manifest must pass.
5. New offsite bundle must pass GPG/gzip/tar listing, sidecar, remote rclone content hash, remote size and quota guard.
6. Full archive extraction into isolated scratch must pass; host replacement recovery remains a separate gate.

Status: CANDIDATE / NOT DEPLOYED. Smart Cleanup remains read-only; delete_authorized=0.

## Follow-up isolation correction — 2026-11-15

The offsite builder previously generated Python/OS dependency snapshots inside
/opt/hes-trade-agent/docs/checkpoints/, mutating the live checkout and
requiring a systemd write exception to the source tree. The builder now writes
these three recovery metadata files under
/var/backups/hes-trade-agent/offsite-staging/recovery-metadata/offsite-dependency-snapshot.
That directory is explicitly included in the encrypted archive input list and
the manifest identifies the archived path. The systemd drop-in resets the
legacy ReadWritePaths exception and re-adds only the existing staging, lock,
GPG and rclone paths. A regression test asserts that no project-tree write
path remains in the builder or service drop-in. This is candidate code only;
the live unit/drop-in and backup services have not been changed.
