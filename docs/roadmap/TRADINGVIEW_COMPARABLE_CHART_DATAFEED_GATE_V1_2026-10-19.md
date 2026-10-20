# TradingView / comparable chart integration gate — 2026-10-19

## Priority
High-priority required roadmap item. Integrate HES's existing native-candle/data boundary with a charting layer; do not create a second market-data engine or silently substitute venues.

## Active source constraint — project DNA (2026-10-19)

- **Wallex is the currently approved active exchange for market-data/WebSocket work.** Implement and validate the chart datafeed against the existing Wallex native OHLCV adapter first, preserving source/market identity and the known volume-semantic gate.
- The pinned Wallex adapter currently enables only 1m and 1h (`resolution=1` and `60`): live probes found other requested resolutions returning wrong spacing or an error. Do not promise/display native Wallex 15m candles until the endpoint is independently shown to honor that interval; do not synthesize them from trades or relabel another venue's bars.
- Tabdeal and Nobitex references below are research/history or future candidate sources only; they are **not authorization to switch the active target**. Do not probe, prioritize, or label them as active production sources unless the user explicitly changes the venue decision or a separately documented contingency is approved.
- This charting work is independent of trade `sequence`: candle-only display consumes native OHLCV through the existing bridge. Sequence research remains separate and conditional on features that need individual-trade identity/order guarantees.
- Resource-first rule: reuse the existing native adapters, normalizer, bridge and a supported chart library. Do not create another candle engine, invent undocumented endpoints, or build a parallel frontend without a verified frontend entry point and a documented gap.

## Findings from official documentation
- TradingView Advanced Charts / Trading Platform libraries do not provide market data; HES must supply its own datafeed: https://www.tradingview.com/charting-library-docs/latest/connecting_data/
- The official Advanced Charts library is hosted in a private GitHub repository, requires access approval, and is not redistributable or permitted in public code repositories: https://www.tradingview.com/charting-library-docs/latest/quick-start/
- TradingView states that Advanced Charts and Trading Platform are not available for personal/internal projects; those licenses are for companies operating public web projects/apps: https://www.tradingview.com/free-charting-libraries/
- TradingView Lightweight Charts is publicly available under Apache 2.0 and supports custom candlestick series fed by application data. Attribution is required: https://github.com/tradingview/lightweight-charts

## Historical / non-active Tabdeal Futures endpoint probe (2026-10-19; not the current source target)

Read-only checks against the official `api1.tabdeal.org` host add the following evidence:

- `GET /r/fapi/v1/time` returned JSON with `serverTime` (the public time endpoint is reachable).
- `GET /r/fapi/v1/exchangeInfo` returned live symbols using the underscore form, including `BTC_USDT`; querying `symbol=BTCUSDT` returned an empty symbols list.
- `GET /r/fapi/v1/depth?symbol=BTC_USDT&limit=5` returned a live order book for the exact `BTC_USDT` Futures identity.
- Candidate `GET /r/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=3` returned HTTP 404; repeating with the verified symbol `BTC_USDT` also returned HTTP 404. This is evidence against those exact public route candidates, not proof that no chart-specific endpoint exists.
- The official [Tabdeal Python SDK](https://github.com/Tabdeal-Exchange/tabdeal-python), including `tabdeal/future.py`, exposes public ping/time/exchangeInfo/depth methods but no kline/candlestick method in the inspected current source.

**Historical conclusion (Tabdeal is not the active source):** native Tabdeal Futures candles were not available through a verified documented/public REST route in this probe. Do not build a fake Binance-compatible adapter, synthesize OHLCV from sequence, or assume the website's chart is sourced from this REST path. Next source-discovery step is inspect the existing official Futures chart's own datafeed/network contract (read-only) and verify its schema before implementing any thin adapter. Candle-based analysis remains sequence-independent.

## Current repository fit
The repository currently has no verified frontend/chart application to extend. Therefore, do not copy proprietary Advanced Charts files into this public repository, do not claim a TradingView Advanced Charts integration without approved access and eligible licensing, and do not create an unrelated parallel frontend just to check a box.

## Recommended default for this project
Use the official open-source TradingView Lightweight Charts as the chart renderer once the HES frontend entry point is selected. Keep the existing native candle bridge and source adapters as the only data lineage. If Advanced Charts becomes eligible later under an approved public-product license, evaluate it separately; do not assume it is available for this private owner-only workflow.

## Datafeed contract to implement
1. **Symbol identity:** explicit venue + market type + exchange symbol; never label Binance bars as Tabdeal or mix Spot and Futures.
2. **History:** return only fully closed canonical OHLC bars with UTC epoch-second chart times and strict chronological ordering; preserve source identity and evidence hashes in the backend.
3. **Gaps:** expose missing intervals to HES quality reporting; do not synthesize candles or silently interpolate prices.
4. **Realtime:** later, use the existing supervised collector/stream boundary only after stale-data, disconnect, restart, single-writer and rollback tests pass. Chart rendering must not own market-data collection.
5. **Volume:** keep Wallex volume-dependent chart features disabled until the observed UDF-vs-public-trades discrepancy is authoritatively resolved; do not halve or otherwise normalize it without evidence.
6. **Market eligibility:** official Tabdeal Futures OHLCV and chart parity remain unproven. Binance adapter contract tests are not evidence that Binance is the approved production source.
7. **Safety:** display/observation only. No order controls, strategy activation, evidence-registry promotion, deployment or live-trading authorization is implied.

## Acceptance gates
- [ ] Select and document the actual existing HES frontend entry point (none verified at this checkpoint).
- [ ] Pin the selected Lightweight Charts version and preserve Apache-2.0/TradingView attribution.
- [ ] Implement a read-only datafeed over the existing canonical candle boundary; no duplicate adapter/aggregator.
- [ ] Contract tests cover symbol/market isolation, UTC/timeframe mapping, closed-bar finality, ordering, gaps, duplicate updates, reconnect/stale behavior, and no fabricated candles.
- [ ] Compare chart OHLC against the exact source candle records over a pinned window; archive hashes and capture a rendered chart for visual parity.
- [ ] Only after source-specific acceptance may a chart be called integrated; collector activation and deployment remain separately gated.

Overall HES status remains `HOLD / NO-TRADE`.


## Delivery schedule and immediate critical path (2026-10-20)
- **Target application delivery:** 2026-11-19 (28 Aban 1405).
- **Frontend path decision due:** 2026-10-22. A recursive repository-tree scan of the current chart-bridge branch found no `package.json`, frontend directory, `index.html`, or TSX/JSX UI entry point. The actual authorized frontend remains unverified; do not report it as found.
- **First usable chart slice due:** 2026-10-26. Scope: read-only Wallex BTCUSDT native 1m and 1h candles, existing adapter + canonical bridge, source-to-chart parity and rendered capture. Volume features remain disabled; no order controls.
- **Release candidate:** 2026-11-16.

The frontend entry point is the critical path. Do not wait for exchange support replies or reopen sequence/volume as global blockers. If no existing frontend can be verified by 22 Oct, record the smallest architecture decision needed before implementation; do not silently invent a parallel app. All dates are planning targets and require evidence-based acceptance.
