# HES Trade Agent — Application Adapter Family v1

**Status:** catalog and guardrails candidate; no runtime provider selection or execution is introduced.  
**Baseline release inspected:** `786f9187ac326f27c243507ccbd297b34d01db1b`  
**Delivery target:** 2026-11-19

## 1. Design decision

HES uses a **family of domain-specific ports**, not one oversized universal adapter interface. Market-data, feature conversion, news ingestion, journaling, orchestration, and execution have different data shapes and side-effect risks. They therefore keep their existing typed contracts and are connected through explicit boundaries.

The new `adapter_family_catalog_v1.json` is an inventory and release guardrail only. It is **not** a plugin loader, runtime router, provider selector, or new data path. The validator reads Python AST and file metadata; it never imports provider modules or calls an exchange.

This preserves the existing implementation and avoids rebuilding the Gate.io collector, OHLCV reader, feature engine, dashboard, Signal Agent, Mother, news monitor, journal, or execution path.

## 2. Non-negotiable boundaries

1. **One canonical analytical source for the current BTC workflow:** Gate.io Public Spot. The Gate.io adapter maps the HES analysis key `BTCUSDT` to Gate.io's `BTC_USDT` pair. The same persisted closed-candle batch feeds chart and analysis.
2. **No silent provider fallback:** no dynamic discovery, automatic failover, browser-to-exchange requests, or alternate candle source is allowed in this release.
3. **Execution is separate:** the exchange/broker application remains the user's execution surface. Market-data adapters cannot read private accounts, submit orders, or mutate capital.
4. **No automated execution in v1:** `execution_enabled=false`, `orders_placed=false`. The current `core/execution/contract.py` is only a venue-neutral placeholder with DISABLED/SHADOW modes; there is no approved concrete exchange adapter in the active release.
5. **Sequence semantics are venue/channel-specific:** a numeric field name is not an identity, order, continuity, or gap guarantee. Tabdeal Broadcast `trade.sequence` is informational only under the 2026-11-04 clarification; it must not be used as a unique trade ID, ordering authority, or gap detector.
6. **No adapter may self-authorize:** capability claims need exact product/endpoint/channel scope, primary-source evidence, pinned hashes, tests, and review appropriate to the side effect.

## 3. Existing adapter family inventory

| Adapter | Responsibility | Catalog status | Boundary |
|---|---|---|---|
| `market-data.gateio.spot.ohlcv` | Public Gate.io Spot candles | Active | Canonical analytical source; exact native OHLCV contract and symbol map |
| `analytics.native_ohlcv_to_features` | Native OHLCV to existing feature candles | Active | Pure conversion; retains source digest and gap context |
| `strategy.gateio.evidence-provider` | Strategy/confirmation evidence from validated Gate.io batches | Active component | Evidence only; no market fetch or order side effect |
| `journal.decision-to-forward` | Decision result to the existing forward journal schema | Active component | Mapping only; no future outcome fabrication |
| `journal.signal-to-learning-ledger` | Signal decision to the existing append-only journal | Active component | Deterministic identity, hash provenance, idempotent exact replay |
| `news.public-rss-atom` | Public RSS/Atom source adapter | Active component | Bounded public reads; context only |
| `news.gateio-announcements` | Gate.io announcement source adapter | Active component | Bounded public reads; context only |
| `mother.precomputed-specialist-port` | Existing specialist evidence into Mother | Active component | Deterministic control-plane adapter; not a second agent or strategy engine |
| `execution.venue-neutral-port` | Future execution port | Interface only | No concrete venue implementation; execution remains OFF |
| `market-data.binance-native-fixture` | Historical native OHLCV parser/source | Fixture only | Not the selected analytical source |
| `market-data.tabdeal-legacy-trade-frame` | Legacy read-only trade parser | Legacy disabled | Not a candle/chart/indicator source; sequence field is not authority |
| `protocol.sequence-semantics-registry` | Exact-scope sequence capability registry | Candidate, not wired | Must not influence live paths until separately accepted |
| `collector.forward-observation-bridge` | Legacy forward-observation handoff | Disabled | Default-deny until a separate wiring and sequence review |
| `transport.binance-spot-kline-stream` | Historical Binance stream transport | Fixture only | Not part of the Gate.io runtime path |

