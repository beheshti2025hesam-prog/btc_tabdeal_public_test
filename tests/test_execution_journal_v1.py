from forward.execution_journal_v1 import ExecutionJournalV1


def make_journal(tmp_path):
    return ExecutionJournalV1(tmp_path / "execution.sqlite3")


def test_reservation_is_durable_and_duplicate_intent_is_rejected(tmp_path):
    path = tmp_path / "execution.sqlite3"
    journal = ExecutionJournalV1(path)
    first = journal.reserve(
        client_order_id="hes-client-1",
        decision_id="decision-1",
        payload_sha256="a" * 64,
    )
    assert first.accepted
    assert first.state == "PREPARED"

    # Reopen the database to prove state survives a process/instance boundary.
    reopened = ExecutionJournalV1(path)
    duplicate = reopened.reserve(
        client_order_id="hes-client-1",
        decision_id="decision-1",
        payload_sha256="a" * 64,
    )
    assert not duplicate.accepted
    assert duplicate.reason_code == "DUPLICATE_ORDER_INTENT"
    assert reopened.get(client_order_id="hes-client-1")["state"] == "PREPARED"


def test_same_decision_cannot_be_reserved_under_another_client_id(tmp_path):
    journal = make_journal(tmp_path)
    journal.reserve(client_order_id="hes-client-1", decision_id="decision-1",
                    payload_sha256="a" * 64)
    result = journal.reserve(client_order_id="hes-client-2", decision_id="decision-1",
                             payload_sha256="a" * 64)
    assert not result.accepted
    assert result.reason_code == "DECISION_ALREADY_RESERVED"


def test_payload_conflict_is_rejected_not_reinterpreted_as_retry(tmp_path):
    journal = make_journal(tmp_path)
    journal.reserve(client_order_id="hes-client-1", decision_id="decision-1",
                    payload_sha256="a" * 64)
    result = journal.reserve(client_order_id="hes-client-1", decision_id="decision-1",
                             payload_sha256="b" * 64)
    assert not result.accepted
    assert result.reason_code == "IDEMPOTENCY_PAYLOAD_CONFLICT"


def test_ambiguous_submit_cannot_be_retried_without_reconciliation(tmp_path):
    journal = make_journal(tmp_path)
    journal.reserve(client_order_id="hes-client-1", decision_id="decision-1",
                    payload_sha256="a" * 64)
    assert journal.mark_submitting(client_order_id="hes-client-1").accepted
    unknown = journal.record_submit_outcome(
        client_order_id="hes-client-1", outcome="UNKNOWN", error_code="TIMEOUT_AFTER_SEND"
    )
    assert unknown.accepted and unknown.state == "UNKNOWN"

    retry = journal.mark_submitting(client_order_id="hes-client-1")
    assert not retry.accepted
    assert retry.reason_code == "ORDER_STATE_TRANSITION_REJECTED"

    no_evidence = journal.reconcile_unknown(
        client_order_id="hes-client-1", venue_outcome="REJECTED", reconciliation_ref=""
    )
    assert not no_evidence.accepted
    assert no_evidence.reason_code == "RECONCILIATION_EVIDENCE_MISSING"

    reconciled = journal.reconcile_unknown(
        client_order_id="hes-client-1", venue_outcome="REJECTED",
        reconciliation_ref="read-only-reconciliation:run-1",
    )
    assert reconciled.accepted
    assert reconciled.state == "RECONCILED_REJECTED"


def test_submit_state_machine_requires_reserved_intent_and_order_id(tmp_path):
    journal = make_journal(tmp_path)
    missing = journal.mark_submitting(client_order_id="unknown-id")
    assert not missing.accepted
    assert missing.reason_code == "ORDER_INTENT_NOT_FOUND"

    journal.reserve(client_order_id="hes-client-1", decision_id="decision-1",
                    payload_sha256="a" * 64)
    ack_before_submit = journal.record_submit_outcome(
        client_order_id="hes-client-1", outcome="ACKNOWLEDGED",
        venue_order_id="venue-order-1",
    )
    assert not ack_before_submit.accepted
    assert ack_before_submit.reason_code == "ORDER_STATE_TRANSITION_REJECTED"

    journal.mark_submitting(client_order_id="hes-client-1")
    missing_venue_id = journal.record_submit_outcome(
        client_order_id="hes-client-1", outcome="ACKNOWLEDGED", venue_order_id=""
    )
    assert not missing_venue_id.accepted
    assert missing_venue_id.reason_code == "VENUE_ORDER_ID_MISSING"

    ack = journal.record_submit_outcome(
        client_order_id="hes-client-1", outcome="ACKNOWLEDGED",
        venue_order_id="venue-order-1",
    )
    assert ack.accepted
    assert ack.state == "ACKNOWLEDGED"


