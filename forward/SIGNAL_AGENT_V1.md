# HES Signal Agent v1 — implementation boundary

Status: **implemented as a deterministic, read-only composition layer; not production-approved**.

## Canonical path

Validated native OHLCV batch (PR #297 canonical contract) → existing feature pipeline → upstream structure/quality evidence → opportunity policy → confirmation policy → risk gate → decision resolver → forward journal.

This module composes existing policy components. It does not create a second candle schema, chart path, indicator implementation, execution adapter, or data collector.

## Safety contract

- Decisions are forward-only and use evidence timestamped no later than the observation.
- Evidence must be timezone-aware, have a non-empty provenance reference, and use PASS/FAIL/UNKNOWN states.
- Direction must be explicitly established upstream: UPTREND + BULLISH structure for LONG; DOWNTREND + BEARISH structure for SHORT. BOS/CHOCH without direction is insufficient.
- `signal_quality_gate_passed` is derived internally from `StrategyPolicyV1`, not accepted as a caller assertion. Six named evidence groups are required: HTF trend alignment, pullback location, reversal/break confirmation, MFI confirmation, ADX directional strength, and 3:1 risk geometry. At least 5/6 must pass; the risk-geometry check is mandatory regardless of quorum.
- Existing candidate, confirmation, and risk policies remain independent; unknown/missing/failed evidence means NO_TRADE.
- The risk policy must approve; a signal cannot override a veto.
- Risk approval requires explicit upstream PASS evidence for entry/stop/target geometry and the versioned risk/reward gate. The Signal Agent independently validates positive finite prices, directionally ordered entry/stop/target levels, and the existing 3:1 minimum reward-to-risk baseline; missing or invalid geometry fails closed.
- The risk evidence includes execution_disabled; the agent has no order-placement capability.
- The existing scope policy remains BTC_USDT / 15m. Other scopes fail closed until a versioned policy explicitly supports them.
- This is not a profitability or win-rate guarantee. The strategy must be validated with fresh forward observations and an immutable journal.

## Deliberately not claimed complete

The existing read-only dashboard entry point now calls SignalAgentV1 through `GET /api/signal?symbol=BTCUSDT&interval=15m` and renders the returned decision and block reasons. It reuses the same native OHLCV batch/cache and feature pipeline as the chart. The route currently returns BLOCKED / NO_TRADE because source-to-agent symbol mapping evidence, validated directional structure, strategy-level signal-quality provider, and provenance-bound entry/stop/target geometry are not wired. Feature-engine quality is reported descriptively and is never promoted to strategy-level quality. These missing inputs must be connected to existing validated providers or added through versioned, tested contracts; do not invent thresholds or map fields by resemblance. Production runtime/browser parity on the authorized VPS, PR #297 and #346 acceptance, and any live-execution gates remain open. Do not activate execution or deploy solely on unit tests.


## Strategy Policy v1 — forward evidence quorum

- Policy ID: `hes-strategy-policy-v1`; required checks and minimum quorum are versioned in `forward/strategy_policy_v1.py`.
- The policy validates externally supplied evidence only. It does not fabricate EMA200/EMA50, VWAP/pullback, MFI14, ADX/+DI, structure direction, or entry/stop/target values.
- Every check requires PASS/FAIL/UNKNOWN, a provider and version, an evidence reference, a 64-character SHA-256, and a timezone-aware observation timestamp no later than the decision observation.
- All six checks must be present and measurable. UNKNOWN, missing evidence, duplicate checks, invalid hashes, future timestamps, or incomplete scope produce UNKNOWN and NO_TRADE.
- A PASS requires at least five of six measured checks to pass, with `risk_geometry_3_to_1` always PASS. The Signal Agent separately verifies actual numeric geometry and the minimum 3:1 ratio.
- The selected current profile is `binance / spot / BTCUSDT / 15m`. This fixes the former `BTC_USDT` versus `BTCUSDT` mismatch between the candidate policy and dashboard data path. Spot and Futures are never silently aliased.
- The dashboard currently passes no real strategy-evidence provider; its strategy quality remains UNKNOWN and decision remains NO_TRADE. Unit tests with synthetic evidence validate policy mechanics only, not live market evidence or performance.
