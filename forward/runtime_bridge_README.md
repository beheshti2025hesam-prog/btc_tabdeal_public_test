# Forward Runtime Bridge v1

Connects the run controller to the existing forward pipeline without adding
hidden strategy rules.

The bridge:
- requires a READY run;
- delegates decision construction to the versioned pipeline;
- does not execute orders;
- does not read historical populations;
- does not mutate decisions after the fact;
- does not perform Git operations.

The caller must inject all policy/engine dependencies explicitly.
