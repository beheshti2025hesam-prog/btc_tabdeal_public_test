# Observation-Only Forward Policy v1

This is the first ACTIVE forward policy, but it is deliberately **observation
only**. It records fresh forward observations and exercises the runtime safety
path without authorizing LONG/SHORT decisions or live execution.

It is not a trading strategy and must not be evaluated as profitable/unprofitable.

Activation does not authorize order execution.
