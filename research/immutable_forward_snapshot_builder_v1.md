# HES Trade Agent — Immutable Forward Snapshot Builder v1

## Purpose

Create an immutable, research-only candidate snapshot for the post-boundary forward population without mutating the historical Forward OOS Lock v1.

## Invariants

- Historical source commit `f396de84cb7f4c6b16e81effc91b653e26049ab4` remains untouched.
- Boundary remains `2026-10-05T00:00:00+00:00`.
- Eligibility is strictly event timestamp > boundary.
- Raw trade rows are never treated as one-minute observations.
- Locked protocol remains train=800, test=400, step=400, folds=8, gross threshold >14 bps.
- No tuning, winner reselection, deletion, synthetic observations, or protocol mutation.
- Snapshot is research-only; live execution and promotion remain blocked.
- A candidate below 3600 valid one-minute observations is ACCUMULATING, not evaluable.
- Only a frozen source blob plus hash may become an immutable Forward Source Lock.

## Candidate artifact contract

The builder must record source commit/path, raw source blob SHA-256, boundary, first/last eligible timestamps, raw forward trade-row count, valid chronological one-minute observation count, timestamp uniqueness/ordering, sequence uniqueness/ordering, single-writer attribution, protocol capacity requirement (3600), capacity status, and fail-closed verdict.

## Important distinction

`data/trades.csv` on the moving `main` branch is an append-only working dataset. It is not itself an immutable Forward Source Lock.

The immutable source for evaluation must be a Git object identified by an exact commit/path/blob hash and frozen before any outcomes are interpreted.

## Current state

The existing Forward OOS evaluator v1 is intentionally not modified by this change. It is hard-coded to the historical Run #196 source object. A future evaluator revision must consume the newly frozen forward snapshot artifact rather than silently replacing the v1 source.

## Gate

Until the candidate contains at least 3600 valid chronological one-minute observations, G6_FORWARD_OOS remains BLOCKED / ACCUMULATING. No outcome-based forward verdict may be claimed.
