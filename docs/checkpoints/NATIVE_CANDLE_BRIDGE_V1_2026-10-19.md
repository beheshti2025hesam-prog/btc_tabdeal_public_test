# Native candle bridge v1 — scope and safety

## Purpose
Connect existing native OHLCV adapters to the established HES candle-feature boundary without reimplementing exchange transport, trade aggregation, chart rendering, or sequence semantics.

## Reused components
- Wallex adapter: forward/native_wallex_ohlcv_v1.py (PR #320).
- Binance Spot/USDⓈ-M Futures adapter: forward/native_binance_ohlcv_v1.py (PR #327).
- Existing feature candle model: core/data_engine/candles.py.
- Existing consumers include EMA and price/VWAP features.

## Contract
- One call represents exactly one venue/market/symbol/timeframe; callers explicitly identify venue and market.
- Accepts the existing adapters structurally, without importing either adapter and creating cross-PR coupling.
- Requires timezone-aware times, strict ordering, unique opens, valid OHLC bounds, finite decimal values, nonnegative volume, and only fully closed bars.
- Returns a canonical Decimal-preserving batch with explicit gaps and count of discarded open bars.
- Converts to the existing float-based core.data_engine.candles.Candle only through to_feature_candles; trade_count=None means unknown and is not fabricated.
- The original adapter evidence/raw payload remains the provenance record. This bridge does not fetch data or replace source evidence.

## Scope limits
- No sequence field is required for candles.
- Volume-dependent decisions remain blocked for sources with unresolved volume semantics.
- Does not render or embed TradingView. Chart access/licensing and source parity remain separate roadmap tasks.
- No collector activation, order APIs, deployment, evidence registry pin, or trading authorization.
- Draft PR only; exact-head CI and independent review required. Overall status remains HOLD / NO-TRADE.
