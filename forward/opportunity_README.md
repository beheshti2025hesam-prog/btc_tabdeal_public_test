# Opportunity Detection Layer v1

Forward-only boundary between Market Structure and Confirmation.

## Purpose
Represent a possible trading opportunity without declaring it tradable.

Pipeline:
Market Data → Market Structure → Opportunity Candidate → Confirmation → Risk → Decision

States:
- CANDIDATE_LONG
- CANDIDATE_SHORT
- NO_CANDIDATE

The reference detector fails closed when no versioned policy is supplied.

## Explicitly excluded
- Historical Winner/Survivor optimization
- Future outcome leakage
- Hidden thresholds
- Entry execution
- Profitability claims
- Automatic tuning toward a target win rate

A candidate is only an opportunity hypothesis. Confirmation and Risk Gate remain mandatory.
