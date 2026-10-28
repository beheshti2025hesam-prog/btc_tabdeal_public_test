# HES Trade Agent — Master Checkpoint: Security & Operational Stability
**Date:** 2026-10-28  
**Delivery target:** 2026-11-19.  
**Scope:** Single HES VPS, existing application and operational paths only.  
**Trading posture:** NO_TRADE_ONLY; no live trading, deployment, or promotion authorization.

## Completed and verified

### Host security and OS maintenance
- SSH hardened: port 9011; public-key authentication only; password and keyboard-interactive authentication disabled; root login remains key-only; `MaxAuthTries 3`, client keepalive policy, and X11 forwarding disabled. SSH socket activation and a real local SSH key-exchange handshake were verified.
- nftables is enabled with input default DROP. New inbound TCP is allowed only on 9011 and 443, plus loopback, established/related traffic and ICMP.
- Periodic package-list refresh and unattended package upgrades are enabled; automatic reboot remains disabled.
- Completed `apt-get upgrade` and `apt-get full-upgrade`: no pending upgrades/removals, `dpkg --audit` clean, `apt-get check` clean. Installed kernel 6.8.0-147-generic and rebooted successfully at 2026-10-28 06:33 UTC. Reboot-required marker is now clear.
- Fixed the pre-existing BIOS-on-GPT bootloader warning without moving/resizing the root filesystem: added a 1 MiB BIOS boot partition in the verified free gap before `/dev/vda1`, backed up the prior partition table/MBR/core image, reinstalled GRUB with no embedding warning, and validated `grub.cfg`. The new kernel booted successfully after reboot.
- Resolved the post-upgrade fwupd library/daemon mismatch by aligning the package versions. No failed systemd units remain after the legacy collector's failure state was reset; the collector itself remains disabled and inactive.
- Xray tunnel hardening: moved the service from shared `nobody` to a dedicated `xray` system identity; config is root-owned and readable by the service group; capability bounding and ambient capabilities now include only `CAP_NET_BIND_SERVICE`; added read-only filesystem, home, private temp/device and kernel/control-group protections. Xray config test passes under the service identity and port 443 remains listening. A static verifier still warns about the base unit's legacy `User=nobody` line, but the effective runtime identity/capabilities confirm `xray` and `CAP_NET_BIND_SERVICE` only; the installer-managed base unit was not rewritten.

### Application and operational monitoring
- Active Gate.io market-data services (base, 1h, 4h), read-only dashboard, learning loop and paper evaluator are active after reboot. The legacy Tabdeal collector was not re-enabled; it is not the canonical chart/candle path.
- Added a root-owned systemd health-check service and five-minute timer. It checks critical active units, freshness of persisted market-data and no-trade audit files, disk pressure, time synchronization, SSH port 9011 and tunnel port 443. It logs state transitions to journald and is currently healthy. The script, unit/timer files, Xray override and install/limits guide are stored in the draft checkpoint PR for reproducibility.
- Dashboard runtime/security checks passed **7/7**: health endpoint, candle endpoint, fail-closed signal route, invalid symbol rejection, invalid signal scope rejection, POST/order-action rejection (405), and security headers. Dashboard binds only to `127.0.0.1:8765`; CSP, frame denial, nosniff, no-store, referrer and permissions policies are present. Signal remains `NO_TRADE` and execution-disabled.
- Full application test suite passed **456/456** after dependency remediation and reboot. A later combined audit command timed out during a redundant test invocation; a verbose rerun immediately afterwards completed successfully in 7.17 seconds with all 456 tests passing.
- Local backup and recovery drill passed: root-only post-change archive at `/var/backups/hes-trade-agent/security-stability-postchange-20261028T063214Z`; checksum verification successful, and isolated restore verified. Partition table, GRUB artifacts, SSH/update policy, package inventory, requirements, venv freeze, health script and Xray service/config artifacts are included.
- Dependency audit found vulnerabilities in the old installed stack, driven in part by the unused `tabdeal-python 0.4.6` SDK pinning `requests==2.27.1` and forcing `urllib3<1.27`. The SDK is not imported by the active code and was removed. Updated requirements now constrain patched `requests`, `urllib3`, `certifi`, and `cryptography`; installed versions are requests 2.34.2, urllib3 2.8.0, certifi 2026.10.23, cryptography 50.0.2, pip 26.2.2 and websocket-client 1.9.2. `pip check` is clean; `pip-audit` against both the installed environment and requirements reports **no known vulnerabilities**.
- Bandit scan: 0 high-severity findings. Two medium findings were context-reviewed: the URL opener uses a hard-coded loopback dashboard URL, and the flagged `/tmp` contract path is read-only input, not a temporary-file write. Most low findings are test assertions or legacy exception-handling patterns; they are recorded for targeted follow-up rather than blindly suppressed.
- Draft dependency-remediation PR **#395** is open, not merged; all 27 workflow runs completed successfully, including Dependency Security Audit. Draft checkpoint/ops PR **#396** is open, not merged; all 26 workflow runs completed successfully. No unrelated working-tree changes were committed or discarded.

## Remaining acceptance blockers — do not mark full operational acceptance yet
1. **Off-host backup and restore:** no approved remote backup destination or credentials/configuration were present. The local encrypted/off-host backup requirement cannot be completed safely without a user-approved destination/key. The local backup is not a substitute for off-host disaster recovery.
2. **External alert delivery:** monitoring currently writes state-change alerts to the local journal. No approved email/webhook/notification destination is configured, so external delivery has not been claimed.
3. **Exact release reproducibility:** the existing working tree contains pre-existing modifications, deletions and untracked files. The dashboard runs from `/opt/hes-trade-agent/current`, while several data/learning services launch scripts from `/opt/hes-trade-agent`. Data is shared through the existing `current/data/forward` symlink, but this mixed code-source layout still needs reconciliation to one reviewed, immutable release SHA before release promotion; do not reset or clean the working tree to force it.
4. **Legacy collector lifecycle:** `hes-trade-agent-collector.service` remains disabled/inactive and must not be restarted blindly. Retire it or formally replace it only through a reviewed change after the canonical global-feed architecture and recovery tests are accepted.

## Next acceptance gates
- Supply an approved off-host backup target and encryption-key custody plan; run and verify a restore from that target.
- Supply/approve an external alert destination; test delivery and recovery notifications.
- Reconcile active service source paths to one clean, exact release SHA; run release CI/evidence gates on that SHA.
- Resolve legacy collector retirement in a reviewed change.
- Keep live execution, deployment and promotion blocked until these gates pass.

**Status:** Host security hardening, full OS patching/reboot, local restore drill, dependency remediation, application runtime checks and 456 tests are complete. **Full security/operational acceptance is still gated by off-host recovery, external alert delivery, and exact-release consistency.** This checkpoint does not authorize live trading or deployment.
