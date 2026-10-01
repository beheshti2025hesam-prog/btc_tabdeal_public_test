# Controlled Signal Research v1 — Frozen Evidence Manifest

## Source evidence
- Prior validated workflow run: 36489452534
- Run conclusion: success
- Run head SHA: b8c4fe4fa054dbfa4fca17d2f307d269c16335e1
- Evidence artifact: real-btcusdt-oos-cost-matrix-evidence
- Artifact ID: 11000741523
- Artifact SHA-256: 2d6417289b3ddbc5befb622f8e64d1259dd6eea73a7c24d6abc37e64de85addc
- Protocol: oos-real-btcusdt-v1-800x400x400-e0
- Folds: 8
- Evaluated observations: 1049
- Cost-boundary survival counts: 14 at 5 bps transaction + 2 bps slippage per side; 1 at 10 bps + 5 bps per side.

## Important boundary
The cost-matrix artifact is evidence of the evaluated population and cost-boundary results. It is **not** a feature snapshot. It contains no EMA20, Momentum10, VWAP, sequence-level feature rows, or Winner/Control feature vectors.

Therefore CSRv1-A evaluation MUST NOT run against this artifact as if it were the feature snapshot.

## Required next input
A separately identified, immutable feature/evaluation snapshot containing for each of the 1049 observations:
- observation identifier;
- fold;
- sequence;
- feature timestamp;
- outcome timestamp;
- EMA20;
- Momentum10;
- VWAP;
- outcome / boundary label;
- provenance/hash tying the rows to the audited 1049 population.

Until that artifact is identified and hash-verified, CSRv1-A remains **specified but unevaluated**.
