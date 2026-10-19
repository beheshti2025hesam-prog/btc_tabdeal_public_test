# Native OHLCV → causal structure observation bridge — 2026-10-19

## Purpose
Allow the existing forward-only Market Structure observer to consume a normalized native 15-minute OHLCV batch without pretending that trade-level sequence metadata exists.

## Reused components
- Native source parser: Binance Spot/USDⓈ-M Futures adapter at immutable SHA `264ad62f51dee485c8ab9e1053631929c6379e4b`.
- Shared normalization boundary: `forward/native_candle_bridge_v1.py`.
- Existing candle contract: `forward/candle_normalizer_v1.py`.
- Existing causal observer: `forward/structure_observation_v1.py` and `forward/structure_policy_v1.py`.

## Contract
- Only normalized 15-minute batches may be converted for the existing structure observer.
- OHLCV remains Decimal in the structure input.
- Native candles have no trade sequence, trade count, or trade-observed timestamps; those fields remain `None`, not fabricated values.
- Existing causal observer still enforces closed candles and `observed_at`; no look-ahead or strategy tuning is added.
- Missing intervals are not synthesized. Existing swing confirmation checks require contiguous windows and therefore skip windows across gaps.

## Scope and limitations
- The contract test invokes the pinned Binance parser offline. It proves parser-to-observer compatibility, **not** that Binance is the approved production source for Tabdeal BTC_USDT Futures.
- Wallex native UDF adapter currently supports minute resolutions `1, 60, 180, 360, 720`; it does not provide native 15m candles in the pinned adapter. Its volume discrepancy remains unresolved, so volume-dependent Wallex features remain blocked.
- Official Tabdeal native 15m OHLCV parity is not yet established. Do not substitute another venue silently.
- This PR is an integration contract only. No collector activation, evidence-registry pin, deployment, merge, or trading authorization. Overall status remains `HOLD / NO-TRADE`.
- TradingView/chart source integration remains a high-priority separate gate: first identify the approved market-data source and licensing/access, then map this bridge to the documented datafeed API. Do not create a parallel chart frontend merely to claim integration.
