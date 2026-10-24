"""Durable, restart-safe execution idempotency and venue-order lifecycle journal.

Stores order intent and normalized venue snapshots only. It never calls a venue,
stores credentials, or retries an ambiguous submission automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3
from typing import Literal

from forward.execution_adapter_contract_v1 import (
    ExecutionOrderRequestV1,
    VenueOrderSnapshotV1,
)

OrderState = Literal[
    "PREPARED", "SUBMITTING", "ACKNOWLEDGED", "REJECTED", "UNKNOWN",
    "RECONCILED_ACKNOWLEDGED", "RECONCILED_REJECTED",
    "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED",
    "RECONCILED_PARTIALLY_FILLED", "RECONCILED_FILLED",
    "RECONCILED_CANCELED", "RECONCILED_EXPIRED",
]


@dataclass(frozen=True)
class JournalResultV1:
    accepted: bool
    client_order_id: str
    state: str | None
    reason_code: str


class ExecutionJournalV1:
    """SQLite-backed intent uniqueness, lifecycle, and ambiguity guard."""

    VERSION = "hes-execution-journal-v1"
    _TABLE_SQL = """CREATE TABLE execution_orders (
        client_order_id TEXT PRIMARY KEY,
        decision_id TEXT NOT NULL UNIQUE,
        payload_sha256 TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN (
            'PREPARED','SUBMITTING','ACKNOWLEDGED','REJECTED','UNKNOWN',
            'RECONCILED_ACKNOWLEDGED','RECONCILED_REJECTED',
            'PARTIALLY_FILLED','FILLED','CANCELED','EXPIRED',
            'RECONCILED_PARTIALLY_FILLED','RECONCILED_FILLED',
            'RECONCILED_CANCELED','RECONCILED_EXPIRED'
        )),
        venue_order_id TEXT,
        reconciliation_ref TEXT,
        last_error_code TEXT,
        venue_status TEXT,
        executed_quantity TEXT,
        average_fill_price TEXT,
        raw_response_sha256 TEXT,
        observed_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""

    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self):
        db = sqlite3.connect(self.database_path, timeout=5.0, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def _ensure_schema(self) -> None:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            table = db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='execution_orders'"
            ).fetchone()
            if table is None:
                db.execute(self._TABLE_SQL)
            else:
                columns = {
                    row["name"] for row in db.execute("PRAGMA table_info(execution_orders)").fetchall()
                }
                sql = table["sql"] or ""
                needs_migration = (
                    "PARTIALLY_FILLED" not in sql
                    or not {
                        "venue_status", "executed_quantity", "average_fill_price",
                        "raw_response_sha256", "observed_at",
                    }.issubset(columns)
                )
                if needs_migration:
                    db.execute("DROP INDEX IF EXISTS idx_execution_orders_state")
                    db.execute("ALTER TABLE execution_orders RENAME TO execution_orders_v1_legacy")
                    db.execute(self._TABLE_SQL)
                    legacy_columns = {
                        row["name"]
                        for row in db.execute(
                            "PRAGMA table_info(execution_orders_v1_legacy)"
                        ).fetchall()
                    }
                    preserved = [
                        "client_order_id", "decision_id", "payload_sha256", "state",
                        "venue_order_id", "reconciliation_ref", "last_error_code",
                        "created_at", "updated_at",
                    ]
                    if not set(preserved).issubset(legacy_columns):
                        raise RuntimeError("EXECUTION_JOURNAL_LEGACY_SCHEMA_INVALID")
                    names = ", ".join(preserved)
                    db.execute(
                        f"INSERT INTO execution_orders ({names}) "
                        f"SELECT {names} FROM execution_orders_v1_legacy"
                    )
                    db.execute("DROP TABLE execution_orders_v1_legacy")
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_execution_orders_state ON execution_orders(state)"
            )
            db.execute("COMMIT")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _text(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    @staticmethod
    def _hash(value: object) -> bool:
        return isinstance(value, str) and len(value) == 64 and all(
            char in "0123456789abcdef" for char in value.lower()
        )

    def reserve(self, *, client_order_id: str, decision_id: str,
                payload_sha256: str) -> JournalResultV1:
        if not self._text(client_order_id) or not self._text(decision_id) or not self._hash(payload_sha256):
            return JournalResultV1(False, str(client_order_id), None, "JOURNAL_INPUT_INVALID")
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            by_client = db.execute(
                "SELECT * FROM execution_orders WHERE client_order_id=?", (client_order_id,)
            ).fetchone()
            by_decision = db.execute(
                "SELECT * FROM execution_orders WHERE decision_id=?", (decision_id,)
            ).fetchone()
            if by_client or by_decision:
                existing = by_client or by_decision
                db.execute("ROLLBACK")
                if existing["client_order_id"] != client_order_id:
                    return JournalResultV1(False, client_order_id, existing["state"], "DECISION_ALREADY_RESERVED")
                if existing["payload_sha256"] != payload_sha256 or existing["decision_id"] != decision_id:
                    return JournalResultV1(False, client_order_id, existing["state"], "IDEMPOTENCY_PAYLOAD_CONFLICT")
                return JournalResultV1(False, client_order_id, existing["state"], "DUPLICATE_ORDER_INTENT")
            db.execute(
                "INSERT INTO execution_orders(client_order_id,decision_id,payload_sha256,state) VALUES(?,?,?,'PREPARED')",
                (client_order_id, decision_id, payload_sha256),
            )
            db.execute("COMMIT")
            return JournalResultV1(True, client_order_id, "PREPARED", "ORDER_INTENT_RESERVED")
        except sqlite3.IntegrityError:
            if db.in_transaction:
                db.execute("ROLLBACK")
            return JournalResultV1(False, client_order_id, None, "DUPLICATE_ORDER_INTENT")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def mark_submitting(self, *, client_order_id: str) -> JournalResultV1:
        return self._transition(
            client_order_id=client_order_id, expected="PREPARED", target="SUBMITTING",
            reason="ORDER_SUBMISSION_MARKED",
        )

    def record_submit_outcome(self, *, client_order_id: str,
                              outcome: Literal["ACKNOWLEDGED", "REJECTED", "UNKNOWN"],
                              venue_order_id: str | None = None,
                              error_code: str | None = None) -> JournalResultV1:
        if outcome not in ("ACKNOWLEDGED", "REJECTED", "UNKNOWN"):
            return JournalResultV1(False, client_order_id, None, "SUBMIT_OUTCOME_INVALID")
        if outcome == "ACKNOWLEDGED" and not self._text(venue_order_id):
            return JournalResultV1(False, client_order_id, None, "VENUE_ORDER_ID_MISSING")
        return self._transition(
            client_order_id=client_order_id, expected="SUBMITTING", target=outcome,
            venue_order_id=venue_order_id, error_code=error_code,
            reason="SUBMIT_OUTCOME_RECORDED",
        )

    def record_venue_snapshot(
        self,
        *,
        request: ExecutionOrderRequestV1,
        snapshot: VenueOrderSnapshotV1,
        reconciliation_ref: str | None = None,
    ) -> JournalResultV1:
        """Validate and durably record one adapter snapshot; never resubmits an order."""
        if request.validation_errors():
            return JournalResultV1(False, request.client_order_id, None, "ORDER_REQUEST_INVALID")
        if snapshot.validation_errors(request):
            return JournalResultV1(False, request.client_order_id, None, "VENUE_SNAPSHOT_INVALID")
        if reconciliation_ref is not None and not self._text(reconciliation_ref):
            return JournalResultV1(False, request.client_order_id, None, "RECONCILIATION_EVIDENCE_MISSING")

        status_to_state = {
            "NEW": "ACKNOWLEDGED",
            "PARTIALLY_FILLED": "PARTIALLY_FILLED",
            "FILLED": "FILLED",
            "CANCELED": "CANCELED",
            "REJECTED": "REJECTED",
            "EXPIRED": "EXPIRED",
            "UNKNOWN": "UNKNOWN",
        }
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM execution_orders WHERE client_order_id=?",
                (request.client_order_id,),
            ).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                return JournalResultV1(False, request.client_order_id, None, "ORDER_INTENT_NOT_FOUND")
            if row["decision_id"] != request.decision_id or row["payload_sha256"] != request.payload_sha256:
                db.execute("ROLLBACK")
                return JournalResultV1(False, request.client_order_id, row["state"], "ORDER_INTENT_IDENTITY_MISMATCH")

            current = row["state"]
            target = status_to_state[snapshot.status]

            # Venue snapshots may arrive late or out of order. Never let an
            # UNKNOWN/stale response erase a known acknowledgement or reduce
            # the amount already confirmed filled.
            if current in ("ACKNOWLEDGED", "PARTIALLY_FILLED"):
                if target == "UNKNOWN":
                    db.execute("ROLLBACK")
                    return JournalResultV1(
                        False, request.client_order_id, current,
                        "UNKNOWN_STATUS_REGRESSION_REJECTED",
                    )
                if row["venue_order_id"] and snapshot.venue_order_id and (
                    row["venue_order_id"] != snapshot.venue_order_id
                ):
                    db.execute("ROLLBACK")
                    return JournalResultV1(
                        False, request.client_order_id, current,
                        "VENUE_ORDER_ID_CONFLICT",
                    )
                try:
                    prior_executed = Decimal(row["executed_quantity"] or "0")
                    incoming_executed = Decimal(str(snapshot.executed_quantity))
                except (InvalidOperation, TypeError, ValueError):
                    db.execute("ROLLBACK")
                    return JournalResultV1(
                        False, request.client_order_id, current,
                        "EXECUTED_QUANTITY_INVALID",
                    )
                if incoming_executed < prior_executed:
                    db.execute("ROLLBACK")
                    return JournalResultV1(
                        False, request.client_order_id, current,
                        "EXECUTED_QUANTITY_REGRESSION_REJECTED",
                    )

            if current == "UNKNOWN" and target != "UNKNOWN":
                if not self._text(reconciliation_ref):
                    db.execute("ROLLBACK")
                    return JournalResultV1(False, request.client_order_id, current, "RECONCILIATION_EVIDENCE_MISSING")
                target = "RECONCILED_" + target
            elif current.startswith("RECONCILED_") or current in ("REJECTED", "FILLED", "CANCELED", "EXPIRED"):
                exact_duplicate = (
                    row["venue_status"] == snapshot.status
                    and row["venue_order_id"] == snapshot.venue_order_id
                    and row["executed_quantity"] == str(snapshot.executed_quantity)
                    and row["average_fill_price"] == (
                        str(snapshot.average_fill_price) if snapshot.average_fill_price is not None else None
                    )
                    and row["raw_response_sha256"] == snapshot.raw_response_sha256
                )
                db.execute("ROLLBACK")
                if exact_duplicate:
                    return JournalResultV1(True, request.client_order_id, current, "DUPLICATE_VENUE_SNAPSHOT_NOOP")
                return JournalResultV1(False, request.client_order_id, current, "TERMINAL_ORDER_STATE_CONFLICT")

            allowed = {
                "SUBMITTING": {"ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED", "EXPIRED", "UNKNOWN"},
                "ACKNOWLEDGED": {"ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "UNKNOWN"},
                "PARTIALLY_FILLED": {"PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "UNKNOWN"},
                "UNKNOWN": {"UNKNOWN", "RECONCILED_ACKNOWLEDGED", "RECONCILED_PARTIALLY_FILLED", "RECONCILED_FILLED", "RECONCILED_CANCELED", "RECONCILED_REJECTED", "RECONCILED_EXPIRED"},
            }
            if target not in allowed.get(current, set()):
                db.execute("ROLLBACK")
                return JournalResultV1(False, request.client_order_id, current, "ORDER_STATE_TRANSITION_REJECTED")

            observed = snapshot.observed_at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            db.execute(
                """UPDATE execution_orders
                   SET state=?, venue_order_id=COALESCE(?, venue_order_id),
                       reconciliation_ref=COALESCE(?, reconciliation_ref),
                       venue_status=?, executed_quantity=?, average_fill_price=?,
                       raw_response_sha256=?, observed_at=?, last_error_code=NULL,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE client_order_id=?""",
                (
                    target, snapshot.venue_order_id, reconciliation_ref,
                    snapshot.status, str(snapshot.executed_quantity),
                    str(snapshot.average_fill_price) if snapshot.average_fill_price is not None else None,
                    snapshot.raw_response_sha256, observed, request.client_order_id,
                ),
            )
            db.execute("COMMIT")
            return JournalResultV1(True, request.client_order_id, target, "VENUE_SNAPSHOT_RECORDED")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def reconcile_unknown(self, *, client_order_id: str,
                          venue_outcome: Literal["ACKNOWLEDGED", "REJECTED"],
                          reconciliation_ref: str,
                          venue_order_id: str | None = None) -> JournalResultV1:
        if not self._text(reconciliation_ref):
            return JournalResultV1(False, client_order_id, "UNKNOWN", "RECONCILIATION_EVIDENCE_MISSING")
        if venue_outcome not in ("ACKNOWLEDGED", "REJECTED"):
            return JournalResultV1(False, client_order_id, "UNKNOWN", "RECONCILIATION_OUTCOME_INVALID")
        if venue_outcome == "ACKNOWLEDGED" and not self._text(venue_order_id):
            return JournalResultV1(False, client_order_id, "UNKNOWN", "VENUE_ORDER_ID_MISSING")
        target = "RECONCILED_" + venue_outcome
        return self._transition(
            client_order_id=client_order_id, expected="UNKNOWN", target=target,
            venue_order_id=venue_order_id, reconciliation_ref=reconciliation_ref,
            reason="UNKNOWN_SUBMISSION_RECONCILED",
        )

    def get(self, *, client_order_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM execution_orders WHERE client_order_id=?", (client_order_id,)
            ).fetchone()
            return dict(row) if row else None

    def _transition(self, *, client_order_id: str, expected: str, target: str,
                    reason: str, venue_order_id: str | None = None,
                    reconciliation_ref: str | None = None,
                    error_code: str | None = None) -> JournalResultV1:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT state FROM execution_orders WHERE client_order_id=?", (client_order_id,)
            ).fetchone()
            if row is None:
                db.execute("ROLLBACK")
                return JournalResultV1(False, client_order_id, None, "ORDER_INTENT_NOT_FOUND")
            if row["state"] != expected:
                db.execute("ROLLBACK")
                return JournalResultV1(False, client_order_id, row["state"], "ORDER_STATE_TRANSITION_REJECTED")
            db.execute("""UPDATE execution_orders
                   SET state=?, venue_order_id=COALESCE(?, venue_order_id),
                       reconciliation_ref=COALESCE(?, reconciliation_ref),
                       last_error_code=?, updated_at=CURRENT_TIMESTAMP
                 WHERE client_order_id=? AND state=?""",
                (target, venue_order_id, reconciliation_ref, error_code, client_order_id, expected))
            db.execute("COMMIT")
            return JournalResultV1(True, client_order_id, target, reason)
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()
