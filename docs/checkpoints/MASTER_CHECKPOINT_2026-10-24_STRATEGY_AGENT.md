# HES Strategy Agent — Master Checkpoint — 2026-10-24

## Fixed project controls
- Product delivery target: **2026-11-19**.
- Risk checkpoint: **2026-10-26**.
- Safety state: **HOLD / NO_TRADE_ONLY**; live execution OFF.
- Architecture: one canonical analysis source, one existing feature path, existing Signal/Confirmation/Risk/Decision layers, exchange adapters for execution only. Do not create a parallel chart, candle schema, indicator engine, or UI.

## Strategy-policy work on the existing Signal Agent path
- Added `forward/strategy_policy_v1.py` (`hes-strategy-policy-v1`) and `forward/test_strategy_policy_v1.py`.
- Six required evidence groups: HTF trend alignment, pullback location, reversal/break confirmation, MFI confirmation, ADX directional strength, and 3:1 risk geometry.
- Quorum: at least 5 of 6 measured checks must PASS. The 3:1 risk-geometry check is mandatory regardless of the total. The Signal Agent separately validates actual numeric entry/stop/target ordering and the 3:1 ratio.
- Every evidence check must include PASS/FAIL/UNKNOWN, a reference, a SHA-256 digest, provider/version, and a timezone-aware timestamp not later than the decision observation. Missing, duplicate, UNKNOWN, malformed, hash-invalid, or future evidence cannot produce a quality PASS.
- Signal Agent now computes `signal_quality_gate_passed` from StrategyPolicyV1; caller-supplied quality assertions are rejected. Existing Opportunity, Confirmation, Risk, and Decision components are reused.
- Fixed a proven scope defect: the opportunity policy expected `BTC_USDT` while the existing canonical chart/dashboard sends `BTCUSDT`. The configured analysis profile is now explicitly `binance / spot / BTCUSDT / 15m`; venue/product/symbol/timeframe are not silently aliased. Other scopes fail closed.
- The existing read-only dashboard surfaces the policy state, quorum count, version, and evidence digest from the same canonical native OHLCV batch and Signal Agent path.

## What this does and does not prove
- Synthetic unit tests validate policy mechanics, quorum rules, provenance fields, timestamps, scope, and negative/fail-closed behavior.
- No verified live strategy evidence provider currently supplies all six checks. The dashboard therefore remains UNKNOWN/BLOCKED and NO_TRADE. No EMA/MFI/ADX values, structure direction, entry geometry, or profitability are fabricated.
- This work does not claim strategy performance, calibrated probabilities, profitable signals, production acceptance, or live-trading readiness.
- No merge, deployment, VPS mutation, collector activation, credential use, or order submission is authorized by this checkpoint.

## Exact verification
- The branch workflows are configured to run `forward/test_strategy_policy_v1.py` together with the existing Signal Agent, opportunity, confirmation, risk, decision and dashboard regressions. Do not mark this checkpoint verified until Actions pass on the exact final head SHA and the logs are inspected.
- Parent PRs #297, #346, #361 and #362 remain separate draft/unmerged dependencies as of this checkpoint. Resolve them through exact-SHA review and the repository's required independent approval; do not merge a child independently of its parent chain.

## Next critical work
1. Run and inspect the exact-head CI after the final strategy-policy commit.
2. Use the existing native feature/market-structure components to identify whether validated providers can supply each required strategy evidence group without duplicating indicator logic.
3. Where a provider is absent, leave its evidence UNKNOWN and NO_TRADE; add only a versioned adapter to a genuinely existing validated provider or an explicitly reviewed implementation.
4. Preserve the fixed delivery target **2026-11-19** and risk checkpoint **2026-10-26**; escalate schedule risk rather than weakening the evidence gates.


## Provider and order-block implementation follow-up

