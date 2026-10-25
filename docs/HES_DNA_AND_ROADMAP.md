# HES Trade Agent DNA & Roadmap — Canonical Frontend Location
Recorded: 2026-10-25
Status: candidate path verified; production deployment remains unverified.

## Canonical repository
- GitHub repository: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test
- Local VPS checkout: /opt/hes-trade-agent
- Repository role: HES data-foundation / market-data / trading-agent repository. It is not accurate to call the currently checked-out VPS tree a deployed production frontend.
- Candidate frontend entrypoint: `web/dashboard.py`
- Candidate chart assets: `web/static/third_party/lightweight-charts/5.0.8/`
- Candidate data/analysis contracts: `forward/native_ohlcv_v1.py`, `forward/native_ohlcv_feature_pipeline_v1.py`
- Candidate Signal Agent integration: PR #362, `GET /api/signal?symbol=BTCUSDT&interval=15m`, dashboard panel.

## Exact review chain and state
- PR #297: canonical Native OHLCV source/feature pipeline foundation.
- PR #346: dashboard using the same NativeOHLCVBatch for chart projection and descriptive features; local pinned Lightweight Charts build; read-only UI.
- PR #362: stacks Signal Agent endpoint/panel on the dashboard.
- These are Draft/open/unmerged candidates as last verified 2026-10-25. PR #361 overlaps Signal Agent files; do not merge it independently of #362. PR #340's competing dashboard implementation was closed unmerged.
- Candidate tested head for PR #362: `5b5b26e92e9d0d4c167dc5af035245e90ccaece4`.
- Reported exact-head CI: dashboard native path, browser render, Signal Agent regression, and Signal Agent contract succeeded; live WebSocket smoke was skipped because PR is Draft. CI on GitHub runners does not prove connectivity or rendered parity on the authorized VPS.

## Production acceptance blockers
1. The currently authorized VPS checkout at `/opt/hes-trade-agent`, branch `feat/gateio-global-market-data-v1`, HEAD `b2466bc118217dcc6446498effe38181589ed2db`, does not contain the candidate `web/dashboard.py` path; it is also dirty. Do not reset, clean, copy PR code over it, or merge blindly.
2. The selected Binance Spot feed has documented reachability problems from the authorized runtime; candidate PR notes record that VPS chart/feed parity is UNVERIFIED.
3. No approved production deployment/reverse-proxy mapping or authorized browser capture proves the dashboard is deployed.
4. Provider qualification remains open; no provider is approved merely because GitHub CI passed.

## Anti-rediscovery rule
Do not repeat generic repository searches. Canonical candidate location is this repository + `web/dashboard.py` in PR #346, with Signal Agent integration in PR #362. Reopen discovery only if new evidence contradicts this or new repository access/URL/deployment manifest appears. Continue work against this candidate and the existing PR dependency chain; no parallel UI.

## Roadmap
- Continue exact-head dependency/overlap review for #297 -> #346 -> #362.
- Resolve approved-runtime data-source reachability and provider qualification.
- Build/test the candidate in an isolated checkout at the exact SHA; then obtain authorized runtime browser/render evidence.
- Only after gates pass, plan controlled deployment with rollback and security checks.
- Keep live execution disabled (HOLD / NO_TRADE_ONLY).
- Delivery target: 2026-11-19.
