# HES Signal Agent v1 — implementation boundary

Status: **implemented as a deterministic, read-only composition layer; not production-approved**.

## Canonical path

Validated native OHLCV batch (PR #297 canonical contract) → existing feature pipeline → upstream structure/quality evidence → opportunity policy → confirmation policy → risk gate → decision resolver → forward journal.

This module composes existing policy components. It does not create a second candle schema, chart path, indicator implementation, execution adapter, or data collector.

## Safety contract

- Decisions are forward-only and use evidence timestamped no later than the observation.
- Evidence must be timezone-aware, have a non-empty provenance reference, and use PASS/FAIL/UNKNOWN states.
- Direction must be explicitly established upstream: UPTREND + BULLISH structure for LONG; DOWNTREND + BEARISH structure for SHORT. BOS/CHOCH without direction is insufficient.
- A separate upstream signal_quality_gate_passed confirmation is mandatory. This module does not invent its threshold or calculate it.
- Existing candidate, confirmation, and risk policies remain independent; unknown/missing/failed evidence means NO_TRADE.
- The risk policy must approve; a signal cannot override a veto.
- Risk approval requires explicit upstream PASS evidence for entry/stop/target geometry and the versioned risk/reward gate. The Signal Agent does not invent a numeric RR threshold or calculate geometry without validated price inputs.
- The risk evidence includes execution_disabled; the agent has no order-placement capability.
- The existing scope policy remains BTC_USDT / 15m. Other scopes fail closed until a versioned policy explicitly supports them.
- This is not a profitability or win-rate guarantee. The strategy must be validated with fresh forward observations and an immutable journal.

## Deliberately not claimed complete

The component-level Signal Agent contract and negative/positive tests are implemented, but production signal readiness still depends on verified runtime wiring, a validated upstream quality/structure provider, an upstream provider that proves entry/stop/target geometry and the configured RR rule (rather than merely asserting labels), and the application's real frontend/runtime entry point. Do not activate live execution or merge this into production solely on the basis of unit tests.