- Added `forward/strategy_evidence_provider_v1.py`: derives 4h HTF alignment, 15m pullback/retest, confirmed-swing break, MFI14, ADX14/+DI/-DI, and structure-based 3R geometry from the canonical Binance Spot OHLCV path. Existing EMA and confirmed-swing calculators are reused; MFI14 and ADX14 were absent and are now covered by deterministic tests.
- Wired the provider into the existing read-only dashboard `GET /api/signal`; it fetches 15m and 4h candles from the same native source/cache and exposes strategy state/quorum plus indicator diagnostics. A separate risk-context check stays UNKNOWN until risk budget/account/venue constraints are approved, so the final decision remains NO_TRADE.
- Added `forward/order_block_v1.py`: last opposing candle before a confirmed swing break, with a seven-factor descriptive score (BOS/CHOCH, liquidity sweep, FVG, freshness/mitigation, HTF alignment, volume expansion, EMA/VWAP/support-resistance confluence). It is `CONTEXT_ONLY`; no score threshold is authorized and it cannot bypass the 5/6 strategy quorum or Risk Gate.
- Binance Spot volume semantics are approved only for this source because the official kline contract identifies base-asset volume and quote-asset volume separately: https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md#klinecandlestick-streams-for-utc. Do not transfer this approval to Wallex or another venue.
- Exact-head CI must be rerun after the last code changes; do not use earlier successful runs as final evidence. Live WebSocket smoke remains skipped for this Draft PR. No deployment, account access, order placement, or execution activation.


- Evidence provenance hardening: each strategy check hashes only the closed candle rows actually used at the common `as_of_ms`; its evidence reference separately records the raw Binance response SHA-256 and as-of timestamp. The provider filters both timeframes to the common cutoff, so a newer 15m response cannot leak rows past an older cached 4h observation.
- Order-block context now distinguishes confirmed BOS from CHOCH, scores the seven contextual factors, and includes price confluence against the existing EMA50, the existing VWAP snapshot, or confirmed swing/support-resistance levels. Long and short/CHOCH paths are covered by tests. Score remains non-authorizing.


## Exact-head CI evidence — implementation SHA `4b26a8e4f84be3c9152669625db69165407d4993`

- Strategy policy + evidence provider + order-block + Signal Agent contract suite: **PASS, 69 tests** — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40080290061
- Existing Signal Agent and adjacent gate regression: **PASS, 75 tests** — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40080290033
- Dashboard/native source-path integration: **PASS** — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40080290002
- Browser chart render/source-path smoke: **PASS** — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40080290006
- Live WebSocket smoke: **SKIPPED**, not passed — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40080290007

These runs verified the implementation at the SHA above. This checkpoint addition is documentation-only; the repository will rerun the workflows on the resulting new head. The final promotion gate remains HOLD until that new head is checked and independent review is complete.


- Scope hardening: the Opportunity Policy and Signal Agent accept explicit scope configuration rather than symbol-specific duplicated logic. StrategyEvidenceProviderV1 can be configured for additional Binance Spot symbols while rejecting other venue/product volume profiles until a source-specific adapter proves their volume semantics.


- Final strategy refinement supports the saved MFI rule fully: directional MFI14 threshold OR confirmed bullish/bearish divergence at the last two confirmed swing lows/highs. Pullback checks reuse the existing VWAP snapshot as well as EMA50 and confirmed swing retests. Divergence is causal and tested separately for long and short cases.


## Latest implementation verification — 2026-10-24

Exact implementation head `c87dc30ec9189d72daa7fb81f1bb052e8b2746a5`:
- Strategy contract + provider + OB tests: **PASS, 73 tests** — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40080619221
- Signal Agent + adjacent policy regression: **PASS, 79 tests** — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40080619226
- Dashboard/native path: **PASS** — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40080619231
- Browser render: **PASS** — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40080619229
- Live WebSocket smoke: **SKIPPED** — https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40080619246

The strategy provider now supports MFI14 threshold OR confirmed directional divergence, pullback against the existing VWAP/EMA50/confirmed-swing level, configurable opportunity scopes, and a source-scoped Binance Spot provider. Order-block score includes BOS/CHOCH, liquidity sweep, FVG, freshness/mitigation, HTF alignment, volume expansion and EMA/VWAP/support-resistance confluence. It remains contextual only, with no authorized score threshold.

This checkpoint update is documentation-only. Re-run the same workflows on the new branch head and store those final-head run IDs in the Notion Master Checkpoint. Keep Draft/HOLD until independent review and parent-PR stack reconciliation.
