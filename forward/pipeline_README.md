# Forward Pipeline v1

Composition boundary for fresh forward observations.

The pipeline only composes explicitly supplied, versioned components. It does
not define strategy thresholds, indicators, optimization, execution, or
historical Winner/Survivor selection.

A production collector must supply contemporaneous inputs and an explicitly
configured policy. Until those exist, components fail closed and the journal
records NO_TRADE where applicable.

The pipeline must never rewrite a prior decision from a later outcome.
