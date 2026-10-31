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


## Read-only dashboard (staged; not installed)

The existing entrypoint is `web.dashboard`; this service template does not introduce another UI or data source:
`hes-readonly-dashboard.service`.

- Binds to loopback only (`127.0.0.1:8765)); do not expose it directly to the internet.
- Uses the versioned-release pointer `/opt/hes-trade-agent/current`; each release must be immutable and contain the exact reviewed source SHA.
- Reads canonical persisted candles from `/opt/hes-trade-agent/data/forward`; do not copy a stale feed into the release directory for deployment.
- Runs as `sentinelx`, with a read-only filesystem sandbox, private temporary directory, no-new-privileges, and no writable project paths. The News Radar snapshot is stored only in the systemd-managed `/var/lib/hes-news-monitor` state directory; the optional `30-news-monitor-state.conf.example` drop-in adds `StateDirectory=hes-news-monitor` (mode `0750`) and grants only this service scoped write access without making the release tree writable.
- Starts one in-process News Radar monitor on dashboard startup (immediate poll, then 60-second interval) and persists its versioned brief/provenance atomically under `/var/lib/hes-news-monitor`. The monitor uses only already-qualified sources and is fail-closed when its snapshot is missing, corrupt, future-dated, or stale.
- Does not enable the Gate.io collector, WebSocket stream, or order execution. The dashboard's stream remains disabled and the API is read-only.
- `ConditionPathExists` prevents startup before a staged release pointer exists.

**Release gate:** installing this file, installing `30-news-monitor-state.conf.example` as `/etc/systemd/system/hes-readonly-dashboard.service.d/30-news-monitor-state.conf`, creating the production release pointer, running `systemctl daemon-reload`, starting or enabling the unit, and any remote ingress configuration require explicit release approval. Do not run those commands as part of CI or this staging audit. First validate the unit/drop-in, service user/group, systemd state-directory ownership, exact artifact hash, health gate, browser/API batch identity, and rollback target in an isolated environment.
