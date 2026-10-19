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

## Read-only chart projection contract
- `to_lightweight_chart_payload()` projects canonical closed candles into UTC epoch-second OHLC bars for a future Lightweight Charts datafeed; this is a projection helper, not a frontend, HTTP server, or production integration.
- Source identity is carried with the payload, and gaps/open-candle counts remain explicit. No candle is synthesized.
- Volume is omitted by default. Requesting Wallex UDF volume fails closed while its 2x discrepancy remains unresolved; any opt-in volume is explicitly labeled raw source-reported.
- Contract tests use pinned parser implementations and no live market requests. The rendered chart, approved Tabdeal source, and independent visual parity are still not established.

## Volume semantics safety
- The core feature-engine Candle contract permits `volume=None` so price-only features can continue without inventing a zero.
- `to_feature_candles()` omits native volume by default. Explicit `include_volume=True` is required for source-reported volume, and Wallex UDF volume is rejected while its 2x discrepancy remains unresolved.
- `to_structure_candles()` is price-only and sets structure-input volume to `None`; exact Decimal volume remains available only in the normalized native batch for evidence. This prevents unverified volume from silently entering the legacy feature or structure path.
