# HES Trade Agent — Master Checkpoint
**Date:** 2026-10-26  
**Rule:** Memory = project map/context; GitHub = technical truth; Chat = conversation log.

## Current decision
- **Delivery target:** 2026-11-19.
- **Risk checkpoint:** 2026-10-26.
- **Release:** **HOLD / NO_TRADE_ONLY**. No live trading, merge, or deployment is authorized by this checkpoint.
- **Infrastructure:** exactly **one VPS**; current live state must be verified rather than inferred.
- **Canonical repository:** `beheshti2025hesam-prog/btc_tabdeal_public_test`.
- **Latest dated prior checkpoint:** [2026-10-25 progress and run audit](MASTER_CHECKPOINT_2026-10-25_PROGRESS_AND_RUN_AUDIT.md).
- **Release criteria and schedule:** [Release Readiness & Delivery Control](../RELEASE_READINESS.md).

## Locked decisions — do not rediscover without new evidence
1. One unified, validated global market-data source feeds charts/candles and analysis through the same batch/provenance.
2. Exchange adapter is for order execution and order status only. Do not revisit chart candle sequence or exchange-volume reconciliation unless new evidence shows an execution-relevant issue.
3. Reuse the existing dashboard candidate `web/dashboard.py`; do not build a parallel frontend.
4. Gate.io is the interim operational global-feed candidate in the current repo record. Binance access was previously reported unavailable; do not reopen absent new evidence.
5. Missing, stale, gapped, malformed, mismatched, or unapproved evidence fails closed. Risk context and execution symbol mapping are separate approvals.
6. One VPS only; no invented second machine.

## Evidence status at 2026-10-26
- The prior checkpoint records 414/414 tests and short feed sampling as **reported historical evidence**, not freshly rerun in this checkpoint.
- Current exact VPS SHA, dirty-tree state, service health, and runtime-to-remote lineage are **not reverified** in this checkpoint.
- The independently audited 24-hour data-only soak and disconnect/reconnect/restart fault evidence are **not established as passed**.
- Production frontend identity/deployment path and actual runtime end-to-end canonical data → analysis → risk integration remain **unproven**.
- Risk context and execution symbol/instrument mapping remain unapproved/unknown in the available record.
- The open PR list includes multiple Draft/HOLD candidates with dependencies and overlap. Do not merge an isolated PR before reconciling its ancestry and exact-head checks.
- No profitability or live-trading readiness claim is supported by the above.

## Release blockers, in priority order
1. Reconcile PR dependency/overlap chain; define one non-duplicated release-candidate lineage.
2. Verify sole VPS/device access, actual SHA, worktree state, services and allowed execution/deployment environment.
3. Run relevant CI/tests on the exact proposed SHA; preserve run URLs, artifacts and hashes.
4. Complete independently audited 24-hour read-only soak and reconnect/restart fault injection.
5. Prove real frontend/runtime path uses the same validated market-data batch for chart and analysis.
6. Approve risk context and execution symbol/instrument mapping independently; until then NO_TRADE and execution OFF.
7. Finish operational/security review, rollback plan, independent review and final go/no-go.

## Schedule control
- **2026-10-26:** risk checkpoint; identify and assign every blocker, with no gate waivers.
- **2026-10-27–11-02:** exact lineage, exact-head validation, read-only soak and frontend identification.
- **2026-11-03–11-09:** resilience, same-batch integration, risk/mapping evidence, operational review.
- **2026-11-10–11-15:** final candidate, non-overlapping PR stack, release docs and independent review.
- **2026-11-16–11-18:** scope freeze and exact-final-SHA go/no-go.
- **2026-11-19:** deliver only the verified scope; software delivery does not authorize trading.

## Anti-duplication protocol
Before any implementation: search repository + open PRs + tests + workflows + checkpoints. Prefer reuse or targeted optimization of existing code. Record a new component only when a proven gap exists. Never turn a report, skipped workflow, candidate PR, or local-only state into a verified pass. Do not tune strategy thresholds to satisfy a release gate.

## Last action / provenance
This checkpoint and the release-control document are documentation-only candidates on branch `docs/release-readiness-checkpoint-2026-10-26`, based on prior checkpoint PR #377 head `adbcb775fa69e0d772c5a52d34509c506a0be1e1`. They do not modify application code, runtime, VPS, services, or trading behavior. Review and required CI are still needed before merge.
