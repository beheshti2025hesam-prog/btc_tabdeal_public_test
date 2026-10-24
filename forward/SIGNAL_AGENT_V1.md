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
- Risk approval requires explicit upstream PASS evidence for entry/stop/target geometry and the versioned risk/reward gate. The Signal Agent independently validates positive finite prices, directionally ordered entry/stop/target levels, and the existing 3:1 minimum reward-to-risk baseline; missing or invalid geometry fails closed.
- The risk evidence includes execution_disabled; the agent has no order-placement capability.
- The existing scope policy remains BTC_USDT / 15m. Other scopes fail closed until a versioned policy explicitly supports them.
- This is not a profitability or win-rate guarantee. The strategy must be validated with fresh forward observations and an immutable journal.

## Deliberately not claimed complete

The existing read-only dashboard entry point now calls SignalAgentV1 through `GET /api/signal?symbol=BTCUSDT&interval=15m` and renders the returned decision and block reasons. It reuses the same native OHLCV batch/cache and feature pipeline as the chart. The route currently returns BLOCKED / NO_TRADE because source-to-agent symbol mapping evidence, validated directional structure, strategy-level signal-quality provider, and provenance-bound entry/stop/target geometry are not wired. Feature-engine quality is reported descriptively and is never promoted to strategy-level quality. These missing inputs must be connected to existing validated providers or added through versioned, tested contracts; do not invent thresholds or map fields by resemblance. Production runtime/browser parity on the authorized VPS, PR #297 and #346 acceptance, and any live-execution gates remain open. Do not activate execution or deploy solely on unit tests.
