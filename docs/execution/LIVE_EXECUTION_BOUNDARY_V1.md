# Live Execution Boundary v1 — Contract

Status: **implemented as a fail-closed preflight contract; live venue execution NOT enabled**.

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
- Duplicate client-order IDs are rejected by preflight. The deterministic ID is intended to be enforced by a durable execution journal before any adapter call.

## Safety properties
- Runtime defaults deny live execution.
- Missing, malformed, stale, future-dated, duplicated, or unknown evidence denies authorization.
- The gate only returns a permit; it does not place, cancel, or query orders.
- No live exchange adapter, credentials, dashboard order route, collector activation, or deployment is introduced here.
- A positive unit test is only a contract test. It is not evidence that a real venue adapter, account state, order lifecycle, exchange filters, partial fills, fees, or reconciliation works.

## Promotion sequence (no skipping)
1. Accept the canonical data source and dashboard dependency chain (#297 → #346 → #362).
2. Select and document the execution venue; verify official API/order semantics and exact instrument mapping. Market-data source and execution venue remain separate.
3. Implement one venue adapter behind `ExecutionAdapterV1`, with no credentials in source, deterministic client IDs, precision/minimum filters, request signing, timeouts, bounded retries, and explicit handling of unknown submit outcomes.
4. Add a durable idempotency/order journal and restart-safe reconciliation. Never retry an ambiguous submit until venue order status is reconciled.
5. Test mocked success/failure, duplicate submissions, timeout-after-accept, partial fills, rejected orders, rate limits, precision, minimum notional, reduce-only/position mode, protective-stop acknowledgement, cancel/replace, and kill-switch behavior.
6. Verify read-only account/balance/position/open-order reconciliation from the approved environment; then paper/shadow observation and exact-SHA tests.
7. Separate owner approval is required to enable live mode. No automatic promotion from CI or from a green preflight test.

## Why this is not marked LIVE
Current Signal Agent integration intentionally lacks accepted symbol mapping, validated causal structure, strategy-level quality evidence, and provenance-bound production risk evidence. The canonical data/dashboard PRs are still Draft/HOLD, target-runtime parity and source access are unverified, and no approved execution venue adapter is present. The gate makes these prerequisites explicit; it cannot manufacture the missing external evidence.

## Compatibility / anti-rework rule
Continue from the single existing path: NativeOHLCV source → feature pipeline → Signal Agent → Risk Gate → execution boundary. Do not add a second dashboard, candle schema, market-data adapter, or signal implementation.
