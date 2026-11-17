# HES Universal Adaptive Indicator Engine V1

**Status:** integrated PR candidate based on latest `main`; research-only; not merged or activated in the production dashboard.
**Candidate:** `candidates/rc-universal-indicator-engine-v1-20261117-dashboard-current`
**Base release:** `9b7701fffcd436ad1f72f4f3f23bf95c561e2c86` (the actual `dashboard-current` target used by `hes-readonly-dashboard.service`)

## Purpose

Provide one symbol-agnostic OHLCV indicator library, a conservative five-state regime classifier, regime-specific research profiles, and a read-only dashboard projection. The engine is not a strategy and does not create entries, trade scores, predictive probabilities, or execution instructions.

## Input contract

- Consumes only already-validated, closed OHLCV candles supplied by an existing market adapter.
- Requires strictly increasing timestamps, finite positive OHLC prices, valid high/low envelopes, and non-negative optional volume fields.
- Drops explicitly open candles and rejects duplicate/out-of-order timestamps.
- Fixed-interval gap detection and freshness remain the responsibility of the existing Gate.io/global market-data reader; this engine does not replace those gates.
- Decimal input from the native candle adapter is normalized to float only after validation.
- Donchian breakout reference levels exclude the current candle to avoid look-ahead.

## Indicator library

| Family | Features |
|---|---|
| Trend | EMA 20/50/200, EMA slope, ADX, +DI/-DI, Supertrend state, Aroon up/down |
| Momentum | RSI, MACD line/signal/histogram, Stochastic %K/%D, Williams %R, ROC, CCI |
| Volatility | Wilder ATR and ATR%, Bollinger Bands/%B/bandwidth, Keltner Channels, prior Donchian boundaries |
| Volume & flow | Rolling quote/base VWAP, relative volume, OBV/change, MFI, CMF |
| Regime diagnostics | Choppiness Index, Efficiency Ratio |
| Existing HES components | Market Structure/BOS/CHoCH/liquidity/OB/FVG remain external evidence inputs; not duplicated here |

Relative volume uses the current bar divided by the average of the prior 20 completed bars; the current bar is excluded from its own baseline. OBV change compares current OBV with OBV 20 bars earlier.

Rolling VWAP V1 is calculated as sum(quote volume)/sum(base volume) over the configured rolling window. It is **not** session-anchored VWAP. Volume Profile, order-book imbalance, funding, open interest, basis, liquidation maps, and cross-venue consolidated volume are not implemented in V1.

## Multi-market policy

Price-derived indicators are market-agnostic after OHLCV normalization. Volume-derived indicators require explicit `volume_semantics_qualified=True`; the default is false. The initial Gate.io Public Spot adapter passes this flag only because the existing Gate.io base/quote volume contract is approved. Forex tick volume, equity session volume, index volume, futures contract volume, and commodity volume remain disabled until their provider/product semantics are separately evidenced. Equities additionally require corporate-action-adjusted data and session-aware handling.

No symbol, country, broker, exchange, or market is hard-coded into the calculation engine. The first dashboard adapter remains the existing BTC_USDT Gate.io feed because that is the only currently approved global source in HES.

## Regime classifier

Outputs:
- `BULLISH`
- `BEARISH`
- `RANGE`
- `TRANSITION`
- `UNKNOWN`

Initial research thresholds use ADX/DMI, EMA alignment and slope, Efficiency Ratio, and Choppiness Index. At least 220 closed candles are required. `evidence_confidence` is a normalized share of the classifier's internal evidence scores; it is **not** a calibrated probability, win-rate estimate, or confidence in a future return.

The classifier is intentionally conservative: mixed/weak evidence maps to TRANSITION; insufficient history maps to UNKNOWN. Regime profiles only prioritize which descriptive indicators appear as primary research context. They do not select or activate a strategy.

## Initial BTC timeframe roles

- 4H and 1H: higher-timeframe context
- 15M: initial setup-authority timeframe
- 1M: precision/refinement context only; cannot create or reverse a setup

This is a first BTC profile, not a universal timeframe rule for all markets. Each market/symbol/timeframe profile needs its own walk-forward evidence.

## Dashboard interface

