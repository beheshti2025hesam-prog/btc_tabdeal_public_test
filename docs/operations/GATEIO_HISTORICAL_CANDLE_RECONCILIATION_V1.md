# Gate.io historical candle reconciliation v1

**Scope:** Gate.io Public Spot BTC_USDT, persisted 1h and 4h closed-candle JSONL only.  
**Status:** Evidence-gated one-time correction; no automatic historical overwrite.

## Why this exists

The 2026-11-05 read-only reconciliation found six genuine numeric differences between the persisted Gate.io records and current public REST history: two 1h candles and four 4h candles. A formatting-only decimal difference is not a conflict; exact finite Decimal equality is already implemented by PR #446. These six rows differ numerically in close and/or base/quote volume.

The 1h collector repeatedly rejected the historical conflict before it could append new closed candles. That made the 1h reader stale and correctly blocked Strategy V2, Mother V2 and Precision Entry. The latest 2026-11-05 soak attempt failed on stale 1h data and is not accepted. Four earlier runs have explicit `passed=true` 24-hour summaries with all samples successful; those historical results remain valid and must be preserved, not relabeled as failed.

## Evidence contract

The reconciler is intentionally narrow:

- It only accepts the six pre-registered (timeframe, open_time) identities and their pinned old values.
- It fetches three independent 500-candle public REST snapshots per timeframe through the existing `GateioSpotKlineSource`.
- All three snapshots must have zero gaps and semantically identical closed-candle rows. Raw response bodies and SHA-256 values are retained.
- Every overlapping persisted row is compared. Any numeric conflict outside the six registered identities aborts the operation.
- Each registered old row must exactly match its pinned persisted values, and each new row must exactly match the pinned values observed in the 2026-11-04 research capture, the 2026-11-05 05:57Z REST probe, and the three new probes.
- The candidate retains every existing row, replaces only those six approved rows, and adds missing newer closed candles. It never shortens the historical series.
- The merged history must be strictly ordered, unique, and contiguous.

## Operator procedure

1. Run `python scripts/reconcile_gateio_historical_candle_conflicts_v1.py` from the immutable release. Default mode is **stage only**; it does not change live candle files or restart services.
2. Review the generated `data/archives/gateio-historical-candle-reconciliation-*/manifest.json`, original archives, raw REST snapshots, candidate hashes, six corrections, and added rows.
3. Stop `hes-global-market-data-gateio-1h.service` and `hes-global-market-data-gateio-4h.service`.
4. Apply the exact staged candidate with `python scripts/reconcile_gateio_historical_candle_conflicts_v1.py --apply --stage-dir <stage-dir>`. The script requires both services to be inactive and exact live-file SHA-256 values to match the stage manifest. A partial two-file replacement is rolled back from the byte-for-byte originals.
5. Verify the manifest reports `APPLIED`, live file hashes equal candidate hashes, and `global_market_data_reader_v1` accepts 1h and 4h with fresh contiguous closed candles.
6. Start both collectors. Confirm they append new rows without truncating history, and verify dashboard chart, Strategy V2 and Mother V2 all use matching canonical batch digests.
7. Only then start a fresh uninterrupted 24-hour soak. The soak unit uses `Restart=no`: any failed sample terminates that run and requires explicit investigation and manual restart. A later manual run archives the previous output under a neutral `.archive.<UTC timestamp>` suffix; it never relabels a prior successful run as an attempt. Any restart, failed sample, stale candle, gap, or digest mismatch invalidates that run.

## Durable history

The collector's REST fetch window (500 candles for 15m/1h/4h and 1,500 for 1m) is not a disk-retention policy. Normal operation validates a bounded 5,000-row tail and appends only new rows. A historical backfill reads the full file and uses an atomic sorted rewrite. Existing history is never truncated to the REST fetch window.

## Safety

- Gate.io Public Spot BTC_USDT remains the only canonical live market-data source.
- The collector is read-only; no credentials, account endpoints, orders or execution paths are used.
- Strategy, Mother, Precision Entry and signal authority remain blocked until the data, provenance and soak gates pass.
- The 24-hour soak is observation evidence only; it does not prove strategy edge or authorize live trading.
