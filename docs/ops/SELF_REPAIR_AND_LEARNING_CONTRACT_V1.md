# HES Trade Agent — Self-Improvement and Self-Repair Contract v1

**Status:** Candidate for review; not installed or activated on the VPS.  
**Delivery target:** 2026-11-19.  
**Market-data boundary:** Gate.io Public Spot BTC_USDT is the canonical live analysis/chart/candle/indicator source. Exchange/broker adapters are execution-only.  
**Execution boundary:** PAPER-ONLY / NO-TRADE-ONLY; `execution_enabled=false`, `orders_placed=false`.

## 1. Reuse existing project components

This contract wires and hardens existing components; it does not introduce a second collector, journal, dashboard, learning loop, market-data adapter, or order path:

- `global_market_data_reader_v1` and the existing Gate.io 1m/15m/1h/4h persisted feeds remain the source of market evidence.
- `run_strategy_policy_v2_forward_eval.py` remains the paper evaluator and canonical writer of the Strategy V2 journal/report.
- `run_precision_entry_journal_v1.py` remains the 1m Precision Entry paper journal; it may record at most three actionable paper candidates per UTC day, as a cap and never a quota.
- `run_strategy_learning_loop_v1.py` remains read-only and hypothesis-only. It does not edit strategy thresholds, policy files, risk rules, or place orders.
- Existing crash-safe checkpoint, health monitor, sequence-safe recovery, runtime-health gate, soak harness, signal-quality acceptance, and promotion-gate modules remain authoritative for their respective contracts.

## 2. Self-improvement state machine

`OBSERVE → VALIDATE → ATTRIBUTE → HYPOTHESIZE → ISOLATED_TEST → INDEPENDENT_OOS → PROMOTION_REVIEW → APPROVED_RELEASE`

- Observations are forward-only, immutable, timestamped, source-bound, and hash-linked.
- Gate attribution distinguishes avoided-loss hypotheses, missed-profit hypotheses, rejected proposals, unverified proposals, and directionless market context. Counterfactuals are not causal proof or executable P&L.
- The learning loop may propose hypotheses only. No automatic threshold relaxation, strategy mutation, risk-gate bypass, or promotion is allowed.
- A strategy change requires a preregistered hypothesis, deterministic tests, independent out-of-sample evidence, verified fees/slippage, regime/direction stability, complete event/candidate/outcome linkage, and explicit owner release approval.
- The paper acceptance target remains strictly greater than 90% over at least 100 resolved closed trades, no more than three actionable entries per UTC day, positive net expectancy after verified costs, and independent OOS evidence. Missing or ambiguous evidence fails closed. The target is not a promise of future returns.

## 3. Bounded self-repair state machine

`DETECT → CLASSIFY → PRECONDITION_CHECK → BOUNDED_START → VERIFY → AUDIT`

Automatic recovery is limited to these already-existing paper-only workers, in dependency order:

1. `hes-strategy-paper-evaluator.service`
2. `hes-strategy-learning-loop.service`
3. `hes-precision-entry-journal.service`

Recovery is permitted only when all conditions hold:

- The active `current` pointer is a symlink into `/opt/hes-trade-agent/releases` and has been stable for at least 10 minutes.
- The immutable release manifest and every listed file hash verify.
- The exclusive `/var/lib/hes-operational-health/deployment.lock` is acquired; a deployment must hold the same lock throughout stop/switch/start. A manual hold marker under `/var/lib/hes-operational-health/hold/<unit>.hold` suppresses recovery for that service.
- All unrelated runtime checks pass: canonical Gate.io feeds are active and fresh, the 1m integrity witness passes, journals are parseable and unique, paper-only flags are intact, disk/NTP/SSH/tunnel checks pass.
- Each target unit is enabled, its dependencies are active, and the retry budget allows the attempt (maximum two attempts per service per hour, with a 15-minute cooldown).
- The service is started, never blindly restarted. After each start, the monitor must take a fresh runtime + host-health snapshot; the target service's own freshness/journal checks must clear before the next worker is started. A preflight snapshot must never be reused as post-start evidence. A timeout, malformed health report, or any unrelated/new critical issue stops the recovery chain.
- Repair-audit timestamps must be timezone-aware; future timestamps beyond the clock-skew tolerance fail closed rather than being ignored by the retry-budget calculation.

