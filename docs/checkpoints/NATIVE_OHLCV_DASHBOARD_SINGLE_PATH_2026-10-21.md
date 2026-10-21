# Native OHLCV dashboard single-path checkpoint — 2026-10-21

## Integration shape

- Branch: `feat/native-ohlcv-dashboard-single-path-20261021`
- Draft PR: #346
- Existing native source contract: `forward/native_ohlcv_v1.py`
- Existing descriptive consumer: `forward/native_ohlcv_feature_pipeline_v1.py`
- Existing chart entry point reused: `web/dashboard.py` (derived from the existing dashboard slice in PR #340; no parallel frontend).
- WebSocket transport/parser: `forward/native_ohlcv_stream_transport_v1.py` and `forward/native_ohlcv_websocket_v1.py`.

The dashboard chart projection and descriptive features are generated from the same validated `NativeOHLCVBatch`. WebSocket is transport/notification only: startup and reconnect call the existing REST source for history; each closed event is admitted only after exact comparison with the latest closed REST candle. No synthetic candles are generated. Decimal volume remains unchanged. REST/stream mismatch, stale data, malformed events, source failures, and invalid batches fail closed.

The stream profile is explicitly `binance / spot / BTCUSDT / 1m`. Other supported chart symbol/timeframe selections use the same native REST source and feature pipeline, but do not have a separate live WebSocket session in this slice. USDⓈ-M Futures is not mixed with Spot.

## Verification

- The focused exact-head workflow [Native OHLCV Dashboard Single Path v1](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39639914607) passed on code commit `d4171959150584734bda7847980682ee95d6ecdd` after the transport/reconciliation tests were added.
- All **30/30** pull-request workflows completed successfully on that same code commit. The checkpoint commit is documentation-only; it does not change the tested runtime code.
- Deterministic tests cover dashboard route safety, same-batch chart/features, WebSocket parsing, transport supervision, exact REST/stream parity, and fail-closed field mismatch.
- No orders, account endpoints, credentials, deployment, collector activation, or production worktree writes were performed.

## Live-runtime blocker

A fresh probe on the authorized VPS `vps-second-261930` found:
- `api.binance.com` resolves to a private address in this runtime and the HTTPS request fails with `Network is unreachable`.
- `data-api.binance.vision` resolves publicly but returns HTTP 451.
- `query1.finance.yahoo.com` responds, but Yahoo remains an unqualified reference feed and is not substituted into the approved Binance path.
- The current VPS checkout `/opt/hes-trade-agent` remains on `main` at `4956cf519c44` with pre-existing dirty changes; it was not modified.

Do not bypass the provider/network restrictions using proxy tricks or alternate hostnames. Restore an approved outbound route or provide an authorized runtime where the official Binance REST and WebSocket endpoints are permitted. Until a live REST/WebSocket smoke and same-window rendered-chart comparison are captured on the actual runtime, live acceptance is **BLOCKED** and the project remains `HOLD / NO_TRADE_ONLY`.

## Scope caveat

Binance Spot is a single venue's feed, not a documented multi-venue consolidated global OHLCV product. This integration follows the explicit Binance Spot profile for this slice; it does not resolve the separate global-provider qualification/licensing requirement and must not be labelled a global aggregate. The PR remains Draft/unmerged.
