# TradingView / comparable chart integration gate — 2026-10-19

## Priority
High-priority required roadmap item. Integrate HES's existing native-candle/data boundary with a charting layer; do not create a second market-data engine or silently substitute venues.

## Findings from official documentation
- TradingView Advanced Charts / Trading Platform libraries do not provide market data; HES must supply its own datafeed: https://www.tradingview.com/charting-library-docs/latest/connecting_data/
- The official Advanced Charts library is hosted in a private GitHub repository, requires access approval, and is not redistributable or permitted in public code repositories: https://www.tradingview.com/charting-library-docs/latest/quick-start/
- TradingView states that Advanced Charts and Trading Platform are not available for personal/internal projects; those licenses are for companies operating public web projects/apps: https://www.tradingview.com/free-charting-libraries/
- TradingView Lightweight Charts is publicly available under Apache 2.0 and supports custom candlestick series fed by application data. Attribution is required: https://github.com/tradingview/lightweight-charts

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
