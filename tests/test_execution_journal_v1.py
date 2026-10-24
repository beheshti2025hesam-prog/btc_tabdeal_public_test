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
