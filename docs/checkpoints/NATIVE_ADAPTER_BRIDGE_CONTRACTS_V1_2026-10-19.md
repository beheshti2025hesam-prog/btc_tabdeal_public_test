# Native adapter-to-bridge contract checkpoint — 2026-10-19

## Why this follow-up exists
The bridge in PR #329 originally used adapter-shaped deterministic fixtures. This follow-up adds offline contract tests against the exact source commits of both native adapters, exercising the real parser output objects.

## Pinned source revisions
- Wallex native OHLCV adapter: `b490611636cca6d133ba9f9cc08d5d9d6333628b` (PR #320).
- Binance Spot/USDⓈ-M Futures adapter: `264ad62f51dee485c8ab9e1053631929c6379e4b` (PR #327).
- Bridge base: `ab97feae34b1548a05f1150b1031024685a4e7b6` (PR #329).

The workflow checks out these immutable revisions into isolated directories and asserts each checkout SHA before running tests. No network requests are made; deterministic fixtures are parsed by the real adapter code and the resulting objects pass directly into `normalize_native_candles` and `to_feature_candles`.

## Assertions
- Wallex Spot, Binance Spot, and Binance USDⓈ-M Futures output normalize into the same canonical 60-second candle contract.
- Wallex's exclusive close boundary and Binance's inclusive final millisecond both become the same exclusive end boundary.
- Decimal precision is preserved until the explicit feature-engine conversion.
- Unknown trade count remains `None`, never fabricated as zero.
- Market-identity mismatch fails closed.

## Status and safety
CI must be checked against the exact current contract-test head. This PR does not merge PRs #320, #327, or #329 and does not claim live rendered-chart parity. No collector activation, evidence-registry pin, deployment, account mutation, or trading is authorized. Overall disposition remains `HOLD / NO-TRADE`.

## Chart-source gate
No verified in-repo chart frontend has been identified. TradingView Charting Library is a visualization/datafeed interface, not a market-data provider. Before adding a UI, confirm library access/licensing and map the existing candle bridge into documented datafeed methods. Do not build a parallel chart frontend merely to claim integration.
