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
- Runs as `sentinelx`, with a read-only filesystem sandbox, private temporary directory, no-new-privileges, and no writable project paths.
- Does not enable the Gate.io collector, WebSocket stream, or order execution. The dashboard's stream remains disabled and the API is read-only.
- News Radar state is isolated under `/var/lib/hes-news-monitor` by `30-news-monitor-state.conf.example`; this does not grant write access to market data or the canonical trade journal.
- `ConditionPathExists` prevents startup before a staged release pointer exists.

**Release gate:** installing this file, creating the production release pointer, running `systemctl daemon-reload`, starting or enabling the unit, and any remote ingress configuration require explicit release approval. Do not run those commands as part of CI or the staging rehearsal. First validate the unit, service user/group, filesystem permissions, exact artifact hash, health gate, browser/API batch identity, and rollback target in an isolated environment.


## Strategy V2 paper services

- Install the reviewed evaluator and learning-loop units from this directory during the controlled release.
- Both services execute code only through /opt/hes-trade-agent/current and use HES_DATA_ROOT=/opt/hes-trade-agent for shared mutable evidence.
- Only data/forward and logs are writable; source code under current remains immutable.
- The paper evaluator reads persisted Gate.io Public Spot candles and appends paper decision/candidate/outcome events. The Learning Loop reads the same canonical journal and writes validation/report artifacts. Neither service can submit exchange orders.
- Do not leave either unit pointed at /opt/hes-trade-agent/scripts in the mutable working tree.


## Gate.io public market-data collector (versioned service templates)

The existing Gate.io collector is a separate market-data service; it does not change the read-only dashboard unit or enable a browser WebSocket stream.

- hes-global-market-data-gateio.service collects 15m closed candles.
- hes-global-market-data-gateio-1h.service collects 1h closed candles.
- hes-global-market-data-gateio-4h.service collects 4h closed candles.
- hes-global-market-data-gateio-soak.service is an optional 24-hour read-only integrity soak; do not enable it by default.
- The collector reuses GateioSpotKlineSource for REST reconciliation, so the eight-field closed-candle contract has one parser. WebSocket messages are wake-up notifications only, require both base (a) and quote (v) volume, and are never persisted as candle records.
- Persisted JSONL history is durable and is not truncated to the REST fetch window. The collector fetches 500 candles for 15m/1h/4h (1,500 for 1m), validates a bounded 5,000-row tail during steady state, and appends new closed candles. Rare historical backfills read the full file and use a validated atomic sorted rewrite; unresolved gaps or conflicting duplicates fail closed.
- The optional 24-hour soak uses `Restart=no`. Any failed sample terminates that run; an operator must inspect the evidence and explicitly start a new run. This prevents an invalid run from being silently restarted. `ExecStartPre` archives the previous output with a neutral `.archive.<UTC timestamp>` suffix.
- Matching systemd drop-ins preserve the deployed UMask=0077 and sandbox restrictions. The service units use /opt/hes-trade-agent and sentinelx because that is the current VPS layout; adapt these paths/account names for other hosts.
- Installing units, daemon-reload, enabling, starting, restarting, or changing service state remains a separately authorized operational action. CI and code review must never run those actions.


## Bounded operational health and paper-worker recovery (staged; not installed)

The versioned `hes-operational-healthcheck.service` and five-minute timer use the existing Gate.io feed, evaluator, Learning Loop, and Precision Entry workers. This adds no second collector, journal, dashboard, or order path.

- The monitor runs from the immutable `/opt/hes-trade-agent/current` release using system Python and writes only to `/var/lib/hes-operational-health`.
- It verifies the active release manifest and listed file hashes, Gate.io feed freshness, the independent 1m integrity witness, canonical journal integrity, paper-only flags, Precision Entry ledger counts/source identity, the daily cap, disk, NTP, SSH, tunnel, and Xray.
- Automatic recovery is restricted to `hes-strategy-paper-evaluator.service`, `hes-strategy-learning-loop.service`, and `hes-precision-entry-journal.service`, in dependency order. It starts (does not blindly restart) only an enabled, inactive paper worker, after all unrelated checks pass.
- It never restarts Gate.io feeds, dashboard, Xray, SSH/firewall, the release pointer, policy/risk components, or any order path. Feed/evidence corruption remains fail-closed.
- Recovery requires a stable release pointer (10 minutes), a valid immutable manifest, active dependencies, no deployment lock/manual hold, and a finite retry budget (2 attempts per unit per hour, 15-minute cooldown). Each attempt/result is appended and fsynced to a mode-0600 repair audit.
- A deployment must hold the shared lock for its complete stop/switch/start/verify sequence:
  `exec 9>/var/lib/hes-operational-health/deployment.lock; flock -x 9`.
  While held, the monitor reports `MAINTENANCE` and takes no repair action. A per-service hold marker is available under `/var/lib/hes-operational-health/hold/<unit>.hold`.

Focused recovery/runtime tests and `systemd-analyze verify` must pass before release. This candidate is not production-active: installing the units, daemon-reload, enabling the timer, and activating a release require the existing explicit owner release approval and exact-SHA acceptance gates. The Learning Loop remains hypothesis-only; no automatic strategy/risk mutation or live trading is permitted.
