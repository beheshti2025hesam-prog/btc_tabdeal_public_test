# HES Smart Storage Manager v1

## Purpose
A read-only capacity, archive, Dropbox quota and compression planner. It consumes the existing IDLM v1 source audit and dependency-aware Smart Cleanup Manager v1 output. It deliberately does not create a second recursive project scanner or a second dependency resolver.

## Safety
- Report-only: no delete, move, truncate, rotation, prune, archive rewrite, or service mutation.
- IDLM and Smart Cleanup reports must match exact schema/source snapshot, be no older than 15 minutes, and pass source/dependency scan gates. Stale, mismatched, incomplete or error-bearing input fails closed.
- Full restore gate must pass before any retention or cleanup authorization. Current recovery status remains BLOCKED_NOT_PROVEN.
- Active/rollback releases, canonical Gate.io data, journals, evidence and all backup archives remain protected.
- Unknown paths, scan errors and uncertain dependencies mean KEEP.
- Compression recommendations never alter existing archives. A future versioned zstd archive must be verified before publication, retain legacy gzip readers, and keep the encryption key outside Dropbox.
- No automatic cleanup timer is authorized by this version.

## Capacity controls
Uses the existing lifecycle inventory's per-item allocated bytes and Smart Cleanup dependency classifications, plus filesystem capacity/inodes, archive counts and same-day archive multiplicity, and Dropbox quota. This avoids duplicating the existing IDLM/Smart Cleanup scanner. The storage manager does not independently authorize cache cleanup.

## Compression evidence (2026-11-15)

A full-scope streaming benchmark used the same include-list semantics as the production offsite builder: 30,546 entries and 4,077,824,000 uncompressed tar bytes, including active and rollback releases. The benchmark streamed to byte counters; it did not write an archive or modify production data.

| Format | Output bytes | Elapsed | Peak RSS |
|---|---:|---:|---:|
| gzip -1 | 1,601,064,546 | 73.89 s | 8,016 KiB |
| zstd -3, single thread | 1,407,220,695 | 28.07 s | 7,936 KiB |
| zstd -9, single thread | 1,228,742,799 | 160.95 s | 8,000 KiB |

zstd -9 was 23.25% smaller than gzip -1 and 12.68% smaller than zstd -3. Both zstd levels are below the existing 1.5 GiB archive cap; zstd -9 has 381,869,937 bytes of headroom. The benchmark used nice 15, idle I/O priority and one zstd thread. These are full-scope measurements. A full streaming round-trip then passed: tar -> zstd -9 -> AES-256 GPG encryption -> GPG decryption -> zstd decompression -> tar listing, verifying all 30,546 members and both active/rollback release paths. Peak RSS was 8,016 KiB and elapsed time 168.89 seconds. No archive file was written or extracted to disk. This validates the complete codec/encryption stream but does not prove full extraction or replacement-host recovery. Evidence JSON: evidence/operations/hes_zstd_full_scope_benchmark_20261115.json.

A new streaming verifier, scripts/ops/hes_backup_archive_verify_v1.py, now detects legacy .tar.gz.gpg and versioned .tar.zst.gpg archives by suffix, decrypts and decompresses them, checks every tar member path for traversal/absolute paths, and confirms both active and rollback release paths without extracting files. It verified the current production legacy gzip offsite archive: 29,792 members, GPG decrypt PASS, no unsafe paths, active and rollback paths present. A small encrypted fixture also passed for both gzip and zstd formats.

Production still uses encrypted gzip. Do not switch until the versioned zstd builder/cycle integration and backward-compatible restore path are reviewed, exact-head CI passes, and Dropbox stable-object overwrite/quota behavior is reviewed. Never recompress ciphertext or remove a valid gzip archive before a new backup is independently verified.

## Current recovery boundary
The current Smart Cleanup report confirms encrypted local/offsite backup integrity and remote Dropbox hash match, but its full restore gate is BLOCKED_NOT_PROVEN. A prior selective restore and same-host application restore evidence do not prove full-system/replacement-host recovery. With one VPS and no suitable secondary local capacity, do not force full extraction onto production root or RAM.

