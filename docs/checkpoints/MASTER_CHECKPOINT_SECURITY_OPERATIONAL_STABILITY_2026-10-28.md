# HES Trade Agent — Master Checkpoint: Security & Operational Stability
**Date:** 2026-10-28  
**Scope:** Read-only audit + low-risk host hardening on the single HES VPS.  
**Delivery target:** 2026-11-19.  
**Trading posture:** No live trading authorization; execution/promotion stays gated.

## Verified and completed
- Confirmed the active host is Ubuntu 24.04 LTS, kernel 6.8.0-31-generic; SentinelX service is enabled and active.
- Verified SSH effective configuration before and after change: port 9011, public-key authentication enabled, password and keyboard-interactive authentication disabled, root login key-only (prohibit-password), TCP forwarding preserved to avoid breaking existing tunnel workflows.
- Added /etc/ssh/sshd_config.d/98-hes-operational-hardening.conf: X11Forwarding no, ClientAliveInterval 300, ClientAliveCountMax 2, MaxAuthTries 3. sshd -t passed; SSH service reload succeeded; listener on 9011 remained present.
- Verified nftables input policy is DROP; only new inbound TCP 9011 and 443 are allowed, plus loopback, established/related, and ICMP. Port 443 is retained for the existing separate tunnel service.
- Enabled periodic package-list updates and unattended upgrades via /etc/apt/apt.conf.d/20auto-upgrades; no automatic reboot was enabled. apt-daily-upgrade.timer is active.
- Created root-only pre-change backup at /var/backups/hes-security/20261028T060447Z/ for SSH configuration and auto-upgrade policy.
- Existing reliability tests passed: tests/test_crash_safe_checkpoint_v1.py, tests/test_clean_structure_stability_v1.py, tests/collector/test_final_checkpoint.py — 16 passed.
- No application source files or existing dirty working-tree changes were altered by this checkpoint.

## Findings / still open (do not mark complete)
- The legacy hes-trade-agent-collector.service is failed and disabled since 2026-10-06. Its final Git checkpoint refused to write because origin/main advanced after collector startup. This is a fail-safe stop, not proof of current market-data collection. Do not blindly re-enable it: the current project direction uses a unified global market-data feed and the collector path must first be reconciled with the canonical architecture and current branch.
- SSH port 9011 remains open to all source addresses at the host firewall; key-only authentication is active, but source allowlisting/rate-limiting and an external reachability check remain to be evaluated against access requirements before changing firewall policy.
- Many OS security updates are available. They were not installed during this pass to avoid an uncontrolled package/kernel change or surprise service interruption near delivery; apply in a controlled maintenance window, then verify health. Current audit did not require an immediate reboot.
- Backup inventory showed old application data archives but no verified recent, automated, off-host application backup/restore proof. Establish and test a recovery point before declaring operational resilience complete.
- Existing repository working tree contains unrelated modifications/deletions and untracked files. Do not reset, clean, merge, or commit them as part of this work. A full application security review and CI run against a clean, exact commit remain required.

## Next acceptance gates
1. Resolve the collector decision: retire/replace legacy Tabdeal collector or repair only if still part of the canonical architecture; test persisted-feed freshness, reconnect behavior, single-writer behavior, crash recovery, and bounded restart/backoff.
2. Add/verify service health monitoring and alerting for stale data, failed units, disk pressure, time drift, and missed scheduled jobs.
3. Implement and test encrypted off-host backups plus a documented restore drill; preserve evidence hashes/provenance.
4. Review app secrets, permissions, dependency/security scan, auth/session/CSRF/rate-limit boundaries, and frontend-to-backend authorization on the exact delivery commit.
5. Apply pending security updates in a controlled window and verify SSH/SentinelX/firewall/application health afterwards.
6. Re-run all required CI/evidence gates on the exact release SHA. Keep live execution, promotion, and deployment blocked until explicit acceptance evidence passes.

**Status:** Host-level hardening and a focused regression test set are complete. The entire security/operational-stability section is not yet accepted because collector lifecycle, recovery proof, pending patching, and full application/release evidence remain open. This checkpoint does not authorize live trading or deployment.
