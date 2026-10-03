# HES Trade Agent — Persistent Collector Migration

## Purpose

Move raw-data acquisition from a GitHub Actions scheduling dependency to a
continuously supervised persistent process. This addresses the confirmed
Pending root cause without changing the Roadmap, DNA, live-trading boundary,
or data-engine-v1 separation.

## Target boundary

- Primary acquisition: persistent VPS/self-hosted filesystem.
- Process supervision: systemd plus collector_supervisor.py.
- Collector responsibilities: websocket reconnect, sequence recovery, active
  150k window, permanent archive, durable CSV writes, graceful stop.
- GitHub Actions: CI, integrity audits, packaging and controlled operational
  checks; not the 24/7 acquisition clock.
- Live execution remains disabled.

## Migration phases

1. Validate the supervisor in an isolated environment.
2. Add and validate a persistent-mode switch that prevents the VPS collector
   from pushing acquisition data into main during parallel validation.
3. Validate restart after clean exit, crash, SIGTERM and websocket disconnect.
4. Validate archive rotation recovery and global sequence continuity.
5. Run a parallel observation period with independent storage and compare
   timestamp and sequence continuity.
6. Establish watchdog evidence: process alive, collector connected/reconnecting,
   latest saved trade age, sequence monotonicity, archive integrity.
7. Only after all acceptance tests are green, demote GitHub Actions from the
   primary acquisition path.
8. Keep GitHub Actions as CI/audit infrastructure.

## Non-negotiable acceptance criteria

The migration is not complete until:

- No scheduled GitHub Action is required to keep the collector alive.
- Collector restarts automatically after process exit/failure.
- A websocket disconnect reconnects without manual intervention.
- A process restart resumes from the persisted global sequence.
- Archive rotation cannot destroy or overwrite existing data.
- Active/archive sequence boundary remains monotonic.
- A stale-data watchdog produces an actionable failure signal.
- Parallel validation shows no unexplained timestamp or sequence gaps.
- No live trading is enabled by this migration.
- data-engine-v1 remains separate from main.

## Current status

Architecture implemented as a controlled branch only.

This branch does not authorize production cutover. The current GitHub
Actions collector remains active until the persistent path has passed the
acceptance criteria above.