def test_invalid_reservation_inputs_fail_closed(tmp_path):
    journal = make_journal(tmp_path)
    result = journal.reserve(client_order_id="", decision_id="decision-1",
                             payload_sha256="not-a-hash")
    assert not result.accepted
    assert result.reason_code == "JOURNAL_INPUT_INVALID"


from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

from forward.execution_adapter_contract_v1 import ExecutionOrderRequestV1, VenueOrderSnapshotV1


NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def adapter_request(**overrides):
    values = dict(
        venue_id="unselected-venue", market_type="USDM_FUTURES",
        analysis_symbol="BTCUSDT", venue_symbol="BTCUSDT",
        symbol_mapping_ref="mapping-evidence:test",
        client_order_id="hes-client-1", decision_id="decision-1",
        payload_sha256="a" * 64, side="LONG", order_type="LIMIT",
        quantity_unit="CONTRACTS", quantity_unit_evidence_ref="instrument-rules:test",
        quantity=Decimal("0.01"), limit_price=Decimal("100"),
        stop_loss=Decimal("90"), take_profit=Decimal("130"),
        reduce_only=False, time_in_force="GTC",
    )
    values.update(overrides)
    return ExecutionOrderRequestV1(**values)


def venue_snapshot(**overrides):
    values = dict(
        venue_id="unselected-venue", market_type="USDM_FUTURES",
        venue_symbol="BTCUSDT", client_order_id="hes-client-1",
        venue_order_id="venue-order-1", side="LONG", status="PARTIALLY_FILLED",
        requested_quantity=Decimal("0.01"), executed_quantity=Decimal("0.004"),
        average_fill_price=Decimal("100"), reduce_only=False,
        observed_at=NOW, raw_response_sha256="b" * 64,
    )
    values.update(overrides)
    return VenueOrderSnapshotV1(**values)


def _prepare(journal):
    assert journal.reserve(client_order_id="hes-client-1", decision_id="decision-1",
                           payload_sha256="a" * 64).accepted
    assert journal.mark_submitting(client_order_id="hes-client-1").accepted


def test_partial_fill_is_durable_and_can_advance_to_filled(tmp_path):
    path = tmp_path / "execution.sqlite3"
    journal = ExecutionJournalV1(path)
    _prepare(journal)

    partial = venue_snapshot()
    result = journal.record_venue_snapshot(request=adapter_request(), snapshot=partial)
    assert result.accepted and result.state == "PARTIALLY_FILLED"
    reopened = ExecutionJournalV1(path)
    row = reopened.get(client_order_id="hes-client-1")
    assert row["executed_quantity"] == "0.004"
    assert row["venue_status"] == "PARTIALLY_FILLED"
    assert row["raw_response_sha256"] == "b" * 64

    filled = venue_snapshot(
        status="FILLED", executed_quantity=Decimal("0.01"),
        average_fill_price=Decimal("101"), raw_response_sha256="c" * 64,
    )
    result = reopened.record_venue_snapshot(request=adapter_request(), snapshot=filled)
    assert result.accepted and result.state == "FILLED"
    duplicate = reopened.record_venue_snapshot(request=adapter_request(), snapshot=filled)
    assert duplicate.accepted and duplicate.reason_code == "DUPLICATE_VENUE_SNAPSHOT_NOOP"


def test_ambiguous_order_requires_reconciliation_before_known_status(tmp_path):
    journal = make_journal(tmp_path)
    _prepare(journal)
    unknown = venue_snapshot(
        status="UNKNOWN", venue_order_id=None, executed_quantity=Decimal("0"),
        average_fill_price=None, raw_response_sha256="d" * 64,
    )
    result = journal.record_venue_snapshot(request=adapter_request(), snapshot=unknown)
    assert result.accepted and result.state == "UNKNOWN"

    filled = venue_snapshot(
        status="FILLED", executed_quantity=Decimal("0.01"),
        average_fill_price=Decimal("100"), raw_response_sha256="e" * 64,
    )
    blocked = journal.record_venue_snapshot(request=adapter_request(), snapshot=filled)
    assert not blocked.accepted
    assert blocked.reason_code == "RECONCILIATION_EVIDENCE_MISSING"

    reconciled = journal.record_venue_snapshot(
        request=adapter_request(), snapshot=filled,
        reconciliation_ref="read-only-reconciliation:verified-run",
    )
    assert reconciled.accepted and reconciled.state == "RECONCILED_FILLED"


