# HES Trade Agent — Forward OOS Lock v1

Status: LOCKED / RESEARCH-ONLY / NO LIVE EXECUTION

## Purpose
Pre-register an untouched forward evaluation boundary before its outcomes are inspected. This artifact is a boundary contract, not a performance result.

## Frozen protocol
- train: 800
- test: 400
- step: 400
- folds: 8
- gross threshold: >14 bps
- no threshold changes
- no winner reselection
- no observation deletion
- no protocol mutation

## Forward boundary
- Evaluation population source: post-lock collector observations only.
- Boundary timestamp: `2026-10-05T00:00:00+00:00`
- Eligibility: observations whose event timestamp is strictly greater than the boundary.
- No observation at or before the boundary may enter the forward evaluation set.
- No forward outcomes may be inspected to alter this contract.

## Evaluation procedure
1. Freeze the exact forward input blob/hash before evaluation.
2. Validate timestamp monotonicity, uniqueness, gaps, duplicates, and single-writer lineage.
3. Apply the already-locked protocol unchanged.
4. Produce a blind forward evaluation artifact.
5. Only after artifact creation may results be opened for interpretation.
6. Promotion remains blocked regardless of interim result.

## Required outputs
- source blob SHA
- source commit
- boundary timestamp
- first/last eligible timestamp
- row count
- gap/duplicate/single-writer checks
- protocol hash
- forward winner/control counts
- gross/net outcome summaries
- direction/regime breakdown
- fold/sequence concentration
- fail-closed claim boundaries

## Gate
`G6_FORWARD_OOS = NOT_STARTED` until the forward input is frozen and independently validated.

## Non-negotiable
This lock does not authorize live trading or execution.
