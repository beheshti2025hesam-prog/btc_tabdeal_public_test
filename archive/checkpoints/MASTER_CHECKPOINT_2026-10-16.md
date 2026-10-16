# HES Trade Agent — Master Checkpoint
**Date:** 2026-10-16  
**Checkpoint:** `SEQUENCE_SEMANTICS_AND_JOURNAL_SAFETY`  
**Disposition:** `HOLD — TABDEAL SEQUENCE CONTRACT UNVERIFIED; LIVE PATH BLOCKED`

## Operating rule
- Memory = project map and plan.
- GitHub = technical source of truth.
- Chat = conversation log.
- Continue forward; do not repeat completed work unless new evidence contradicts it.
- A skipped workflow is not a pass. A green CI result is evidence for that exact commit only, not permission to deploy, collect live, or trade.

## Completed — checked
- [x] Read the previous checkpoint `archive/checkpoints/MASTER_CHECKPOINT_2026-10-13.md`; respected its instruction not to repeat the 42-record reconciliation.
- [x] Saved this checkpoint and the Binance smoke-test evidence to main. The evidence/checkpoint commit before this refresh was `785bcf68e8b036f07a69c226937c366dbceb5b5d`.
- [x] PR #282 was inspected at exact head `e8f6763c4e956270e2d13dc322bb32bca654e979`; all **27/27 checks** passed on that exact head. The PR remains a draft and unmerged.
- [x] Reviewed the official Tabdeal documentation entry point and official SDK WebSocket helper. They identify the `special_margin/broadcast/` helper/endpoint but do not establish the inner `trade.sequence` contract (uniqueness, ordering, completeness, replay, reconnect, or cross-session scope). Keep sequence semantics `unknown/opaque`.
- [x] Reused the existing locked independent source-identity evidence instead of repeating reconciliation: `evidence/source_identity_independent_verification_v1.json` and its lock. That existing artifact records the SHA-256/byte-length lock match and **42/42** records (14 prior + 28 current), with zero cross-group key intersection. This is existing locked evidence, not a new recomputation in this continuation.
- [x] Confirmed the Effective Evidence Audit completed successfully on main commit `785bcf68e8b036f07a69c226937c366dbceb5b5d`: [run 38873806036](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/38873806036). Its `effective-evidence-audit-v1` artifact exists with digest `sha256:554d35895265d0daeb813ce1329115cae97acb5adb0c3b011a2fa7e4de93d3a3`. The audit contract remains fail-closed; this is not a promotion signal.
- [x] The previous main commit `785bcf68e8b036f07a69c226937c366dbceb5b5d` finished with **22/22 checks successful and zero failures**.
- [x] Fixed the missing `DecisionResult.as_journal_record()` path and datetime-to-ISO normalization in PR [#292](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/292). Exact PR head `dd6dd6f8ab9777bfa2e7a40d0711d1b6300c7f77` passed **26/26 checks**; PR #292 was squash-merged as `023b471af6196b67b2b4608306d9b95596cbea97`. The risk-veto → `NO_TRADE` → append-only JSONL integration check passed. Superseded PR #291 was closed unmerged after its collector tests raced a concurrent main-branch update; the test was not weakened.
- [x] Post-merge CI for code commit `023b471af6196b67b2b4608306d9b95596cbea97` completed with **22/22 checks successful and zero failures**.
- [x] Read-only Binance public market-data smoke test completed and was recorded in `evidence/binance_market_data_smoke_2026-10-16.json`. Spot `BTCUSDT` and USDⓈ-M Futures `BTCUSDT` metadata, recent-trade IDs, prices, and timestamps were returned. Sample trade IDs were consecutive within each three-record sample only.
- [x] Recorded a Binance time anomaly: Spot `exchangeInfo.serverTime` was `1792139145381` (`2026-10-16T08:25:45.381Z`); USDⓈ-M `exchangeInfo.serverTime` remained around `1792137674761` (`2026-10-16T08:01:14.761Z`) across three calls — **1,470,620 ms (24m 30.620s) behind**. USDⓈ-M trade and ticker timestamps were current. Root cause is unknown; do not use that stale `serverTime` as a shared clock.
- [x] No live collector or VPS commands were started. No exchange orders, deployments, or production promotions were performed.

## Still open — do not tick until evidence exists
- [ ] PR #282 needs a fresh safety review and branch refresh before merge. GitHub compare reports it is **14 commits behind and 111 ahead of current main**, and it is still a **draft**. Its 27 green checks apply to the old exact head only; do not merge based on those checks.
- [ ] Obtain authoritative Tabdeal clarification for `special_margin/broadcast/` trade payloads, `trade.sequence`, event completeness, replay/reconnect behavior, and session scope. Keep production evidence pin unset and sequence-based identity/order/gap capabilities disabled until then.
- [ ] Investigate why USDⓈ-M `exchangeInfo.serverTime` is stale in the connector and verify the timestamp against a fresh raw/public API response or another authoritative clock. Public data retrieval works; cross-endpoint clock consistency is **not** verified.
- [ ] Verify private/authenticated Binance account access only if needed and authorized; it was not tested. A WebSocket stream was not opened or verified.
- [ ] Use only the project-authorized first VPS. The only SentinelX host currently listed is `vps-second-261930`; no host commands were run because that host violates the project constraint.
- [ ] Resolve remaining source-attestation, session/run/probe lineage, and single-writer attribution blockers before any live observation or promotion.

## Safety boundary
- [x] No historical records, selected winners, thresholds, or evidence logic were changed.
- [x] The 42-record reconciliation was not repeated.
- [x] No production promotion or live trading.
- [x] Current decision remains **HOLD / NO_TRADE_ONLY**.

## Next actions
1. Refresh PR #282 onto current main, review its full diff, and rerun all required checks; do not remove the draft status until the review is complete.
2. Resolve the stale USDⓈ-M exchangeInfo timestamp and preserve the result as evidence.
3. Obtain Tabdeal's authoritative sequence contract; do not infer guarantees from consecutive sample IDs.
4. Keep all live paths disabled until every required gate passes. Do not invent a release date or relax a gate to obtain a green dashboard.
