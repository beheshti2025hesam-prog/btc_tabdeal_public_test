# HES Indicator Strategy Family V1 — Research Integration Checkpoint

**Date:** 2026-11-17 UTC  
**Status:** IMPLEMENTED IN DEVELOPMENT CHECKOUT; HISTORICAL RESEARCH ONLY; TRAINING AND PRODUCTION PROMOTION BLOCKED.  
**Canonical data:** Gate.io Public Spot BTC_USDT.  
**Dataset:** locked 90-day 15m / 1h / 4h research sample.  
**Dataset manifest SHA-256:** `dcb978345a84cae88a06a422ee0c0df1ab79fe4787aba06d78eff29552100fb4`.

## 1. Scope and architecture

Added `indicator_strategy` as a separate research family using the existing `forward/universal_indicator_engine_v1.py`. The descriptive indicator engine remains separate from strategy rules; no indicator weights are interpreted as independent votes or predictive probabilities.

The family has three frozen V1 variants:

1. **trend_confirmation** — EMA 20/50/200 stack, ADX/DMI, RSI, MACD histogram, Supertrend and matching 1h/4h regime context.
2. **momentum_breakout** — closed 15m close beyond the prior-candle-excluded Donchian boundary, ADX, ROC, MACD and matching 1h/4h context.
3. **range_mean_reversion** — 15m RANGE regime, Bollinger %B extreme plus RSI extreme, and no strongly directional 1h/4h context.

Initial BTC timeframe roles are preserved: 15m setup authority; 1h/4h context. The 1m precision layer is not allowed to originate an indicator setup.

All variants use the same preregistered geometry for this screen: entry at the next 15m open, stop distance 1.5 × setup ATR(14), target 3R, maximum 96 subsequent 15m bars, conservative stop-first resolution when stop and target are touched in the same candle, and one open simulated position per variant. Cost sensitivity is 10/20/30/50 bps round-trip assumptions; these are not verified fees or slippage.

## 2. Historical replay results

Replay completed successfully. **401 candidate events** were recorded in append-only research ledgers.

| Variant | Candidate events | LONG resolved | LONG win rate at 20 bps | Expectancy at 20 bps | Profit factor at 20 bps |
|---|---:|---:|---:|---:|---:|
| Trend confirmation | 336 | 24 | 33.33% | -0.104318% | 0.725936 |
| Momentum breakout | 65 | 19 | 31.58% | -0.091536% | 0.785844 |
| Range mean reversion | 0 | 0 | N/A | N/A | N/A |

### Candidate and regime coverage

- Trend confirmation: 200 SHORT candidates are not economically testable from Spot candles; 136 LONG candidates yielded 24 resolved outcomes, 111 overlap-skipped and 1 pending.
- Momentum breakout: 31 SHORT candidates are not economically testable from Spot candles; 34 LONG candidates yielded 19 resolved outcomes and 15 overlap-skipped.
- Range mean reversion: no candidates were produced by the frozen RANGE/extreme-confluence predicates in this historical sample. No thresholds were loosened to manufacture trades.
- Candidate regime coverage was directional only: trend confirmation produced 200 BEARISH and 136 BULLISH events; momentum breakout produced 31 BEARISH and 34 BULLISH events. No RANGE events were produced.

### Cost sensitivity

**Trend confirmation**

| Round-trip assumption | Win rate | Expectancy/trade | Profit factor | Net compounded return |
|---|---:|---:|---:|---:|
| 10 bps | 33.33% | -0.004318% | 0.986246 | -0.166590% |
| 20 bps | 33.33% | -0.104318% | 0.725936 | -2.535463% |
| 30 bps | 33.33% | -0.204318% | 0.543220 | -4.850415% |
| 50 bps | 33.33% | -0.404318% | 0.303662 | -9.323234% |

**Momentum breakout**

| Round-trip assumption | Win rate | Expectancy/trade | Profit factor | Net compounded return |
|---|---:|---:|---:|---:|
| 10 bps | 31.58% | +0.008464% | 1.023576 | +0.093888% |
| 20 bps | 31.58% | -0.091536% | 0.785844 | -1.790849% |
| 30 bps | 31.58% | -0.191536% | 0.613720 | -3.641933% |
| 50 bps | 31.58% | -0.391536% | 0.381157 | -7.245399% |

**Interpretation:** neither tested variant meets the project's win-rate objective or demonstrates robust positive net expectancy. Momentum breakout is marginally positive only under the 10 bps assumption and is negative at 20 bps and above. No family is selected or promoted.

## 3. Journal and learning integration

- Added the append-only research decision ledger: `data/forward/indicator_strategy_shadow_journal_v1.jsonl` (401 records).
- Added the separate append-only outcome ledger: `data/forward/indicator_strategy_shadow_outcomes_v1.jsonl` (401 records).
- The existing `ForwardJournalV1` writer and its event-ID idempotency are reused.
- Historical simulation records are explicitly research-only and `performance_eligible=false`; they are not merged into or counted as production `trade_journal_v2.jsonl` decisions.
- Added `scripts/run_indicator_strategy_learning_v1.py` to link outcome records to family/variant/regime decisions, summarize research labels, and expose a training gate.
- Connected that bridge to the development-checkout `scripts/run_strategy_learning_loop_v1.py`; the parent learning report now carries an `indicator_strategy_learning` section.
- The learner distinguishes historical research outcomes from eligible forward paper labels. Current eligible forward paper labels: **0**. Status: `TRAINING_BLOCKED_NO_ELIGIBLE_FORWARD_PAPER_LABELS`. No supervised model was trained, no policy was mutated, and no threshold was tuned.