## Next gates
1. Exact-head CI and independent review.
2. Representative full-scope compression benchmark including CPU, RAM, elapsed time, output size and archive integrity; no output archive written during benchmark.
3. Versioned zstd archive/restore implementation with legacy gzip compatibility before any format migration.
4. Full restore proof in a safe isolated target before changing backup retention.
5. Explicitly reviewed and reversible cache cleanup canary only after the dependency-aware scanner and restore gates permit it.


## 10. HES 10 GiB storage objective and measured baseline — 2026-11-16

The requested storage ceiling is tracked in two explicit scopes so backups are not hidden inside a vague "agent size" number:

1. **Agent core:** project checkout (including releases/candidates/worktrees) plus independent /srv/hes-evidence.
2. **Complete local HES footprint:** agent core plus all HES local backups and offsite staging copies. Ubuntu and SentinelX platform files are reported separately and are not counted as HES application data.

Fresh root-run IDLM + dependency-aware Smart Cleanup + Storage Manager snapshot (all exact source timestamps matched; 918 rows):
- Agent project checkout: 6,924,898,304 allocated bytes.
- Independent evidence store: 431,423,488 allocated bytes.
- Agent core total: 7,356,321,792 bytes (~6.85 GiB), currently within the 10 GiB target.
- Local backup + offsite staging roots: 23,239,327,744 bytes.
- Complete local HES footprint: 30,595,649,536 bytes (~28.49 GiB), about 18.5 GiB over the aspirational 10 GiB complete-footprint target.
- Root filesystem: 50 GiB total, 86% used, about 6.93 GiB free at the time of this audit; inode availability remains healthy.
- Eight local full encrypted gzip backups consume 17,735,777,522 logical bytes. Two local offsite staging Zstandard bundles consume 2,727,900,259 bytes. The two older security-stability restore trees and other protected backup material are included in the backup-root total.
- Dropbox Basic remote quota read: 2 GiB total, 1,366,621,708 bytes used, 780,861,940 bytes free. No remote object was changed.

The budget report sums only direct-child allocated-byte rows from the same IDLM/Smart Cleanup snapshot. Nested rows are excluded to avoid double counting. The code reports both scopes and refuses to call the complete footprint within budget while backups exceed the cap.

### 10.1 Local backup Zstandard v2 candidate

A separate, uninstalled candidate was added:
- scripts/ops/hes_encrypted_local_backup_v2.sh
- scripts/ops/hes_backup_retention_v2.py
- Existing hes_backup_archive_verify_v1.py is reused for both gzip and Zstandard archive verification.

Candidate behavior:
- New local full backups use .tar.zst.gpg, Zstandard level 9, one thread, low CPU priority and idle I/O priority, then AES-256 GPG encryption.
- Frozen NUL-delimited include list, tar --no-recursion, exact /srv/hes-evidence entry-count check, SHA-256 sidecar and coverage manifest are retained.
- Before accepting the archive, the verifier decrypts and streams decompression, checks member paths, and requires both current active and rollback release directories.
- Mixed-format retention understands legacy .tar.gz.gpg and new .tar.zst.gpg names under the existing 7-day daily / 28-day Sunday / 180-day first-of-month policy. Same-day superseded archives are selected by parsed UTC timestamp, not filename format. Invalid/future/unparseable names fail closed to KEEP.
- The helper's default output is a report with automatic_action=NONE and delete_authorized=false; the backup script only invokes the delete-list after the new archive has passed verification, preserving the existing retention behavior.
- The candidate script is network-isolated; Dropbox upload remains a separate existing workflow.
- The live systemd service, installed /usr/local/sbin script, timer, existing gzip archives and retention settings were not changed.

### 10.2 Local-scope compression benchmark — 2026-11-16

The benchmark uses the exact local-backup include-list semantics (project checkout, independent evidence store, SSH/nftables/systemd and optional runtime scripts), freezes 60,803 path entries, streams to byte counters, and writes no archive. Compression runs at low CPU and idle I/O priority. Results:
- Raw tar stream: 7,315,415,040 bytes; 60,807 entries.
- Gzip level 1: 2,453,424,957 output bytes, 122 seconds.
- Zstandard level 3, one thread: 2,193,274,296 output bytes, 63 seconds (10.60% smaller than gzip level 1).
- Zstandard level 9, one thread: 1,920,590,051 output bytes, 303 seconds (21.72% smaller than gzip level 1; 12.43% smaller than zstd level 3).
- Evidence JSON: evidence/operations/hes_local_backup_zstd_benchmark_20261116.json.
- No production backup archive was created, replaced or deleted by this benchmark. The root free-space reading did not change.

