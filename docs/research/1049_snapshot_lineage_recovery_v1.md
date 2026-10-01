# 1,049 Snapshot Lineage Recovery v1

Frozen source commit: 3247bf37f4f80e01916180ed0dd5594f81701752
Raw input blob: 2c2d075f80ade4eba402809a106ab265eddba081
Historical workflow: 36489452534
Historical evidence artifact: 11000741523

Expected evaluated population: 1,049
Expected gross wins/losses: 528 / 479
Expected gross total return: 0.027839866468923342

Current deterministic replay reproduces the 8-fold structure, aggregate gross
return, and win/loss counts, but produces 1,050 evaluated observations.
The mismatch is isolated to fold 5 (128 replayed vs 127 historical).
The unresolved row is not guessed or silently dropped.

Gate: no 1,049-row snapshot is emitted until the exact historical row identity
is proven from immutable lineage. Candidate Performance Study, Signal creation,
promotion, execution, and data-engine-v1 integration remain OFF.