The recovery audit is append-only, fsynced, mode 0600, and records service, action, reason, active release ID, attempt budget, and result. Corrupt audit state fails closed.

## 4. Never auto-repair these categories

- Gate.io feed services, sequence/candle integrity, market-data provenance, dashboard, Xray/tunnel, firewall, SSH, package upgrades, system reboot, release pointer, systemd unit definitions, Git branches, strategy/risk policies, or any exchange/broker order path.
- Stale, missing, conflicting, gapped, or malformed market evidence is not repaired by inventing or replaying data. It is blocked and reported.
- A missing approval, an invalid release manifest, a deployment lock, a manual hold, exhausted retry budget, or failed health precondition blocks automatic action.

## 5. Long-horizon maintenance

- Keep code/contracts versioned and immutable per release; keep runtime evidence in the shared data root, not inside a release directory.
- Keep append-only evidence, stable event IDs, checksums, crash-safe writes, and explicit segment boundaries.
- Run deterministic fault-injection and recovery tests on every release; retain soak and rollback evidence.
- Revalidate dependencies, exchange API semantics, time synchronization, certificate/secret rotation, backup restoration, and security posture during scheduled maintenance windows. No software can guarantee immunity for 20 years without ongoing maintenance.
- A recovery action never implies trading authorization. Live execution remains a separate, explicit, instrument-mapped, risk-approved release gate.

## 6. Rollback and disable

- Disable automatic recovery by creating `/var/lib/hes-operational-health/hold/<unit>.hold` for the relevant paper worker, or by stopping the operational healthcheck timer through an approved maintenance procedure.
- Remove a hold only after the cause is reviewed. Do not delete repair audit events.
- Roll back by restoring the previous immutable release pointer and its exact systemd unit/configuration from the recorded rollback bundle. Preserve canonical journals and their lock inode.
- This candidate is not production-active. Installation, daemon reload, and timer activation require the existing explicit release approval and exact-SHA acceptance gates.

## 7. Deployment-lock procedure

All controlled release operations that stop a paper worker or change `/opt/hes-trade-agent/current` must hold the same exclusive lock used by the recovery worker. For a multi-command release procedure, use one shell session and keep the lock held until the new release, services, and post-deploy checks are complete:

```bash
install -d -m 0700 /var/lib/hes-operational-health
exec 9>/var/lib/hes-operational-health/deployment.lock
flock -x 9
# Perform the approved stop / atomic release switch / start / verification here.
# The lock is released when this shell exits.
```

Do not run deployment commands outside this lock. The monitor reports `MAINTENANCE` and takes no recovery action while the lock is held. For a deliberate per-service hold outside a deployment, create the corresponding `hold/<unit>.hold` file; remove it only after the operator has reviewed the cause.


## 8. Self-cleanup safety contract — staged, not yet activated

The existing IDLM scanner remains the sole inventory/classification source. It is read-only by default; it must not be converted into an unrestricted cleanup command.

- `KEEP` is mandatory for evidence, canonical journals, market-data payloads/candles, registered Git worktrees, immutable releases/candidates, rollback assets, backups, Dropbox staging, unknown/unparsed paths, symlinks, and files with unresolved ownership or provenance.
- Automatic cleanup, if separately approved in a future release, may target only a small versioned allowlist of demonstrably regenerable caches outside immutable releases and registered worktrees. Age alone is never proof that a file is disposable.
- Every cleanup candidate must be tied to a fresh inventory, exact path + device/inode + size + mtime + content/tree digest, an explicit policy version, a minimum age, no active process/file reference, and a second pre-action revalidation. Any mismatch cancels the whole batch.
- Temporary clones, scratch workspaces, old logs, backups, and arbitrary `REVIEW_*` candidates remain manual-review only. No recursive deletion based on wildcard patterns.
- Cleanup must have a dry-run plan, bounded batch/byte budget, append-only pre/post audit, recoverable quarantine where appropriate, and a tested rollback/rebuild path. If the audit, registry, filesystem identity, or capacity probe is unavailable, take no action.
- Until the cleanup executor, adversarial tests, owner-approved allowlist, rollback proof, and exact-release deployment gate all pass, keep `automatic_action=NONE` and `deletion_authorized=false`. No cleanup is run by this candidate.