The earlier independent full-scope offsite benchmark measured Zstandard level 9 at 23.25% smaller than gzip level 1 and passed a full encrypted streaming round-trip over 30,546 members. That result is not substituted for the local-scope comparison.

### 10.3 Validation performed

- Local backup retention planner, v2 backup script contract, gzip/zstd archive verifier and storage budget/compression parser: 34 focused tests passed.
- IDLM temporary-cache quarantine safety suite after scan-completeness correction: 25 tests passed.
- Storage manager + archive verifier + retention + backup-v2 + lifecycle audit suite: 46 tests passed.
- Encrypted fixture round-trips: both Zstandard and legacy gzip archives passed the streaming verifier; active/rollback paths present, no unsafe member paths, no extraction performed.
- Live retention dry-run over current local backup folder kept all eight valid full backups and two nonstandard archive names; no deletion was proposed.
- Root-run dependency-aware audit: 918 items; 366 KEEP, 552 REVIEW_ONLY, 304 live-referenced, zero dependency-unknown. Full restore gate remains BLOCKED_NOT_PROVEN; delete_authorized=0.

### 10.4 Cleanup boundary and next engineering steps

The largest regenerable-cache classifications are outside the HES project itself:
- /opt/sentinelx-cloud-core/.cache ~1.03 GB.
- /home/hes-remote/.cache ~0.97 GB.
- /home/hes-remote/.npm ~0.72 GB.
These are SentinelX/platform-user caches, not HES-owned project data. Although the dependency scan observed no live process/unit references, they remain REVIEW_ONLY; no cache was deleted. They must not be silently counted as HES cleanup or removed without a separate platform-owner decision.

Within HES, the checkout is ~6.85 GiB and the largest subtrees are releases (~2.92 GB), candidates (~1.64 GB), and registered worktrees (~1.11 GB). These contain versioned code and working branches; they are not disposable caches. A future release/worktree compaction planner must verify active/rollback pointers, systemd/process/scheduled-job references, clean Git state, exact commit provenance and remote GitHub availability before proposing any removal.

The 10 GiB agent-core target is currently met. The 10 GiB complete-local-footprint target is not yet met because full local backup retention is the dominant cost. Next steps are: finish the exact local gzip comparison; validate the Zstandard v2 candidate on an isolated archive fixture; prototype content-deduplicated/incremental snapshots or a reduced local staging model while preserving a verified offsite recovery copy; and prove a full restore before changing backup retention. No live deletion, quarantine, backup migration, service change or release-pointer change is authorized by this report.


### 10.5 Temporary-cache scanner completeness correction

The isolated IDLM cache-quarantine candidate initially hit its 100-directory discovery cap and failed closed. A bounded correction raised the discovery ceiling to 300 (the observed /tmp + /var/tmp candidate-name count was 267) and explicitly skips systemd-private temporary roots. ENOENT/ESRCH races for ephemeral paths are treated as vanished entries, not actionable scan targets; permission and other scan errors still block execution.

Fresh root-run dry-run after this correction:
- Git worktree registry: readable, 25 registered worktrees.
- scan_errors: empty.
- 10 cache directories eligible under the narrow existing allowlist, total 716,800 allocated bytes (~0.68 MiB), all within one old pip-build-env temporary tree.
- automatic_action=NONE, execution_enabled=false, deletion_authorized=false.
- No quarantine or deletion was performed. The recovered scan completeness did not uncover a meaningful multi-gigabyte HES cleanup opportunity; larger platform caches remain outside the HES-owned cleanup allowlist.
- IDLM cache-quarantine safety suite after the correction: 25 tests passed.

### 10.6 Restic deduplication prototype — 2026-11-16

