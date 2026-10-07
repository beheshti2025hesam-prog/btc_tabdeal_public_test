# Forward Tabdeal Collector v1

A branch-safe, observation-only WebSocket collector for fresh BTC_USDT trades.

## Hard boundaries
- Disabled by default.
- No Git operations.
- No push/checkpoint.
- No writes to main.
- No historical CSV/archive import.
- No order execution.
- Order-shaped events are ignored.
- Duplicate/non-monotonic sequence values are rejected.
- Writes append-only JSONL with fsync.

This collector is intentionally separate from the legacy
`tabdeal_futures_ws_test.py`, whose checkpoint path can push to
`origin/main`.

Before VPS activation, the runtime should be executed under a dedicated
forward systemd/service identity and verified with the observation-run record.
