# HES Intelligent Data Lifecycle Manager (IDLM) v1

**Status:** Accepted architecture; Phase A read-only audit implementation proposed for review.  
**Principle:** prevent uncontrolled storage growth without sacrificing evidence, replayability, learning, audit, security, or recovery.

## 1. Purpose and scope

IDLM is a permanent Universal Core capability, not a one-off cleanup script. It inventories storage, classifies data, applies versioned retention policy, identifies archive and cleanup candidates, monitors disk/inode pressure, and records auditable outcomes.

The first implementation is deliberately read-only. It does not delete, move, truncate, compress, rotate, or change service configuration.

## 2. Components

- **Data Inventory & Classification:** path/service owner, purpose, source, sensitivity, dependencies, reproducibility, allocated size, age, and retention class.
- **Retention Policy Engine:** versioned KEEP / ARCHIVE / REVIEW / DELETE eligibility. Unknown means KEEP.
- **Storage Optimizer:** compression and proven deduplication only; preserve hashes, schema, timestamps, and lineage.
- **Cleanup Executor:** dry-run manifest, reason codes, locks, bounded batches, quarantine/atomic operations, fail-closed behavior, and kill switch.
- **Disk & Inode Guard:** free bytes, inode availability, growth rate, per-service budgets, and time-to-capacity forecast.
- **Audit & Recovery:** append-only action records, checksums, archive manifests, tested restore procedures, and rollback references.

Reuse the existing HES operational/runtime health checks, journald/logrotate, backup, and recovery controls. Do not create duplicate monitors or parallel implementations.

## 3. Data protection and retention classes

### KEEP — protected

- Trade journals, outcomes, rejected-signal records, NO_TRADE decisions, and counterfactual evaluation evidence.
- Canonical market candles and raw market/trade payloads.
- Source identity, endpoint/channel, connection/session epochs, receive and venue timestamps, schema fingerprints, registry revisions, and source hashes.
- Model/policy/config versions, code/run hashes, provenance, decision attribution, reproducibility fixtures.
- Security/audit records, recovery manifests, backup evidence, current and rollback release pointers.
- Dirty/untracked files, registered Git worktrees, active runtime data, and all unknown or dependency-unverified items.

### ARCHIVE — only after proof

Immutable cold data may be archived only after retention review, dependency analysis, checksum/manifest verification, and a tested restore path. Archive must preserve original hashes, schema, timestamps, source identity, and lineage.

### REVIEW — not deletion permission

Stale temporary workspaces, same-day additional backup snapshots, caches, old build/test artifacts, and logs are review candidates. A same-day additional snapshot is not necessarily content-identical to another backup. Age, filename, size, cache naming, or lack of recent reads alone never authorizes deletion.

### DELETE — gated

Deletion is allowed only for explicitly allowlisted regenerable/disposable data after retention expiry, clean dependency/process/reference scans, verified recovery where required, dry-run manifest approval, bounded execution, and audit recording.

## 4. Exchange sequence and raw-event protection

A field named `sequence`, `seq`, `id`, or `tradeId` has no generic meaning. Semantics belong to the exact venue/product/endpoint/channel/message-type/protocol version.

For Tabdeal FAPI/Margin, current reviewed public evidence does not establish `trade.sequence` as unique identity, ordering, contiguity, or a gap detector. Do not deduplicate or delete events based on this opaque field. Preserve full raw payload and source/session/timestamp/hash/registry lineage. Exact-payload replay handling is distinct from event-ID deduplication. Only adapter capabilities supported by pinned evidence may authorize those operations.

## 5. Safety invariants

1. No deletion based only on age, filename, size, last access, or a repeated sequence-like value.
2. Never mutate canonical market data, journals, evidence, model state, or active runtime files in place.
3. Dry-run is the rollout default; uncertainty means KEEP.
4. Verify checksums and restore paths before source deletion.
5. Never remove active/rollback releases, registered worktrees, dirty/untracked project files, running-service data, or backups without proven dependencies and recovery coverage.
6. Keep an append-only audit trail with policy version, actor, timestamp, target, hashes, action, result, and recovery reference.
7. Maintain disk and inode reserves; alert and apply backpressure before exhaustion.
8. No trading/execution authority is granted to IDLM.

