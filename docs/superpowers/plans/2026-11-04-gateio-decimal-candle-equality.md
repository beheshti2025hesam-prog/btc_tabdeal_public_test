# Gate.io Decimal Candle Equality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Prevent false Gate.io candle conflicts caused solely by different decimal string formatting.

**Architecture:** Keep the existing REST collector and _append_new reconciliation path. Change only candle equality so identity fields remain exact and numeric fields use exact Decimal equality.

**Tech Stack:** Python 3, decimal.Decimal, pytest.

**Spec:** docs/superpowers/specs/2026-11-04-gateio-decimal-candle-equality-design.md

## Global Constraints
- Gate.io Public Spot BTC_USDT remains the canonical market-data source.
- No float tolerance; exact decimal equality only.
- Genuine numeric conflicts and unresolved gaps remain fail-closed.
- Do not modify live data files, services, current symlink, or the protected dirty checkout.
- Execution remains disabled; no orders are placed.

## Review Focus
- Equivalent values with trailing zeros must reconcile without rewriting the last-good file.
- A real base-volume difference must remain a conflict.
- A real quote-volume difference must remain a conflict.
- Different close/price values must remain a conflict.
- Candle identity, timestamps, and closed-state mismatches must remain conflicts.

---

### Task 1: Decimal-safe candle reconciliation

**Files:**
- Modify: forward/global_market_data_gateio_v1.py (_same_candle only).
- Modify: tests/collector/test_global_market_data_gateio_v1.py.
- Create: this design and plan document.

**Interfaces:**
- Preserve _same_candle(left: dict[str, Any], right: dict[str, Any]) -> bool.
- Preserve _append_new(candles, last_ts, output) behavior and fail-closed contract.

- [ ] Step 1: Add failing regression tests
  - Add a formatting-only duplicate test using volume='1.20000000' and quote_volume='2.40000000' against persisted '1.2' and '2.4'.
  - Assert _append_new returns the existing latest timestamp and leaves the persisted bytes unchanged.
  - Add separate real base-volume and quote-volume conflict tests.

- [ ] Step 2: Verify RED
  - Run: pytest -q -p no:cacheprovider tests/collector/test_global_market_data_gateio_v1.py
  - Expected: formatting-only test fails with Conflicting Gate.io candle; true-conflict tests pass.

- [ ] Step 3: Implement the minimal fix
  - Compare schema, source, symbol, timeframe, open_time, close_time, and closed exactly.
  - Compare open, high, low, close, volume, and quote_volume as finite Decimal(str(value)) values.
  - Return false for missing, malformed, or non-finite numeric values.

- [ ] Step 4: Verify GREEN and regression
  - Run focused collector tests.
  - Run the complete repository test suite.
  - Run git diff --check.
  - Confirm the worktree contains only the planned files.

- [ ] Step 5: Commit the isolated change
  - Commit the two source/test files and the design/plan docs on the isolated branch.
  - Do not merge or deploy until remote CI and release review pass.
