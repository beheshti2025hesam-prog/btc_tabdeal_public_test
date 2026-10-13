# Architectural Blocker: Authoritative Probe and Exit Producers

**Recorded:** 2026-10-13  
**Inspected branch:** `integration/controlled-lineage-gate-20261013`  
**Inspected head before this record:** `7cdaebad5cd5b17f3d1d4dcaaf166321de66b1a6`  
**Disposition:** `BLOCKED — NO VERIFIED PRODUCTION PROBE/EXIT PRODUCER FOUND`

## Scope inspected

The repository tree and relevant contracts on the inspected head were reviewed, including:

- `core/execution/contract.py`
- `core/paper/session.py`
- `forward/controlled_forward_observation_runner_v1.py`
- `forward/forward_observation_path_v1.py`
- `tests/test_controlled_lineage_boundary_v1.py`
- `tests/test_lineage_id_propagation_v1.py`
- `tests/test_forward_observation_path_v1.py`
- PR #271's isolated Session → Execution → Probe → Exit validator contract and PR #274's controlled observation lineage changes.

## Findings

1. The controlled observation runner creates and propagates `session_id` and `run_id` through transport and observation consumer paths. This is transport/observation lineage, not proof of actual Probe and authoritative Exit event production.
2. `core/execution/contract.py` explicitly describes a future execution port; it defines a Protocol and data contracts, not a concrete venue execution implementation or authoritative execution event producer.
3. `core/paper/session.py` emits `PaperEvent` state-transition records from paper-validation observations. These records are simulation/paper events, contain no `session_id`, `run_id`, Probe parent linkage, or authoritative Exit identity, and must not be relabeled as production Probe/Exit events.
4. The four-event lineage validator in PR #271 is a validation contract/test slice. It does not itself produce the underlying events.
5. The reviewed paths and repository tree did not identify a production Probe producer or authoritative Exit producer that supplies source-generated IDs and explicit parent-event links. This is a bounded repository inspection finding, not a claim that no such component could exist outside this repository or on an uninspected revision.

## Required next step

Keep the full Session → Execution → Probe → Exit chain **unproven** until an actual producer and its event schema are identified. The owning implementation must define source-generated event IDs, parent-event links, and propagation of the same lifecycle IDs. Then add end-to-end tests using those real producer interfaces, including missing/mismatched IDs and broken-parent failures.

Do not fabricate events, derive linkage by timestamp proximity, or adapt paper events as authoritative evidence. Do not weaken the fail-closed gates, pin evidence, activate the collector, deploy, or enable trading because of this record.

## Verification status

This file records the architectural finding only. Its own commit SHA, exact diff, and CI status must be checked independently after commit. No new code behavior or successful end-to-end producer integration is claimed.