The catalog records module paths, public symbols, contract versions, status, side effects, capabilities, and evidence references. Its validator checks that the declared symbols and evidence files still exist.

## 4. Important cleanup found during the audit

The release contained `core/feature_engine/boundary.py`, but that file imported `core.feature_engine.adapter` and `core.feature_engine.temporal`, neither of which exists in the active release. A repository-wide reference search found no caller other than the broken boundary file itself.

The current supported bridge is already `forward/native_ohlcv_feature_adapter_v1.py`, which converts the validated native OHLCV batch into the existing feature engine. Restoring the old adapter and temporal modules would resurrect a second, stale conversion path. The obsolete, unreferenced boundary file is therefore removed in this candidate rather than re-created.

## 5. Execution adapter decision — deliberately not implemented

A fuller typed `ExecutionAdapterV1` candidate already exists in PR #401, carried forward from PR #366. Its contract includes submit/query/cancel/open-orders/positions/account reconciliation, evidence-pinned capability readiness, and ambiguous-submit handling. PR #401 itself records that exact-head VPS regression and GitHub Actions are pending on its rebased stack and that it is stacked on PR #398.

That candidate is not part of the active release and is not an approved concrete exchange integration. **Do not copy or recreate it.** If automated execution is ever explicitly approved, first restack and review the existing candidate against the then-current mainline, select a venue/product, prove official instrument and order lifecycle semantics, and complete paper/shadow, reconciliation, security, and owner-approval gates. This catalog does not authorize any of those actions.

## 6. Extension protocol for future markets and venues

A future adapter is added only when all of the following are true:

- A specific market profile is selected: venue, product, symbol, endpoint/channel, interval, and intended use.
- The official provider contract and permitted use are recorded with retrieval date, source snapshot hash, and relevant excerpt hash.
- The adapter implements the existing domain port where one exists; a new port is justified only when no current contract fits.
- Native values, decimal precision, source timestamps, closed/finality rules, symbol mapping, and unavailable fields are preserved explicitly.
- Freshness, gaps, duplicate/replay, schema drift, reconnect/reset, timeout, rate-limit, and malformed-payload behavior are covered by deterministic fixtures.
- The adapter is registered with a unique identity and an explicit status; candidate/fixture/legacy adapters cannot silently become active.
- No market-data provider is used as proof of execution readiness. Execution instrument rules, fees, funding, margin, protective orders, client-order idempotency, and fill reconciliation are a separate evidence gate.
- A source outage fails closed. The system does not silently switch provider, symbol, product, or timeframe.

## 7. Long-horizon maintenance controls

- Version contracts and catalog revisions; never silently change the meaning of a field.
- Keep raw-response/source hashes and small representative fixtures beside the evidence.
- Run the catalog validator and adapter contract tests in CI.
- Re-verify official docs on a schedule and when an endpoint/schema/changelog changes.
- Preserve backward compatibility through explicit deprecation windows and migration notes.
- Keep provider secrets outside code, logs, catalog files, and chat.
- Keep recovery bounded and auditable; an adapter must not restart unrelated services, alter policy, or place orders.
- Treat this catalog as an inventory, not a runtime source of truth for secrets or account permissions.

## 8. Acceptance boundary

The catalog is complete for describing the **existing v1 adapter family** and enforcing its current safety invariants. It does **not** claim that every asset class, venue, broker, or execution workflow is production-ready. Current production scope remains Gate.io Spot BTCUSDT analytical data, the existing read-only/paper application, and manual execution in the separate exchange/broker application. Multi-market and automated execution remain future, separately gated extensions.

Run the validator from the repository root:

```bash
python3 scripts/validate_adapter_family_catalog_v1.py
pytest -q tests/test_adapter_family_catalog_v1.py
```
