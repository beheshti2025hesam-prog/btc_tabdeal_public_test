# Forward Runtime Boundary Tests

These tests verify only the safety boundary of the collector adapter.

They do **not** prove market-data correctness, strategy profitability, or
production readiness. The default-disabled test is especially important:
forward collection cannot accidentally become active merely by importing the
adapter.
