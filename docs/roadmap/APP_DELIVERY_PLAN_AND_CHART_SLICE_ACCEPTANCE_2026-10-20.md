# HES Trade Agent — Delivery Plan and First Chart Slice Acceptance
**Planning date:** 2026-10-20  
**Target delivery:** **2026-11-19 (28 Aban 1405)**  
**First usable chart slice:** **2026-10-26**  
**Status:** In progress; frontend entry point remains unverified.

## Milestones
- [ ] **22 Oct — Frontend path decision:** verify the actual authorized application/frontend entry point and its run/build instructions. Current repository tree inspection found no frontend package or entrypoint. Do not invent a path or claim an existing app has been found. This is the current critical-path risk.
- [ ] **26 Oct — First usable chart slice:** read-only BTCUSDT chart for Wallex native 1m and 1h candles, fed through the existing native adapter and candle bridge.
- [ ] **16 Nov — Release candidate:** acceptance tests and security/data-quality gates complete on the exact release-candidate commit.
- [ ] **19 Nov — Delivery:** application packaged/documented with its operating mode, supported markets/timeframes, limitations and startup/health instructions. Live trading is not implicitly enabled.

## First chart slice — acceptance criteria
### Source and lineage
- [ ] Uses the existing Wallex native OHLCV adapter and canonical candle bridge; no second candle engine, invented endpoint, synthetic bars or venue relabelling.
- [ ] Only supported Wallex resolutions are offered: **1m and 1h**. Other resolutions are rejected/disabled until separately verified.
- [ ] Every payload has explicit venue, market type, exchange symbol, timeframe, source timestamp and retrieval/evidence metadata.
- [ ] Datafeed is read-only; no private API credentials or order submission are required for chart rendering.

### Candle correctness
- [ ] Only closed candles are displayed as historical/final bars; open-bar updates, if later supported, are clearly distinguished.
- [ ] UTC epoch-second mapping and timeframe boundaries are tested.
- [ ] Bars are strictly chronological; duplicates, invalid OHLC, mixed identity and malformed timestamps fail closed.
- [ ] Gaps and stale data are surfaced; no interpolation or synthetic candle generation.
- [ ] A pinned source window is compared against the chart data payload, with raw response hashes and mismatch counts archived.
- [ ] Capture at least one rendered chart and verify its displayed OHLC against the pinned source window.

### Volume and safety
- [ ] Preserve Wallex source volume exactly as returned; do not halve or normalize it.
- [ ] Volume-dependent indicators/features remain disabled while the known UDF-vs-public-trades semantics discrepancy is unresolved.
- [ ] No order controls, strategy activation, deployment, collector activation or live trading is included in this milestone.
- [ ] Chart failure, stale data, unsupported timeframe or source identity mismatch fails visibly and safely.

### Frontend integration rule
- [ ] Identify and verify the actual frontend entry point before implementing UI. Current repo tree inspection did not find a frontend package/entrypoint.
- [ ] Prefer the existing authorized app. If none can be located, document the smallest required architecture decision before creating any new frontend; do not create a parallel frontend by assumption.
- [ ] Default renderer candidate is open-source TradingView Lightweight Charts with required attribution, subject to the verified frontend stack and package/licensing fit.

## Dependency and work discipline
- Exchange support emails/replies are not dependencies for this milestone.
- Trade sequence semantics are not a dependency for candle-only rendering.
- Unknown volume semantics block only volume-dependent features, not candle display.
- Every completed milestone must cite the exact commit, CI run, source evidence and rendered artifact that prove it.
- Overall status stays **HOLD / NO_TRADE_ONLY** until the relevant acceptance gates pass.