Restic 0.16.4 (Ubuntu package, extracted and run from an isolated temporary directory; not installed system-wide) was evaluated with repository format v2 and maximum compression.

Full-scope local prototype:
- Source: /opt/hes-trade-agent plus /srv/hes-evidence, excluding only regenerable Python bytecode and test/linter caches.
- Processed 6.713 GiB across 54,372 files / 5,965 directories.
- Encrypted repository size after first snapshot: 804,782,531 bytes.
- Repository raw-data statistics: 1,014.515 MiB uncompressed, 766.449 MiB stored, 1.32x ratio, 24.45% compression space saving.
- restic check --read-data: PASS, no errors.
- Selective restore of active release manifest and independent evidence sample: PASS, both byte-for-byte cmp matched.
- Separate incremental fixture: unchanged second snapshot added 0 bytes; a small third-snapshot change added 2,642 repository bytes.

Offsite feasibility:
- A local simulation copied all 48/48 packs into a second Restic repository initialized with source chunker parameters.
- Simulated remote repository was 818,060,463 bytes, exceeding last observed Dropbox free quota (780,861,940 bytes) by 37,198,523 bytes (~35.5 MiB).
- No Dropbox upload occurred. Simulation repository was not retained after isolated SentinelX job cleanup; its post-copy read-data check and restore are NOT RUN. Do not describe remote-copy test as restore-verified.
- A quota-aware backup scope/profile or additional remote storage capacity is needed before offsite adoption.

Prototype evidence only. No Restic package installation, production service/timer change, retention change, Dropbox object mutation, archive deletion, or release-pointer change was made. Prototype password was temporary and not reused for production.


## 11. Restic deduplicated backup and Dropbox capacity gate — 2026-11-16

The isolated Restic 0.16.4 prototype is recorded in evidence/operations/hes_restic_dedup_prototype_20261116.json. It covered the HES project checkout and independent evidence store (6.713 GiB source); the local encrypted repository was 804,782,531 bytes. Restic raw-data statistics reported 1,014.515 MiB uncompressed and 766.449 MiB stored. The local repository passed check --read-data; selective restore of the release manifest and evidence sample passed hash comparison. The fixture proved unchanged second snapshots add zero bytes and a small third-snapshot change added 2,642 bytes.

The copy simulation produced an 818,060,463-byte remote repository (48/48 packs copied). The remote post-copy check --read-data and restore were not completed, and no Dropbox upload occurred. The isolated prototype workspace was removed by its temporary-job cleanup; it is not a production repository.

Evidence is recorded in evidence/operations/hes_restic_offsite_capacity_gate_20261116.json. A new fail-closed preflight, scripts/ops/hes_restic_offsite_capacity_gate_v1.py, now compares the measured repository bytes with live rclone about hesdropbox: --json quota and a 64 MiB reserve. It rejects inconsistent quota readings and never authorizes transfer itself. With the observed Dropbox capacity (2,147,483,648 total; 1,366,621,708 used; 780,861,940 free) and the prototype's 818,060,463-byte repository, the gate returns BLOCKED_INSUFFICIENT_FREE_QUOTA: 104,307,387 bytes short including reserve (37,198,523 bytes short before reserve).

This is a preflight implementation and a verified block, not an offsite deployment. The current Dropbox archive, checksum, manifest, and decompression sidecar were left untouched. No Restic remote repository was initialized; no upload, overwrite, deletion, local archive pruning, or service/timer change was made. Transfer remains blocked until enough free quota exists and a post-copy full integrity check plus selective/full restore are demonstrated.


## 12. Restore compression detection hardening — 2026-11-16

The encrypted archive verifier now determines the decoder from the first four bytes of the decrypted payload, not from the archive filename. It recognizes the gzip magic (1F 8B) and Zstandard frame magic (28 B5 2F FD), then streams the already-read prefix and remaining decrypted bytes into the selected decoder without buffering the archive to disk or memory. Filename suffix remains only a compatibility hint for callers that have not yet opened the encrypted stream; it is not authoritative during verification.

