# HES Blackbox Experiential Memory & Hypothesis Tournament V1

**Status:** isolated development implementation; research-only; not deployed, not connected to production decision authority.

## Resource-first integration

This layer indexes existing canonical evidence. It does not create a second trade journal or rewrite `trade_journal_v2.jsonl`, `neutral_decision_outcomes_v1.jsonl`, family shadow journals, or the 1m forward-paper ledger. `experience_memory_v1.jsonl` stores compact references, provenance hashes, four-state regime context and eligibility metadata only. Full source payloads remain in their canonical ledgers.

## Four experience states

- `BULLISH`, `BEARISH`, `RANGE`, `NO_TRADE` are explicit and mutually exclusive.
- Trade outcomes, rejected proposals, NO_TRADE counterfactuals, directionless market context and family research are distinct experience types.
- A counterfactual can never become a trade-training label. Directionless movement is context only.
- Only a matured gate-approved trade outcome with complete provenance, verified costs, clean outcome class and valid direction can be marked `training_eligible=true`. That flag is necessary, never sufficient, for model training.

## Immutable memory contract

- Stable event identity derives from source path, source event ID, source payload SHA and experience type.
- Append is locked and idempotent. Exact replay is ignored; same identity with changed content fails closed.
- Each memory record references its canonical source; it does not copy the source payload.
- No source row is backfilled or rewritten. Existing historical records may be indexed only when their original provenance and eligibility are verifiable.

## Hypothesis lifecycle

`DISCOVERED -> PREREGISTERED -> TESTING -> ACCEPTED | REJECTED | INCONCLUSIVE -> RETIRED`.

Status changes are separate append-only events. Discovery records require a time window, source hashes, frozen feature definition, null/alternative hypotheses, primary metric, falsification rule and multiple-testing family. Final status requires a 64-character evidence hash and rationale. Rejected hypotheses remain searchable; they are not deleted.

## Statistical tournament V1

- Paired exact sign test on per-event OOS net-R differences against a matched preregistered baseline.
- Holm-Bonferroni correction across the full tested hypothesis family (family-wise alpha 0.05).
- Minimum 100 training outcomes and 100 independent chronological purged OOS outcomes.
- Require clean linkage/scoring, complete provenance, verified execution costs, at least two OOS regimes, positive net expectancy in train and OOS, and OOS expectancy above the preregistered baseline.
- SHORT requires independently validated short-side economics; Spot-only outcomes cannot pass.
- Any missing prerequisite yields `INCONCLUSIVE`; statistical significance alone is not enough.

`ACCEPTED` means accepted as a research finding for the named scope only. It does not train a production model, mutate policy, enter the strategy router, authorize a signal, pass Risk Gate, or enable execution. Production approval remains a separate human/release gate.

## Current boundary

This module is deliberately not yet wired into the live learning-loop daemon. It is first tested in isolation against synthetic fixtures. The canonical readiness evaluator still blocks because there are zero gate-approved matured trade outcomes and zero gate-approved candidates. The existing 401-row historical indicator family replay and 231-row forward observer journal remain separate research evidence; forward observer currently has zero resolved outcomes. No retrospective data is promoted to forward training.


## First canonical source preview (2026-11-18)

Read-only preview against the live VPS canonical ledgers:

| Source ledger | Indexed references |
|---|---:|
| `trade_journal_v2.jsonl` | 2,358 |
| `neutral_decision_outcomes_v1.jsonl` | 6,461 |
| `strategy_policy_v2_eval_outcomes.jsonl` | 29 |
| `indicator_strategy_shadow_outcomes_v1.jsonl` | 44 |
| `indicator_strategy_forward_paper_journal_v1.jsonl` | 234 |
| **Total** | **9,126** |

Four-state classification: BULLISH 640; BEARISH 682; RANGE 1,068; NO_TRADE 6,736. Experience classes: NO_TRADE counterfactual 6,461; market context 2,510; rejected proposals 82; family research 44; trade-outcome references 29. Eligible training labels: **0**. This is a read-only preview; no memory ledger was appended to the live VPS and no production data or service was changed.


## Pattern-discovery engine — first exploratory run (2026-11-18)

A deterministic descriptive motif miner now reads only the existing historical indicator shadow decision ledger. It freezes feature quartile boundaries within the discovery window and creates regime-conditioned feature-motif hypotheses when support is at least 20 observations. It does not read outcomes to choose patterns, optimize thresholds, infer profitability, or produce training labels. Every result is `DISCOVERED`, `research_only=true`, `training_eligible=false`, and requires independent preregistered OOS testing.

First read-only run produced **35 candidate motifs** from six feature dimensions: EMA20, EMA50, EMA200, ADX14, MACD histogram and RSI14. Coverage in this historical source was BEARISH 20 and BULLISH 15; it contained no RANGE or NO_TRADE motif candidates. Support ranged from 27 to 101 observations. This does not contradict the four-state memory coverage: the wider experience memory includes RANGE and NO_TRADE from the other canonical ledgers, while this particular historical indicator-family source is directional-only.

No hypothesis events were appended to the live VPS. The CLI defaults to preview; appending memory or hypothesis events requires separate explicit flags.


## Latest source refresh (2026-11-18)

A later read-only refresh observed 9,133 reference events across the same five ledgers (BULLISH 640, BEARISH 686, RANGE 1,068, NO_TRADE 6,739) and 35 discovery-only motifs. The underlying journals continued appending during the day; these are point-in-time counts, not fixed totals. Eligible training labels remained zero.
