# Forward Signal Engine v1

This directory is the forward-only engineering boundary for HES Trade Agent.

## Current state

The repository's existing collector remains a market-data collector. The forward engine is currently a **contract/skeleton**, not a trading strategy.

The engine intentionally fails closed to `NO_TRADE` until a versioned policy is explicitly supplied.

## Pipeline

`Market Data → Market Structure → Opportunity Candidate → Confirmation → Risk Gate → LONG/SHORT/NO_TRADE`

Every evaluated opportunity must be journalable, including `NO_TRADE`.

## Explicitly out of scope

- historical Winner/Survivor reselection
- historical performance optimization
- threshold tuning against old results
- feature selection from historical outcomes
- future-outcome leakage
- live order execution

## Next engineering layer

Build the **Market Data → normalized candles/features contract** first. It must consume fresh observations and expose stable inputs to this engine without embedding strategy thresholds.
