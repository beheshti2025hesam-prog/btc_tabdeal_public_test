# Gate.io multi-crypto observation registry v1

This registry extends the existing persisted Gate.io Spot feed without changing the BTC canonical path.

- BTC_USDT remains the only currently accepted strategy-analysis scope.
- ETH_USDT and SOL_USDT are additional read-only observation/chart candidates.
- Each instrument and timeframe is persisted to its own JSONL path and validated by the same fail-closed reader.
- One parameterized systemd template plus six per-instance environment files are staged only. They are not copied to `/etc`, enabled, or started by this PR.
- No chart/analysis path may fetch a second candle batch or blend volume across venues.
- No execution symbol mapping is implied by this market-data registry.


## Event identity and recovery policy
See `docs/EXCHANGE_EVENT_IDENTITY_AND_SEQUENCE_POLICY_V1.md`. The Gate.io candle feed uses the exact (provider, product, symbol, timeframe, open_time) candle identity; it does not use trade/order-book sequence fields. Reconnect backfill is merged by this scoped key. No generic numeric sequence semantics are inferred.
