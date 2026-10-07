# Runtime Guard v1

The runtime guard is a final forward-only boundary.

It requires a forward run identifier, timezone-aware observation time, and
rejects historical/Winner/Survivor sources. New decisions cannot arrive with
closed future outcomes.

This is a safety boundary, not a strategy policy and not a performance target.
