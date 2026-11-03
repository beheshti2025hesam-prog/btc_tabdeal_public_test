# HES Trade Agent — Master Checkpoint: Test & Evidence Validation
**Checkpoint date:** 2026-11-03  
**Scope:** Test coverage, evidence provenance, exchange sequence semantics, release gates  
**Delivery target:** 2026-11-19  
**Chart acceptance milestone:** 2026-11-04 — at risk until browser visual acceptance is recorded  
**Runtime policy:** HOLD / PAPER-TEST-ONLY / NO_TRADE_ONLY; execution remains OFF

## 1. Reuse-first baseline — do not rebuild
- Canonical application integration is merged as `388d4aa326ce4e678f63400f7ad4b53ae76b7b20` (PR #408).
- Existing dashboard, local chart assets, Gate.io Spot persisted feed and `global_market_data_reader_v1`, Strategy V2, Mother V2 evidence adapter/witness, News Radar and canonical journal are the paths to reuse.
- Gate.io public Spot `BTC_USDT` is the authoritative source for live market candles/chart/indicators. Execution is a separate system and is not authorized.
- The 1m precision-entry work must reuse the canonical feed/reader and must not become an independent signal authority; 15m setup validation remains authoritative.
- There is one VPS. Do not reset/overwrite the dirty working checkout or create a second runtime/app/collector.

## 2. Verified evidence already recorded
- PR #408 reports exact-head CI 32/32 successful; 817 tests and 70 subtests passed; clean VPS-side clone reproduction recorded.
- Browser evidence reports 239 closed candles with chart/API parity, matching displayed close and volume, no browser-to-exchange request or external chart CDN, and responsive widths 390/768/1440 without horizontal overflow.
- Gate.io Spot candle contract uses the documented eight-field payload and validates the closed-window flag. 15m/1h/4h feeds are wired to the canonical reader; do not invent trade-count/taker-buy fields where the public endpoint does not provide them.
- Single-VPS read-only dashboard runtime acceptance was recorded on 2026-11-02: HTTP 200 for tested read endpoints, POST journal returns 405, 285.6-second soak passed, journal hash unchanged, service loopback-only at 127.0.0.1:8765.
- PR #415 records a live read-only VPS recheck and existing-key Windows SSH tunnel. API/asset checks are not a substitute for browser visual acceptance.

## 3. Evidence-validation rules
- A test result is valid for a candidate only when tied to the exact commit SHA/tree under review; stale branch or nearby-commit green CI is not transferable evidence.
- Preserve raw evidence, source URL/endpoint, retrieval time, schema/registry revision, payload or artifact SHA-256, test command/run URL, and explicit PASS/FAIL/UNKNOWN.
- Unknown is not false and not pass. Missing evidence must remain UNKNOWN/BLOCKED; never infer a guarantee from a numeric-looking field or sample payload.
- Keep separate: source-contract verification, deterministic unit/property tests, integration tests, browser/UI acceptance, runtime soak, forward-only paper trading, and release authorization. Passing one layer does not imply another.
- Preserve failures and rejected cases. No threshold tuning to retroactively improve historical outcomes; evaluation must be forward-only and leakage-resistant.
- Do not report a win rate until a defined, sufficient forward-only paper sample has matured, including fees/slippage assumptions, unfilled/expired signals, overlapping positions, and explicit denominator.

## 4. Exchange sequence semantics — conservative contract
- Sequence-like fields (`sequence`, `seq`, `id`, `tradeId`, `u`, `updateId`) have no generic semantics. Bind each to venue + product + endpoint + channel/message type + field path + protocol version.
- Only documented/proven capabilities may drive behavior: exact-payload replay idempotency, event identity deduplication, within-scope ordering/contiguity, book range/link gap detection, checksum validation, and snapshot reset.
- Do not infer missing events from arithmetic gaps unless that exact channel contract grants contiguous range semantics. Do not compare IDs across symbols, products, channels, connections, or reconnect epochs without explicit evidence.
- Tabdeal public docs reviewed in the supplied research do not establish semantics for the inner `trade.sequence` on `special_margin/broadcast`, nor sequence linkage for its documented depth messages. Treat those fields as opaque/unknown; do not use them as gap detectors or conflict keys.
- On schema drift, missing required fields, corrupt checkpoints, stale feeds, broken documented book links, or unresolved conflicts: quarantine/stop dependent state mutation and remain NO_TRADE_ONLY until safe recovery/re-baselining.
- Preserve the supplied research document's 16 deterministic vectors (SEQ-001…SEQ-016) and property-based invariants as acceptance criteria. This checkpoint records criteria, not a claim that every vector has already been implemented or passed.

## 5. Release gates still open
1. **Browser visual acceptance:** explicitly inspect the real dashboard in browser at target widths and record evidence. Existing automated browser proof does not automatically close the separately tracked visual acceptance.
2. **Sequence-semantic implementation audit:** map existing registry/adapters/tests to SEQ-001…SEQ-016; identify only genuine missing coverage, reuse existing fixtures, and add regression tests only where absent.
3. **Exact-SHA CI:** run the full relevant suite on the final candidate head; attach run IDs and artifact hashes.
4. **Forward-only paper evidence:** collect enough out-of-sample observations before estimating win rate or signal frequency. The >90% win-rate / at-most-3-signals-per-day goal is an aspiration, not a proven result or guaranteed outcome.
5. **Independent strategy and risk approval:** still required; a Mother/strategy evidence report is not independent approval.
6. **Venue execution instrument mapping:** unverified. No exchange account/order path or live execution may be enabled.
7. **Runtime/reconnect soak:** runner tests are not proof of Gate.io WebSocket reconnect/recovery or a long authorized-runtime soak. Keep WS activation gated until the exact adapter/runtime path is validated.

## 6. Delivery control
- Fixed delivery target remains **2026-11-19**; chart acceptance target **2026-11-04** is at risk.
- Prioritize chart acceptance and release-blocking evidence before optional features. No broad refactor or duplicate implementation.
- Keep the one-VPS release immutable, preserve rollback lineage, and never deploy a candidate solely because CI is green.
- No merge, deploy, service mutation, collector activation, public ingress, or live order execution is authorized by this checkpoint.

## 7. Next non-duplicative actions
1. Inspect existing registry, adapters, and tests in the current canonical branch against SEQ-001…SEQ-016; produce a coverage matrix first.
2. Add only missing deterministic/property regression tests on a dedicated candidate branch; no new sequence engine or parallel registry.
3. Run targeted tests, then full exact-head CI; record failures and hashes.
4. Complete browser visual acceptance on the existing dashboard and save proof.
5. Continue paper-only forward observations; do not claim >90% win rate until measured on sufficient eligible outcomes.

## Status
**Evidence validation: IN PROGRESS — not fully accepted.** Existing CI/runtime evidence is substantial, but the remaining gates above prevent declaring this section mature or the trading system release-ready.
