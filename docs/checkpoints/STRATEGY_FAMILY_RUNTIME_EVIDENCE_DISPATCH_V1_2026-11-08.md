# Strategy-family runtime evidence and research dispatch — checkpoint

**Date:** 2026-11-08  
**Implementation base:** PR #480 head `cfd2783f9d3a5ee0e3c02e7d2436e5f30ea219e6`  
**Worktree:** `/opt/hes-trade-agent/.worktrees/strategy-family-confirmation-20261107`  
**Active release:** unchanged `f5d505567522555ee1be9c260e83085347515721`

## Delivered in the isolated worktree

1. **Canonical persisted Gate.io normalization** — extended `native_ohlcv_gateio_v1` with `from_persisted_global_rows`. It consumes the existing `global_market_data_reader_v1` rows only; validates source/symbol/timeframe, closed-candle boundary, OHLCV decimals and geometry, timezone-aware observation times, feed freshness, ordering and gaps; rejects fabricated trade-count/taker-buy fields; preserves gaps explicitly; and hashes the exact persisted row window. `fetched_at_ms` is the adapter's file-read time, while each original `observed_at` remains in the hashed payload.
2. **Range family evidence builder** — added `strategy_family_evidence_v1` and promoted the existing sweep/reclaim research policy from the dirty root checkout into the isolated feature worktree. It uses only 15m setup candles with 1h/4h context; filters all timeframes to the 15m setup close before taking the 240-bar evidence window; uses existing Wilder ADX14/+DI/-DI, MFI14 base-volume, RSI14, EMA50 and ATR14 calculations; derives 36-bar prior boundaries plus a disjoint 12-bar persistence window; and binds candidate/checks to exact source-window hashes. The 1m frame is intentionally ignored.
3. **Independent pipeline dispatch** — bumped `strategy_gate_pipeline_v1` to `v1.1.0`. Trend family confirmation delegates to the existing three-check confirmation policy; the existing Trend candidate/risk path is preserved. Range now has a separate eight-check research confirmation. A Range research confirmation is passed to the unchanged global Risk Gate, which rejects it; the unchanged 3R check is still applied. The final decision remains `NO_TRADE` and both execution flags remain false.
4. **Journal attribution** — the forward runner passes the actual persisted-reader read time into the pipeline, records family candidate/confirmation/evidence as top-level fields in the existing append-only decision event (and keeps the nested `gate_evidence`), and reports the pipeline version dynamically. The journal view exposes family candidate direction/state, family confirmation state, evidence status/hash and a separate family-confirmation gate stage. It fails closed on cross-family, candidate/evidence, or digest mismatches.
5. **Deterministic healthcheck test** — isolated the precision/paper-only test from the VPS's actual disk free percentage by mocking disk usage in that test only. Production disk-health checks are unchanged and still report real disk pressure.

## Verification

- Focused family/data/journal/healthcheck suite: **151 passed**, warnings treated as errors.
- Full repository suite: **1,240 passed + 82 subtests passed in 14.74s**, warnings treated as errors.
- `py_compile` on changed runtime modules and runner: passed.
- `git diff --check`: passed.
- No production service, release pointer, live data feed, Risk Gate policy, 3R threshold, execution adapter, or live-order setting was changed.

## Safety and status

- Gate.io Public Spot BTC_USDT remains the only authoritative market-data source.
- 15m remains setup authority; 1m remains downstream precision-entry refinement only.
- Range remains `RESEARCH_ONLY_NOT_ACTIVE`; its cost model is explicitly `ASSUMPTION_BASED`, not verified account fees/slippage.
- Trend/Range family contracts and dispatch are now connected in the feature worktree, but no raw family-specific resolved-outcome cohort/report producer has been connected yet. The family acceptance evaluator still requires separate >=100 resolved trades per family, strictly >90% in-sample and independent OOS win rates, positive expectancy, PF>1, verified fee/slippage evidence, and the global <=3 actionable-signals/day cap.
- No >90% win-rate claim is established. No strategy activation or real trading is authorized.
- Active release remains `f5d505...`; both `hes-strategy-paper-evaluator.service` and `hes-precision-entry-journal.service` were observed active. No deployment/restart occurred.
- The latest remote PR #480 head remains `cfd2783...`; this implementation has been verified locally on top of that head but has not been published to the remote branch or run through GitHub Actions yet.

## Next P0

Build the append-only family-specific paper outcome cohort using the existing decision journal and existing 15m paper resolver, then produce separate Trend and Range reports consumed by `strategy_family_evaluation_v1`. Keep assumed costs visibly unverified; do not promote or activate either family until the independent acceptance contract is met.

## Persistence / host note

- The isolated worktree is fully tested but remains uncommitted. `git add` was attempted once and the repository object database returned `insufficient permission`; no permissions or ownership were changed, and the working tree remains intact. Remote PR #480 has not been updated; publication requires explicit approval.
- Filesystem is 50G total / 40G used / 6.7G free (86% used). The production healthcheck's 15%-free threshold therefore legitimately remains WARN. Read-only usage inspection found about 6.1G under `/tmp`, 1.5G under `candidates`, 2.5G under `releases`, 1.3G under `/var/backups`, and 924M of Playwright browser cache. No deletion or cleanup was performed because old worktrees, release artifacts and backups may be needed for audit/rollback.
