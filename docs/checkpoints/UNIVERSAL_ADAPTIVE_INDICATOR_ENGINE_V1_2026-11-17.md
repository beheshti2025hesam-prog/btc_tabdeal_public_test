
## 7. Integration and additional validation addendum (2026-11-17)

- Latest source-of-truth `main` was verified at `1f4a990e2f6a12392c46e8327b665b48b6a52df2` (PR #524). The indicator additions were merged three-way against the exact base commit `9b7701fffcd436ad1f72f4f3f23bf95c561e2c86`; dashboard changes are additive and preserve the newer deterministic Mother Chat, Hoshyar local assistant and project-memory implementation from latest `main`.
- Integrated worktree: `/opt/hes-trade-agent/candidates/universal-indicator-mainline-20261117`, branch `feat/universal-adaptive-indicator-engine-v1-20261117`. It is based on latest `main`; no unrelated source checkout changes were touched.
- Full latest-main integration regression: **1,471 passed, 82 subtests passed**, warnings treated as errors. Focused engine + independent parity suite: **27 passed**.
- DOM/localization/fail-closed smoke rerun on integrated latest-main worktree: **PASS**, 39 indicator rows, 15m/4h/1m switching, Persian RTL, responsive CSS, no console errors; simulated API failure correctly becomes BLOCKED.
- Added independent reference formulas for Supertrend recurrence, Choppiness, Aroon, Stochastic, MFI and OBV. Fixed two calculation-definition issues discovered during the independent review: Relative Volume now divides the current candle by the **previous 20 completed bars** (not a baseline containing itself); OBV change now compares current OBV with OBV **20 bars earlier** (21 observations). Focused parity now 7 tests and includes these definitions.
- Live Gate.io Public Spot portability smoke: 5 symbols (BTC, ETH, SOL, XRP, DOGE) × 4 timeframes (1m, 15m, 1h, 4h) = **20/20 passed**; at least 220 closed candles each, zero timestamp gaps, finite indicator outputs, all safety flags false. This is runtime/formula portability evidence only, not predictive performance or cross-venue validation.
- Local Playwright browser execution attempted; blocked because the VPS lacks Chromium OS libraries. This is an environment dependency, not a dashboard assertion failure. The GitHub Actions workflow installs Chromium plus OS dependencies on a clean Ubuntu runner and remains the final browser gate.
- Production pointers and service remain unchanged. No merge to `main`, production deploy, restart, signal activation, strategy mutation, journal write or order was performed.

## 8. Remaining evidence boundary

The indicator engine and dashboard are research-only. Multi-symbol Gate.io smoke, synthetic parity, regime distribution diagnostics and DOM tests do **not** establish regime classification accuracy, profitable strategy expectancy, win rate, or readiness for Forex/equities/futures/commodities. Those require independently labelled market regimes, additional venue-specific adapters/volume semantics, chronological out-of-sample evaluation, feature ablation, realistic fees/slippage and a sufficiently long forward observation. The current dashboard live route intentionally remains BTC_USDT until each additional market has its own evidence gate.


## 9. Explicit mapped-symbol dashboard integration (2026-11-17)

- Extended the existing dashboard facade without creating a second candle parser or collector: BTCUSDT continues through the persisted `global_market_data_reader_v1`; explicitly mapped ETHUSDT and SOLUSDT reuse the existing versioned `GateioSpotKlineSource` native adapter. The chart and technical-intelligence API share the exact same returned batch and SHA-256 provenance.
- Added the dashboard selector for BTC/USDT, ETH/USDT and SOL/USDT. The selector refreshes both the chart and technical panel. `source_reader` identity is explicit and fail-closed; unknown reader identities are rejected. ETH/SOL are REST-only and do not inherit BTC's 1m WebSocket status.
- BTC retains its existing initial timeframe-role profile (15m setup authority, 1m precision-only, 1h/4h context). ETH/SOL are explicitly marked `DESCRIPTIVE_ONLY_NOT_YET_VALIDATED_FOR_SYMBOL`; no setup/precision authority or strategy decision is assigned to them. Strategy/Mother decision panels remain BTC-canonical and the UI states that clearly.
- Dashboard native-adapter live smoke: **8/8 passed** (ETH/SOL × 1m/15m/1h/4h), 239 closed candles each, zero gaps, exact native-feature batch provenance, feature pipeline READY, 39 finite indicator outputs, safety flags false.
- Cross-market formula test was tightened: generic Forex price calculations remain scale-invariant, but unqualified tick-volume inputs must keep VWAP/Relative Volume/OBV/MFI/CMF unavailable. No Forex volume features are enabled.
- Added explicit fail-closed reader identity test and API contract tests for mapped ETH; full latest-main regression now **1,475 passed, 82 subtests passed** (warnings as errors). Focused dashboard + indicator tests: **65 passed, 16 subtests**. DOM smoke remains PASS (39 indicator rows, Persian RTL, fail-closed, no console errors).
- First exact-head GitHub CI completed: all existing HES regression workflows passed, including the full regression gate; the new indicator workflow passed Python full suite and DOM smoke, then failed only at Playwright install because `ubuntu-latest` had advanced to Ubuntu 26.04, unsupported by Playwright 1.56.1. The workflow is now pinned to `ubuntu-24.04`; a new exact-head CI run is required to close browser acceptance.
- No production symlink, service, strategy, journal, Risk Gate, signal authority or order state was changed. PR remains draft and unmerged.

## 10. Supported scope boundary

V1 dashboard live support is currently the three explicit Gate.io Spot mappings BTCUSDT, ETHUSDT and SOLUSDT. The engine's calculation layer is symbol/market-agnostic, but additional Gate.io pairs require explicit mapping and native adapter validation. Forex, equities, indices, futures, commodities and other venues remain research-library-compatible only; they are not live-enabled. Volume-derived indicators remain disabled wherever provider volume semantics are not qualified. This boundary is deliberate, not an incomplete or silently inferred symbol mapping.


## 11. Final source packaging and multilingual scope checks (2026-11-17)

- Added localization regression for all four dashboard locales covering the new symbol-scope note and dynamic timeframe-role labels. Persian RTL, German and French translations are present; machine identifiers remain unchanged.
- Updated DOM evidence to record the three explicit symbol options, translated scope copy, translated timeframe roles and fail-closed source-reader identity. DOM smoke: **PASS**, 39 indicator rows, no console errors.
- Full local regression after the localization addition: **1,475 passed, 82 subtests passed** (`-W error`).
- GitHub CI on the second PR commit exposed a packaging defect in the connector-uploaded `web/dashboard.py` blob: the final `main()` lines had been omitted by a line-range truncation during transfer, although the local source was complete. The next commit re-uploads the entire file using verified 945-line chunks and the complete 366-line dashboard JS; this is a source-transfer correction, not an application runtime failure. Exact-head CI must be rerun after the corrected upload.
