# HES Trade Agent — Evidence Lock CI Gate v1

This gate validates the immutable Evidence Lock Gate artifact without changing evaluator data, main, data-engine-v1, execution, or promotion.

## Required assertions

- Exact locked evaluator population: 1049 observations.
- Eight fold evaluated counts sum exactly to 1049.
- Immutable source commit, workflow run, artifact ID, and SHA-256 remain unchanged.
- Fold-7 raw gap boundary remains unchanged.
- Gap intersects Fold 7 only.
- Excluded observation count remains 0.
- Observation coverage delta remains 0.0%.
- Raw time coverage loss remains 5.226350833333333 hours.
- No synthetic rows, replacement rows, interpolation, or causal reassignment.
- main and data-engine-v1 are not modified by this gate.
- Live execution and promotion remain disabled.

## Lock rule

If any assertion differs from evidence/evidence_lock_gate_v1.json, the gate must fail. A passing gate permits formal evidence lock only; it does not authorize merge, promotion, or live execution.
