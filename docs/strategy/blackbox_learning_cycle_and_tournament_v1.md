# Blackbox Learning-Cycle Integration & Continuous Tournament V1

**Status:** implemented in the stacked development branch; shadow/research-only; not deployed to the active release.

## 1. Reuse the existing five-minute learning loop

The existing `hes-strategy-learning-loop.service` is the single integration point. Each successful cycle now:

1. Refreshes the existing decision, NO_TRADE and indicator-family learning projections.
2. Reads the canonical journals and appends compact source references to `blackbox_experience_memory_v1.jsonl`.
3. Discovers regime-conditioned motifs from the existing indicator shadow journal and appends immutable `DISCOVERED` events to `blackbox_hypothesis_events_v1.jsonl`.
4. Audits the existing Trend Breakout and Range Mean Reversion family journals.
5. Runs the paired OOS tournament only for hypotheses that have been explicitly preregistered and moved to `TESTING`.
6. Adds hashes and a fail-closed Blackbox status to the existing learning-loop report.

Memory and hypothesis writes use file locks, stable event identities and exact-replay suppression. A repeated cycle must not duplicate a source event. Full source rows remain in their canonical journals.

## 2. Evidence intake and eligibility

The continuous family audit snapshots the canonical family report and each journal SHA. It cross-checks family IDs, candidate linkage, event counts and outcome counts. It records rejected evidence with explicit reasons.

An outcome can enter the paired tournament only when all relevant evidence is present:

- Gate-approved candidate and resolved outcome linkage
- Verified, finite net-R and a matched baseline net-R for OOS
- Explicitly verified costs (not a fixed fee/slippage assumption)
- Complete source and run provenance
- Frozen preregistration and source-manifest hashes
- Explicit TRAIN/OOS role
- Independent, chronological, purged OOS evidence
- At least two OOS regimes
- Independently validated short economics for SHORT hypotheses

Existing family outcomes with `performance_eligible=false`, `costs_verified=false`, or no paired net-R are retained as research evidence but excluded from training and tournament statistics.

## 3. Continuous competition

Each learning cycle scans the family journals for event-level evidence carrying a hypothesis ID and the frozen evidence metadata. It aggregates paired TRAIN and OOS net-R arrays, then calls the existing exact paired sign-test evaluator with Holm correction per multiple-testing family.

- `DISCOVERED` is not automatically preregistered.
- Only `TESTING` hypotheses with complete evidence are evaluated.
- Statistically significant paired underperformance becomes `REJECTED`.
- Acceptance requires all data, cost, provenance, regime and statistical gates.
- Missing or weak evidence remains `INCONCLUSIVE`.
- A new evidence hash is required before an inconclusive hypothesis is re-opened.
- Status transitions are append-only and evidence-hashed.

The report is written to `blackbox_continuous_tournament_v1_report.json`. The one-shot entry point is `scripts/run_blackbox_tournament_cycle_v1.py`; the combined memory + tournament entry point is `scripts/run_blackbox_learning_cycle_v1.py`.

## 4. Current live-source findings (2026-11-18)

The active Gate.io strategy evaluator is producing paper outcomes, but the current sample is not admissible tournament evidence:

- 29 strategy outcomes exist; the inspected recent rows have `final_gate_decision=NO_TRADE` and `performance_eligible=false`.
- Their risk context explicitly labels fee/slippage assumptions as unverified.
- The independent 1m precision journal has 2 paper outcomes; both label the cost model `ASSUMPTION_BASED_NOT_VERIFIED`.
- Trend Breakout and Range Mean Reversion family journals have 15 and 14 outcomes respectively; both report zero performance-eligible resolved outcomes.
- No current family outcome contains a verified matched net-R baseline or independent purged OOS metadata.

Therefore the runtime correctly reports `WAITING_FOR_VERIFIED_FAMILY_EVIDENCE` and `WAITING_FOR_PREREGISTERED_INDEPENDENT_OOS_EVIDENCE`. It does not promote, rank, train, tune thresholds, issue signals, or execute orders.

## 5. Release boundary

This branch adds code and tests only. The production `/opt/hes-trade-agent` checkout is dirty and is not modified. The active immutable release and running services remain untouched. Deployment into the five-minute learning loop requires the normal release approval and exact-head CI/review gate. Until then, the current forward-paper observers continue collecting their existing research records; no claims of verified performance are made.
