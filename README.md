# HES Trade Agent

**Product:** HES Trade Agent — an evidence-driven, multi-agent financial decision platform.
**Delivery target:** 2026-11-19.
**Runtime topology:** one production VPS; one existing dashboard and Mother orchestration path.

## Product boundary

HES is a decision-support and paper-trading system. A signal is not an order. The product must prefer a justified `NO_TRADE` over an unverified or low-quality trade.

- The user-facing Mother Command Center is **Free-First**, bounded and read-only. It reuses the existing Mother orchestrator; it is not a second trading brain or a shell/operations console.
- The dashboard is served on the VPS loopback interface (`127.0.0.1:8765`) and must not be exposed as a public listener.
- Supported UI locales are English (`en`) and Persian (`fa`), including RTL layout where appropriate.
- The product is paper-only until every release, risk, venue and performance gate is independently accepted.

## Canonical market-data and execution boundaries

- **Market analysis:** Gate.io Public Spot `BTC_USDT` is the single canonical source for live market data, candles, charts and indicator inputs. Reuse the existing Gate.io adapters, persisted feed and `global_market_data_reader_v1`; do not create a parallel candle source or silently fall back to another venue.
- **Execution:** market-data ingestion and order execution are separate concerns. An exchange/broker adapter may be used for execution only after its instrument mapping, account permissions and risk contract are verified and explicitly approved. Gate.io market-data selection does not imply that Gate.io is the execution venue.
- Venue-specific sequence fields are not generic IDs. Unknown uniqueness, ordering, contiguity, replay and reconnect semantics must remain unknown and fail closed until exact-scope primary evidence and tests support a capability.

## Non-negotiable safety invariants

- `execution_enabled=false`; `orders_placed=false`; `policy_mutation_enabled=false` unless a separately approved release changes those controls.
- Maximum signal allowance is **three per day**; this is a hard ceiling, not a quota or target.
- No live execution before explicit owner authorization and all source, strategy, confirmation, independent-risk, instrument-mapping, operational and recovery gates pass.
- A win-rate claim is prohibited until at least **100 eligible, resolved, closed paper trades** demonstrate **greater than 90%** on verified net-of-cost outcomes with independent out-of-sample evidence. Zero eligible outcomes means the rate is not calculable.
- No automatic threshold, strategy, risk or policy tuning to force a target metric.

## Documentation map

| Document | Purpose |
| --- | --- |
| [Mother Command Center contract](docs/checkpoints/MOTHER_CHAT_COMMAND_CENTER_CONTRACT_2026-11-06.md) | Scope, trust boundary, allowed interactions and non-goals |
| [Dashboard security, release and rollback runbook](docs/release/HES_DASHBOARD_SECURITY_RELEASE_ROLLBACK_RUNBOOK.md) | Deployment record, security checks and rollback procedure |
| [Sequence semantics registry guide](docs/protocol/SEQUENCE_SEMANTICS_REGISTRY_README.md) | Evidence-scoped protocol semantics; candidate status is explicit |
| [Immutable release manifest proposal](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/470) | Deterministic release-file provenance; remains unmerged until reviewed |
| [Encrypted backup/restore proposal](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/473) | Encrypted recovery workflow; remains unmerged until reviewed |

The Master Checkpoint in Notion is the project resume map, not a substitute for source code or immutable release evidence. GitHub commits, tests, manifests and runtime records are the technical source of truth. Keep volatile status and timestamps in the checkpoint; keep durable contracts and procedures in versioned repository documentation.

## Release and change discipline

1. Make changes on a focused branch; preserve the sole VPS's dirty working checkout. Never reset, clean, overwrite or deploy from an unreviewed working tree.
2. Review the exact diff and dependency/ancestry overlap before merging. A green CI run is necessary evidence, not release approval.
3. Run required CI and regression checks on the exact candidate SHA. Record workflow results, test counts, browser evidence and artifact hashes against that SHA.
4. Build an immutable release from the exact commit. Verify every tracked file against Git blobs and retain a manifest plus SHA-256 sidecar before making the release read-only and switching the `current` pointer.
5. Run the operational healthcheck, source/chart parity, browser checks, soak, security and recovery tests. Keep the previous immutable release and rollback record.
6. Promote only after explicit owner approval. Never let a delivery date waive a failed safety or evidence gate.

See the release runbook and the release-readiness checklist for the detailed acceptance sequence. Do not treat a draft PR, a candidate artifact, a historical test run or a successful deployment smoke as proof that every product gate is closed.

## Historical component note

The project began with a public Tabdeal BTC/USDT futures data-collection component. That legacy collector is not the canonical source for current live chart/indicator analysis and must not be reactivated as a fallback. Current live analysis uses Gate.io Public Spot BTC_USDT; any future venue ingestion requires its own adapter contract, evidence and release approval.

## Ownership / attribution

**HES Trade Agent**
**Owner:** Seyed Hesameddin Beheshti Shirazi
