# Native adapter-to-bridge contract checkpoint — 2026-10-19

## Why this follow-up exists
The bridge in PR #329 originally used adapter-shaped deterministic fixtures. Those tests are useful unit tests but, alone, do not prove compatibility with the actual Wallex and Binance parser output types. This follow-up adds an offline contract test against the exact source commits of both adapters.

## Pinned source revisions
- Wallex native OHLCV adapter: `b490611636cca6d133ba9f9cc08d5d9d6333628b` (PR #320).
- Binance Spot/USDⓈ-M Futures adapter: `264ad62f51dee485c8ab9e1053631929c6379e4b` (PR #327).
- Bridge base: `ab97feae34b1548a05f1150b1031024685a4e7b6` (PR #329).

The workflow checks out these immutable revisions into isolated directories and asserts each checkout SHA before running tests. No network requests are made by the contract test; each real adapter parser is fed a deterministic fixture, and its actual output objects are passed into `normalize_native_candles` and `to_feature_candles`.

## Assertions
- Both adapter outputs normalize to the same canonical 60-second candle contract.
- Wallex's exclusive close boundary and Binance's inclusive final millisecond both become the same exclusive end boundary.
- Decimal precision is preserved until the explicit feature-engine conversion.
- Feature candles represent unknown trade count as `None`.
- A Binance market-identity mismatch fails closed.

## Status and safety
The CI result is pending until GitHub Actions reports completed checks for the exact head SHA. This contract test does not merge PRs #320, #327, or #329 and does not claim live rendered-chart parity. No collector activation, evidence-registry pin, deployment, account mutation, or trading is authorized. Overall project disposition remains `HOLD / NO-TRADE`.

## Next chart-source gate
The repository currently has no verified in-repo chart frontend to extend. TradingView Charting Library is a visualization/datafeed interface, not a market-data provider; before adding a UI, first confirm licensing/access, identify the intended venue/market/timeframe contract, and map the existing bridge into the documented datafeed methods. Do not build a parallel chart frontend just to claim integration.
