# Forward Run Controller v1

The controller is the runtime entry boundary for a single forward run.

It requires:
- an explicit run_id;
- timezone-aware observation time;
- an ACTIVE policy;
- an ACTIVE ruleset;
- no historical inputs;
- no future-outcome leakage;
- no live execution.

The current implementation is intentionally non-executing and returns READY
only after structural activation checks pass. Decision production remains a
separate, versioned step.

A READY result is **not** a claim of profitability or production readiness.
