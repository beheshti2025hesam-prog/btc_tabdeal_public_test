# HES Strategy-Family Runtime Evidence & Research Dispatch — Design

**Date:** 2026-11-08  
**Base:** `f5d505567522555ee1be9c260e83085347515721`  
**Scope:** Gate.io-only BTC_USDT family evidence and 15m family dispatch; research/paper only.

## Intent

Connect the existing Trend and Range family contracts to the current forward decision pipeline. The system must choose the family from validated 15m regime evidence, apply that family's independent confirmation rules, and retain the shared Risk Gate as an unbypassable veto. This work must not rebuild or fork the live market-data feed.

## What exists today (verified on the sole VPS)

- The active immutable release is `f5d505567522555ee1be9c260e83085347515721` (manifest created 2026-11-07 19:46 UTC).
- `global_market_data_reader_v1` already reads the persisted Gate.io Spot BTC_USDT closed-candle files for 15m, 1h and 4h; the 1m feed is separate and downstream.
- `native_ohlcv_gateio_v1` already validates Gate.io Spot candle semantics. Gate.io candle evidence has base/quote volume but no trade-count or taker-buy flow; those fields must remain `None`.
- `StrategyEvidenceProviderV1` already implements provenance-bound 15m/4h evidence, including MFI14, Wilder ADX14/+DI/-DI, EMA50/EMA200 and structure/order-block data. It is currently not called by the active forward evaluator/pipeline.
- `strategy_family_router_v1` already routes UPTREND/DOWNTREND to Trend and RANGE to research-only Range. `strategy_family_context_v1` already provides a digest-bound, authority-false envelope.
- `strategy_gate_pipeline_v1` currently attaches family route/context as diagnostic metadata but still sends every regime through the shared directional `OpportunityDetector` and three-check `ConfirmationPolicy`. A RANGE route therefore has no independent candidate/confirmation dispatch.
- The dirty root checkout contains two unmerged Range prototypes. The first research slice will use only the sweep/reclaim prototype (`range_opportunity_policy_v1`) as the single Range v1 candidate policy. The Bollinger-band prototype remains an isolated research alternative and is not combined with v1.
- PR #480 contains independent family confirmation/evaluation contracts, but no production family evidence builder, Range candidate dispatch, or raw family outcome cohort integration.

## Goals

1. Consume only the already persisted `global_market_data_reader_v1` frames; no new REST/WebSocket fetch path.
2. Normalize those exact Gate.io rows into the existing `NativeOHLCVBatch` contract with source-bound hashes, correct millisecond boundaries, no fabricated trade-flow fields, and fail-closed validation.
3. Reuse `StrategyEvidenceProviderV1`, its MFI14/ADX14 calculations, existing EMA feature engine, and the existing Range sweep/reclaim policy rather than duplicating them.
4. Build Range evidence causally from closed 15m/1h/4h candles. Boundaries exclude the setup candle; persistence is measured on a disjoint recent window.
5. Dispatch Trend and Range through separate family confirmation contracts. Trend behavior must remain output-equivalent to the current shared three-check path.
6. For Range, return only `RESEARCH_CONFIRMED_LONG/SHORT`; the shared Risk Gate must continue to reject those states. Overall final decision remains `NO_TRADE`, with execution flags false.
7. Persist family candidate, family confirmation and source evidence inside the existing immutable decision journal record. Do not create a parallel journal or service.

## Non-goals

- No live order placement, execution adapter change, deployment, service restart, or release-pointer movement.
- No change to the global Risk Gate, 3R minimum, leverage, position sizing, or account risk controls.
- No new VPS, market-data source, network client, database, or journal format.
- No 1m-originated setup. 1m remains downstream precision-entry refinement only.
- No claim that >90% win rate or three daily opportunities have been achieved. The >90% threshold remains an evidence-based acceptance gate requiring >=100 resolved outcomes per family plus independent OOS evidence and verified costs.
- This slice does not claim raw family outcome resolution complete; it creates the source-bound candidate/confirmation records needed for the next append-only cohort integration.

## Approaches considered

1. **Fetch fresh Gate.io candles inside the family provider.** Rejected: it would create a second source path and could diverge from the dashboard/reader's persisted candle set.
2. **Normalize existing persisted Gate.io rows and reuse the existing native evidence provider.** Chosen: one canonical feed, one source-bound evidence envelope, existing calculations reused, minimal adapter glue.
3. **Replace the current Signal Agent or OpportunityDetector with a generalized multi-family engine.** Rejected for this slice: it risks changing Trend behavior and blurs the global Risk Gate boundary. Dispatch will be additive at the existing pipeline boundary.

## Builder decisions

- Canonical scope remains `gateio_public_spot` / `BTC_USDT` / 15m setup; 1h and 4h are context only.
- Gate.io rows map to `venue=gateio`, `product=spot`, `symbol=BTCUSDT`, `endpoint_kind=global_market_data_reader_v1`; `trade_count`, `taker_buy_volume`, and `taker_buy_quote_volume` remain unavailable (`None`). The batch digest is over the exact persisted row set and is labelled as such, not misrepresented as a raw HTTP response hash. `fetched_at_ms` is the time this adapter reads the persisted file; each row's original `observed_at` remains inside the hash and is validated separately. This avoids treating a 1h/4h candle's original write time as a new fetch time.
- Range persistence v1: use the prior 36 closed 15m bars to calculate high/low boundaries; evaluate the 12 immediately preceding bars for close-within-boundary persistence; exclude the current setup candle from both windows. At least 70% of those 12 closes must remain inside.
- All timeframe calculations are filtered to `as_of_ms = 15m setup candle close boundary`; native candle close timestamps are inclusive milliseconds, so the final millisecond before that boundary is eligible. Higher-timeframe rows observed after the setup are not eligible unless their source observation is within a 60-second ingestion allowance. This prevents historical/future 1h/4h candle leakage.
- EMA50 slope v1: change over the latest 3 completed EMA50 points, divided by the same timeframe's ATR14 simple mean of the latest 14 true ranges. Use the existing EMA calculator and existing volatility calculator; document the ATR formula and test it with hand-derived values.
- ADX14 on 15m/1h/4h reuses the existing Wilder `adx14` helper. MFI14 reversal uses the existing base-volume MFI series. It is not taker-buy/order-flow evidence.
- Range's cost-adjusted geometry may use the existing explicitly labelled simulation assumptions to score a research candidate; this is not verified fee/slippage evidence and cannot satisfy family promotion. The family acceptance contract still requires independently verified fee/slippage evidence.
- The existing Range research threshold is not an exception to the global 3R Risk Gate. Range confirmation remains research-only and the shared Risk Gate remains the final veto.
- The daily three-entry ceiling remains enforced at the existing downstream precision-entry layer and aggregated across families by the existing family acceptance contract. This slice does not create a second cap or a second journal.

## Safety invariants

`execution_enabled=false`; `orders_placed=false`; no live execution; no Risk Gate changes; no 3R changes; no synthetic Gate.io trade-flow fields; no cross-family outcome pooling; no strategy activation from a passing family report.

## Verification focus

- Exact source/symbol/timeframe and closed-candle validation; future/stale/gapped/malformed rows fail closed.
- Evidence hashes bind exact persisted row windows; no current-candle lookahead in range boundaries/persistence.
- Range requires every one of its eight checks to pass; UNKNOWN/FAIL/missing evidence cannot confirm.
- Trend output remains unchanged; Range research confirmation is rejected by the shared Risk Gate; final decision stays NO_TRADE.
- Existing append-only journal retains no-future-outcome invariant and paper-only flags.
