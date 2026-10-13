# Architectural Blocker: Authoritative Probe and Exit Producers

**Recorded:** 2026-10-13  
**Inspected branch:** `integration/controlled-lineage-gate-20261013`  
**Inspection base:** `7cdaebad5cd5b17f3d1d4dcaaf166321de66b1a6`  
**Blocker-record commit:** `9f57f54bee7f80c8f000eea36bd59206ecca92b9`  
**Disposition:** `BLOCKED — NO VERIFIED PRODUCTION PROBE/EXIT PRODUCER FOUND`

## Scope inspected

Repository tree and relevant code/contracts were reviewed on the controlled-lineage branch:

- `core/execution/contract.py`, `core/execution/order_state.py`
- `core/paper/session.py`, `core/models/trade.py`, `core/strategy/baseline.py`
- `forward/signal_engine_v1.py`, `forward/opportunity_detector_v1.py`, `forward/decision_engine_v1.py`
- `forward/forward_run_controller_v1.py`, `forward/decision_journal_adapter_v1.py`, `forward/forward_journal_v1.py`, `forward/forward_writer_v1.py`
- `forward/controlled_forward_observation_runner_v1.py`, `forward/forward_observation_path_v1.py`
- `tests/test_controlled_lineage_boundary_v1.py`, `tests/test_lineage_id_propagation_v1.py`, `tests/test_forward_observation_path_v1.py`
- PR #271's isolated Session → Execution → Probe → Exit validator contract; PR #274's controlled observation lineage changes; related audit findings in PRs #260, #263 and #264.

## Findings

1. The controlled observation runner creates and propagates `session_id` and `run_id` through transport and observation consumer paths. This is transport/observation lineage, not proof of actual Probe and authoritative Exit event production.
2. `core/execution/contract.py` explicitly describes a future execution port; it defines a Protocol and data contracts, not a concrete venue execution implementation or authoritative execution event producer.
3. `core/execution/order_state.py` is an execution-free state machine. It models transitions but does not submit orders or emit identity-linked venue events.
4. `core/paper/session.py` emits `PaperEvent` state-transition records from paper-validation observations. These are simulation/paper events and contain no `session_id`, `run_id`, Probe parent linkage, or authoritative Exit identity. They must not be relabeled as production events.
5. `forward/signal_engine_v1.py`, `forward/opportunity_detector_v1.py`, and `forward/decision_engine_v1.py` are signal/candidate/decision layers, not execution or Probe/Exit event producers. The opportunity detector fails closed without a policy.
6. `forward/forward_writer_v1.py` writes decision records and separate outcome artifacts. An outcome artifact or inferred matching exit price is not an authoritative exit event with source-generated identity and explicit parent linkage.
7. PR #271 explicitly states its four-event lineage validator is not integrated with production producers. PR #274 explicitly retains the same gap. PR #260/#263/#264 also record inferred exit association and unresolved session/run/probe lineage; none supplies an authoritative event producer.
8. The repository tree and the second-pass code review did not identify a production Probe producer or authoritative Exit producer that supplies source-generated event IDs, explicit parent-event links, and consistent lifecycle IDs. This is a bounded finding for the inspected repository revision, not a claim about components outside this repository.

## Verification of the blocker-record commit

For commit `9f57f54bee7f80c8f000eea36bd59206ecca92b9`:

- The GitHub commit diff was read back and confirmed as a documentation-only addition of 37 lines.
- GitHub Actions check-runs were refreshed: **28/28 completed successfully**, 0 queued, 0 in progress, 0 failures at the time of inspection.
- This CI result validates the tested repository workflows on that exact commit; it does not establish producer existence or close the architectural blocker.

## Required next step

Keep the full Session → Execution → Probe → Exit chain **unproven** until an actual producer and its event schema are identified. The owning implementation must define source-generated event IDs, parent-event links, and propagation of the same lifecycle IDs. Then add end-to-end tests using those real producer interfaces, including missing/mismatched IDs and broken-parent failures.

Do not fabricate events, derive linkage by timestamp proximity, treat paper events or outcome artifacts as authoritative exits, or adapt inferred price matches as event identity. Do not weaken fail-closed gates, pin evidence, activate the collector, deploy, or enable trading because of this record.

## Safety boundary

No new runtime code behavior or successful end-to-end producer integration is claimed. Keep PR #274 Draft and project status HOLD until real producer integration, exact-head CI, independent review, and the remaining evidence gates are satisfied.
