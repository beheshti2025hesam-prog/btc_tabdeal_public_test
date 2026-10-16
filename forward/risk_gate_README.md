# Risk Gate Layer v1

Forward-only risk boundary between Confirmation and final Decision.

Possible states:
- RISK_APPROVED
- RISK_REJECTED

Each risk check carries:
- name
- PASS / FAIL / UNKNOWN
- evidence reference
- observation time

The reference gate fails closed when no versioned risk policy is supplied.

## Explicitly excluded
- Historical Winner/Survivor optimization
- Future outcome leakage
- Hidden leverage or sizing rules
- Hidden RR/stop/drawdown thresholds
- Execution
- Automatic tuning toward a target win rate

Risk approval means only that the opportunity is permitted to reach the Decision layer. It does not place an order.

## Gate-level defense in depth

Even when a policy returns `RISK_APPROVED`, the gate independently validates the result before passing it downstream. Approval requires a non-empty declared `REQUIRED` list, every required check present, unique non-empty check names, valid state, non-empty evidence reference, non-null observation time, and `PASS` for every returned check. Missing, malformed, duplicated, `FAIL`, or `UNKNOWN` evidence is converted to `RISK_REJECTED`. The policy's confirmation state must match the actual confirmation input.

These checks validate structure and fail-closed behavior; they do not independently prove that an evidence reference is authentic or that a timestamp reflects a trusted clock. Risk approval remains observation-only and never authorizes order execution.
Approval also requires a valid directional confirmation (`CONFIRMED_LONG` or `CONFIRMED_SHORT`), a policy-result observation time equal to the gate input time, and non-empty reason codes.
