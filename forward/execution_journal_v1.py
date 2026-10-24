"""Durable, restart-safe idempotency journal for a future execution adapter.

This module stores order intent and lifecycle metadata only; it never calls a
venue, stores credentials, or retries an ambiguous submission automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Literal


OrderState = Literal[
    "PREPARED", "SUBMITTING", "ACKNOWLEDGED", "REJECTED", "UNKNOWN",
    "RECONCILED_ACKNOWLEDGED", "RECONCILED_REJECTED",
]


@dataclass(frozen=True)
class JournalResultV1:
    accepted: bool
    client_order_id: str
    state: str | None
    reason_code: str


class ExecutionJournalV1:
    """SQLite-backed uniqueness and ambiguity guard; no automatic order retry."""

    VERSION = "hes-execution-journal-v1"

    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS execution_orders (
                    client_order_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL UNIQUE,
                    payload_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN (
                        'PREPARED','SUBMITTING','ACKNOWLEDGED','REJECTED','UNKNOWN',
                        'RECONCILED_ACKNOWLEDGED','RECONCILED_REJECTED'
                    )),
                    venue_order_id TEXT,
                    reconciliation_ref TEXT,
                    last_error_code TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_execution_orders_state ON execution_orders(state)")

    def _connect(self):
        db = sqlite3.connect(self.database_path, timeout=5.0, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        return db

    @staticmethod
    def _text(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    @staticmethod
    def _hash(value: object) -> bool:
        return isinstance(value, str) and len(value) == 64 and all(
            c in "0123456789abcdef" for c in value.lower()
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
            db.execute("""
                UPDATE execution_orders
                   SET state=?, venue_order_id=COALESCE(?, venue_order_id),
                       reconciliation_ref=COALESCE(?, reconciliation_ref),
                       last_error_code=?, updated_at=CURRENT_TIMESTAMP
                 WHERE client_order_id=? AND state=?
            """, (target, venue_order_id, reconciliation_ref, error_code, client_order_id, expected))
            db.execute("COMMIT")
            return JournalResultV1(True, client_order_id, target, reason)
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()
