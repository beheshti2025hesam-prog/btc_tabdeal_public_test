# TradingView / comparable chart integration gate — 2026-10-19

## Priority
High-priority required roadmap item. Integrate HES's existing native-candle/data boundary with a charting layer; do not create a second market-data engine or silently substitute venues.

## Active architecture constraint — independent market data, venue-only execution

- **Chart/candle/analysis inputs must come from a documented global market-data source** (TradingView or a comparable public feed). The source venue and market identity remain explicit; no claim that a global feed equals every execution venue's price.
- **Exchange chart candles are not the analytical source of truth.** Exchange/private APIs are reserved for order submission, order state, fills, and venue-specific execution constraints.
- The initial public provider adapter uses Binance Spot klines (data-api.binance.vision/api/v3/klines) as a comparable global feed, with no credentials. This is a provider choice for read-only market data, not an execution venue choice.
- Use the existing native candle bridge and canonical validation; do not create a second candle engine, invent endpoints, synthesize bars, or relabel Binance data as Wallex/another venue.
- Ordinary candle analysis does not depend on trade sequence. Source volume is preserved as reported; unresolved volume semantics disable only features that require them.
- Before any execution, validate source-to-execution symbol mapping, market type, price freshness, spread/basis, tick/step sizes, minimum notional, order type, fees, slippage, margin/leverage, and duplicate/unknown order outcomes. Global chart price is not proof of executable venue price.
- No concrete private execution adapter is present in the current architecture. Live execution remains disabled until a venue is explicitly selected and its order/fill reconciliation and safety tests pass.
- Repository tree inspection finds no verified frontend entry point. Reuse the authorized existing frontend if located; do not create a parallel app or invent a path. If no existing frontend can be located, record the smallest explicit architecture decision before creating one.
- Sequence/order-book semantics remain adapter-specific only for features that require a stateful book; unknown semantics disable that feature, not candle display.
- Historical Tabdeal Futures endpoint research below remains non-active history and does not authorize switching the data source or execution venue.

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
