# HES Trade Agent — Master Checkpoint Revision 27
**Captured:** 2026-11-03  
**Purpose:** Resume without duplicate work; evidence-first delivery tracking.  
**Canonical repository:** `beheshti2025hesam-prog/btc_tabdeal_public_test`  
**Delivery target:** 2026-11-19. **Chart acceptance target:** 2026-11-04 (at risk).

## Immutable architecture and operating constraints
- One VPS only. Reuse the existing deployed dashboard, collector, persisted reader, feature/strategy components, paper evaluator, journal and learning loop. No parallel implementation.
- Sole authoritative live market/candle/indicator source: existing Gate.io public Spot BTC_USDT/BTCUSDT persisted closed-OHLCV path, through `global_market_data_reader_v1`. The chart and analysis must use the same validated batch and retain its source identity/hash.
- Market-data acquisition is separate from order execution. Execution, if ever authorized, occurs only through a separately selected exchange/broker app/adapter after its own evidence and owner-approval gates. Gate.io market data does not authorize Gate.io execution.
- 15m is the setup/validation authority. 1m is only a precision-entry helper for an already-valid 15m setup; 1m cannot originate a trade independently.
- Maximum 3 candidate signals/day; no signal quota. If evidence is weak, emit NO_TRADE. A >90% win rate is an empirical target, not a guarantee; it must be measured on forward-only paper-trade outcomes with fees/slippage, sufficient sample size, and uncertainty reported.
- Preserve HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY. No live orders, no execution enablement, no unsafe deployment.

## Latest evidence observed during this checkpoint update
- PR #427 (full regression + sequence safeguards) is open, not merged. Earlier reported exact revision validation was 843 tests + 70 subtests green; do not treat that historical result as proof of the latest PR head until current exact-head checks are confirmed.
- A workflow-run query for commit `a49bfa8d87964b247c47b4090d827f47bfe4899c` returned successful runs for the listed workflows, but this SHA belongs to the sequence-registry candidate (PR #402), not PR #427. Do not conflate evidence across branches/SHAs.
- PR #416 is an open documentation-only checkpoint PR, not merged. This revision is being recorded on its existing branch; it does not authorize merge or release.
- PR #415 documents a read-only VPS dashboard verification and a successful existing-key SSH tunnel, but browser visual acceptance remains open.
- PR #423's Fed calendar candidate reports 40 targeted tests + 14 subtests and 834 full-suite tests + 70 subtests, plus a live VPS read-only probe. This is contextual News Radar evidence only and does not satisfy chart/E2E acceptance.
- Existing dashboard deployment notes document `hes-readonly-dashboard.service` at loopback `127.0.0.1:8765`, `/healthz` returning HTTP 200 with `NO_TRADE_ONLY`, `/api/candles` returning 240 closed candles and `/api/signal` blocked. These are prior recorded observations; re-check current state before relying on them.
- Attached exchange-sequence research is explicitly research-only and says not to infer uniqueness, monotonicity, contiguity, or cross-reconnect comparability from generic sequence-like field names. Unknown semantics must fail closed.

## Ordered remaining release gates (do not waive)
1. **Exact-head status:** inspect the latest PR heads and required checks; rerun checks if any code changed. Never mix CI evidence across SHAs/branches.
2. **Chart acceptance:** on the actual existing frontend/browser, confirm live Gate.io closed candles render, symbol/timeframe labels are truthful, stale/empty/error states are visible, and displayed candles match the canonical persisted batch/hash. Capture reproducible screenshot/pixel evidence and record exact app/runtime identity.
3. **Frontend-to-analysis E2E:** prove the same canonical batch feeds chart and read-only analysis/signal endpoint; test missing/stale/corrupt data, unsupported timeframe/symbol, source mismatch, reconnect, and service restart. Missing evidence must yield NO_TRADE, not a fallback source.
4. **One-VPS operational evidence:** verify active service state, process/runtime hashes, health endpoints, feed freshness/continuity, disk/log persistence, and restart/recovery behavior without resetting a dirty checkout or disturbing an active soak. Preserve raw evidence and hashes.
5. **Paper-trading evaluation:** append-only journal with timestamp, input batch hash, candidate/rejection reasons, entry/SL/TP and expiry; evaluate both rejected and accepted setups against fees/slippage and a fixed outcome horizon. No retrospective tuning or cherry-picking. Report sample size and confidence, not just win rate.
6. **Safety evidence:** prove no order-capable route from dashboard/agent, kill-switch/NO_TRADE behavior, idempotency/reconciliation prerequisites for any future venue adapter, SSH key-only access and firewall remain intact. Execution remains OFF.
7. **Checkpoint/release decision:** update this file with exact commands/results, timestamps, hashes, links, and pass/fail for each gate. Do not mark complete on intention or old reports alone.

## Immediate next action
Prioritize the browser visual acceptance and chart-to-analysis same-batch E2E using the existing dashboard path; then perform a read-only operational/safety recheck on the sole VPS. If a step requires interactive access or a user-held device not exposed to the connected tools, report only that exact step and provide the shortest user-side action—do not claim access that was not actually exercised.

## Status
**HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY.** Chart acceptance, exact-head verification for open candidates, current 24-hour continuity evidence, browser E2E, and current operational/safety recheck are not all proven complete. No claim of >90% paper win rate is established by this checkpoint.
