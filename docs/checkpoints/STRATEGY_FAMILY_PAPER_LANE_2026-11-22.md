# Strategy-family paper lane checkpoint — 2026-11-22

## Root cause

The live Mother runtime's Signal specialist used only `strategy_policy_v2` (the strict 20-bar breakout policy). `strategy_family_router_v1` only identified a family; it did not generate candidates or feed them into Confirmation/Risk. Consequently, valid trend/range family evidence could not reach the specialist chain and the Mother signal remained `NO_TRADE` with `NO_CONFIRMED_20_BAR_BREAKOUT`.

## Implemented in isolated branch

- Added `forward/strategy_family_paper_lane_v1.py` to reuse the existing universal indicator engine and indicator-family evaluator over validated closed Gate.io BTC_USDT 15m/1h/4h candles.
- Wired the lane into Mother Signal, Confirmation, Risk and Decision specialist evidence; surfaced the lane in `/api/mother` as `strategy_family_paper_lane` and added a visible, four-language-labeled Mother-panel summary.
- Reconstructed the exact active dashboard brand baseline (`e8118c555e925ce80928b93e99a1734ef83a6749`) in the isolated release branch, including its two source-file brand edits and four untracked logo/checkpoint assets, so the candidate release preserves the active HES logo.
- Added a distinct `PAPER_SHADOW_ACTIVE` state. Live router activation remains locked/research-only. The family lane has no decision authority, no risk bypass, no execution, no orders and no capital mutation.
- The lane passes Trend candidates through the existing independent opportunity/structure confirmation and risk checks. It requires valid 3R geometry and uses simulation-only sizing assumptions. The legacy indicator-family Range variant is filtered; Range v2 stays research-only with no Mother candidate authority.
- Missing/unready News Radar context and high-impact news vetoes block confirmation and reject risk. The 1m feed remains precision-only.
- Preserved the legacy Strategy V2 final policy gate and `PaperExecutionGateV1`; neither is auto-activated by this change.
- Added focused unit and Mother integration tests, and updated project DNA and operations documentation.

## Evidence

- Full test suite: **1,626 passed, 84 subtests passed** (exact isolated branch worktree).
- `git diff --check`, Python compile checks, and `node --check web/static/dashboard.js` passed. The active HES official emblem/logo assets and their current footer/header contract are now tracked in the release source; legacy brand assertions were aligned to the deployed logo.
- Live read-only Gate.io snapshot: DOWNTREND across 15m/1h/4h; one `trend_confirmation` SHORT candidate; 3R geometry; bearish structural event and base confirmation/risk checks passed.
- Current live News Radar carried `HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION`; final lane state was `BLOCKED_NEWS_VETO`, Confirmation `UNCONFIRMED`, Risk `RISK_REJECTED`. Mother final decision remained `NO_TRADE`.
- Controlled no-news-veto test: family candidate passed Confirmation and Risk, Mother consensus resolved SHORT, while final decision stayed `NO_TRADE` due the separate live policy-activation boundary.
- `MotherAuditWitnessV1` verified the runtime response in both live-news and controlled no-veto cases.

## Promotion boundary

This checkpoint records code and test evidence only. It does not activate the live policy/ruleset, authorize a live trade, or enable the paper-execution gate. The dashboard-only release is based on the exact active dashboard brand baseline and must pass its immutable release manifest, runtime smoke test, and health checks before pointer promotion. The shared `/opt/hes-trade-agent/current` pointer and all market-data/evaluator services remain untouched; only `/opt/hes-trade-agent/dashboard-current` may be changed for this dashboard-only release.

## Production deployment — 2026-11-22

- GitHub source PR is scoped to the Mother family lane and panel; the official HES logo remains present in the deployed immutable dashboard release, while its binary asset overlay is kept outside this PR.

- Active dashboard release: `7e06c9c73eb26a7ade12d7c14e90466bdca5c6da`.
- Manifest: PASS, 791 files checked; SHA-256 `9b489cced6d8f0ceeb17ea79243182945474e01840c280cf1099d13e19046dae`.
- Only `dashboard-current` was switched. Shared `current` stayed on `4c9a0f30c9aac67c6d711fe3699f55820a9b1322`.
- Dashboard service is active. Live API, visible family-lane panel, JavaScript, official emblem and footer-logo checks passed. Audit witness verified.
- Current live state: `BLOCKED_RISK_VETO / NO_TRADE`; no Trend family candidate, Range remains `RESEARCH_ONLY_NOT_PROMOTED`, high-impact news veto active; execution/orders/capital mutation remain disabled.
