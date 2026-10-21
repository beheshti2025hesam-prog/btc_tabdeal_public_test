# Native OHLCV dashboard single-path checkpoint — 2026-10-21

## Integration shape

- Branch: `feat/native-ohlcv-dashboard-single-path-20261021`
- Draft PR: #346 (base retargeted to `feat/native-ohlcv-candle-sources-20261017`, PR #297; 13 changed files relative to that base)
- UI note: this PR carries the native-source implementation of `web/dashboard.py`; its UI follows the provisional PR #340 layout, but it is a different file revision. Do not merge the competing `web/dashboard.py` variants without reconciling the shared path.
- Existing native source contract: `forward/native_ohlcv_v1.py`
- Existing descriptive consumer: `forward/native_ohlcv_feature_pipeline_v1.py`
- Dashboard entry point: `web/dashboard.py`; one read-only UI route in this branch, using the native source and existing feature pipeline.
- WebSocket transport/parser: `forward/native_ohlcv_stream_transport_v1.py` and `forward/native_ohlcv_websocket_v1.py`.
- Chart runtime: `web/static/third_party/lightweight-charts/5.0.8/` contains the exact npm `lightweight-charts@5.0.8` standalone build, verified against the page's SHA-384 SRI value; Apache-2.0 `LICENSE` and upstream `NOTICE` are included. The page now serves this pinned asset locally and no longer requires `unpkg.com` or jsDelivr at runtime.

The dashboard chart projection and descriptive features are generated from the same validated `NativeOHLCVBatch`. WebSocket is transport/notification only: startup and reconnect call the existing REST source for history; each closed event is admitted only after exact comparison with the latest closed REST candle. No synthetic candles are generated. Decimal volume remains unchanged. REST/stream mismatch, stale data, malformed events, source failures, and invalid batches fail closed.

The stream profile is explicitly `binance / spot / BTCUSDT / 1m`. Other supported chart symbol/timeframe selections use the same native REST source and feature pipeline, but do not have a separate live WebSocket session in this slice. USDⓈ-M Futures is not mixed with Spot.

## Verification

- Exact-head integration tests on code commit `5dca985db88aa238cd81aa3478d718e56e16439b`: [Native OHLCV Dashboard Single Path v1](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39641474491) passed. All **31 executed pull-request workflows succeeded** on that head; one duplicate live-smoke run was skipped while the PR was Draft.
- **Live WebSocket smoke passed** on GitHub Actions runner: [run 39641190585](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39641190585). One closed `binance / spot / BTCUSDT / 1m` WebSocket candle matched the latest REST candle field-by-field; event delay was **67 ms**, REST history contained **239** candles with **0 gaps**, REST response SHA-256 `18df7471efe302d9d99608fa64a3dff8f3b6699ff6db4f9371835dac94360fed`, WebSocket payload SHA-256 `a85b4ae8dd0f10babba882e9fd9754bc768ea08ad123346152a87953be4588c5`. The evidence artifact is attached to that workflow run.
- [Native OHLCV Live Parity Evidence v1](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39641474260), [Native OHLCV Verification v1](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39641474566), and [Forward Integration Verification v1](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39641474363) also passed on the same head.
- Deterministic tests cover dashboard route safety, same-batch chart/features, WebSocket parsing, transport supervision, exact REST/stream parity, fail-closed field mismatch, local chart-asset delivery, attribution, and exact SHA-384 SRI integrity. Exact-head dashboard tests passed on `53a50b8e10ec27d9495f58bea6cb10a1b3febe74`: [run 39643675678](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39643675678).
- Important boundary: GitHub Actions live success does **not** prove the authorized VPS can reach Binance or that the dashboard has been deployed/rendered there.
- No orders, account endpoints, credentials, deployment, collector activation, or production worktree writes were performed.

## Live-runtime blocker

A fresh probe on the authorized VPS `vps-second-261930` found:
- `api.binance.com` resolves to private address `10.10.34.34` on this VPS and HTTPS times out; `fapi.binance.com` also times out. `data-api.binance.vision` resolves publicly but returns HTTP 451. Do not replace DNS or tunnel around the block without explicit network-operator approval.
- The root-owned `/etc/hes-trade-agent/coinapi.env` file exists and contains a `COINAPI_API_KEY` variable (presence only checked; the value was never displayed). A read-only authenticated request to CoinAPI returned HTTP 401. This proves authentication is not currently accepted; it does not yet identify whether the cause is key validity, account permissions, or product access.
- CoinGecko's public OHLC endpoint responds HTTP 200, but returns 48 candles at 30-minute spacing for a 1-day request. This is not a replacement for the required 1-minute path. Coinbase REST timed out; Kraken and Bitstamp returned HTTP 403; CoinCap DNS resolution and CryptoCompare TLS timed out. None of these was promoted to the approved source.
- The current VPS checkout `/opt/hes-trade-agent` remains on `main` at `4956cf519c44` with pre-existing dirty changes; it was not modified. No dashboard frontend was found in `/var/www` or `/workspace`, and nginx is inactive; port 443 does not complete a local TLS handshake.

Do not bypass provider/network restrictions using proxy tricks, alternate hostnames, or unapproved DNS changes. The authorized next paths are: (a) network-operator-approved access to official Binance REST and WebSocket endpoints, or (b) repair/confirm the existing CoinAPI credential and verify its permitted product/feed, or (c) qualify a licensed provider trial for the required OHLCV granularity and trading-use license. Kaiko remains the primary vendor to qualify and CoinAPI the fallback in [PR #344](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/344); neither is approved yet. Until an authorized provider is available and a same-window rendered-chart comparison is captured on the actual runtime, live acceptance is **BLOCKED** and the project remains `HOLD / NO_TRADE_ONLY`.

## Scope caveat

Binance Spot is a single venue's feed, not a documented multi-venue consolidated global OHLCV product. This integration follows the explicit Binance Spot profile for this slice; it does not resolve the separate global-provider qualification/licensing requirement and must not be labelled a global aggregate. The PR remains Draft/unmerged.
