# HES Trade Agent — Master Checkpoint
Date: 2026-10-17 (local time, +03:30)
Status: HOLD / NO TRADE
Source of truth: GitHub repository `beheshti2025hesam-prog/btc_tabdeal_public_test`

## Current verified checkpoint
- Research PR: [#308](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/308), open and draft.
- Exact PR head checked: `0457239ebb7e3a0b0f6441c222c9c35a5c63e2d6`.
- GitHub connector returned 26/26 completed successful PR-triggered workflow runs for that exact SHA.
- PR #308 review endpoint: 0 submitted reviews; inline review threads: 0.
- PR #282 remains open/draft at `e2f2c88075ea7856025f9d928b0abdbc8f9a9a50`; connector returned 27/27 successful PR-triggered workflow runs for that SHA.
- Latest documentation update commit: `388090cc0d3f0e60092c0a0825bb88f9a7384b61` (verify CI again for this exact new commit before treating it as green).
- Research note: [Binance BTCUSDT Spot vs USDⓈ-M Futures REST Schema Check](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/blob/research/binance-btcusdt-rest-schema-20261017/docs/research/BINANCE_BTCUSDT_SPOT_USDM_REST_SCHEMA_CHECK_2026-10-17.md).

## Evidence established
- Read-only Binance REST schema observations for BTCUSDT Spot and USDⓈ-M Futures: exchange metadata, recent trades, depth snapshots.
- Limited Spot historical/recent-trade overlap replay was reproduced for three records; this is not evidence of WebSocket replay guarantees.
- Official Spot/Futures WebSocket documentation fields and safe next-step protocol distinctions were recorded: Spot trade `t`, aggregate `a/f/l`, Spot depth `U/u`, Futures depth `U/u/pu`, and Futures `ps/st` where present.
- VPS diagnostics showed Binance hostnames resolving to `10.10.34.34` through configured and queried public resolvers, direct Binance HTTPS timing out, while GitHub HTTPS worked. This suggests DNS/egress filtering/interception but does not identify the responsible layer. No DNS, route, firewall, SSH, or service settings were changed.

## Not passed / must not be claimed
- No raw live WebSocket frames captured and hashed.
- No Spot snapshot-to-diff-depth bridge or deliberate gap-triggered resync proven.
- No Futures `U/u/pu` continuity or controlled disconnect/reconnect proof.
- No complete destructive-test suite proven (hash-valid invalid sequence, exact duplicate, same ID/different content, gap, disconnect, deletion/tampering, protocol/order changes).
- Source identity gate requiring exact byte-for-byte reconciliation of all 42/42 records and valid hash lock remains unaccepted until reproduced against the exact candidate commit.
- Independent review has not been submitted.
- Overall project completion of 70% is not verified; no defensible project-wide completed-vs-remaining denominator has been reconciled from this PR alone.

## Next actions (order matters; avoid rework)
1. Recheck CI on latest commit `388090cc0d3f0e60092c0a0825bb88f9a7384b61`.
2. Resolve VPS-to-Binance connectivity through an authorized network/provider path. Do not bypass controls or weaken host security.
3. Capture raw Spot `trade`, `aggTrade`, `depth` and USDⓈ-M `aggTrade`/diff-depth frames with endpoint, subscription, session ID, receive timestamps, and SHA-256.
4. Run destructive sequence and fail-closed recovery tests, including all cases listed above.
5. Recompute/compare the 42 evidence-record hashes byte-for-byte; verify lock integrity and negative cases.
6. Run CI on the final exact candidate commit and obtain independent review.
7. Keep PRs draft; do not merge, enable live collection, or trade until all required gates pass.
8. Only then calculate overall completion using a project-wide deliverable inventory and explicit acceptance criteria.

## Continuity rule
Memory = map; GitHub = technical truth; Chat = conversation notebook. Start the next chat by opening this checkpoint and the linked research note, verify the exact live PR head and CI, and continue from action 1. Do not redo completed REST schema/documentation checks unless new evidence invalidates them.
