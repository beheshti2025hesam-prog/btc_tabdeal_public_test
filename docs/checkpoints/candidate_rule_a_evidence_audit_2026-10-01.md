# Candidate Rule A — Formal Evidence Audit Checkpoint v1
Date: 2026-10-01
Status: CLOSED — EVIDENCE REGISTERED / NO PROMOTION

## Evidence artifact
- Workflow: HES Trade Agent — Controlled Candidate Performance Study v1
- Workflow run: #72 (run id 36895478410)
- Run conclusion: SUCCESS
- Head commit: 5c956799d66abfd16a9e4e84245f800fcb46b9e7
- Artifact: candidate-rule-a-performance-study-v1
- Artifact SHA-256: 230b4fd9b8214807cc6426bb88c0be74a179ec6e98c609058aa8e581919915c9
- Candidate: CANDIDATE_RESEARCH_V1_RULE_A

## Fresh-snapshot lineage
- snapshot_data_blob_sha: b296b1c95f075518bea0b56fd11bbf5f0f613a04
- snapshot_source_commit: 86631f2522aa74a38cfa21fa28afe8d49fbc5f20
- protocol: 8 folds; 800 train / 400 test / 400 step; shuffle=false
- rows_read: 147,949
- rows_invalid: 0
- candidate_observations: 5,405
- OOS observations: 3,200
- population: LONG 1,513; SHORT 1,686; NO_TRADE 1

## Rule lock
- LONG: buy_ratio > 0.5 AND buy_sell_delta > 0
- SHORT: buy_ratio < 0.5 AND buy_sell_delta < 0
- Otherwise: NO_TRADE
- trade_count: finite/validity-only; no directional threshold
- No threshold tuning, model fitting, ranking, optimization, or outcome-derived rescue.

## Cost / turnover boundary
- Cost matrix is evaluated on 3,199 trade-bearing observations (one no-trade observation excluded from costed evaluation).
- 0 / 0 bps per side: total net return +0.013238175729231517.
- 5 / 2 bps per side: total net return -4.465361824270769.
- 10 / 5 bps per side: total net return -9.58376182427077.
- The artifact does NOT define an independent turnover cap/limit; therefore no turnover threshold is invented or inferred.
- For this evidence gate, turnover/activity is represented by the costed evaluated observations and the explicit per-side cost/slippage matrix only.
- No profitability or execution-viability claim is permitted from the zero-cost case.

## Integrity / claim boundary
- Evidence is descriptive and snapshot-lineage-specific.
- Negative and fold-level results are retained.
- No production Signal, promotion, live execution, capital mutation, wallet operation, or data-engine-v1 integration is authorized.
- Candidate A is closed as an evidence record; its result must not be used to tune the next candidate.

## Next gate
Proceed only with a separately pre-registered independent candidate definition, a fresh lineage-locked evaluation boundary, fixed walk-forward protocol, and the same cost/turnover audit. No Candidate B rule is inferred from Candidate A outcomes in this checkpoint.
