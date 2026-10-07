# HES Trade Agent — Forward Start

## Status
FORWARD_ONLY

## Forward Start
2026-10-07

## Purpose
This marker defines the operational boundary for the new forward-only development and evaluation path.

## Historical Boundary
All pre-existing historical analysis, including prior Winner/Survivor populations and historical failure-performance analysis, is archival context only. It must not be used as an optimization target, threshold-tuning basis, feature-selection basis, or future decision rule.

## Forward Rules
- No historical Winner/Survivor reselection.
- No threshold tuning from historical outcomes.
- No feature selection from historical outcomes.
- No deletion or rewriting of historical records.
- Fresh forward observations are the basis for future evaluation.
- NO_TRADE is a valid forward decision and must be recorded.
- Any future strategy change requires evidence generated from the new forward period, not the archived historical population.

## Operational Chain
Fresh Data -> Signal -> Confirmation -> Risk -> LONG/SHORT/NO_TRADE -> Forward Journal -> Forward Evaluation -> Learning

## Baseline Principle
Past = Archive. Future = Evidence.

## Scope
This marker does not claim that the current strategy is profitable or production-ready. It establishes only the boundary and protocol for forward evaluation.