def test_mismatched_adapter_snapshot_is_not_persisted(tmp_path):
    journal = make_journal(tmp_path)
    _prepare(journal)
    bad = venue_snapshot(venue_symbol="ETHUSDT")
    result = journal.record_venue_snapshot(request=adapter_request(), snapshot=bad)
    assert not result.accepted and result.reason_code == "VENUE_SNAPSHOT_INVALID"
    assert journal.get(client_order_id="hes-client-1")["state"] == "SUBMITTING"


def test_legacy_journal_schema_migrates_without_losing_reserved_intents(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE execution_orders (
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
    )""")
    db.execute("CREATE INDEX idx_execution_orders_state ON execution_orders(state)")
    db.execute(
        "INSERT INTO execution_orders(client_order_id,decision_id,payload_sha256,state) VALUES(?,?,?,'PREPARED')",
        ("legacy-client", "legacy-decision", "f" * 64),
    )
    db.commit()
    db.close()

    migrated = ExecutionJournalV1(path)
    row = migrated.get(client_order_id="legacy-client")
    assert row["state"] == "PREPARED"
    assert row["decision_id"] == "legacy-decision"
    assert "executed_quantity" in row
    assert migrated.mark_submitting(client_order_id="legacy-client").accepted



def test_stale_partial_fill_cannot_reduce_confirmed_execution_quantity(tmp_path):
    journal = make_journal(tmp_path)
    _prepare(journal)
    first = venue_snapshot(
        status="PARTIALLY_FILLED", executed_quantity=Decimal("0.006"),
        raw_response_sha256="1" * 64,
    )
    accepted = journal.record_venue_snapshot(request=adapter_request(), snapshot=first)
    assert accepted.accepted and accepted.state == "PARTIALLY_FILLED"

    stale = venue_snapshot(
        status="PARTIALLY_FILLED", executed_quantity=Decimal("0.004"),
        raw_response_sha256="2" * 64,
    )
    rejected = journal.record_venue_snapshot(request=adapter_request(), snapshot=stale)
    assert not rejected.accepted
    assert rejected.reason_code == "EXECUTED_QUANTITY_REGRESSION_REJECTED"
    row = journal.get(client_order_id="hes-client-1")
    assert row["state"] == "PARTIALLY_FILLED"
    assert row["executed_quantity"] == "0.006"
    assert row["raw_response_sha256"] == "1" * 64


def test_unknown_or_conflicting_order_snapshot_cannot_erase_known_fill(tmp_path):
    journal = make_journal(tmp_path)
    _prepare(journal)
    partial = venue_snapshot(
        status="PARTIALLY_FILLED", executed_quantity=Decimal("0.004"),
        raw_response_sha256="3" * 64,
    )
    assert journal.record_venue_snapshot(
        request=adapter_request(), snapshot=partial
    ).accepted

    unknown = venue_snapshot(
        status="UNKNOWN", venue_order_id=None,
        executed_quantity=Decimal("0"), average_fill_price=None,
        raw_response_sha256="4" * 64,
    )
    rejected_unknown = journal.record_venue_snapshot(
        request=adapter_request(), snapshot=unknown
    )
    assert not rejected_unknown.accepted
    assert rejected_unknown.reason_code == "UNKNOWN_STATUS_REGRESSION_REJECTED"

    conflicting_id = venue_snapshot(
        status="PARTIALLY_FILLED", venue_order_id="different-venue-order",
        executed_quantity=Decimal("0.005"), raw_response_sha256="5" * 64,
    )
    rejected_id = journal.record_venue_snapshot(
        request=adapter_request(), snapshot=conflicting_id
    )
    assert not rejected_id.accepted
    assert rejected_id.reason_code == "VENUE_ORDER_ID_CONFLICT"

    row = journal.get(client_order_id="hes-client-1")
    assert row["state"] == "PARTIALLY_FILLED"
    assert row["executed_quantity"] == "0.004"
    assert row["venue_order_id"] == "venue-order-1"
