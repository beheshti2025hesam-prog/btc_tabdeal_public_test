# Dashboard Minimal UX Refinement — 2026-11-19

## Objective
Reduce visual noise and make the existing HES Trade Agent dashboard easier to scan without creating a second frontend or changing trading behavior.

## Baseline verified
- Production dashboard service: `hes-readonly-dashboard.service`, active on the sole VPS.
- Runtime entry point: existing Python dashboard with local CSS/JS and vendored Lightweight Charts.
- Dashboard release inspected: `d2049427716037d74d5ad106df83b26201a789b2`.
- Market source remains Gate.io Public Spot; dashboard remains read-only and `NO_TRADE_ONLY`.
- Existing market-data, decision, strategy, risk, journal, Mother Agent, and execution contracts are outside this UI-only change.

## Design direction
- Dark, low-glare surface with restrained accent colors and consistent spacing.
- Stronger visual hierarchy; chart and key market metrics receive more space.
- Compact header, language control, navigation, toolbar, and status copy.
- Reduce repeated explanatory copy without hiding decision evidence or changing API payloads.
- Responsive metric grid and chart sizing for phones and desktops.
- Clear keyboard focus and reduced-motion support.
- Preserve Persian RTL, English LTR, German and French language behavior.

## Implementation
- CSS-only visual refinement in `web/static/dashboard.css`.
- No new runtime dependency.
- No HTML, JavaScript, backend, market-data, strategy, risk, or execution changes.
- Working branch: `feat/dashboard-minimal-ux-mainline-20261119`.
- Pull request: #539 (draft).

## Validation status at checkpoint
- Dashboard native-path workflow: PASS.
- Browser-render smoke: running at checkpoint time.
- Full dashboard repository regression: running at checkpoint time.
- Full regression and visual acceptance are not yet declared complete.
- No merge, production deployment, service restart, or live-execution change performed.

## Release rule
Keep the PR in draft and production unchanged until browser rendering, mobile/RTL visual review, and relevant regression checks pass. Deploy only through the established immutable dashboard-release and rollback process.