## 6. Phase A audit tool

`scripts/ops/hes_data_lifecycle_audit_v1.py` inventories configured filesystem roots and emits a JSON manifest. It:
- reports allocated bytes, file counts, scan errors, age, disk and inode availability;
- classifies protected data, unknown data, caches, logs, temporary workspaces, and backup candidates;
- reads the repository's `git worktree list --porcelain` registry and protects exact registered worktree paths;
- fails closed for temporary paths if the Git worktree registry cannot be verified;
- identifies additional full backup snapshots when multiple encrypted snapshots exist for the same UTC day; it does not establish byte-level/content identity or verify backup sidecar checksums;
- never follows symlinks;
- always emits `automatic_action: NONE`.

Example:

```bash
python3 scripts/ops/hes_data_lifecycle_audit_v1.py \
  --output /var/tmp/hes-idlm-audit.json
```

Choose an output location outside the scanned roots. The report is a review artifact, not a deletion authorization. The script intentionally has no destructive CLI flag or deletion implementation.

## 7. Roadmap and acceptance gates

- **A — Read-only discovery:** inventory filesystem, active writers/readers, data classes, backup schedule, retention mechanisms, disk/inode use, and growth baseline.
- **B — Policy mapping:** assign owner, retention class, replay/audit value, dependencies, and restore requirements to every discovered class.
- **C — Dry-run implementation:** candidate manifest, reason codes, disk/inode forecast, audit output, and deterministic tests. No production deletion.
- **D — Safety validation:** unknown files, symlinks/path traversal, concurrent writers, open descriptors, interrupted archives, checksum mismatch, disk-full/inode exhaustion, stale manifests, rollback, and restore tests.
- **E — Canary:** only allowlisted regenerable cache/temp data, low batch limits, monitoring, and immediate kill switch.
- **F — Production acceptance:** exact-SHA tests, independent review, verified backup/restore, measured disk reduction, zero protected-data loss, clean audit, and soak.

## 8. Current status

- Architecture accepted: 2026-11-08.
- Phase A scanner implementation is read-only and intended for review.
- Existing VPS inventory and findings are recorded separately in `docs/checkpoints/IDLM_READ_ONLY_DISCOVERY_2026-11-08.md`.
- No production cleanup, retention-setting change, service restart, or live trading action is part of this phase.


## 9. Existing health monitor capacity extension — proposed in PR #485

The existing HES health monitor is extended in-place; no duplicate monitor or new systemd service is introduced.

- Runtime health adds inode availability using `statvfs`: at least 10% free = OK, 5–10% = WARN, below 5% = CRITICAL. Probe failure or invalid metrics fail closed as CRITICAL.
- The existing five-minute operational monitor samples disk capacity at most once per hour and stores a compact EWMA state at `/var/lib/hes-operational-health/capacity-trend-v1.json`.
- The trend state is a single atomic, mode-0600 JSON record, not an unbounded history. It requires six hourly samples before issuing a forecast; a gap longer than 48 hours or filesystem-size change resets the baseline.
- Estimated time-to-full below 72 hours = WARN; below 24 hours = CRITICAL. A corrupt state or backward clock produces WARN and preserves the existing state rather than overwriting it.
- The first five hours report insufficient history as OK; the forecast becomes meaningful only after samples accumulate. Existing free-space checks remain authoritative and immediate.
- The operational monitor already owns `StateDirectory=hes-operational-health` and `ReadWritePaths=/var/lib/hes-operational-health`; the new state file fits that existing sandbox boundary.
- This code is in the isolated PR only. It has not been deployed to the VPS or activated by systemd.


## 10. Encrypted staging artifacts

The scanner explicitly inventories `/var/backups/hes-trade-agent/dropbox-staging` and classifies its contents as `KEEP_BACKUP_STAGING`. A local staging artifact is not an offsite copy. Keep the archive and sidecar until its encryption-key provenance, integrity, restore path, and successful remote upload are independently verified. Do not infer offsite status from a filename containing `offsite`.


## 11. Dry-run local backup retention planner

The read-only scanner now mirrors the current local backup policy without executing it:

- Daily window: keep all snapshots younger than 7 UTC date-days.
- Weekly anchor: keep Sunday snapshots younger than 28 date-days.
- Monthly anchor: keep first-of-month snapshots younger than 180 date-days.
- Future-dated or unparseable backup names fail closed as KEEP.
- Expired items are marked `REVIEW_RETENTION_EXPIRED`, with `retention_action=NONE`.
- The report records whether the SHA-256 sidecar exists, but does not claim that the sidecar was verified.
- Full-restore/offsite status is explicitly `NOT_CHECKED_BY_SCANNER`; `deletion_authorized=false` always.

This planner is a simulation of the existing policy, not an approval to prune. Same-day extra snapshots remain separate review candidates and are not assumed content-identical.


## 12. Evidence-store protection

The scanner includes `/srv/hes-evidence` as an explicit root and classifies all descendants as `KEEP_EVIDENCE`. This store contains provenance/evidence records and must not be treated as temporary data, a cache, or a generic archive. Unknown files inside it remain protected regardless of age.


## 13. Phase A inventory depth limitation

Phase A emits one record per direct child of each configured scan root and computes recursive allocated-size/file-count rollups for directories. It does not emit one manifest row per file inside every protected tree. This keeps the first audit bounded and avoids exposing unnecessary internal filenames from protected stores. A later targeted deep-inventory pass may inspect only allowlisted REVIEW candidates; KEEP_EVIDENCE, KEEP_BACKUP, registered worktrees, and other protected roots remain summarized and untouched.


## 14. Narrow temporary-cache quarantine candidate — isolated PR

The first production scanner remains read-only. A separate isolated candidate reuses its policy boundaries and adds a reversible quarantine planner; it does not change the VPS or the active release.

**Owner-approved development scope (2026-11-10):**
- Only directory names __pycache__ and .pytest_cache.
- Only below /tmp and /var/tmp; no other roots, cache families, logs, workspaces, backups, releases, evidence, journals, or project files.
- Minimum age is 14 days for the directory and every entry inside it. A recent child blocks the whole candidate.
- The Git worktree registry must be readable. Any registered worktree ancestor/descendant relationship excludes the candidate.
- Any symlink, mount/device boundary, hard-linked regular file, special file, mixed UID/GID ownership, setuid/setgid bit, unreadable scan, open descriptor, process cwd/root/executable reference, or memory mapping blocks the whole candidate.
- File contents are SHA-256 hashed. Directory and file metadata are revalidated across scans (including ctime); the manifest records exact path, device/inode, size, nanosecond mtime, owner/group, and a deterministic tree digest.
- Conservative bounds: at most 5,000 filesystem entries per candidate, 100 discovered candidates per scan, 128 MiB per candidate, 10 actionable candidates, and 512 MiB per batch.

**Execution boundary:**
- Normal invocation only emits a new, exclusive, mode-0600 dry-run manifest (existing output is never overwritten); automatic_action=NONE, execution_enabled=false, and deletion_authorized=false.
- The isolated candidate has no recursive-delete or purge operation. Quarantine is a reversible isolation/canary stage and does not reclaim disk space. Any later purge implementation requires a separate retention/hold policy and explicit owner authorization. An explicit quarantine invocation requires root, the exact SHA-256 of the saved manifest, and the typed phrase QUARANTINE HES TEMP CACHES.
- Before each same-filesystem atomic rename, it performs a fresh inventory, re-hashes the tree, rechecks process references, pins source/destination parent directories with no-follow directory descriptors, and verifies source inode identity before and after rename. Any mismatch aborts.
- Items move into a mode-0700 .hes-idlm-quarantine-v1 directory under the same temp root. An append-only mode-0600 audit records intent and completion through a pinned no-follow audit-directory descriptor and is fsynced. Restore can recover safely if the process stops after rename but before the completion record is appended, using the audited intent plus exact tree and inode identity. Quarantine is reversible through the audited restore command; restore refuses to overwrite an existing path.
- No cleanup command has been run. No cache has been moved or deleted. This candidate is not merged, deployed, or enabled on the VPS. The user approved development of this narrow policy, not production execution or release deployment.
- Production acceptance still requires adversarial tests, exact-head CI, code review, a separate deployment gate, and an explicit owner decision before any canary. Keep the current production scanner read-only until then.