Validation:
- 11 archive-verifier tests passed, including wrong/misleading suffix and unknown-magic cases.
- End-to-end encrypted fixtures passed in both directions: gzip payload named .tar.zst.gpg and zstd payload named .tar.gz.gpg were both detected from content and verified successfully.
- Active and rollback release paths were required in both fixtures; extraction was not performed.
- No production verifier was installed/replaced and no backup/restore service or timer was restarted. This change remains in the draft PR until review and the separate production rollout gate.


## 13. Fresh complete-footprint audit — 2026-11-16

A fresh root-run, read-only IDLM + dependency-aware Smart Cleanup + Storage Manager audit completed with 929 inventory rows and no deletion authority. Evidence: evidence/operations/hes_storage_budget_audit_20261116.json.

- Project checkout: 6,925,520,896 allocated bytes.
- Independent evidence store: 431,423,488 allocated bytes.
- Agent core excluding backup copies: 7,356,944,384 bytes (about 6.85 GiB), within the 10 GiB core target.
- Local backup and offsite staging roots: 23,239,327,744 bytes.
- Complete local HES footprint including backups: 30,596,272,128 bytes (28.495 GiB), not within the 10 GiB total-footprint target.
- Local encrypted full archives: 8 files, 17,735,777,522 bytes.
- Offsite staging archives: 2 files, 2,727,900,259 bytes.
- Root filesystem free space: 6,574,469,120 bytes (12.47%, WARN pressure).
- Dropbox quota remains 780,861,940 bytes free.

Interpretation: the project and independent evidence set are already under 10 GiB. The excess is overwhelmingly backup/staging copies, not the active agent core. The Restic prototype currently covers /opt/hes-trade-agent and /srv/hes-evidence, but it is not yet proven to replace the complete encrypted system backup roots (SSH, firewall, systemd/runtime configuration, dependency metadata). Do not delete or prune the existing eight local archives or two staging archives until a complete replacement scope is built, full recovery is validated, and offsite capacity is available. No production backup, retention, Dropbox object, service, timer, release pointer, or evidence file was changed by this audit.

### 14. Recovery-scope completeness correction — 2026-11-16

A live comparison of the installed local backup and Dropbox offsite builder found that the previous explicit path lists omitted recovery-critical host state: UFW and netplan configuration, APT sources/preferences and package state, SentinelX host configuration, sysctl/modules configuration, HES operational state, root SSH material, and the rclone remote configuration. The backup encryption passphrase remains intentionally external.

The draft v2 local-backup candidate now adds these paths to its encrypted archive scope and updates its coverage manifest. The scope is still a candidate only: no production script or unit was replaced, no backup was created, and no retention/deletion was run as part of this change.

The draft branch now also carries a separately testable offsite-builder candidate with the same expanded host-configuration and runtime-state path set. The installed offsite builder remains unchanged; neither candidate was installed or executed. The current Dropbox archive therefore must not be treated as a complete system-recovery replacement. Before migration, both candidate scopes must pass archive-listing and manifest coverage checks, and an isolated restore must validate sensitive host configuration and application/runtime recovery. The external backup passphrase must remain available through separate secure escrow; it must never be included in its own archive.

Live recovery-scope path inventory on 2026-11-16 confirmed all 16 added host-configuration/runtime paths exist (2,133,390 bytes by du -sb; 2,981,888 bytes allocated by du -sB1). A no-persistent-output tar stream/listing over the exact added paths passed, confirming they can be enumerated and read by the archive pipeline. Evidence: evidence/operations/hes_recovery_scope_coverage_20261116.json. This is a path/stream check only, not an encrypted backup or restore test.

### 15. Recovery-scope completeness and retention safety — 2026-11-16

The local and offsite v2 candidates now share the same expanded host-recovery paths: sudo policy, cron and logrotate configuration, security/environment/cloud/network configuration, cron spool, cloud-init state, SentinelX audit log, runtime snapshots, release manifests and the live-replay journal. Both retain AES-256 encryption and omit the external backup passphrase itself. A live inventory confirmed all 33 explicit host paths exist (14,336,143 apparent bytes), and the exact no-persistent-output tar stream/listing passed. Evidence is recorded in evidence/operations/hes_recovery_scope_coverage_20261116.json.