The candidate adds `GET /api/technical-intelligence?symbol=BTCUSDT` and a Technical Intelligence panel. It reuses the dashboard's existing `_get_batch` and persisted closed-candle input path, binds each timeframe to its input SHA-256, and returns per-timeframe regime, indicators, adaptive research profile, availability, and source provenance. It is an additive extension to the actual dashboard-current release: the pre-existing EMA/VWAP chart overlays, native indicator summary, chart provenance/quality gates, HES Trade AI local Command Center, and Hoshyar project-memory integration remain intact.

The endpoint returns `VERIFIED` only when all four timeframe batches pass the existing data boundary; otherwise it returns `PARTIAL` with explicit blocked timeframes. It does not silently substitute stale data.

## Safety invariants

The response hard-codes all of the following to false: decision authority, signal generation, Risk Gate bypass, execution, orders, journal writes, and policy mutation. The existing Risk Gate remains an independent veto. No live strategy, strategy threshold, journal, order route, or service unit was modified.

## Validation performed

- Synthetic uptrend, downtrend, and range fixtures.
- Live Gate.io Public Spot portability smoke: BTC, ETH, SOL, XRP and DOGE across 1m/15m/1h/4h (20/20 batches, at least 220 closed candles each, zero timestamp gaps, finite outputs, all safety flags false). This validates runtime/formula portability on Gate.io spot only; it does not establish predictive quality or support for other venues.
- Insufficient-history, open-candle, timestamp-order, OHLC-envelope, parameter, volume-qualification, provenance, and safety tests.
- Independent reference parity tests: 7 passed across EMA, RSI, DMI/ADX, ATR, Bollinger, Donchian, ROC, Williams %R, CCI, VWAP, relative volume and CMF; includes Supertrend, Choppiness, Aroon, Stochastic, MFI, OBV, prior-window Relative Volume, market/symbol price-scale invariance and current-bar exclusion safeguards.
- Full actual-dashboard-current candidate regression suite: 1,444 passed and 82 subtests passed with warnings treated as errors.
- DOM/localization smoke: PASS; 39 indicator rows; 15m/4h/1m timeframe switching; Persian RTL language and family labels; simulated API failure correctly changes the panel to BLOCKED; no JavaScript console errors.
- Chronological rolling regime diagnostic on Gate.io BTC_USDT: 1m 5,000 candles/4,781 windows; 15m 1,573/1,354; 1h 1,079/860; 4h 644/425; zero timestamp gaps. Last 30% is a temporal holdout. This measures regime-distribution/transition stability only, not forecast accuracy, win rate or PnL.
- Python compile and JavaScript syntax checks passed.
- Local HTTP smoke: technical-intelligence API returned VERIFIED for 4H/1H/15M/1M; 240 closed candles per timeframe; Gate.io source and SHA-256 provenance present; all safety flags false.
- Existing legacy signal route remained HTTP 410; arbitrary order route remained HTTP 405.
- A Playwright desktop/mobile/Persian RTL browser-acceptance test and immutable-action-pinned GitHub Actions workflow were added. The workflow is not yet run; local Chromium execution is blocked by missing OS browser libraries on the VPS, while the workflow installs Chromium with system dependencies on GitHub-hosted Ubuntu. Local Chrome 157 could not be used inside the SentinelX host runner due Chromium network-service FD ownership failures; real-browser screenshots remain a CI gate.

## Promotion gates still required

1. Integrate the exact dashboard-current-based candidate into the source-of-truth branch without touching unrelated dirty work.
2. Run the immutable-action-pinned GitHub Actions workflow at the exact candidate commit; retain browser screenshots and artifact hashes.
3. Complete real-browser desktop/mobile and Persian RTL/English LTR acceptance.
4. Extend independent formula parity to Supertrend, Choppiness, Aroon, Stochastic, MFI and OBV.
5. Collect longer multi-regime data and run labelled regime-quality, market/symbol/timeframe walk-forward, feature ablation and cost-aware expectancy tests. Current rolling audit is descriptive only.
6. Explicit release approval before changing the production `dashboard-current` symlink or restarting the dashboard service.

**No live deployment, no strategy activation, no trade, and no change to production symlinks were performed. The candidate was rebased onto the exact dashboard-current release rather than the unrelated current release.**
