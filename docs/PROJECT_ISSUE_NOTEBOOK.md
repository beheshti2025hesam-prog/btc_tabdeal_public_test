# HES Trade Agent — Project Issue Notebook

## Entry: 2026-09-28 — Collector Pending Queue / 24-7 Coverage

### Incident
GitHub Actions collector runs are accumulating in `pending`.

Live audit at 2026-09-28:
- Run #156: `in_progress`; job started at 03:07 UTC after being created at 20:22 UTC.
- Run #157: `pending`, created at 00:35 UTC.
- Run #158: `pending`, created at 04:27 UTC.
- Main workflow currently schedules every 4 hours.
- Collector runtime is configured for 19,200 seconds (5h20m).
- Concurrency uses the same group with `cancel-in-progress: false` and `queue: max`.

### Root Cause — CONFIRMED
The current architecture deliberately creates a scheduling interval shorter than the maximum collector execution window:

`cadence = 4h < runtime = 5h20m`

Therefore a new scheduled run can legitimately arrive while the previous collector is still active. With `queue: max`, GitHub is explicitly allowed to retain multiple pending runs (up to 100 per concurrency group). GitHub documents that queued runs in the same concurrency group remain pending until the active run completes.

This means Pending is not an incidental bug in the collector code. It is an architectural consequence of:
1. fixed Cron scheduling,
2. a single shared concurrency group,
3. non-canceling concurrency,
4. `queue: max`,
5. and a collector runtime longer than the schedule interval.

### Secondary Root Cause — RUNNER START DELAY
Run #156 demonstrates that the delay is not limited to our intentional overlap. The run was created at 20:22 UTC but its collector job did not start until 03:07 UTC. GitHub documents that scheduled events can be delayed during high load.

Consequently, no Cron interval can provide a hard guarantee of zero queueing and zero data gaps on GitHub-hosted runners.

### Important Non-Solutions
The following are NOT considered permanent fixes:
- merely changing Cron minutes;
- merely reducing the number of schedule entries;
- switching `queue: max` to the default single pending queue;
- setting `cancel-in-progress: true`;
- manually canceling pending runs;
- repeatedly tuning the overlap window.

These may change the appearance of Pending, but they do not provide a deterministic 24/7 raw-data acquisition guarantee.

### Permanent Architecture Decision
The raw-data Collector must eventually run as a continuously supervised process on a persistent machine (the project's planned VPS / self-hosted infrastructure), rather than depending on GitHub-hosted scheduled jobs for continuous acquisition.

Target architecture:
- **Collector:** persistent 24/7 process with automatic reconnect/restart and durable local persistence.
- **Supervisor:** systemd/container supervisor with restart-on-failure and health checks.
- **Persistence:** active 150k window + permanent archive remains the source of truth.
- **Sequence integrity:** global sequence recovery remains mandatory.
- **GitHub Actions:** CI, tests, audits, packaging, integrity checks, and controlled operational workflows — not the sole 24/7 acquisition clock.
- **No live trading:** unchanged.
- **data-engine-v1:** remains separate from main; no merge/rebase/sync as part of this incident.

GitHub documents self-hosted runners as persistent machines that can be managed as services, including systemd on Linux. This is compatible with the project's future VPS architecture, but the Collector process itself should remain independently supervised so a GitHub Actions scheduler outage cannot become a market-data outage.

### Transition Safety Requirements
Before replacing the current GitHub collector as the primary acquisition path:
1. Build the persistent Collector deployment.
2. Prove reconnect/restart behavior.
3. Prove durable checkpoint and archive recovery after process interruption.
4. Prove no duplicate/destructive archive rotation.
5. Prove global sequence continuity across restarts.
6. Run parallel audit against the existing GitHub collector long enough to establish timestamp/sequence continuity.
7. Only after evidence is green, demote GitHub Actions from primary acquisition to audit/CI role.
8. Never enable live trading as part of this migration.

### Acceptance Criteria
The issue is considered permanently resolved only when all are true:
- Pending accumulation is no longer part of the primary data-acquisition architecture.
- Collector has a continuously supervised execution path.
- Restart/reconnect is automatic.
- Raw-data timestamp continuity is measured, not assumed.
- Sequence continuity is measured across active/archive boundaries.
- No destructive recovery behavior is possible.
- A health watchdog can detect stale/no-data conditions.
- GitHub Actions remains useful for verification but is not a single point of failure for raw-data collection.

### Status
**Root cause confirmed. Permanent architectural remediation identified. Deployment intentionally NOT performed yet.**

Reason: changing the live workflow before the persistent acquisition path is validated would trade one failure mode for another and could create a real raw-data gap.

### Evidence
- Live workflow configuration on main: `.github/workflows/run.yml`
- Live audit: Runs #156, #157, #158 on 2026-09-28
- GitHub Actions concurrency documentation
- GitHub Actions schedule/event documentation
- GitHub Actions runner limits and self-hosted runner documentation
