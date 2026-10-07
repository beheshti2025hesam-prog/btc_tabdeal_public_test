# Forward End-to-End Boundary Test

This smoke test verifies the most important safety invariant before live
forward data is introduced:

**An unactivated policy must be rejected before the decision pipeline can run.**

It intentionally uses an exploding fake pipeline. If the gate fails open, the
test fails immediately.

This is a safety test, not a profitability test.
