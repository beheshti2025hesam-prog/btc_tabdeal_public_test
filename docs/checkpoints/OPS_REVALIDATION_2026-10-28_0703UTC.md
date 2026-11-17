# HES Trade Agent — Operational Revalidation
**Captured:** 2026-10-28 07:03 UTC  
**Scope:** Read-only runtime verification on the existing single VPS.  
**Trading posture:** NO_TRADE_ONLY; execution, deployment, and promotion remain disabled.

## Fresh evidence

- Dashboard contract gate: **PASS, 15/15 checks**, zero failures.
- Full existing test suite: **456 passed** using `PYTHONPATH=/opt/hes-trade-agent .venv/bin/python -m pytest -q --disable-warnings --maxfail=1`.
- Active services: Gate.io public market data at 15m, 1h, 4h; read-only dashboard; strategy learning loop; paper evaluator; operational health timer. Legacy Tabdeal collector remains inactive.
- Canonical data source: `gateio_public_spot`; source reader: `global_market_data_reader_v1`.
- Candle endpoint: `/api/candles?symbol=BTCUSDT&timeframe=15m`; returned interval `15m`, 240 candles, latest closed candle close time `2026-10-28T06:59:59.999Z`, latest age about 163 seconds at capture.
- Candle and signal share input SHA-256: `eb53754bdbbff7ca6ff919699730af5458c0d974fac33aface5003ef1545e85b`.
- Signal route remains `BLOCKED / NO_TRADE`; `execution_enabled=false`. Market-data symbol mapping is verified, but `execution_instrument_mapping_verified=false`; this gate must not be assumed or bypassed.
- Git HEAD from both `/opt/hes-trade-agent` and `/opt/hes-trade-agent/current` is `060d0d36ae6140a03d9a74495bb3899637ed3827`. The release directory basename is `2e8d3859ef154b030e0965ad4479f3fad36ae4c0`, which differs from the actual Git SHA. Preserve the dirty worktree; do not reset or clean it. This naming/path discrepancy does not itself prove a code mismatch, but immutable-release consistency and rollback acceptance remain open.
- Root-only local backup at `/var/backups/hes-trade-agent/security-stability-postchange-20261028T063214Z` was rechecked. Both checksum manifests pass and the project/evidence archive can be listed. The directory is `root:root` mode `0700`; this is a same-host backup, not encrypted off-host disaster recovery.
- Correct health unit is `hes-operational-healthcheck.timer`; it is enabled/active. Last run completed successfully with `HEALTHY` at 07:00:57 UTC.

## Open acceptance blockers

1. **Email alert delivery:** no saved Resend integration existed. A one-time setup link was generated for integration name `hes-ops-email`; the user must connect a Resend API key and verified default sender on the protected provider page. Do not claim delivery until the setup completes and a real test email is received at `beheshti2025hesam@gmail.com`; verify alert, recovery, and delivery-failure behavior.
2. **Encrypted off-host backup:** no approved remote target or key custody was configured. Obtain an approved SFTP/object-storage destination and separate encryption-key custody; then verify a completed encrypted backup and a restore drill. Do not upload archives to an unapproved/public destination.
3. **Immutable release and rollback:** keep the dirty worktree untouched. Reconcile exact service code paths, build a reviewed immutable release from an explicitly selected commit, validate in staging, and prove rollback before switching active service definitions.
4. **Execution instrument mapping:** mapping from the canonical analysis instrument to the actual execution instrument remains unverified. Keep execution disabled until independent evidence proves the mapping.

No service restart/switch, merge, deployment, order placement, or live-trading enablement was performed. Delivery target remains 2026-11-19.