# Strategy-family result journals v1

## Purpose

Keep Trend Breakout and Range Mean Reversion paper results independently auditable without duplicating or mutating the canonical candidate/outcome ledgers.

## Source of truth and projections

- `strategy_policy_v2_eval_candidates.jsonl` and `strategy_policy_v2_eval_outcomes.jsonl` remain the canonical append-only inputs.
- `strategy_family_trend_breakout_results_v1.jsonl` and `strategy_family_range_mean_reversion_results_v1.jsonl` are deterministic, append-only projections.
- Each projection event stores its source event ID and SHA-256. Outcome attribution requires an exact `candidate_event_id` link and the candidate's explicit, version-matched family route.
- Existing records without a supported family route remain unattributed. No family is inferred from direction, timestamps, nearby records, or current market regime.
- Replaying the projection is idempotent. The original candidate/outcome records are never rewritten.

## Authority and acceptance

Both families remain non-authoritative:
- Trend Breakout: `CANDIDATE_LOCKED_NOT_ACTIVE`.
- Range Mean Reversion: `RESEARCH_ONLY_NOT_ACTIVE`.

The family journals record paper/research candidates and outcomes only. They do not generate an order, approve a signal, or bypass Confirmation/Risk/Final Policy gates. Every projected event must keep `execution_enabled=false` and `orders_placed=false`.

Raw research outcomes are reported separately from performance-eligible resolved trades. A win-rate claim is null until the relevant family has performance-eligible resolved outcomes; the official acceptance gate remains strictly above 90% across at least 100 resolved closed precision trades, with a maximum of three actionable signals per UTC day (a cap, not a quota), verified costs, clean linkage, and independent out-of-sample evidence.

## Runtime

The existing paper evaluator backfills the two projections from the canonical ledgers at startup and refreshes them after each evaluation cycle. `strategy_family_results_report_v1.json` provides per-family counts, eligibility, outcome distribution, journal hashes, and unattributed/unmatched counts. The runtime healthcheck requires this report to remain fresh.

## Market-data and execution boundaries

The source remains Gate.io Public Spot `BTC_USDT` for live candles, charts, and indicators. The 15m timeframe owns setup classification; 1m remains a downstream precision-entry layer. Exchange/broker execution is separate and remains disabled in this research path.
