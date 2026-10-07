# Confirmation / Confluence Layer v1

Forward-only confirmation boundary.

## Purpose
Combine contemporaneous evidence checks around an opportunity candidate.
Confirmation is not execution authorization.

Possible states:
- CONFIRMED_LONG
- CONFIRMED_SHORT
- UNCONFIRMED

Each check carries:
- name
- PASS / FAIL / UNKNOWN
- evidence reference
- observation time

UNKNOWN never becomes PASS.

## Explicitly excluded
- Historical Winner/Survivor optimization
- Future outcome leakage
- Hidden thresholds or weights
- Automatic tuning toward 98% win rate
- Execution

Next downstream gate: Risk Gate.
