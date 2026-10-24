# Signal Agent Entry Point Integration — 2026-10-24

## Purpose
A durable record for the single existing application path. Do not create a second UI, candle schema, source pipeline, or signal implementation.

## Canonical dependency chain
PR #297 (NativeOHLCVBatch + source/feature pipeline) → PR #346 (read-only dashboard using the same native batch) → PR #362 (dashboard-to-Signal-Agent entrypoint) → future validated structure/quality/risk evidence providers → NO_TRADE/Risk Gate → decision journal.

PR #361 remains the reusable Signal Agent component candidate; PR #362 consumes its existing implementation instead of cloning or reimplementing it.

## Current entry point
- Python module: `web/dashboard.py`
- Browser route: `/`
- Candle API: `GET /api/candles`
- Signal API: `GET /api/signal?symbol=BTCUSDT&interval=15m`
- Health: `GET /healthz`
- Local development command: `python -m web.dashboard`
- The signal route reuses `_get_batch`, the existing native OHLCV cache, and `NativeOHLCVFeaturePipelineV1`; no second candle or indicator path is allowed.
- Source provenance is returned using the native batch response SHA-256.

## Mandatory fail-closed rules
- The route only accepts the explicitly supported BTCUSDT / 15m signal scope.
- Do not treat descriptive feature quality as strategy-level `signal_quality_gate_passed`.
- No implicit mapping from Binance `BTCUSDT` to the agent's `BTC_USDT` policy scope without a reviewed, versioned mapping record.
- No direction inference from BOS/CHOCH labels alone.
- Unknown or absent structure, strategy-quality, or risk geometry evidence means `BLOCKED / NO_TRADE`.
- Risk must independently approve the versioned policy, entry/stop/target ordering and minimum 3:1 reward-to-risk.
- Execution is disabled; no order route, credentials, collector activation, or deployment is part of this PR.

## Exact-head verification
Integration head when opened: `7b59c4462da8d9b88837fdf3829979e42615099a`.
- Signal Agent Contract Tests: passed — run [40070741584](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40070741584).
- Dashboard/native source path tests: passed — run [40070741595](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40070741595).
- Signal Agent + existing gate regression: passed — run [40070741462](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40070741462).
- Browser-render smoke was still running at checkpoint creation; do not claim it passed until a completed exact-head result is verified.
- Live WebSocket smoke was skipped because this PR is Draft; no current-head live-feed claim is made.

## Release/delivery control
- Product delivery target: 19 November 2026.
- Risk checkpoint: 26 October 2026 until critical blockers clear.
- PR #362 is Draft/HOLD and stacked on PR #346; PR #346 is stacked on PR #297. No downstream PR is approved just because an upstream test passes.
- The existing VPS working tree contains uncommitted changes. Do not reset, clean, or overwrite it. Deployment and live execution require separate acceptance gates.

## Remaining blockers
1. A reviewed symbol mapping/evidence contract between the analysis source symbol and Signal Agent policy scope.
2. A validated causal structure provider and explicit directional output.
3. A versioned strategy-level signal quality gate and its provenance.
4. Provenance-bound actual entry/stop/target geometry and versioned risk evidence.
5. Exact target-runtime/browser parity and acceptance of the canonical data foundation/dashboard PRs.
6. Forward-observation validation; no profitability or win-rate claim follows from component tests.


## Strategy Agent completion follow-up — 2026-10-24

- Added `forward/strategy_policy_v1.py` and tests. The versioned policy requires six named checks (HTF trend, pullback location, reversal/break, MFI, ADX/+DI, and 3:1 risk geometry), at least 5/6 measured PASS, and always PASS on the risk-geometry gate.
- Every check must include provider/version, evidence reference, evidence SHA-256, state, and timezone-aware observation timestamp. Missing/UNKNOWN/future/malformed evidence fails closed. The policy validates evidence; it does not calculate or fabricate indicator values.
- Signal Agent now derives `signal_quality_gate_passed` from the policy itself and rejects caller-supplied quality overrides. It separately checks actual numeric entry/stop/target geometry and execution remains disabled.
- Fixed the scope mismatch: the active profile is explicitly `binance / spot / BTCUSDT / 15m`; prior candidate policy used `BTC_USDT`, which could never match the dashboard's Binance symbol. Spot/Futures are not aliased.
- The existing dashboard calls the same Signal Agent and surfaces strategy policy state/count/hash. Because no validated strategy-evidence provider is wired yet, the live route must continue to report UNKNOWN/BLOCKED and NO_TRADE. Synthetic unit tests prove contract mechanics, not real signal quality.
- PR remains Draft/HOLD, no merge/deployment/collector activation/order placement. Delivery target remains 2026-11-19; risk checkpoint 2026-10-26.
