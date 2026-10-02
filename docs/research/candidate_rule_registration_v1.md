# Candidate Rule Registration v1

status: research-only
candidate_id: CANDIDATE_RESEARCH_V1_RULE_A
registration_basis: pre-registered deterministic research rule; not derived from fresh OOS outcomes

## Purpose

Register one deterministic candidate rule before any fresh OOS performance evaluation. This document is a rule definition, not a profitability claim and not a production Signal authorization.

## Inputs

Exactly three inputs:
- buy_ratio
- buy_sell_delta
- trade_count

No EMA, VWAP, price-distance feature, model output, or external outcome may be used.

## Directional rule

Use only the sign of the three registered pressure features relative to their neutral zero/center points:

LONG when all three conditions are true:
- buy_ratio > 0.5
- buy_sell_delta > 0
- trade_count is not used directionally; it is a required finite/valid observation only

SHORT when all three conditions are true:
- buy_ratio < 0.5
- buy_sell_delta < 0
- trade_count is a required finite/valid observation only

Otherwise NO_TRADE.

## Important constraint

Trade Count is deliberately a validity/context feature in Rule A, not a directional threshold. No Trade Count threshold is invented here.

No alternative rule may be compared and selected using fresh OOS outcomes.

## Determinism

For identical feature inputs, the output must always be identical.

Missing, non-finite, or invalid required values produce NO_TRADE.

The rule has no fitted parameters, no optimization, no adaptive threshold, no ranking, and no stateful learning.

## Evaluation contract

After registration, evaluate this exact rule on a fresh lineage-locked snapshot using:
- fixed 8-fold walk-forward boundaries;
- no random shuffle;
- no cross-fold leakage;
- timestamp/sequence boundary checks;
- negative results retained;
- fold-level results;
- exact cost/slippage matrix reconciliation.

The rule must be registered before reading or using the fresh OOS outcome results for this rule.

## Claim boundary

This registration does not establish:
- predictive performance;
- signal quality;
- profitability;
- production readiness;
- promotion;
- live execution.

All live and wallet operations remain OFF/outside agent control.
