# Bybit read-only adapter proposal — 2026-10-17

Status: Draft / test-only / no deployment / no trading.

Bybit documents V5 public WebSocket streams for linear products at
`wss://stream.bybit.com/v5/public/linear`. The adapter subscribes to
`publicTrade.BTCUSDT` and `kline.1.BTCUSDT`, captures raw JSON payloads,
receive timestamps and exact-byte SHA-256 fingerprints. It does not authenticate,
read private account data, submit orders, interpret `seq` as globally unique or
contiguous, or connect to HES decision-grade observation.

Official references:
- https://bybit-exchange.github.io/docs/v5/ws/connect
- https://www.bybit.com/en/help-center/article/How-to-create-your-API-key/

Public market data does not require a personal API key. If private account reads
are later needed, use a separate minimum-permission read-only key, restrict by IP,
and store it only in deployment-owned secret storage. Never commit credentials or
enable trade/withdrawal permissions in this phase.

Required before promotion: exact-head CI, independent review, bounded live public
connectivity test from the enrolled VPS, actual payload/schema verification,
reconnect/replay/duplicate analysis, and HES trusted-source/sequence gates.
No bypass of network restrictions. Production Collector stays inactive and
execution remains OFF.
