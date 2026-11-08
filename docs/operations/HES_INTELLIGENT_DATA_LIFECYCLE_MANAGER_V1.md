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
- Dirty/untracked files, worktrees, active runtime data, and all unknown or dependency-unverified items.

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
5. Never remove active/rollback releases, worktrees, dirty/untracked project files, running-service data, or backups without proven dependencies and recovery coverage.
6. Keep an append-only audit trail with policy version, actor, timestamp, target, hashes, action, result, and recovery reference.
7. Maintain disk and inode reserves; alert and apply backpressure before exhaustion.
8. No trading/execution authority is granted to IDLM.

## 6. Phase A audit tool

`scripts/ops/hes_data_lifecycle_audit_v1.py` inventories configured filesystem roots and emits a JSON manifest. It:
- reports allocated bytes, file counts, scan errors, age, disk and inode availability;
- classifies protected data, unknown data, caches, logs, temporary workspaces, and backup candidates;
- identifies additional full backup snapshots when multiple encrypted snapshots exist for the same UTC day; it does not establish byte-level/content identity or verify the backup sidecar checksum;
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
