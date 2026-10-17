# HES Trade Agent — Exchange Selection DNA & Wallex Continuation Checkpoint
Decision date: 2026-10-17. Status: USER-APPROVED ACTIVE CONSTRAINT.

## 1. Non-negotiable exchange decision
- Wallex is the active replacement exchange for current public market-data/WebSocket work.
- Tabdeal is NOT the active target. Do not resume, prioritize, or silently substitute Tabdeal in code, probes, examples, tests, roadmap steps, or operational recommendations.
- Repository name btc_tabdeal_public_test, legacy TabdealReadOnlyTransportV1, old evidence, and earlier checkpoints are historical identifiers, not authorization to keep targeting Tabdeal.
- Change this decision only if the user explicitly changes it. If Wallex has a blocker, report evidence and pursue the Wallex path or a clearly separated contingency; never silently revert to Tabdeal.

## 2. Anti-regression rule before every exchange-related task
1. Read this DNA and the latest Master Checkpoint.
2. Inspect the real repository tree, branch, exact HEAD SHA, and actual files; never infer files/adapters from the repository name.
3. State and confirm Wallex as the target in the plan before commands or edits.
4. Search Tabdeal references in the touched path; classify as legacy/history, fixture/test, or active implementation. Do not mass-rewrite historical provenance.
5. Make the smallest evidence-based change; run tests/CI against the exact resulting SHA.
6. Update GitHub technical evidence and the Notion Master Checkpoint with changes, SHA, CI/test results, hashes, unknowns, blockers, and next action.
7. If sources conflict, this user-approved exchange decision governs planning; GitHub remains the technical truth about what code actually does.

## 3. Wallex WebSocket evidence observed 2026-10-17
- Endpoint wss://api.wallex.ir/ws; channel BTCUSDT@trade.
- TLS/WebSocket handshake succeeded with HTTP 101 and validated Sec-WebSocket-Accept.
- Observed behavior: receive JSON session/heartbeat frame first, then send ["subscribe", {"channel":"BTCUSDT@trade"}].
- Fresh BTCUSDT trade frame received and cross-checked with public REST latest-trades.
- Fields observed: isBuyOrder, price, quantity, timestamp.
- Example: source timestamp 2026-10-17T10:27:40Z; receive timestamp 2026-10-17T10:27:40.849677Z; isBuyOrder=false (sell); price 81515.04; quantity 0.00472359; observed delay ~849.7 ms.
- VPS evidence: /srv/hes-evidence/wallex/wallex_ws_connection_checkpoint_20261017.json and /srv/hes-evidence/wallex/wallex_btcusdt_live_event_20261017T102740Z.json. Hashes and evidence were reported in GitHub #300; consult raw evidence for exact details.

## 4. Unknowns / no overclaim
Trade payload has no observed trade ID or sequence. Uniqueness, ordering, gap-free delivery, replay/recovery and deduplication remain UNKNOWN. VPS public reachability does not prove reachability from inside Iran during an international outage. One event does not prove uptime, completeness, or production readiness. Do not unlock evidence gates, enable collector, deploy, enable trading, or claim source completeness based on this probe.

## 5. Safety
Keep HOLD / NO-TRADE. Work was read-only: no keys, authenticated account calls, orders, account changes, deployment, or trading. Preserve raw frames, receive/source timestamps, hashes, and independent REST checks. Never fabricate missing identifiers, sequences, acknowledgements, or completeness guarantees. Architecture remains exchange-agnostic through adapters/configuration, but the current selected venue is Wallex.

## 6. Required continuation
1. Inspect actual tree and exact HEAD before edits.
2. Locate the real active market-data/WebSocket adapter; verify whether Wallex protocol is implemented in code. A VPS probe does not mean code integration is done.
3. Add/update Wallex adapter and protocol tests using provenance-preserving fixtures; separate fixtures from live smoke tests.
4. Test malformed frames, ping/pong, disconnect/reconnect, stale feed, duplicates, timestamp anomalies, no-event intervals, and recovery.
5. Keep missing trade identity/sequence as UNKNOWN; gate only features that depend on those semantics.
6. Run exact-head CI and update Master Checkpoint with SHA, changed paths, evidence hashes, test outcomes, blockers, and next action.
7. Deployment, collector promotion, evidence unlock and trading stay disabled until independent acceptance gates pass.

## 7. Durable source-of-truth convention
Project DNA/Memory = enduring decisions; GitHub = code/commit/test/CI technical truth; Notion Master Checkpoint = project map and continuation order; Chat = dialogue log.

Anti-regression acceptance: any future proposal to use Tabdeal as the active exchange without a new explicit user decision is a planning error and must be corrected before execution.