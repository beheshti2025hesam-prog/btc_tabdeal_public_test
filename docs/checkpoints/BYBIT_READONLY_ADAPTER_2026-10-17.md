# Bybit read-only market-data adapter — proposal

Date: 2026-10-17
Status: Draft / test-only / no deployment / no trading

## Why Bybit
Bybit documents V5 public WebSocket market streams for Spot and linear products. For BTCUSDT linear perpetual/futures, the documented public endpoint is
`wss://stream.bybit.com/v5/public/linear`. Public market-data subscriptions do not require a personal API key. A personal key is only needed later if the agent is authorized to access private account endpoints/streams; do not provide or commit keys to GitHub.

Official references:
- WebSocket connection and public endpoint list: https://bybit-exchange.github.io/docs/v5/ws/connect
- API key creation and permission setup: https://www.bybit.com/en/help-center/article/How-to-create-your-API-key/

## Scope of this change
- Bounded WebSocket session with explicit runtime budget.
- Subscribes only to `publicTrade.BTCUSDT` and `kline.1.BTCUSDT`.
- Captures raw JSON payload plus exact-byte SHA-256 fingerprint and local receive timestamps.
- Does not interpret `seq` as globally unique/contiguous, does not deduplicate on it, does not calculate strategy signals, does not access private account data, and does not place orders.
- No credentials, account permissions, order endpoints, or trading code are added.

## Required next gates
1. Run CI against the exact PR head and inspect all test results.
2. Verify live public endpoint reachability from the enrolled VPS using a short bounded read-only test. Do not route around network restrictions.
3. Validate the actual received schema, topic subscription acknowledgements, reconnect behavior, duplicate/replay behavior, and sequence scope against official docs plus captured raw frames.
4. Keep the adapter disconnected from decision-grade observation until HES source identity and sequence-contract gates pass.
5. If private account/API-key connectivity is later needed, create a separate read-only key with the minimum permissions and IP restrictions, store it only in deployment-owned secret storage, and test account reads only. Never enable trade/withdrawal permissions for this stage.

## Safety
This branch is a code proposal only. Do not merge or deploy without independent review. Production Collector stays inactive and execution remains OFF.
