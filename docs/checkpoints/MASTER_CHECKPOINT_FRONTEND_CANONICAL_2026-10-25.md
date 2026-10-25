# Master Checkpoint — Canonical Frontend Candidate Location — 2026-10-25

## Durable answer
**Known candidate frontend location:** repository `beheshti2025hesam-prog/btc_tabdeal_public_test`, file `web/dashboard.py` on Draft PR #346. Signal Agent endpoint/panel integration is stacked in Draft PR #362.

Repository URL: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test

Candidate chart asset: `web/static/third_party/lightweight-charts/5.0.8/`.
Candidate core data path: `forward/native_ohlcv_v1.py` and `forward/native_ohlcv_feature_pipeline_v1.py`.

## Do not confuse candidate with production
- PR #297 -> #346 -> #362 is the intended review/dependency chain; all were open/draft/unmerged as last verified.
- PR #361 overlaps Signal Agent code and must not be independently merged with #362.
- Exact candidate head checked for PR #362: `5b5b26e92e9d0d4c167dc5af035245e90ccaece4`.
- Candidate GitHub CI checks passed for dashboard native path, browser render, Signal Agent regression, and contract. Live WebSocket smoke was skipped. CI is not production deployment evidence.
- Sole VPS checkout is `/opt/hes-trade-agent`, branch `feat/gateio-global-market-data-v1`, observed HEAD `b2466bc118217dcc6446498effe38181589ed2db`, dirty. It does not currently include the candidate `web/dashboard.py`. Preserve the dirty worktree; no reset/clean/merge or overwrite.
- Actual production deployment, approved runtime feed reachability, and target-runtime rendered chart/API parity remain UNVERIFIED/BLOCKED.

## Anti-duplication rule
Stop generic repo rediscovery. Treat the above as canonical candidate path. Reopen discovery only if new authoritative evidence arrives (new GitHub access, user-provided URL, deployment manifest, or newly found checkout). Do not create a parallel frontend.

## Release gates
1. Review and test dependency chain at exact current heads.
2. Resolve provider qualification and authorized runtime connectivity.
3. Isolated exact-SHA build and test.
4. Authorized browser evidence of chart/API parity on target runtime.
5. Controlled deployment plan with rollback/security validation.
Until all gates pass: HOLD / NO_TRADE_ONLY; no live execution.

Delivery target remains 2026-11-19.
DNA/Roadmap record: `docs/HES_DNA_AND_ROADMAP.md`.
