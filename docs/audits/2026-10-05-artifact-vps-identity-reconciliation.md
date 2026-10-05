# Artifact ↔ VPS Identity Reconciliation — 2026-10-05

## Scope

Read-only forensic reconciliation of the HES Trade Agent raw-data lineage.

**Hard rule:** no observation was deleted or modified, and no Collector process/service was started, stopped, restarted, disabled, enabled, or otherwise changed during this audit.

## Frozen references

| Item | Identity |
|---|---|
| VPS repository HEAD at audit | `f396de84cb7f4c6b16e81effc91b653e26049ab4` |
| Current GitHub `main` | `1e4803d569886b3c7bc3f68873b203c6e1f59852` |
| VPS HEAD → main | main is +1 commit |
| Difference between VPS HEAD and main | only `.github/workflows/run.yml` |
| Raw artifact | `data/trades.csv` |
| Artifact/VPS records | 110,566 |
| Artifact/VPS SHA-256 | `c5dbd78fe8aade258c28f1254f0a399051ab32d3b026e246ff36285dd020de87` |
| Artifact file size | 8,342,334 bytes |
| First sequence | 39619958276 |
| Last sequence | 40373844351 |

The one-commit difference between the VPS checkout and current `main` is workflow-only; it does not modify `data/trades.csv`.

## Identity reconciliation

The Git artifact extracted from commit `f396de84cb7f4c6b16e81effc91b653e26049ab4` and the live VPS `data/trades.csv` have identical:

- row count;
- byte size;
- SHA-256;
- first observed sequence;
- last observed sequence.

Therefore:

**Artifact ↔ VPS = exact byte-level identity.**

## Sequence intersection

Across the current VPS lineage:

- 14 archive segments + 1 active segment;
- total rows across all segments: 860,566;
- unique sequence values: 860,566;
- global duplicate sequence count: 0;
- inter-segment sequence intersection: 0;
- per-segment internal duplicate count: 0.

No record is classified as missing merely because a numeric sequence gap exists. Sequence values are treated as identifiers for the observed stream, not as a guarantee of contiguous integer succession.

## Archive lineage

Archive rotation is implemented as a transaction-like state machine:

1. create collision-safe archive name;
2. write archive and replacement active file to temporary files;
3. flush + fsync both;
4. persist a transaction marker containing old/new/archive SHA-256 identities;
5. atomically replace the archive;
6. recover deterministically after interruption.

The audit found no archive overwrite collision, duplicate sequence, or overlap between adjacent archive segments.

## Single-writer proof

At audit time:

- Collector systemd unit: inactive/dead;
- Collector process: none found;
- no process held an open FD on `data/trades.csv`;
- no matching cron entry found;
- no matching systemd timer found;
- GitHub scheduled Collector execution is paused on current `main`.

Therefore the **current-state writer count is 0**.

Important distinction: this is not a claim that historical writer count was always 0. Historical single-writer proof requires event/run lineage and scheduler/service logs. This audit deliberately does not infer history from the current process table.

## Safety finding retained without mutation

`hes-trade-agent-collector.service` is currently **enabled but inactive/dead**.

This was not changed because changing it would alter Collector state. It remains an explicit operational finding for a later controlled infrastructure checkpoint.

## Protocol for future reconciliations

To prevent repeated ad-hoc audits, future raw-data checkpoints should use this fixed order:

1. **Reference identity** — commit, blob SHA, file SHA-256, byte size.
2. **Artifact ↔ VPS exact comparison** — hash + byte + row count.
3. **Sequence intersection** — within-file and cross-segment duplicates.
4. **Missing/extra calculation** — only against a declared reference population.
5. **Archive lineage** — segment ordering, boundaries, hashes, transaction markers.
6. **Writer proof** — systemd, timers/cron, processes, file descriptors, workflow schedules.
7. **Historical writer attribution** — only from run/service/event logs.
8. **Freeze the resulting checkpoint** before any research/evidence analysis.

No tuning, threshold changes, winner filtering, record deletion, or Collector mutation belongs inside this protocol.

## Closure

**Identity Reconciliation: PASS**

**Sequence Intersection: PASS**

**Missing/Extra: PASS for the reconciled population**

**Archive Lineage: PASS**

**Current Single-Writer State: PASS (0 active writers)**

**Historical Single-Writer Attribution: OPEN — requires event/run lineage evidence**

This document is an audit record, not a data transformation.
