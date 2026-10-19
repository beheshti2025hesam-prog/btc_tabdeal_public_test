# Native OHLCV adapter v1 — scope and evidence

## Goal
Read native exchange candlesticks rather than infer them from individual trades. The adapter is read-only and does not place orders. Importing it makes no request; network I/O happens only when `fetch_klines()` is explicitly called.

## Supported endpoints
- Binance Spot: `GET https://api.binance.com/api/v3/klines`
- Binance USDⓈ-M Futures: `GET https://fapi.binance.com/fapi/v1/klines`

Official reference: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints#klinecandlestick-data and https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data

Rows are keyed by candle open time and follow the documented 12-column kline schema. Decimal strings remain `Decimal`; timestamps remain milliseconds. Bars whose close time is greater than or equal to the caller's as-of time are excluded. Missing intervals are reported as gaps, not synthesized. The raw response SHA-256 and retrieval time are returned for provenance.

## Live read-only spot check (2026-10-19)
A connected Binance public-data read fetched BTCUSDT 15-minute Spot klines, Spot UI klines, and USDⓈ-M Futures klines. A fresh comparison at 2026-10-19T07:17:59.960Z compared five fully closed Spot candles (open times 06:00, 06:15, 06:30, 06:45, and 07:00 UTC). All five matched exactly in open time, OHLC, and volume between `klines` and `uiKlines`. The current 07:15 UTC candle was excluded because it was still open. Futures OHLCV values are contract-market data and are not expected to equal Spot.

This is a small live smoke check, not a durable raw HTTP capture or full chart-parity acceptance. CI uses synthetic fixtures only and never calls the network. Before enabling downstream decisions, preserve raw response bytes and independently compare more closed bars against the same platform chart, symbol, interval, and timezone.

## Tabdeal limitation
The official Tabdeal documentation currently retrieved describes public trades and market depth, but this review did not verify an official native OHLCV/kline endpoint for the specific Tabdeal Futures/Margin chart. This adapter must not be represented as Tabdeal data. If Tabdeal is the required chart venue, its endpoint/schema still needs direct official confirmation before a Tabdeal adapter is added.

## Safety
No API key, secret, account endpoint, order endpoint, collector activation, evidence-registry pin, or trading path is used. Production remains `HOLD / NO_TRADE_ONLY` until venue/chart identity, raw evidence retention, full candle validation, and the remaining release gates are independently satisfied.
