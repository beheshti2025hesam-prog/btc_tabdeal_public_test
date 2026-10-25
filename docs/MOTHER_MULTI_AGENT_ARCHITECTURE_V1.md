# HES Mother / Multi-Agent Architecture v1

Status: **read-only integration candidate; not production-approved**.

## Goal and non-duplication rule

Mother is the control plane. It coordinates and audits existing specialist outputs; it is not a second strategy engine, data collector, risk policy, learning loop, frontend, or execution adapter. Existing code remains the owner of each calculation and contract. If a specialist already exists, extend its adapter or schema rather than reimplementing it.

The active dashboard signal path remains the canonical market-data entry point. It fetches one validated closed-candle batch per required timeframe and reuses its feature/strategy outputs. Mother receives the existing results; it does not refetch candles or calculate indicators.

## Stage order and stop behavior

1. **Data Quality** — canonical batch freshness, schema, gaps, feature readiness, and response identity.
2. **Market Structure** — existing regime and explicit bullish/bearish direction alignment.
3. **Signal / Strategy** — existing versioned strategy-quality result and evidence hash.
4. **Confirmation** — existing confirmation-policy result.
5. **Risk** — existing risk policy; only explicit APPROVED can continue. Any other state is a veto.
6. **Decision** — existing disagreement resolver's LONG, SHORT, or NO_TRADE; no new voting or thresholds.
7. **Evaluation handoff** — validates the observation/audit handoff only. It is not a backtest, realized-P&L calculation, or permission to trade.

Missing, extra, malformed, unknown, conflicting, future, or provenance-invalid stage output fails closed to NO_TRADE. A valid directional decision remains observation-only. Execution permission is always false in this contract.

## Stable interface and audit

- Contract: core/orchestration/mother_contract_v1.json.
- Implementation: core/orchestration/mother_v1.py.
- Required context pins venue, product, symbol, timeframe, timezone-aware observation time, snapshot SHA-256, and evidence SHA-256.
- Trace ID binds the scope/time/source snapshot and optional request ID. Audit SHA-256 binds the stage order, states, reason codes, evidence references, decision, and execution boundary.
- Agent output is bounded by maximum counts and text sizes; output payloads are copied at the boundary. The audit never serializes arbitrary payloads or news/article text.
- Stage adapters are explicitly registered. Missing or unexpected specialists block rather than being silently ignored.

## State ownership

| State | Owner | Must not be duplicated by |
|---|---|---|
| Closed candles / source hashes | Native OHLCV source | Mother or execution adapter |
| Feature readiness | Existing feature pipeline | Strategy or Mother |
| Regime / structure / strategy evidence | Existing StrategyEvidenceProvider and policy | Mother |
| Confirmation | Existing ConfirmationEngine / policy | Mother |
| Risk veto | Existing RiskGate / versioned policy | Signal consensus |
| Disagreement arbitration | Existing AgentDisagreementResolver | Majority vote in Mother |
| Forward decisions | Existing immutable decision journal | Execution journal |
| Fills/order lifecycle | Existing execution journal / approved venue adapter | Decision journal |
| Realized outcomes and learning | Existing forward outcome/evaluation pipeline | Mother or signal stage |

## Change and compatibility policy

- Keep v1 fields and meaning stable. Additive optional fields may be introduced only with tests and a documented contract update.
- A breaking state/schema/meaning change requires a new versioned contract/module (v2), migration notes, and compatibility tests; do not silently repurpose v1.
- One canonical implementation per responsibility. Before creating a new module, search this ownership table and existing forward/ contracts.
- Every new specialist must declare its identity, version, allowed states, evidence references, scope, time semantics, error behavior, and evaluation target.
- No hidden retries around side effects. Read-only specialists may retry only when their existing source adapter explicitly defines bounded retry/timeout behavior; any future side-effecting tool needs idempotency and approval before invocation.
- No autonomous self-modification. Learning produces evidence/hypotheses; policy changes require versioned offline evaluation, review, and explicit promotion.
- Keep dependency footprint small; v1 uses the Python standard library and the existing application stack.
- CI must test positive paths, every veto, malformed schemas, missing specialists, extra specialists, exceptions, provenance failures, and that execution remains disabled.

## Deliberate open boundaries

This code-level integration does not claim that every planned specialist is production-qualified. The current news-intelligence source profile is separately qualified and partially covered; domestic/Iran market coverage remains unqualified. The real execution adapter, account/risk context, symbol mapping, durable runtime configuration, and production deployment are separate release gates. A successful Mother run is not a profitability claim and never authorizes a trade.
