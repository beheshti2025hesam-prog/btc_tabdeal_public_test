# HES encrypted backup and restore runbook v1

## Purpose and scope

The scheduled job creates an encrypted HES recovery bundle, not a block-level image of the VPS and not a complete Ubuntu installation backup. It preserves the HES application/release tree, selected host configuration, and HES state needed to recover the service and its evidence.

The archive is encrypted with GPG symmetric AES-256. The passphrase file is intentionally excluded from the archive and must be stored separately in a trusted password manager or offline recovery location.

## Included paths

- /opt/hes-trade-agent — application, releases, source checkout, data, journals, manifests and local evidence.
- /etc/ssh and /root/.ssh/authorized_keys — SSH server configuration/host keys and the root account's public-key allowlist. No SSH private user key is included.
- /etc/nftables.conf and /etc/systemd/system, plus optional /etc/xray and /etc/nginx.
- Optional HES state directories: Gate.io 1m integrity witness, operational health state, news monitor/dashboard state, legacy Tabdeal read-only snapshot state, SentinelX release manifests and runtime snapshots.
- Installed HES healthcheck helpers and the backup script itself when present.

## Deliberate exclusions and cautions

- /root/.config/hes-backup/passphrase is never archived. Keep the passphrase separate from every archive copy.
- /etc/sentinelx/config.yaml is intentionally excluded to avoid cloning a SentinelX host identity onto a replacement machine. Re-enroll SentinelX on a replacement VPS.
- SSH private user keys are not archived. The user retains their private key outside the VPS.
- This is not a full OS image: provision a compatible Ubuntu 24.04 base and reinstall required packages before restoring.
- /etc/ssh contains host keys. When restoring to a genuinely new host, decide whether to preserve or regenerate host keys; do not copy them blindly if the old host may still be online or was compromised.
- The dashboard/news state directory may contain an authentication token. It is inside the encrypted archive; rotate it if compromise is suspected.
- No offsite copy is created by this job. Offsite storage requires a separately approved destination and independently escrowed passphrase.

## Schedule and retention

- Daily at 02:30 UTC with up to 20 minutes randomized delay; persistent timer catches up after downtime.
- Keep daily archives for 7 days, Sunday weekly archives for 28 days, and first-of-month archives for 180 days.
- Before encryption, run the operational healthcheck and require at least 5 GiB free.
- After encryption, decrypt and validate gzip and tar readability, write a SHA-256 sidecar, and verify it with sha256sum -c.

## Restore procedure

1. Provision a clean, compatible Ubuntu 24.04 VPS and install the required base utilities (GPG, tar, gzip, Python runtime/dependencies, systemd and the HES-specific package prerequisites).
2. Obtain the encrypted .tar.gz.gpg archive and its matching .sha256 sidecar from the separately approved storage location. Obtain the passphrase from the separate password manager/offline recovery location; never place it beside the archive.
3. Verify the archive before decrypting:

       sha256sum -c hes-full-YYYYMMDDTHHMMSSZ.tar.gz.gpg.sha256
       gpg --batch --pinentry-mode loopback --passphrase-file /secure/path/passphrase --decrypt hes-full-YYYYMMDDTHHMMSSZ.tar.gz.gpg | gzip -t
       gpg --batch --pinentry-mode loopback --passphrase-file /secure/path/passphrase --decrypt hes-full-YYYYMMDDTHHMMSSZ.tar.gz.gpg | tar -tzf - >/dev/null

4. Inspect the file list and confirm it is the intended recovery bundle. Extract as root with numeric ownership, ACLs and extended attributes preserved:

       gpg --batch --pinentry-mode loopback --passphrase-file /secure/path/passphrase --decrypt hes-full-YYYYMMDDTHHMMSSZ.tar.gz.gpg | tar --numeric-owner --same-owner --same-permissions --xattrs --acls -xzf - -C /

5. Review SSH host keys and the restored /root/.ssh/authorized_keys; ensure the user's private key remains safely available outside the VPS. Regenerate host keys if this is a new host identity.
6. Reinstall/re-enroll SentinelX instead of restoring its old host identity. Reconnect the host and verify the remote administration path before closing the recovery session.
7. Run systemctl daemon-reload, inspect the restored units/timers, then run /usr/local/sbin/hes-operational-healthcheck. Verify the immutable release manifest, Gate.io feed identity/freshness, 1m witness, dashboard authentication, firewall, SSH and backup timer.
8. Keep all execution paths paper-only/NO-TRADE. Do not enable live order execution as part of restore validation.

## Verification status

The current VPS has passed encrypted archive creation, checksum verification, decryption/gzip/tar integrity checks, and a targeted restore smoke test of critical files from a previous archive. A complete disaster-recovery exercise on a replacement VPS has not been performed. Offsite backup and separate passphrase custody remain owner actions.
