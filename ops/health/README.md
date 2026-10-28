# HES operational health monitoring

This monitor is a small systemd oneshot + timer, not a second application or agent. It checks the already-existing HES services and persisted data path.

## Install

1. Install `ops/health/hes-operational-healthcheck` as `/usr/local/sbin/hes-operational-healthcheck` with owner `root:root` and mode `0750`.
2. Install the service and timer files from `ops/systemd/` into `/etc/systemd/system/`.
3. Create `/var/lib/hes-operational-health` as `root:root`, mode `0700`.
4. Run `systemctl daemon-reload`, then `systemctl enable --now hes-operational-healthcheck.timer`.
5. Run `systemctl start hes-operational-healthcheck.service` and verify the result with `systemctl status` and `journalctl -t hes-operational-health`.

The monitor checks active market-data/dashboard/learning/paper-evaluation services, freshness of the existing 15m/1h/4h persisted feeds and no-trade audit, root filesystem usage, NTP synchronization, and listening ports 9011/443. Feed age thresholds are deliberately conservative and should be reviewed if the source cadence changes.

## Alerting and recovery limits

State changes are logged to the local system journal and repeated identical failures are deduplicated. This does **not** provide off-host alert delivery. Configure an approved email/webhook destination and test it before claiming external alerting.

The monitor is read-only with respect to application data; it does not restart services, start the legacy Tabdeal collector, place orders, or enable execution. It is specific to the currently deployed Gate.io feed paths and should not be merged/promoted until the active service paths are reconciled to a reviewed release SHA.
