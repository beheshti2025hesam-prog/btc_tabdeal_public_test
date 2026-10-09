# HES collector supervision (staged deployment)

The collector now supports an opt-in local-durable mode and a versioned health heartbeat.

## Contract

- The heartbeat is written atomically to `data/forward/collector_heartbeat_v1.json`.
- The file includes a UTC timestamp, process identity, current sequence, row count for the process, and current CSV size. It contains no credentials.
- In local-durable mode, a heartbeat is updated on transport activity and at most once per 10 seconds.
- When systemd sets `NOTIFY_SOCKET`, the collector sends `READY=1` at startup and refreshes `WATCHDOG=1` on observed WebSocket message/pong activity.
- If heartbeat persistence fails, the collector stops and closes its WebSocket fail-closed.
- This is not proof that every market event was received; sequence/candle validation remains a separate gate.

## Staged deployment

Do not enable or start the production service merely by installing this file. First run the focused tests and a short, supervised collection test. Verify that:
1. `data/trades.csv` is unchanged before start and advances only by valid new rows during the test.
2. The heartbeat timestamp advances, `status` is `RUNNING`, and `last_sequence` agrees with the last accepted CSV row.
3. Stopping the service leaves the CSV readable and the lock released.
4. No Git fetch/restore/reset/push is performed while local-durable mode is enabled.

After that approval, copy `20-local-durable-watchdog.conf.example` to
`/etc/systemd/system/hes-trade-agent-collector.service.d/20-local-durable-watchdog.conf`,
run `systemctl daemon-reload`, and perform the supervised test. Do not enable the service for boot or start a 48-hour observation until the test evidence is reviewed.

The drop-in changes the unit to `Type=notify`, enables a 75-second systemd watchdog, and sets local-durable mode. The base unit already uses `Restart=always`; watchdog timeout therefore causes a process restart. Invalid local evidence still fails closed at startup.
