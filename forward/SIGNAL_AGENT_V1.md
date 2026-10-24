# HES Signal Agent v1 — implementation boundary

Status: **implemented as a deterministic, read-only composition layer; not production-approved**.

## Canonical path

Validated native OHLCV batch (PR #297 canonical contract) → existing feature pipeline + StrategyEvidenceProviderV1 → StrategyPolicyV1 → existing opportunity policy → confirmation policy → risk gate → decision resolver → forward journal.

The agent composes existing policy components and reuses the canonical candle schema, existing EMA calculator, and existing confirmed-swing calculator. MFI14 and ADX14 are implemented in the strategy provider because no implementation existed in this repository. No second candle schema, chart path, execution adapter, or data collector is created.

## Safety contract

- Decisions are forward-only and use evidence timestamped no later than the observation.
- Evidence must be timezone-aware, have a non-empty provenance reference, and use PASS/FAIL/UNKNOWN states.
- Direction must be explicitly established upstream: UPTREND + BULLISH structure for LONG; DOWNTREND + BEARISH structure for SHORT. BOS/CHOCH without direction is insufficient.
- `signal_quality_gate_passed` is derived internally from `StrategyPolicyV1`, not accepted as a caller assertion. Six named evidence groups are required: HTF trend alignment, pullback location, reversal/break confirmation, MFI confirmation, ADX directional strength, and 3:1 risk geometry. At least 5/6 must pass; the risk-geometry check is mandatory regardless of quorum.
- Existing candidate, confirmation, and risk policies remain independent; unknown/missing/failed evidence means NO_TRADE.
- The risk policy must approve; a signal cannot override a veto.
- Risk approval requires explicit upstream PASS evidence for entry/stop/target geometry and the versioned risk/reward gate. The Signal Agent independently validates positive finite prices, directionally ordered entry/stop/target levels, and the existing 3:1 minimum reward-to-risk baseline; missing or invalid geometry fails closed.
- The risk evidence includes execution_disabled; the agent has no order-placement capability.
- The active configured analysis profile is Binance Spot BTCUSDT / 15m. Venue, product, symbol, and timeframe form one explicit scope tuple; other scopes fail closed until separately configured. The former BTC_USDT spelling was inconsistent with the Binance Spot dashboard and is no longer the active profile.
- This is not a profitability or win-rate guarantee. The strategy must be validated with fresh forward observations and an immutable journal.

## Deliberately not claimed complete

The existing read-only dashboard entry point now calls SignalAgentV1 through `GET /api/signal?symbol=BTCUSDT&interval=15m` and renders the returned decision and block reasons. It reuses the same native OHLCV batch/cache and feature pipeline as the chart. The route now fetches closed Binance Spot BTCUSDT 15m and 4h candles from the same canonical source, derives directional structure and strategy checks, and displays quality/quorum diagnostics. Strategy quality may pass only when the versioned evidence policy passes; the final decision remains NO_TRADE while the independent risk-context gate is UNKNOWN and execution-symbol mapping is not approved. The read-only route does not access accounts or place orders. Production runtime/browser parity on the authorized VPS, parent PR #297/#346 acceptance, and live-execution gates remain open. Do not activate execution or deploy solely on unit tests.


## Strategy Policy v1 — forward evidence quorum

- Policy ID: `hes-strategy-policy-v1`; required checks and minimum quorum are versioned in `forward/strategy_policy_v1.py`.
- `StrategyEvidenceProviderV1` computes evidence from canonical closed OHLCV: 4h close + EMA50/EMA200 alignment; 15m pullback/retest against EMA50 or a confirmed swing level; confirmed-swing break evidence; MFI14; ADX14/+DI/-DI; and stop placement at the last opposite confirmed swing with a 3R target. It reuses the existing EMA and swing calculators. MFI14 and ADX14 were absent from the repository and have deterministic implementations plus regression tests.
- Every check requires PASS/FAIL/UNKNOWN, a provider and version, an evidence reference, a 64-character SHA-256, and a timezone-aware observation timestamp no later than the decision observation.
- All six checks must be present and measurable. UNKNOWN, missing evidence, duplicate checks, invalid hashes, future timestamps, or incomplete scope produce UNKNOWN and NO_TRADE.
- A PASS requires at least five of six measured checks to pass, with `risk_geometry_3_to_1` always PASS. The Signal Agent separately verifies actual numeric geometry and the minimum 3:1 ratio.
- The selected current profile is `binance / spot / BTCUSDT / 15m`. This fixes the former `BTC_USDT` versus `BTCUSDT` mismatch between the candidate policy and dashboard data path. Spot and Futures are never silently aliased.
- Binance Spot's official Kline contract distinguishes base-asset volume (`v`) from quote-asset volume (`q`); volume semantics approval is scoped only to this Binance Spot path, not Wallex or other venues: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#klinecandlestick-streams-for-utc. The strategy provider is wired into the existing dashboard; if source data is stale, gapped, insufficient, or mis-scoped, evidence is UNKNOWN and NO_TRADE.


## Explicit strategy calculation contract

- HTF alignment: the 4h close and EMA50 must be above EMA200 for bullish alignment, or below EMA200 for bearish alignment.
- MFI: MFI14 > 50 for bullish confirmation and < 50 for bearish confirmation.
- Directional strength: ADX14 >= 20 and +DI > -DI for bullish, or ADX14 >= 20 and -DI > +DI for bearish.
- Pullback: closed 15m candle touches/reclaims EMA50 or retests a confirmed swing level in the directional context.
- Break confirmation: the latest closed 15m close crosses a confirmed swing high/low; this is one of six measured gates, not a substitute for directional structure.
- Geometry: stop at the last opposite confirmed swing; target at 3R. Missing/wrong-side swing means geometry UNKNOWN and NO_TRADE.
- Quorum is at least 5/6 measured checks, with geometry always mandatory. Any UNKNOWN check makes overall strategy quality UNKNOWN; the policy never treats missing evidence as a failed vote.
- The risk context gate remains UNKNOWN until independent risk-budget/account/venue constraints are supplied. This deliberately prevents the strategy result from becoming an executable order.


## Order Block context v1

- Reuses the same validated closed Binance Spot 15m native-candle batch; no second candle source or candle schema.
- Finds the last opposing candle before a confirmed swing break, defines its zone, and scores seven binary context factors: confirmed BOS/CHOCH, liquidity sweep, fair-value gap, freshness/unmitigated state, higher-timeframe alignment, volume expansion, and EMA/swing-level confluence.
- Output is a raw `0..7` contextual score with zone and source-response SHA-256. It is explicitly `CONTEXT_ONLY`; `score_threshold_authorized=false`. No score threshold is used to promote or reject a trade until separately pre-registered and reviewed.
- Missing break, direction, stale/gapped data, or invalid source evidence does not create a tradable order block. Tests cover zone, factor scoring, freshness/mitigation, hash validation, and fail-closed behavior.
