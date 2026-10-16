# HES Trade Agent — Master Checkpoint
**Date:** 2026-10-13  
**Checkpoint:** `TRADE_SEQUENCE_CONTRACT_AND_SAFETY_TESTS`  
**Disposition:** `HOLD — OFFICIAL SEQUENCE CONTRACT NOT VERIFIED`

## Operating rule
- Memory = project map and plan.
- GitHub = technical source of truth.
- Chat = conversation log.
- Continue forward from this checkpoint; do not repeat completed work unless new evidence contradicts it.

## User's current instruction
Find official, lockable evidence for the meaning of Tabdeal `trade.sequence`, then run the existing safety tests. Do **not** repeat the 42-record reconciliation. Consider only the two Toobit support replies as supplemental context. Keep the user report concise and simple, with minimal confirmation requests.

## Findings
1. The official Tabdeal API documentation (`https://docs.tabdeal.org/`) and official SDK WebSocket client (`https://github.com/Tabdeal-Exchange/tabdeal-python/blob/master/tabdeal/websocket_client.py`) support the existence of the general API/WebSocket protocol and the `special_margin/broadcast/` client base URL. They do **not** establish the inner `trade.sequence` field's uniqueness, ordering, contiguity, completeness, reconnect recovery, or cross-session comparability.
2. Therefore no authoritative, lockable semantic contract has been established. Keep the Tabdeal sequence semantic class `unknown/opaque`; do not infer missing trades from numeric gaps, do not deduplicate individual trades using this field, and do not compare it across sessions without an explicit reviewed capability.
3. Toobit reply 1: its `v` field was described as globally unique across markets and increasing but not necessarily contiguous for a pair; repeated/out-of-order observations may occur; after reconnect the last 60 trades are sent.
4. Toobit reply 2: if more than 60 trades are missed during disconnection, there is no historical REST endpoint or guaranteed full-reconciliation method; the trade topic does not guarantee lossless delivery. These statements apply to Toobit only and must not be generalized to Tabdeal.
5. The Toobit replies are design context only; they are not proof of Tabdeal protocol semantics.

## Existing relevant HES work (reported results, not a fresh test run in this checkpoint)
- PR #252 — [hash-pinned sequence capability registry](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/252). Its PR description reports 22 tests passed on exact head `6b63c71de2b08ccbbe9cc9c0691e45286a54d997`. Registry semantics remain unknown and the source snapshot is not sufficient to authorize production.
- PR #245 — [preserve opaque Tabdeal Futures sequence observations](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/245). Keeps unknown semantics conservative and prevents numeric gaps from being treated as proof of missing events.
- PR #243 — [prevent self-attested sequence contract bypass](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/243). An arbitrary URL/string must not unlock the production path while the reviewed source pin is unset.
- PR #253 — [preserve raw ingress and rejected frame evidence](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/253). Its PR description reports 36 tests passed on exact head `93e449bc4640cb8d4b5e5a0fa328e8f6e765fe95`. This validates tested code paths only; it does not prove source authenticity or complete delivery.
- No fresh safety test run was executed while preparing this checkpoint. Do not describe the previous CI results as newly rerun.

## Next actions — forward only
1. Inspect the current GitHub branch/PR heads and latest workflow results; do not assume the historical PR head SHAs are still current.
2. Identify the existing targeted safety tests for SEQ-001 through SEQ-016, registry scope/pin enforcement, self-attestation bypass, raw-ingress journal, and fail-closed behavior.
3. Run or rerun the relevant tests on the exact current commit where the available CI tooling permits; record the commit SHA, workflow/run ID, and actual result.
4. Seek an authoritative Tabdeal definition or written clarification specifically covering the `special_margin/broadcast/` inner trade schema, `trade.sequence` semantics, delivery/completeness, reconnect/replay behavior, and session scope.
5. If no authoritative contract is available, preserve a pinned copy of the official documentation/SDK source with retrieval metadata and content hashes as provenance evidence, clearly marked as **not proving sequence semantics**. Keep the production evidence pin unset.
6. Do not repeat the 42-record reconciliation; do not change historical records, Winners, thresholds, or evidence logic; do not perform feature extraction or Effective Evidence calculations; do not start/enable the collector or live observation; do not merge/deploy or authorize trading.
7. Continue to respect the already recorded blockers from PR #260/#263/#264: inferred exit linkage, independent source attestation/trust-root provisioning, session/run/probe lineage, and single-writer attribution remain unresolved.

## Current gate summary
- Official Tabdeal `trade.sequence` contract: **NOT VERIFIED**
- Release-controlled evidence pin: **UNSET**
- Sequence-based gap/identity capabilities: **DISABLED**
- Fresh targeted safety CI in this checkpoint: **NOT RUN**
- 42-record reconciliation: **DO NOT REPEAT**
- Live collector/observation/trading: **BLOCKED**
- Next checkpoint action: **inspect current exact commit and run targeted safety CI; pursue authoritative Tabdeal evidence in parallel**

---
This checkpoint records the state and next actions. It does not claim that the protocol contract is verified or that any production gate has passed.
