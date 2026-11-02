# HES Signal Agent v1 — implementation boundary

Status: **implemented as a deterministic, read-only composition layer; candidate release is not production-approved**.

## Canonical path

Gate.io Public Spot BTC_USDT persisted closed candles → existing global market-data reader → the same validated immutable batch for chart and Signal Agent → existing feature pipeline and StrategyEvidenceProviderV1 → StrategyPolicyV1 → existing opportunity policy → confirmation policy → risk gate → disagreement resolver / Mother Orchestrator → canonical forward journal.

The approved active scope is **Gate.io Spot / BTCUSDT / 15m**, with 4h context. The existing Gate.io reader supports persisted 15m, 1h, and 4h closed candles. The Signal Agent and chart reuse the same batch/cache and expose the same input-batch SHA-256. There is no second candle source, chart engine, frontend, collector, execution adapter, or journal.

Binance-specific OHLCV parser and WebSocket modules remain venue-specific transport/parity fixtures only. They are not the canonical HES analysis source and are rejected by the default Signal Agent scope.

## Safety contract

- Decisions are forward-only and use evidence timestamped no later than the observation.
- Evidence must be timezone-aware, have a non-empty provenance reference, and use PASS/FAIL/UNKNOWN states.
- Direction must be explicitly established upstream: UPTREND + BULLISH structure for LONG; DOWNTREND + BEARISH structure for SHORT. BOS/CHOCH without direction is insufficient.
- `signal_quality_gate_passed` is derived internally from `StrategyPolicyV1`, not accepted as a caller assertion. Six named evidence groups are required: HTF trend alignment, pullback location, reversal/break confirmation, MFI confirmation, ADX confirmation, and 3:1 risk geometry. At least 5/6 must pass; HTF alignment, pullback location, confirmed break, ADX/DI directional strength, and risk geometry are mandatory. MFI is the only optional vote.
- Existing candidate, confirmation, and risk policies remain independent; unknown/missing/failed evidence means NO_TRADE.
- The risk policy must approve; a signal cannot override a veto.
- Risk approval requires explicit upstream PASS evidence for entry/stop/target geometry and the versioned risk/reward gate. The Signal Agent independently validates positive finite prices, directionally ordered entry/stop/target levels, and the existing 3:1 minimum reward-to-risk baseline; missing or invalid geometry fails closed.
- The risk evidence includes `execution_disabled`; the agent has no order-placement capability.
- Default Signal Agent scope is Gate.io Spot BTCUSDT / 15m. Venue, product, symbol, and timeframe form one explicit scope tuple; other scopes fail closed unless separately reviewed and explicitly configured.
- This is not a profitability or win-rate guarantee. Strategy quality must be evaluated with forward observations and the immutable canonical journal.

## Journal integration

- The candidate `GET /api/signal` route evaluates the same Gate.io 15m/4h persisted batches used by the chart and appends one immutable decision through the existing `ForwardJournalV1`.
- It writes to the existing `/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl`, the same journal consumed by the existing paper evaluator and active `scripts/run_strategy_learning_loop_v1.py`.
- Event identity is bound to the 15m and 4h source-response hashes and policy version. Repeated polling for the same evidence is idempotent (`ALREADY_RECORDED`); conflicting duplicates fail closed.
- Signal decision rows keep `outcome=null` and `closed_at=null`. The journal projection is read-only and does not infer outcomes. Paper outcomes remain separate records in the existing journal.
- The systemd candidate sets the canonical journal path explicitly and grants file-level write exceptions only for the journal and its pre-created lock file. The release tree and remaining data directory stay read-only.

## Strategy Policy v1 — forward evidence quorum

