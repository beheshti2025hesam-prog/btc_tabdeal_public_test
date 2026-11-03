# HES Trade Agent — Execution Adapter Boundary Checkpoint

Date: 2026-10-30
Base: PR #398 exact Gate.io dashboard/Signal Agent candidate
Status: CONTRACT READY / VENUE ADAPTERS NOT APPROVED / LIVE EXECUTION OFF

## Reused implementation

This candidate carries forward the reviewed, venue-neutral execution boundary from PR #366 without rebuilding it:

- Typed `ExecutionAdapterV1` protocol for submit/query/cancel/open-orders/positions/account reconciliation.
- Immutable normalized order intent and venue snapshots with symbol mapping, quantity unit, protective geometry, and raw-response provenance.
- Capability validation that requires an exact venue + market type, official contract reference, source SHA-256, independent review revision, and externally pinned evidence/review values.
- Fail-closed preflight gate: fresh evidence, valid LONG/SHORT geometry, risk/reward floor, kill switch, live-mode switch, venue health, account reconciliation, operator approval, and deployment identity.
- Durable SQLite idempotency/lifecycle journal: ambiguous submit becomes UNKNOWN and cannot be retried until read-only reconciliation; conflicting venue IDs and regressive fill quantities are rejected.

## Venue adapter status

No concrete authenticated exchange adapter is approved or enabled. The generic contract is reusable across venues, but a venue-specific adapter requires:
- Explicit venue and product selection.
- Official symbol/instrument filters (tick size, step size, min/max quantity, notional, contract multiplier and settlement).
- Proven client-order-ID idempotency and timeout/ambiguous-submit recovery.
- Authenticated order query, cancel, open-order, position and account reconciliation.
- Native protective order semantics and reduce-only behavior.
- Exact source hashes, independent review revision, paper soak, and explicit owner approval.

The current Gate.io public Spot market-data feed is not an execution authorization. The data source and execution venue are separate decisions. Tabdeal's prior public symbol mapping does not prove its full order filters or authenticated lifecycle. No venue is guessed.

## Safety and release order

- No credentials, private account requests, order submission, or live execution.
- Execution remains OFF; the dashboard remains read-only.
- This contract is stacked on PR #398 so it cannot ship ahead of the canonical Gate.io/Signal Agent base.
- Concrete adapters and live mode remain blocked until an approved venue passes the above evidence gates.
