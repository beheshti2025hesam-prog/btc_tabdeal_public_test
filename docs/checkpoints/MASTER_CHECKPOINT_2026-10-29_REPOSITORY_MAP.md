# HES Trade Agent — Master Checkpoint: Repository Map
**Date:** 2026-10-29  
**Target application delivery date:** 2026-11-19  
**Status:** Repository identified as the canonical *currently evidenced project/data-foundation repository*; production-app repository identity and release readiness are NOT yet proven.

## Canonical repository currently evidenced
- Repository: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test
- Default branch used for this checkpoint branch base: `main`
- Verified README path: `README.md`
- README blob SHA observed: `b42ca7a1666cba9151c65ad37e6304945e87e16c`
- README describes this as the first Tabdeal BTC/USDT futures market-data collector for HES Trade Agent. It explicitly says this component does not use Binance, does not require a Tabdeal API key, does not access balances, does not place orders, and does not trade.
- Therefore, treat this repository as the verified HES project/data-collection repository, NOT automatically as the complete production application repository.

## Existing paths / references to reuse (do not rebuild without evidence)
- `README.md` — project identity and the current collector's scope.
- `web/dashboard.py` — referenced in project PR discussions as an existing dashboard path; verify on the selected branch before editing.
- `NativeOHLCVBatch` — referenced as the canonical OHLCV data contract in prior project work; locate and inspect its actual implementation/tests before changing anything.
- PR #297 — data-contract / canonical OHLCV infrastructure reference: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/297
- PR #346 — candidate dashboard/front-end work, NOT an approved release: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/346
- PR #354 — related UI work reference: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/354
- PR #365 — Gate.io data-path work reference: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/365
- PR #375 — existing dashboard/chart-data integration reference: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/375
- PR #386 — release-readiness / documentation work reference: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/386
- The above PRs are references for investigation, not proof that they are merged, passing, or production-approved. Verify live state and exact commit SHA before relying on them.

## Previously referenced documentation paths — existence not confirmed
- `docs/RELEASE_READINESS.md`
- `docs/checkpoints/MASTER_CHECKPOINT_2026-10-26_RELEASE_READINESS.md`
Attempts to fetch these exact paths from the default branch returned 404. Do not assume they exist at those paths; search the repository and PR branches for their actual locations before editing or recreating.

## Anti-reinvention rules
1. Inspect the current repository, branches, existing modules, tests, and PR diffs before implementing anything.
2. Reuse the existing frontend/dashboard and canonical market-data contract where verified. Do not create a parallel app, parallel OHLCV contract, or duplicate market-data pipeline.
3. Keep market-data/analysis sourcing separate from exchange execution adapters. Do not add sequence reconciliation unless a documented execution-critical requirement proves it necessary.
4. Never promote PR #346 or any candidate PR to approved/production status without exact-SHA checks, required CI/tests, artifact/provenance checks, and explicit release gates.
5. No live trading or deployment permission is implied by this checkpoint. Maintain HOLD / NO_TRADE_ONLY until the release and safety gates pass.

## Next required discovery gates
- Identify the real application repository/production entry point, using repository metadata, imports, deployment manifests, and live runtime evidence rather than names alone.
- Verify whether `web/dashboard.py` and `NativeOHLCVBatch` exist in the chosen branch; identify their tests and callers.
- Inspect PRs #297, #346, #354, #365, #375, #386: state, head/base SHAs, changed files, CI, merge status, and overlap; do not merge as a shortcut.
- Verify the one authorized VPS and runtime target; do not assume a second VPS.
- Complete release documentation, reproducible build/test steps, configuration and secrets guidance, rollback/recovery, health checks, and security checklist only after inspecting existing documentation and improving it rather than duplicating it.
- Target delivery date remains 2026-11-19. This is a planning target, not a claim of readiness.

## Truthful status
The README was fetched from the default branch. The checkpoint is intentionally being added on a separate documentation branch for review; it does not alter the default branch or approve a release.