The local v2 candidate's retention step was also hardened: it now emits a retention report only by default. Actual deletion-list processing requires the explicit HES_BACKUP_RETENTION_APPLY=1 environment flag. This flag is not set in the production service, and no production backup or retention operation was run.

### 16. Full-scope Restic restore drill — 2026-11-16

A disposable encrypted Restic v2 repository (Restic 0.16.4, compression max) was built from the complete HES project working set (historical release collection excluded, active and rollback included), independent evidence store, and the expanded 33-path host/runtime recovery set. It processed 4,475,455,640 source bytes and produced a 787,010,021-byte repository. Raw-data stats: 975.376 MiB uncompressed, 749.764 MiB stored, 1.30x compression ratio.

The repository passed read-data integrity over all 45/45 packs with no errors. A full restore to a separate temporary directory—not over the live root—restored 32,927 files, 4,131 directories and 129 symlinks (4.168 GiB). Restic's post-restore verification passed all 32,927 files; all 18 required recovery paths were present; eight static configuration/content comparisons matched. Evidence: evidence/operations/hes_restic_fullscope_restore_drill_20261116.json.

The existing Dropbox archive's remote hash matched its sidecar and an identical local staging copy; GPG decryption, Zstandard integrity and full tar listing passed (35,004 entries). That older archive does not contain the expanded host paths (including UFW, netplan, APT, SentinelX, sudoers, dpkg state and root SSH/rclone configuration), so it is not a complete replacement for the new scope.

Migration remains blocked: the test Restic repository is 787,010,021 bytes, while Dropbox has 780,861,940 bytes free; with the 64 MiB reserve, the shortfall is 73,256,945 bytes. No upload or Dropbox mutation was attempted. The current GPG recovery passphrase exists only on the VPS (mode 0600); no separate external escrow file was found. The disposable Restic repository and its random test password are not production credentials.

This drill proves a full archive restore into an isolated directory on the same host. It does not prove a replacement-host boot or bare-metal OS rebuild. No production backup/service/timer/retention/release pointer or trading execution state was changed.

The latest existing local legacy-gzip archive was independently verified without extraction: hes-full-20261116T023147Z.tar.gz.gpg, 2,454,418,968 bytes, SHA-256 2df8ec077bc77029e611b42dca0d6c2973de08d5dedc28ec4378c0ed4943d9a6. The streaming archive verifier returned PASS, GPG symmetric AES-256 decryption succeeded, gzip integrity test passed, 60,801 members were listed, zero unsafe paths were found, and both active and rollback releases were present. Evidence is recorded alongside the full Restic restore drill. This remains a legacy backup and does not include the newly expanded host recovery scope.

### 17. Fresh IDLM / Smart Cleanup / Storage Manager reconciliation — 2026-11-16 10:29 UTC

A fresh read-only IDLM scan after the isolated restore and temporary-artifact cleanup inventoried 928 items. The exact dependency-aware Smart Cleanup pass consumed that same IDLM snapshot: 327 KEEP, 601 REVIEW_ONLY, 88 live-referenced, zero dependency-unknown, and deletion authorization false. The integrated storage manager confirms the core project + independent evidence at 7,357,534,208 bytes (~6.85 GiB), while the full local HES footprint including backup/staging copies is 30,596,861,952 bytes (~28.496 GiB). Root disk remains 12.5% free / WARN; no mutation occurred.

The storage manager now consumes the full-scope Restic restore evidence as a separate input. It correctly reports FULL_ARCHIVE_RESTORE_VERIFIED (32,927 files, 18/18 required paths) while keeping replacement-host restore NOT_PROVEN, remote restore NOT_RUN, and cleanup authorization false. The source Smart Cleanup recovery gate remains BLOCKED_NOT_PROVEN because its replacement-host/full-system recovery requirement is distinct from a same-host isolated archive restore. This prevents both under-reporting the successful archive drill and over-claiming bare-metal recovery.


## 18. Production Restic snapshot and scope-aware recovery — 2026-11-16

