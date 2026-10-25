# Forward Signal Engine v1

This directory contains the forward-only market-data, strategy, confirmation, risk, decision-journal, and evaluation interfaces for HES Trade Agent.

## Canonical pipeline

Validated native OHLCV (one approved source/scope) → existing feature pipeline → StrategyEvidenceProvider / StrategyPolicy → SignalAgentV1 → Confirmation → Risk Gate → AgentDisagreementResolver → Mother Orchestrator → optional forward decision journal.

The dashboard entry point is the existing `web/dashboard.py`. Its `GET /api/signal` route reuses the same validated closed-candle batches and feature cache used by the chart. Mother consumes the already-computed specialist outputs; it does not fetch data, recalculate indicators, invent strategy thresholds, or replace the existing disagreement resolver.

## Multi-agent control plane

- Implementation: `core/orchestration/mother_v1.py`
- Versioned contract: `core/orchestration/mother_contract_v1.json`
- Architecture and ownership map: `docs/MOTHER_MULTI_AGENT_ARCHITECTURE_V1.md`
- Dashboard trace: `mother_orchestrator` in `GET /api/signal`, including stage states, reason codes, evidence references, trace ID, and audit SHA-256.

Missing/invalid provenance, unknown states, data/structure/strategy/confirmation failures, or a risk veto fail closed to `NO_TRADE`. Mother is read-only and always returns `execution_authorized=false`.

## Learning and outcome separation

The forward decision journal is outcome-free and records decisions idempotently only when explicitly configured. Realized outcomes belong to the separate immutable outcome/evaluation contract and must be linked to verified evidence; Mother must never infer wins, losses, fees, funding, or P&L.

## Release boundary

The current multi-agent integration is a Draft candidate stacked on the canonical data/dashboard/Signal Agent/learning dependency chain. CI validates the code path but does not prove deployment or runtime parity on the authorized VPS. Live WebSocket smoke is not established on this candidate. Execution remains disabled until the approved venue adapter, account/risk context, symbol mapping, and independently reconciled fill/outcome evidence pass their release gates.

## Non-duplication rule

Before adding a specialist, search the existing `forward/` contracts and the ownership table in `docs/MOTHER_MULTI_AGENT_ARCHITECTURE_V1.md`. Extend the owner module or add a thin adapter; do not create another candle schema, feature calculator, risk engine, decision resolver, journal, or frontend.
