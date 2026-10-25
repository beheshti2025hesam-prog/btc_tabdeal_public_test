"""Read-only projection of the existing SQLite execution lifecycle journal.

This module does not create a second ledger, mutate the database, call a venue,
or infer fees, funding, exits, realized P&L, or execution from decision records.
The execution journal path is opt-in via HES_EXECUTION_JOURNAL_DB.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import os
import sqlite3
from typing import Any
from urllib.parse import quote

MAX_ROWS = 100
_HASH_HEX = frozenset("0123456789abcdef")
_STATES = frozenset({
    "PREPARED", "SUBMITTING", "ACKNOWLEDGED", "REJECTED", "UNKNOWN",
    "RECONCILED_ACKNOWLEDGED", "RECONCILED_REJECTED", "PARTIALLY_FILLED",
    "FILLED", "CANCELED", "EXPIRED", "RECONCILED_PARTIALLY_FILLED",
    "RECONCILED_FILLED", "RECONCILED_CANCELED", "RECONCILED_EXPIRED",
})
_REQUIRED_COLUMNS = frozenset({
    "client_order_id", "decision_id", "payload_sha256", "state", "venue_order_id",
    "venue_status", "executed_quantity", "average_fill_price", "raw_response_sha256",
    "observed_at", "created_at", "updated_at",
})


class ExecutionJournalProjectionError(ValueError):
    """Execution journal cannot safely be projected."""


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in _HASH_HEX for c in value.lower())


def _decimal_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ExecutionJournalProjectionError("invalid_" + field)
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ExecutionJournalProjectionError("invalid_" + field) from exc
    if not number.is_finite() or number < 0:
        raise ExecutionJournalProjectionError("invalid_" + field)
    return format(number, "f")


def _aware_utc(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ExecutionJournalProjectionError("invalid_observed_at")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ExecutionJournalProjectionError("invalid_observed_at") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExecutionJournalProjectionError("naive_observed_at")
    from datetime import timezone
    return parsed.astimezone(timezone.utc).isoformat()


def read_execution_journal(path: str | Path, *, limit: int = 50) -> dict[str, Any]:
    """Open the already-created execution journal strictly read-only."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_ROWS:
        raise ExecutionJournalProjectionError("invalid_limit")
    db_path = Path(path)
    try:
        if db_path.is_symlink() or not db_path.is_file():
            raise ExecutionJournalProjectionError("journal_not_a_regular_file")
        # URI mode=ro prevents accidental writes even if a caller misuses this view.
        uri = "file:" + quote(str(db_path.resolve()), safe="/:") + "?mode=ro"
        db = sqlite3.connect(uri, uri=True, timeout=2.0)
        db.row_factory = sqlite3.Row
        try:
            integrity = db.execute("PRAGMA quick_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise ExecutionJournalProjectionError("sqlite_integrity_check_failed")
            table = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='execution_orders'"
            ).fetchone()
            if table is None:
                raise ExecutionJournalProjectionError("execution_orders_table_missing")
            columns = {row["name"] for row in db.execute("PRAGMA table_info(execution_orders)")}
            if not _REQUIRED_COLUMNS.issubset(columns):
                raise ExecutionJournalProjectionError("execution_journal_schema_incompatible")
            rows = db.execute(
                "SELECT client_order_id,decision_id,payload_sha256,state,venue_order_id,"
                "venue_status,executed_quantity,average_fill_price,raw_response_sha256,observed_at "
                "FROM execution_orders ORDER BY updated_at DESC, client_order_id ASC LIMIT ?",
                (limit + 1,),
            ).fetchall()
        finally:
            db.close()
    except ExecutionJournalProjectionError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise ExecutionJournalProjectionError("execution_journal_unavailable") from exc

    orders = []
    seen_clients: set[str] = set()
    for row in rows[:limit]:
        client_id, decision_id = row["client_order_id"], row["decision_id"]
        if not isinstance(client_id, str) or not client_id.strip():
            raise ExecutionJournalProjectionError("client_order_id_missing")
        if not isinstance(decision_id, str) or not decision_id.strip():
            raise ExecutionJournalProjectionError("decision_id_missing")
        if client_id in seen_clients:
            raise ExecutionJournalProjectionError("duplicate_client_order_id")
        seen_clients.add(client_id)
        if not _valid_hash(row["payload_sha256"]):
            raise ExecutionJournalProjectionError("invalid_payload_sha256")
        state = row["state"]
        if state not in _STATES:
            raise ExecutionJournalProjectionError("unknown_execution_state")
        raw_hash = row["raw_response_sha256"]
        if raw_hash is not None and not _valid_hash(raw_hash):
            raise ExecutionJournalProjectionError("invalid_raw_response_sha256")
        quantity = _decimal_text(row["executed_quantity"], "executed_quantity")
        average_price = _decimal_text(row["average_fill_price"], "average_fill_price")
        observed_at = _aware_utc(row["observed_at"])
        if state in {"PARTIALLY_FILLED", "FILLED", "RECONCILED_PARTIALLY_FILLED", "RECONCILED_FILLED"}:
            if quantity is None or Decimal(quantity) <= 0 or average_price is None or Decimal(average_price) <= 0:
                raise ExecutionJournalProjectionError("fill_evidence_incomplete")
            if raw_hash is None or observed_at is None:
                raise ExecutionJournalProjectionError("fill_provenance_incomplete")
        orders.append({
            "client_order_id": client_id,
            "decision_id": decision_id,
            "payload_sha256": row["payload_sha256"],
            "state": state,
            "venue_order_id": row["venue_order_id"] if isinstance(row["venue_order_id"], str) else None,
            "venue_status": row["venue_status"] if isinstance(row["venue_status"], str) else "UNKNOWN",
            "executed_quantity": quantity,
            "average_fill_price": average_price,
            "raw_response_sha256": raw_hash,
            "observed_at": observed_at,
            "fees": "UNKNOWN",
            "funding": "UNKNOWN",
            "realized_pnl": "UNKNOWN",
            "pnl_evidence": "NOT_LINKED",
        })
    return {
        "schema": "hes.execution_journal_view.v1",
        "status": "VERIFIED",
        "count": len(orders),
        "orders": orders,
        "truncated": len(rows) > limit,
        "read_only": True,
        "execution_enabled": False,
        "outcomes_inferred": False,
    }


def configured_execution_journal(*, limit: int = 50) -> dict[str, Any]:
    path = os.environ.get("HES_EXECUTION_JOURNAL_DB", "").strip()
    if not path:
        return {
            "schema": "hes.execution_journal_view.v1",
            "status": "NOT_CONFIGURED",
            "count": 0,
            "orders": [],
            "read_only": True,
            "execution_enabled": False,
            "outcomes_inferred": False,
        }
    return read_execution_journal(path, limit=limit)