- Policy ID: `hes-strategy-policy-v1`; required checks and minimum quorum are versioned in `forward/strategy_policy_v1.py`.
- `StrategyEvidenceProviderV1` computes evidence from canonical Gate.io closed OHLCV: 4h close + EMA50/EMA200 alignment; 15m pullback/retest against EMA50 or a confirmed swing level; confirmed-swing break evidence; MFI14; ADX14/+DI/-DI; and stop placement at the last opposite confirmed swing with a 3R target. It reuses existing EMA and swing calculators. MFI14 and ADX14 have deterministic implementations and regression tests.
- Every check requires PASS/FAIL/UNKNOWN, a provider and version, an evidence reference, a 64-character SHA-256, and a timezone-aware observation timestamp no later than the decision observation.
- All six checks must be present and measurable. UNKNOWN, missing evidence, duplicate checks, invalid hashes, future timestamps, or incomplete scope produce UNKNOWN and NO_TRADE.
- A PASS requires at least five of six measured checks to pass, with `htf_trend_alignment`, `pullback_location`, `reversal_break_confirmation`, `adx_directional_strength`, and `risk_geometry_3_to_1` all PASS. `mfi_confirmation` is the only optional vote.
- The current profile is `gateio / spot / BTCUSDT / 15m`. Spot and Futures are never silently aliased.
- Gate.io's persisted candle contract provides base and quote volume. Trade count, taker-buy base volume, and taker-buy quote volume are unavailable in this source and must remain null/UNKNOWN; no Binance or other venue flow fields may be copied or fabricated. MFI uses documented base volume; unavailable flow-dependent features remain unavailable. If source data is stale, gapped, insufficient, or mis-scoped, evidence is UNKNOWN and NO_TRADE.

## Explicit strategy calculation contract

- HTF alignment: the 4h close and EMA50 must be above EMA200 for bullish alignment, or below EMA200 for bearish alignment.
- MFI: MFI14 > 50 for bullish confirmation or confirmed bullish divergence (price lower swing low, MFI higher low); MFI14 < 50 for bearish confirmation or confirmed bearish divergence (price higher swing high, MFI lower high).
- Directional strength: ADX14 >= 20 and +DI > -DI for bullish, or ADX14 >= 20 and -DI > +DI for bearish.
- Pullback: closed 15m candle touches/reclaims the existing VWAP snapshot or EMA50, or retests a confirmed swing level in the directional context.
- Break confirmation: the latest closed 15m close crosses a confirmed swing high/low; this is one measured gate, not a substitute for directional structure.
- Geometry: stop at the last opposite confirmed swing; target at 3R. Missing/wrong-side swing means geometry UNKNOWN and NO_TRADE.
- Quorum is at least 5/6 measured checks, with geometry always mandatory. UNKNOWN evidence blocks; it is never treated as a failed vote or a pass.
- The risk context gate remains UNKNOWN until independent risk-budget/account/venue constraints are supplied. This prevents a strategy result from becoming an executable order.

## Order Block context v1

- Reuses the same validated closed Gate.io Spot 15m batch; no second candle source or candle schema.
- Finds the last opposing candle before a confirmed swing break, defines its zone, and scores seven binary context factors: confirmed BOS/CHOCH, liquidity sweep, fair-value gap, freshness/unmitigated state, higher-timeframe alignment, volume expansion, and EMA/VWAP/support-resistance confluence.
- Output is a raw `0..7` contextual score with zone and source-response SHA-256. It is explicitly `CONTEXT_ONLY`; `score_threshold_authorized=false`. No score threshold is used to promote or reject a trade until separately pre-registered and reviewed.
- Missing break, direction, stale/gapped data, or invalid source evidence does not create a tradable order. Tests cover zone, factor scoring, freshness/mitigation, hash validation, and fail-closed behavior.

## Conservative strategy review — 2026-10-24

- Review finding: the earlier generic 5/6 quorum allowed one of the core price-action/strength gates (pullback, break, or ADX/DI) to fail while still passing.
- Change: keep the 5/6 baseline but make five setup gates non-negotiable: HTF trend alignment, pullback location, confirmed break, ADX/DI directional strength, and valid 3R geometry. MFI threshold/divergence is the only optional vote. Unknown evidence still blocks.
- This is a conservative hypothesis, not evidence of higher win rate. No historical/backtest dataset or net-of-fees outcome report proves improved profitability. Compare policies on the same immutable data with chronological walk-forward splits, fees, spread/slippage, funding where applicable, and no lookahead.

## Current release disposition — 2026-10-30

- Exact candidate head: `a8f3c5dbfcb3f6942a86b1e31e2a38678e79f0a8`.
- Exact-head suite: 643 passed, 24 subtests; dashboard single-path, browser render, and bounded WebSocket smoke workflows passed.
- Isolated replay proved Gate.io chart/Signal same-batch identity, immutable journal append, duplicate-poll idempotency, and journal projection integrity. The active Learning Loop reader parsed the same isolated journal event.
- The production dashboard is still on the earlier release and does not yet expose `/api/journal`. Production installation/restart has not occurred. Independent PR review, parent-branch reconciliation, independent risk approval, and execution instrument mapping remain open.
- Keep `DRAFT / HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY`. No merge, production deployment, or live execution is authorized by this candidate.
