# Forward Evaluation v1

Descriptive evaluation only.

It reads forward decision records plus separately recorded closed outcomes and
reports counts, win rate, expectancy, and realized RR where available.

## Guardrails
- No historical Winner/Survivor inputs.
- No tuning toward a target win rate.
- No rewriting decisions from outcomes.
- Open/unresolved trades are excluded from closed-outcome metrics.
- NO_TRADE remains visible as its own population.

Metrics describe the fresh forward period; they are not guarantees of future performance.
