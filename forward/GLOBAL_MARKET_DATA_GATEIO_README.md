# Gate.io public market-data collector v1

This is the existing HES Gate.io candle collector, now versioned beside the canonical native OHLCV adapter. It is **market-data only**: no API credentials, account endpoints, order placement, or trading.

## One canonical source and one persistence path

- Source: Gate.io Public Spot, BTC_USDT.
- The REST bootstrap/reconciliation path reuses `GateioSpotKlineSource` and its versioned `gateio_spot_candlestick_v2` eight-field contract. It does not maintain a second REST parser.
- WebSocket updates are wake-up notifications only. They must contain both `a` (base volume) and `v` (quote volume); missing values are rejected and neither field is substituted. The persisted candle record always comes from the shared REST adapter, so there is no second persisted-candle parser.
- Only closed candles are persisted. The persisted venue symbol is `BTC_USDT`; the native adapter's internal key is explicitly `BTCUSDT`.
- REST reconciliation runs at least every 20 seconds while subscribed. Disconnects/timeouts use bounded exponential backoff; systemd also restarts a failed process.
- The JSONL file is durable history and is never truncated to the bounded REST fetch window (500 candles for 15m/1h/4h; 1,500 for 1m). Normal operation validates a bounded 5,000-row tail and appends new closed candles. Rare historical backfills read the full file and use a validated atomic sorted rewrite. Conflicting duplicates, malformed rows, unresolved gaps, stale/unknown identity, or invalid OHLCV fail closed and leave the last known-good file untouched.
- `trade_count` and taker-buy flow are not supplied by this Gate.io source and remain UNKNOWN; they are not synthesized as zero.

## Existing services

- `hes-global-market-data-gateio.service` — 15m
- `hes-global-market-data-gateio-1h.service` — 1h
- `hes-global-market-data-gateio-4h.service` — 4h
- `hes-global-market-data-gateio-soak.service` — optional 24-hour read-only integrity soak; do not enable by default. It uses `Restart=no`; any failed run terminates and requires explicit review/manual restart.

The service unit templates under `deploy/systemd/` are for the current VPS layout (`/opt/hes-trade-agent`, user/group `sentinelx`). Adapt the root, venv, service user, and `ReadWritePaths` for another host before installation. Drop-ins preserve the deployed UMask and systemd sandbox restrictions.

## Configuration

- `HES_GLOBAL_CANDLES_INTERVAL`: `15m`, `1h`, or `4h` (defaults to `15m`).
- `HES_GLOBAL_CANDLES_OUTPUT`: optional absolute/relative JSONL output path; otherwise the matching `data/forward/global_market_candles*_v1.jsonl` under the repository root is used.
- `HES_GATEIO_SOAK_LOG`: optional output path for the read-only 24h soak report.

## Deployment notes

The collector code, systemd unit files and soak script are versioned for reproducibility. Installing/updating units, daemon reloads, service restarts, or changing the live `current` pointer are separate operational actions and require explicit authorization. Do not run those actions as part of a code-only review.

For a controlled install on a prepared host, copy the matching unit and drop-in directories to `/etc/systemd/system/`, ensure the service account owns the data directory, then run `systemctl daemon-reload`. Enable/start only after the release gates and operator authorization pass.