A local encrypted Restic repository was created at `/var/backups/hes-trade-agent/restic-production-v1/repo` using Restic 0.16.4. The full-scope snapshot is `26c6d6acad02bbc88b8408bf6a26f2633eeb9dd43e3227962e1ccfaa5a634a7b` (`hes-full-recovery-v1`, host `hes-vps-recovery-v1`) and contains all 40 required recovery roots, including active and rollback releases. The full snapshot's raw-data stats are 999.176 MiB uncompressed and 776.523 MiB stored; the repository currently occupies 815,136,818 bytes. `restic check --read-data` passed all 50 packs across three snapshots with no errors. A selective restore from the exact full snapshot ID passed `restic --verify` and 11 static content comparisons across 13 required roots.

**Important restore invariant:** do not use Restic's `latest` alias as a synonym for the latest full-system backup. The repository also contains two later evidence-only snapshots covering `/srv/hes-evidence` only. A naïve `restic restore latest` therefore restores only that partial scope. The retention planner was upgraded to v2 full-scope awareness: it requires all 40 registered roots, matches the actual production host/tag, exposes `latest_full_snapshot_id`, and keeps partial snapshots outside retention/deletion eligibility. A live planner run identified one full snapshot and two partial snapshots, selected the exact full ID above, and proposed zero deletions.

Evidence: `evidence/operations/hes_restic_production_snapshot_20261116.json` and `evidence/operations/hes_restic_scope_aware_retention_20261116.json`. The Restic repository remains local; this checkpoint does not claim that it was uploaded to Dropbox.

## 19. Dropbox offsite replacement — 2026-11-16

The previously approved stable Dropbox object `HES Trade Agent Backups/hes-offsite-latest.tar.zst.gpg` was replaced in place with the new expanded-scope AES-256 encrypted Zstandard archive. The new object is 1,369,944,609 bytes with SHA-256 `16a1c3ced6be0723dd80494eb4b7b2b8a02cbe661ca94430b13b3777b927da52`. Remote content-hash comparison, remote decryption/decompression, full tar listing, 33/33 recovery-root checks, active/rollback release presence, and all 3,744 independent evidence entries passed. SHA-256 and manifest sidecars were updated and verified. Dropbox now has 777,460,340 bytes free, above the 128 MiB reserve.

The older archive's local staging copy was retained. No local full archive was deleted, no local staging was pruned, and no production timer/service or trading configuration was changed. Evidence: `evidence/operations/hes_dropbox_offsite_replacement_20261116.json`.

## 14. Five decimal GB hard target and daily bounded maintenance — 2026-11-20

The user-set objective supersedes the prior 10 GiB planning target: complete local HES footprint must be below 5,000,000,000 allocated bytes (5 decimal GB). The scope includes the project checkout (releases/candidates/worktrees), independent evidence store and local backup/offsite staging roots; Ubuntu/SentinelX platform files are reported separately. This is a hard objective, not an assertion that the current system meets it.

The manager now defaults to `--target-gb 5`, counts all versioned encrypted gzip/Zstandard archives and Git bundles in the correct backup directories, and reports the local production Restic repository separately. 49 focused tests passed after the changes. It remains report-only for releases, candidates, worktrees, canonical data, evidence and backups.

A daily maintenance runner executes IDLM -> exact-snapshot dependency-aware Smart Cleanup -> Smart Storage report, then performs only bounded, regenerable maintenance: direct-child `/tmp/pip-*` temporary build directories older than 24 hours with no active pip/build process and no open file handle; `apt-get clean`; and journald vacuum under a 256 MiB / 30-day policy. Exact paths are revalidated and machine-readable cleanup evidence is emitted. It never deletes project code, models, worktrees, releases, trading data, evidence or backups. Systemd timer runs daily at 03:45 UTC.

Initial 2026-11-20 audit baseline: project checkout 13,583,405,056 bytes; evidence 436,072,448 bytes; local backup/staging 5,469,429,760 bytes; complete local HES footprint 19,488,907,264 bytes (~19.49 GB), 14,490,664,448 bytes over the new target. Full archive, remote and replacement-host restore remain NOT_PROVEN; therefore no backup pruning is authorized. Safe cleanup removed 77 old pip temporary directories (848,449,536 bytes), cleaned apt download cache, and capped journald at about 232.6 MiB. Active release/worktree/candidate compaction remains a separate gated engineering task requiring remote Git commit verification, clean/dirty state handling, active/rollback pointer inventory, manifest integrity and selective restore evidence.

