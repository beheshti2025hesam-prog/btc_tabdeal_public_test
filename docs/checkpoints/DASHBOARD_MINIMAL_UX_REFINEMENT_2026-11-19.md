# Dashboard Minimal UX Refinement — 2026-11-19

## Objective
Keep the HES dashboard visually quiet and easy to scan. The interface should expose only the essential controls and high-level status; detailed evidence remains available on demand.

## Changes in this candidate
- Primary navigation reduced to Market, Entry, Strategy, and Command Center.
- Indicators, Mother diagnostics, news, safety, journal, and documentation remain available in collapsed disclosure panels; no underlying capability or evidence is removed.
- Market controls and metric captions shortened (Pair, TF, Refresh, Last close, UTC, Volume, Candles).
- Secondary section headings shortened while preserving full names for assistive technology.
- Applied a restrained dark visual system, consistent spacing, compact panels, responsive mobile behavior, and visible keyboard focus.
- Updated the original HES monogram asset with green and red candlesticks. The same SVG remains the dashboard header mark and favicon.
- Browser test now reads the documentation catalog version dynamically rather than hard-coding a stale version.

## Non-goals and safety
- UI-only. Market data, indicator calculations, strategy logic, Mother orchestration, risk gates, journal semantics, API contracts, and execution paths are unchanged.
- Dashboard remains read-only / `NO_TRADE_ONLY`; no account access, order submission, or policy mutation was added.
- No new paid service or runtime dependency.
- No production deployment or service restart performed.

## Acceptance gates
- Full repository CI must pass on the exact PR head.
- Browser test must pass desktop, mobile, Persian RTL, and English/German/French LTR checks.
- Confirm secondary panels default closed and open on demand.
- Inspect screenshots and verify the HES SVG logo is served and visible.
- Keep the PR draft and do not merge/deploy until all checks pass.

## Current candidate
- PR: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/552
- Branch: `feat/dashboard-minimal-ux-mainline-v2-20261119`
- Initial head: `9235c8247587b0c767c904aca2e1f0a89460a480`
- CI: running; acceptance not yet granted.
