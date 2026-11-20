# HES Dashboard Minimal UX — Production Deployment Record

**Date:** 2026-11-19  
**Status:** DEPLOYED / RUNTIME-VERIFIED  
**Scope:** Dashboard presentation only

## Source and immutable release
- UI PR: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/552
- Merge commit: `17c17c79c5de13a53fa75f4bd5363963e71dd451`
- Exact merge-commit Actions checks: 24/24 passed.
- PR-head checks before merge: 34/34 passed.
- Immutable release: `/opt/hes-trade-agent/releases/17c17c79c5de13a53fa75f4bd5363963e71dd451`
- Previous dashboard release retained for rollback: `/opt/hes-trade-agent/releases/bcf0ef3e254eb1f90c80887f3de69e974cd9466d`
- Active pointer: `/opt/hes-trade-agent/dashboard-current` → new immutable release.
- Release manifest: `HES_RELEASE_MANIFEST_v1.json`; 781 tracked files verified against the exact Git commit.
- Manifest SHA-256: `92ca5c9c5498e2ca2c8711c803edd3f49a3ed7e028fc494338c9fef320d865af`

## Runtime acceptance
- `hes-readonly-dashboard.service`: active after controlled restart.
- Process working directory resolves to the new immutable release.
- `/`, `/api/candles`, `/api/strategy-v2`, `/api/journal`, `/api/mother`, and `/api/news`: HTTP 200.
- Retired legacy `/api/signal`: HTTP 410, fail-closed NO_TRADE.
- HES green/red SVG mark, four primary navigation links, and collapsed disclosure panels served by the active runtime.
- Security headers verified: no-store, nosniff, DENY, no-referrer, restrictive Permissions-Policy, and restrictive same-origin CSP.
- Canonical journal SHA-256 remained unchanged across post-deploy GET smoke checks: `81f42fd749f2f490128ca0993962862e449ae8f9ce9b00cedc92d0070900ac99`.
- Gate.io 15m/1h/4h/1m feeds, Strategy Paper Evaluator, Learning Loop, and dashboard services remained active.
- Health contract: `source=gateio_public_spot`, `source_reader=global_market_data_reader_v1`, `symbol=BTC_USDT`, `mode=NO_TRADE_ONLY`, `execution_enabled=false`, `orders_placed=false`.

## Safety and rollback
- No checkout reset/clean or overwrite of the sole VPS dirty working tree.
- No market-data, paper-evaluator, Learning Loop, risk, strategy, or execution service was restarted or modified.
- Dashboard remains loopback-only at `127.0.0.1:8765`; no public exposure added.
- Old immutable release retained; rollback is an atomic `dashboard-current` symlink restoration followed by restarting only `hes-readonly-dashboard.service`.
- Trading authorization remains HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY. No account access or live order execution enabled.

## Validation note
Exact-head CI covered the desktop/mobile and RTL/LTR browser checks. The VPS has no installed Playwright/browser binary, so post-deployment acceptance used live HTTP/API/static-asset/security-header and journal-integrity checks against the active process.
