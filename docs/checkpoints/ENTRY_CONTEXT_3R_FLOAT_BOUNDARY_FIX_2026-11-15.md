# HES Strategy Entry Context — Exact 3R Floating-Point Boundary

**Date:** 2026-11-15 UTC  
**Status:** Draft PR; not merged or deployed.

## Root cause

The policy minimum remains exactly 3.0R. Binary floating-point arithmetic can represent mathematically exact 3R geometry as approximately `2.99999999999994`; strict `< 3.0` comparisons falsely rejected those setups in context construction, verification, and the advisory 1m precision validator.

## Correction

- Add a narrow `1e-12` representation tolerance for equality with the 3.0R boundary only.
- Canonicalize values within that tolerance to `3.0` for evidence/reporting.
- Keep materially sub-3R geometry rejected.
- Preserve all existing 15m authority, confirmation, Risk Gate, provenance, 1m advisory-only, and execution-disabled constraints.

## Tests

- Exact SHORT geometry reproduced from the historical HES false-rejection record.
- Exact LONG 3R geometry.
- Full build → provenance-bound verify → 1m precision-context validation.
- Materially sub-3R geometry remains rejected.

## Safety

No strategy threshold reduction, no Risk Gate bypass, no policy activation, no signal generation, no order execution, and no production deployment. The fix only removes binary-float false rejection at an exact mathematical 3R boundary.
