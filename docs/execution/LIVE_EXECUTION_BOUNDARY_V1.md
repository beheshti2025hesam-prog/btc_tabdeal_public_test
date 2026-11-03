# Live Execution Boundary v1 — Contract

Status: **fail-closed preflight and durable idempotency journal implemented; live venue execution NOT enabled**.

## Purpose
This is the final authorization boundary before a reviewed venue adapter may submit an order. It reuses the existing Signal Agent/Risk Gate decision chain; it does not duplicate candles, indicators, strategy logic, or application UI.

## Required evidence
- Signal decision ID and versioned Signal Agent.
- SHA-256 of the exact market-data observation.
- Reviewed symbol-mapping evidence.
- Validated directional structure evidence.
- Versioned strategy-level quality evidence.
- Versioned risk policy and evidence.
- Time-bounded entry/stop/target/quantity; LONG/SHORT geometry and reward:risk floor.
- Account reconciliation evidence and deployment SHA.
- Fresh timezone-aware evidence; operator approval; venue health; explicitly enabled live mode; clear kill switch; reviewed venue adapter.
- Duplicate client-order IDs are rejected by the preflight gate.
- `forward/execution_journal_v1.py` provides a durable SQLite uniqueness/state journal. It rejects duplicate decision/client IDs and payload conflicts, and it will not let an UNKNOWN submission return to SUBMITTING until explicit reconciliation evidence is recorded.

## Safety properties
- Runtime defaults deny live execution.
- Missing, malformed, stale, future-dated, duplicated, or unknown evidence denies authorization.
- The gate only returns a permit; it does not place, cancel, or query orders.
- The journal records order intent/lifecycle metadata only; it does not call a venue, store credentials, or automatically retry ambiguous submissions.
- No live exchange adapter, credentials, dashboard order route, collector activation, or deployment is introduced here.
- Passing unit tests proves only these local contracts. It does not prove a real venue adapter, account state, order lifecycle, exchange filters, partial fills, fees, protective stops, or reconciliation.

## Promotion sequence (no skipping)
1. Accept the canonical data source and dashboard dependency chain (#297 → #346 → #362).
2. Select and document the execution venue; verify official API/order semantics and exact instrument mapping. Market-data source and execution venue remain separate.
3. Implement one venue adapter behind `ExecutionAdapterV1`, with no credentials in source, deterministic client IDs, precision/minimum filters, request signing, timeouts, bounded retries, and explicit handling of unknown submit outcomes.
4. Connect the adapter to the durable journal and implement venue-specific restart-safe order/position reconciliation. Never retry an ambiguous submit until venue order status is reconciled.
5. Test mocked success/failure, duplicate submissions, timeout-after-accept, partial fills, rejected orders, rate limits, precision, minimum notional, reduce-only/position mode, protective-stop acknowledgement, cancel/replace, and kill-switch behavior.
6. Verify read-only account/balance/position/open-order reconciliation from the approved environment; then paper/shadow observation and exact-SHA tests.
7. Separate owner approval is required to enable live mode. No automatic promotion from CI or from a green preflight test.

## Why this is not marked LIVE
Current Signal Agent integration intentionally lacks accepted symbol mapping, validated causal structure, strategy-level quality evidence, and provenance-bound production risk evidence. The canonical data/dashboard PRs are still Draft/HOLD, target-runtime parity and source access are unverified, and no approved execution venue adapter is present. The gate and journal make safety prerequisites explicit; they cannot manufacture the missing external evidence.

## Compatibility / anti-rework rule
Continue from the single existing path: NativeOHLCV source → feature pipeline → Signal Agent → Risk Gate → execution boundary → durable order journal → reviewed venue adapter. Do not add a second dashboard, candle schema, market-data adapter, or signal implementation.


## 2026-10-24 — canonical venue-adapter contract

The existing `ExecutionAdapterV1` interface has been moved to the dedicated
`forward/execution_adapter_contract_v1.py` contract module and made typed.
This is a contract refactor, not a concrete venue integration.

- One explicit request carries both `analysis_symbol` and `venue_symbol`,
  plus a required mapping-evidence reference. Symbols are never inferred or
  silently translated by the adapter.
- Requests carry an immutable decision/client-order identity and payload hash.
- Capability claims default to `UNVERIFIED`. Live readiness requires a pinned
  official API contract reference, evidence SHA-256, independent review revision,
  exact venue/product scope, client-order-ID support, proven idempotent-submit
  behavior, order/open-order/position/account reconciliation, cancellation,
  and native protective-order support.
- Normalized venue snapshots include order status (including partial fills),
  requested/executed quantities, average fill price, venue/client IDs, explicit
  market scope, timezone-aware observation time, and raw-response hash.
- Validation rejects identity/symbol/product mismatch, overfills, inconsistent
  partial/filled states, missing fill price, invalid timestamps, and missing
  provenance. An ambiguous submit remains `UNKNOWN`; the adapter contract
  explicitly prohibits automatic resubmission.
- Contract tests are included in the existing execution-gate workflow. No second
  execution interface or separate order path was added.

## Venue selection remains an external release blocker

The execution adapter contract is now defined and tested, but there is still no
venue-approved concrete implementation. The existing venue-selection decision
(#300) explicitly says no exchange is approved for leveraged/live execution.
Do not label a mock, local contract test, or unverified capability record as a
working exchange adapter. A concrete adapter can be implemented only after one
venue is selected from authoritative evidence and its current official order,
instrument, position-mode, idempotency, protective-order, rate-limit, and
reconciliation contracts are pinned and independently reviewed. Until then:
`HOLD / NO_TRADE_ONLY`; no credentials, private endpoints, VPS mutation, or
live orders.

- **Anti-self-authorization:** a capability object's own `verification_status`,
  evidence URL, digest, or review label is not a trust root. Readiness also
  requires separately supplied trusted `approved_evidence_sha256` and
  `approved_review_revision` pins; absent pins or mismatches always block.
  Those pins must come from reviewed deployment/project configuration, not
  from the adapter response itself.


## Durable order lifecycle follow-up

The SQLite journal now persists validated venue snapshots as well as intent/state:
venue status, executed quantity, average fill price, raw response SHA-256, and
UTC observation time. It accepts the tested lifecycle from submission through
partial fill to fill/cancel/expiry, makes an exact repeated terminal snapshot
idempotent, rejects conflicting terminal snapshots, and requires explicit
reconciliation evidence to resolve an UNKNOWN outcome. Existing journal tables
are migrated transactionally to the expanded schema while preserving prior
intent/state rows. This is still a local persistence contract; it does not prove
that any exchange actually implements the claimed behavior.

- Order quantity now carries an explicit unit (`BASE_ASSET`, `QUOTE_ASSET`, or
  `CONTRACTS`) and a required quantity-unit/instrument-rules evidence reference;
  no contract multiplier or unit conversion is guessed. The contract also
  defines typed balance and position snapshots and validates account/position
  scope, account/position mode, duplicate open-order IDs, timestamps, and raw
  evidence hashes.
