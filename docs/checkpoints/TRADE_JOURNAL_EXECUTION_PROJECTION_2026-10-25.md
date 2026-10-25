# HES Trade Journal — Execution Projection Checkpoint

Date: 2026-10-25  
Status: candidate implementation only; production remains `HOLD / NO_TRADE_ONLY`.  
Delivery target: 2026-11-19. Risk checkpoint: 2026-10-26.

## Canonical reuse map

- Decision observations: `forward/forward_observation_writer_v1.py` and `HES_FORWARD_LEARNING_DECISION_JOURNAL` on the #367/#371 stack.
- Execution lifecycle state: existing `forward/execution_journal_v1.py` SQLite journal from PR #366. The new projection does not create or mutate a second ledger; it opens that database with SQLite `mode=ro`.
- UI: existing `web/dashboard.py`; no parallel frontend or order routes.
- Learning attribution: existing `forward/learning_loop_v1.py` and its separate immutable outcome artifact contract. No outcome is inferred from candles, decisions, or order status.
- Market data remains the existing canonical OHLCV path; no exchange sequence logic was added.

## Implemented in this candidate

- Read-only execution lifecycle projection from the existing SQLite table.
- Validates database integrity, expected schema, stable IDs, lifecycle states, SHA-256 provenance, decimal fill values, and timezone-aware fill observation timestamps.
- Fill states require positive cumulative quantity and average fill price plus response hash and observation time; malformed evidence fails closed.
- Explicit UNKNOWN fees, funding, realized P&L, and P&L evidence until the existing independently reconciled outcome artifact provides them.
- Test covers SQLite read-only immutability, invalid/missing fill provenance, unknown schema, and backup/restore projection parity.
- `forward/sqlite_backup_v1.py` provides a dependency-free online SQLite backup and verified restore utility: SHA-256 manifest, integrity checks, atomic replacement, explicit overwrite protection, and tamper/corrupt-manifest rejection. `tests/test_sqlite_backup_v1.py` covers backup/restore integrity and fail-closed cases.
- Operator entrypoint: `python -m scripts.backup_execution_journal_v1 --backup SOURCE_DB BACKUP_DB` and `--restore BACKUP_DB DESTINATION_DB`; usage and runtime controls are documented in `docs/execution/SQLITE_BACKUP_RESTORE_V1.md`.
- No order routes, venue calls, credential use, service activation, deployment, or VPS mutation.

## Verification limits / remaining external evidence

- The tests prove the local projection contract only. They do not prove a production DB path is configured, that a real venue has supplied the snapshot, or that a backup is scheduled and recoverable in the authorized runtime.
- PR #366 remains a separate Draft dependency. Its execution journal must enter the accepted dependency chain before this projection can be considered integrated with the actual product runtime.
- Fees/funding/exit/realized P&L remain unlinked until actual forward outcome artifacts are supplied and independently reconciled to the execution lifecycle. No fake values or synthetic production outcomes.
- Live WebSocket smoke, production frontend/runtime parity, independent review, and full dependency acceptance remain separate release gates.
- Keep execution OFF and HOLD / NO_TRADE_ONLY. Do not merge this PR independently or enable live trading.
