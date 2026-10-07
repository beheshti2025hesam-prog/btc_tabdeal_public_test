# Forward Policy v1

This boundary defines where explicit strategy, confirmation, and risk rules will
enter the forward pipeline.

No trading thresholds or indicators are invented in this version.

A future policy implementation must be versioned, explicit, auditable, symmetric
for LONG/SHORT, free of historical Winner/Survivor tuning, and fail closed on
UNKNOWN or missing required inputs.

This contract does not enable live execution.
