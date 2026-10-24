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