## 15. Local and Dropbox remote restore evidence — 2026-11-20

The full 43-root local Restic snapshot `6518cb4854b9253a7b14730d60ab04d8db09881ff31742a37cc5cfc15ef14c68` passed `restic check --read-data` (205/205 packs, six snapshots, zero errors) and a full isolated same-host restore (65,047 files/directories, 9.089 GiB). The drill verified 12/12 required roots and hashes for four static host-configuration files, then removed the isolated restore tree. Evidence: `/srv/hes-evidence/operations/storage-lifecycle/2026-11-20T1323Z/full-restore-drill.json`.

The Dropbox compact core object `HES Trade Agent Backups/hes-recovery-core-latest.tar.zst.gpg` was copied back from Dropbox, hash/size matched its remote manifest (`f4702fff3275f828706e081c4f4b3e4dc937058b958bd54f8dbefa599e3d01ec`, 398,216,865 bytes), GPG decryption and Zstandard/tar path validation passed (8,897 members, zero unsafe paths), and full isolated extraction passed. Active release manifest verified 620/620 files; rollback release manifest verified 582/582 files; main Git object connectivity check passed. 7,562 files / 899,049,730 bytes were extracted and the test tree/download removed. Evidence: `/srv/hes-evidence/operations/storage-lifecycle/2026-11-20T1323Z/dropbox-core-remote-restore.json`.

The manager now accepts separate local full-restore and Dropbox remote-restore evidence and reports each independently. Both same-host and remote-core restore are PASS. Replacement-host boot/recovery is still NOT_PROVEN; therefore backup retention/pruning and destructive cleanup remain unauthorized. The daily maintenance runner automatically supplies the latest local and remote restore evidence to the report.

## Global physical accounting and safe compaction — 2026-11-23

The existing IDLM/Smart Cleanup/Smart Storage chain is the sole authority for HES local storage accounting. This is an extension of the current managers, not a parallel scanner.

### IDLM additions
- One global (st_dev, st_ino) set across the exact scan roots.
- logical_allocated_bytes: allocated blocks summed by path.
- unique_allocated_bytes: physical allocated blocks counted once per inode.
- shared_inode_path_bytes: path bytes whose inode was already counted in an earlier scan root.
- ownership_scope: HES_PROJECT, HES_EVIDENCE, HES_BACKUP, HES_TEMP, HES_RUNTIME, PLATFORM_TEMP, PLATFORM, UNCLASSIFIED_TEMP, or OTHER.
- scan_summary: global logical/unique/shared bytes, scan errors, missing roots, HES temp/runtime counts and bytes, unclassified temp count/bytes, and counting method.
- Directory metadata is included; symlinks are not followed. HES scopes are scanned before platform scopes so a shared inode is attributed to HES.

### Smart Cleanup additions
- Preserve the IDLM physical fields and ownership scope in each cleanup item.
- Fail closed on missing global scan summary, missing physical fields, inconsistent logical/unique/shared byte values, or scan errors.
- Unknown/unclassified temporary paths remain KEEP; no cleanup authority is added.

### Smart Storage acceptance
- Sum only unique physical bytes for immediate children of the canonical HES project/evidence/backup roots, plus HES temp/runtime scopes.
- Count unclassified temp conservatively and mark the scope incomplete.
- Report both physical and logical totals; expose shared-inode savings separately.
- complete_footprint_within_target is true only when the scan is complete, error-free, has no unclassified temp paths, and total unique physical HES allocation is below 5,000,000,000 bytes.
- No deletion, move, compression, release pruning, worktree removal, or backup retention change is authorized by a storage report.

### Preservation gates
- Release/worktree compaction requires clean state, preserved branch/commit provenance, no active/rollback/process/unit/job reference, and exact remote/recovery proof.
- Backup pruning requires successful remote recovery, replacement-host recovery, and external encryption-key escrow. Same-host extraction is not replacement-host proof.
- Raw market data, trade/decision journals, rejection evidence, model artifacts, secrets, Git history, user changes, and last known-good releases remain protected.

The 5 GB objective remains NOT MET until a fresh complete-scope report proves the target.
