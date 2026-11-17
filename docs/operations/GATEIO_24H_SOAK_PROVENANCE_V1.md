# Gate.io 24-hour soak: release-bound evidence v3

## Coverage

The read-only soak validates Gate.io Public Spot `BTC_USDT` closed candles on 1m, 15m, 1h, and 4h. The 1m feed is read through the existing `read_closed_candles('1m')` canonical reader, including its schema, source, closed-candle, OHLCV, alignment, continuity, and freshness checks. The 1m integrity timer and all four feed services must already be active.

The soak does not start or repair feed services. Its systemd unit depends only on `network-online.target`; missing feeds cause a fail-closed sample rather than being silently started by the soak itself.

## Provenance

Every sample and the final summary carry:
- `run_id` for one uninterrupted 24-hour run.
- `code_release_id` from `HES_RELEASE_MANIFEST_v1.json`.
- SHA-256 of the exact release manifest.
- SHA-256 of the exact soak script loaded from that immutable release.

The release manifest commit must match the release directory name. Missing or mismatched provenance stops the run. Samples also carry `execution_enabled=false` and `orders_placed=false`.

## Acceptance

A successful run requires at least 1,400 healthy samples over at least 24 hours. Any failed sample exits nonzero and prevents a passing summary. Auditors must group by one `run_id`, verify one consistent release identity across all samples, check 1m/15m/1h/4h presence, and reject runs with parse errors, gaps, stale candles, inactive services, or missing summary.

## Operational safety

The soak service uses `Restart=no` and does not auto-restart after failure. A new run archives the previous log before starting. Do not restart an in-progress soak just to pick up a new release; let it finish, then start a new run against the intended immutable candidate. This preserves the previous evidence and prevents mixed-release samples from being treated as one accepted run.
