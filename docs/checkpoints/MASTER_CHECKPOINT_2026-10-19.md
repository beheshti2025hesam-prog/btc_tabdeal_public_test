# HES Trade Agent — Master Checkpoint
**Date:** 2026-10-19  
**Disposition:** HOLD / NO_TRADE_ONLY  
**Operating model:** Memory = project map; GitHub = technical source of truth; Chat = conversation log.

## Governing project DNA
- Use official exchange capabilities first; prefer native OHLCV candles when they match the target venue/product/chart.
- Keep the design simple and add only decision-critical checks.
- Treat sequence-like fields as opaque unless evidence defines exact venue/product/endpoint/channel/message scope and the required identity/order/continuity guarantees.
- Separate exact-payload replay from repeated opaque values; never infer missing events from numeric gaps without an explicit continuity contract.
- Fail closed on stale, malformed, contradictory, corrupt, or unauthenticated evidence.
- No promotion based only on a green dashboard. Exact-head tests, evidence lineage, and independent review are separate gates.

## Exact-head CI/review audit performed 2026-10-19
Repository default branch inspected at `4956cf519c445edd004fdd4e763bdb3347a7ada9`.

| PR | Exact head | Observed Actions runs | Result | Review state / caveat |
|---|---|---:|---|---|
| #245 opaque Tabdeal sequence | `e5e7e657af43ddb8b6e8152cf08d51850f01d687` | 26 | All returned runs completed successfully | No submitted reviews. Branch is behind current main by 19 commits; synchronize/rebase and rerun exact-head CI before promotion. Production registry pin remains deliberately unset and checked-in evidence registry is empty/unpinned. |
| #318 master checkpoint | `f3d8c1c12fe989d195b89131b56c88bc45edc92d` | 26 | All returned runs completed successfully | Draft documentation PR; does not itself close technical gates. |
| #325 operating principles | `ff780a2b2f41f41de833408156b6a46ad218c100` | 26 | All returned runs completed successfully | Draft documentation PR; no independent review evidenced. |
| #327 Binance native OHLCV | `264ad62f51dee485c8ab9e1053631929c6379e4b` | 27 | All returned runs completed successfully, including Native Binance OHLCV Adapter v1 run 39218587582 | Adapter is Binance-only, read-only. Its five-candle Spot `klines` vs `uiKlines` match is a smoke check, not Tabdeal chart acceptance or full raw HTTP capture. |
| #328 stale Tabdeal WebSocket callbacks | `f1536f39f48f81e04e5a6e9c70e5b25bc9c5e700` | 26 | All returned runs completed successfully, including Forward Integration Verification v1 run 39220590616 | Tests cover delayed callbacks after reconnect and after disconnect. No submitted independent review evidenced. No collector activation or deployment. |

The combined commit-status endpoint returned no status entries for these heads; the counts above refer to completed GitHub Actions runs returned by the workflow-runs endpoint. For #328, the exact-head Forward Integration job completed successfully; the separately named Wallex session-isolation workflow run 39211895824 is from an earlier commit and is not misrepresented as exact-head evidence.

## Technical conclusions
1. **Stale callback isolation:** PR #328 ties callbacks to the exact active socket object, revokes the active session before close, and guards frame normalization/handoff under a lock. Its deterministic tests inject prior-session `on_message` and `on_open` callbacks while a newer session is active and callbacks after disconnect; expected result is rejection with no downstream record.
2. **Sequence semantics:** PR #245 preserves native integer/string identity and requires a reviewed three-part evidence bundle (sequence contract, source completeness, source ordering). The code may stay fail-closed, but this PR must be synchronized with current main and independently reviewed before any promotion. Never pin a production registry using CI fixtures or self-attested evidence.
3. **Native OHLCV:** PR #327 preserves Decimal values, raw response hash, retrieval time, candle timestamps, and gaps; open candles are excluded. It does not establish Tabdeal's official native OHLCV endpoint/schema. Do not wire Binance data into Tabdeal strategy context.
4. **Principle documentation:** PR #325 records the resource-first/minimal-complexity rule. It remains a draft and should be reviewed/merged through normal controls, not treated as a runtime gate closure.
5. **CI recovery:** No failures were returned in the observed exact-head run sets. This is not a claim that every required external acceptance gate passed.

## Remaining blockers (do not silently close)
- No independent human review is recorded for PRs #245, #327, or #328.
- PR #245 is 19 commits behind current main and must be synchronized; then rerun exact-head tests and review the resulting diff.
- Production evidence-registry pin remains unset/empty; source-completeness and ordering/recovery semantics for Tabdeal `trade.sequence` remain unproven.
- Additional source inspection found `SourceEvidenceRegistryV1.resolve()` currently raises `SOURCE_EVIDENCE_REVIEW_PROVENANCE_UNVERIFIABLE` unconditionally after byte/scope checks; there is no authenticated review-record verifier/happy path. This is fail-closed (safe), but means a future registry pin alone cannot enable acceptance. Do not remove the guard without implementing and independently reviewing authenticated reviewer provenance.
- The SEQ-001…016 ledger on the research branch marks only some vectors mapped, many blocked, and scenario-level execution unverified; generic green workflows must not be counted as complete vector coverage.
- The exact-head workflow list for PR #245 did not include its dedicated `Opaque Tabdeal Sequence Evidence v1` job. Run 38420800963 passed that workflow on an older SHA (`f4bf19cb48c86a1f8fbaef7ea4afeb811773c9fd`), which is not transferable to current PR head `e5e7e657af43ddb8b6e8152cf08d51850f01d687`.
- Official Tabdeal native OHLCV endpoint/schema and same-chart parity remain unverified. Binance adapter is not a substitute.
- Wallex OHLCV research remains blocked for volume-dependent promotion: UDF volume was observed at exactly 2x summed public trade quantities across 99 closed bars; do not halve/normalize without authoritative clarification. Official Socket.IO transport reachability and production collector integration also remain unverified.
- No production-like crash/restart proof, forward observation acceptance, deployment authorization, or execution authorization is established by these CI runs.

## Next actions, forward-only
1. Synchronize PR #245 with current main in a dedicated branch/PR; preserve its current branch and evidence without force-resetting user work.
2. Map SEQ-001…016 from the uploaded exchange-semantics contract to named deterministic/property tests and record the exact test mapping; specifically distinguish opaque repeats, exact replay, documented identity conflicts, scope changes, reconnect epochs, timestamp units, and corrupt checkpoints.
3. Obtain authoritative Tabdeal clarification or official endpoint/schema evidence for the actual target chart; compare closed candles over matching symbol/timeframe/timezone and retain exact raw bytes and SHA-256.
4. Request independent review for #245, #327, and #328; do not self-approve.
5. Preserve `HOLD / NO_TRADE_ONLY`; no collector activation, deployment, account mutation, orders, or trading until all required gates pass.

## Provenance
- PR #245: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/245
- PR #318: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/318
- PR #325: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/325
- PR #327: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/327
- PR #328: https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/328
