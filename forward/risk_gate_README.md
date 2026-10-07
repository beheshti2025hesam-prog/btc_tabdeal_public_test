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