The existing project acceptance standard remains binding: no win-rate claim without at least 100 eligible resolved paper outcomes and the required independent chronological evidence; the >90% target is not relaxed.

## 4. Validation

- Indicator family unit tests, learning-bridge tests, universal indicator engine tests, existing strategy-learning tests and router tests: **46 passed**, warnings treated as errors.
- Python compilation: passed for the new family, replay runner, learning bridge and integrated learning-loop source.
- Historical replay: completed; report SHA-256 `fac1425e15911bcc5d9e3f85a114d3c92b48a6cdab627988b8404fcad79ad0d8`.
- Learning report SHA-256 `f3ec1378e2df60d2b2f2e880cf4745d9502bd2b98b1975e36f5da4c160af45de`.
- Family source SHA-256 `26c6896e1174e8be3f106b73e879b8d8120fbe64d5c640fb23f889813eaa61d9`.
- Replay runner SHA-256 `953111bfd33974c29eb5293a0349e7e417436d729058dd0aa50d8739f74d9704`.
- Learning bridge SHA-256 `97ec95c53dc27c9d9eea3cd7ac32fa34b06574539a8dcc78101e259475f3bf03`.
- Learning-loop integration source SHA-256 `b2a996cd5811f5a85eeb81883d816f47d288f7b597c3776962487bc89ef6066a`.

## 5. Safety and deployment boundary

- The historical research sample was previously inspected; it is not an untouched OOS holdout.
- Gate.io Spot cannot validate SHORT economics. SHORT candidates remain NOT_TESTABLE; no derivatives assumptions were invented.
- Cost assumptions are unverified and are not presented as actual execution costs.
- The new family is not added to the live strategy router and cannot authorize candidate generation, confirmation, risk, execution or orders.
- Existing main decision journal remains separate; no production journal records were rewritten.
- No strategy policy or threshold was changed; no live signal was enabled; no order was submitted.
- The active core release remains `f5d505567522555ee1be9c260e83085347515721`; the dashboard release currently resolves to `13b1432d367e4d88e55ee9babb0aa3580da4b849`.
- Paper evaluator, strategy-learning-loop and read-only dashboard services were active at inspection. No service was restarted and no production symlink was changed.
- Development checkout remains dirty with unrelated prior work; no reset, clean, broad commit or merge was performed.

## 6. Remaining gates

1. Add independent formula parity for the indicator functions that remain unverified before relying on them in any candidate.
2. Repeat the preregistered experiment on a fresh untouched chronological forward window with stable data hashes and cost evidence.
3. Obtain economically valid short-side data only from an explicitly validated derivatives instrument; Spot short paths stay unscored.
4. Collect enough eligible, matured forward paper outcomes before supervised strategy-selection training. Historical backtest labels must never satisfy this gate.
5. Review the family in the immutable-release/CI process before any dashboard or service integration. Production activation requires a separate explicit approval.

**Decision:** Indicator Strategy Family V1 is implemented in the development simulation path, writes linked append-only research decisions/outcomes, and is visible to the development learning-loop report. It is not trained, not production-routed, not promoted, and not executable.


## 7. Forward-only paper observer — next-stage implementation (2026-11-17)

A separate closed-candle forward observer has now been added in the development checkout:

- `scripts/run_indicator_strategy_forward_paper_v1.py`
- `deploy/systemd/hes-indicator-strategy-forward-paper.service` (deployment template only)
- `tests/strategy/test_indicator_strategy_forward_paper_v1.py`

The observer reuses the canonical Gate.io Public Spot BTC_USDT closed-candle reader and the universal indicator engine. It processes each newly closed 15m bar exactly once, derives the setup only from the preceding closed 15m candle, constrains 1h/4h context to candles closed no later than the signal close, and uses the next 15m candle open as the hypothetical entry. It records all three variant decisions, including explicit NO_TRADE observations, into a separate forward-paper journal and resolves positions with stop-first same-candle handling, gap-aware stop fills, 3R geometry and a 96-bar maximum hold.

The learning bridge now reads the forward-paper ledgers separately from historical replay and reports per-variant/per-regime forward-paper diagnostics. These labels remain research-only; they do not count toward production acceptance or the supervised-training gate.

**Baseline initialized:** current latest closed 15m candle cursor was recorded with `NO_RETROACTIVE_TRADES`; zero historical backfill, zero forward decisions, zero outcomes and zero open positions. The observer is waiting for the next newly closed 15m candle.

**Deployment boundary:** the systemd template passed syntax verification, but it has deliberately not been installed, enabled, or started. The active immutable release, dashboard symlink and existing paper-evaluator/learning services were not changed. The new observer must first enter a clean, immutable release through the normal GitHub/CI review path; the development checkout is dirty and cannot be treated as a deployable release.

Forward-paper safety remains strict: no orders, no execution authority, no risk-gate bypass, no threshold tuning, no model training, no strategy promotion. SHORT outcomes remain unscored economically from Spot data; 20 bps costs are assumptions, not verified execution costs.

Focused validation after this addition: **52 tests passed**, including the new forward observer and learning-bridge tests. The observer baseline was successfully initialized against the current Gate.io closed-candle feed.
