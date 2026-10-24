from datetime import datetime, timezone
from decimal import Decimal

from forward.execution_adapter_contract_v1 import (
    AccountReconciliationSnapshotV1,
    BalanceSnapshotV1,
    ExecutionAdapterCapabilitiesV1,
    ExecutionOrderRequestV1,
    PositionSnapshotV1,
    VenueOrderSnapshotV1,
    validate_adapter_readiness,
)

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def request(**overrides):
    values = dict(
        venue_id="unselected-venue",
        market_type="USDM_FUTURES",
        analysis_symbol="BTCUSDT",
        venue_symbol="BTCUSDT",
        symbol_mapping_ref="mapping-evidence:test",
        client_order_id="hes-client-1",
        decision_id="decision-1",
        payload_sha256="a" * 64,
        side="LONG",
        order_type="LIMIT",
        quantity_unit="CONTRACTS",
        quantity_unit_evidence_ref="instrument-rules:test",
        quantity=Decimal("0.01"),
        limit_price=Decimal("100"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("130"),
        reduce_only=False,
        time_in_force="GTC",
    )
    values.update(overrides)
    return ExecutionOrderRequestV1(**values)


def capabilities(**overrides):
    values = dict(
        venue_id="unselected-venue",
        market_type="USDM_FUTURES",
        api_contract_version="unverified",
        supported_order_types=("LIMIT",),
        client_order_id_supported=True,
        idempotent_submit_guaranteed=True,
        supports_reduce_only=True,
        supports_native_protective_orders=True,
        supports_cancel=True,
        supports_order_query=True,
        supports_open_order_query=True,
        supports_position_query=True,
        supports_account_reconciliation=True,
        verification_status="UNVERIFIED",
        official_contract_ref="",
        evidence_sha256="",
        reviewed_revision="",
    )
    values.update(overrides)
    return ExecutionAdapterCapabilitiesV1(**values)


def snapshot(**overrides):
    values = dict(
        venue_id="unselected-venue",
        market_type="USDM_FUTURES",
        venue_symbol="BTCUSDT",
        client_order_id="hes-client-1",
        venue_order_id="venue-123",
        side="LONG",
        status="PARTIALLY_FILLED",
        requested_quantity=Decimal("0.01"),
        executed_quantity=Decimal("0.004"),
        average_fill_price=Decimal("100"),
        reduce_only=False,
        observed_at=NOW,
        raw_response_sha256="b" * 64,
    )
    values.update(overrides)
    return VenueOrderSnapshotV1(**values)


def test_order_request_rejects_missing_mapping_bad_hash_and_bad_quantity():
    result = request(symbol_mapping_ref="", payload_sha256="bad", quantity=Decimal("NaN"))
    errors = result.validation_errors()
    assert "SYMBOL_MAPPING_REF_MISSING" in errors
    assert "PAYLOAD_HASH_INVALID" in errors
    assert "QUANTITY_INVALID" in errors


def test_limit_order_requires_price_and_boolean_is_not_quantity():
    result = request(limit_price=None, quantity=True)
    errors = result.validation_errors()
    assert "LIMIT_PRICE_REQUIRED" in errors
    assert "QUANTITY_INVALID" in errors


def test_adapter_defaults_unverified_and_fail_closed():
    candidate = capabilities()
    errors = validate_adapter_readiness(
        candidate, expected_venue_id="unselected-venue",
        expected_market_type="USDM_FUTURES",
    )
    assert "CAPABILITIES_NOT_INDEPENDENTLY_VERIFIED" in errors
    assert "OFFICIAL_CONTRACT_EVIDENCE_MISSING" in errors
    assert "CAPABILITY_EVIDENCE_HASH_INVALID" in errors
    assert "INDEPENDENT_REVIEW_REVISION_MISSING" in errors



def test_capability_claim_cannot_self_authorize_without_trusted_pins():
    candidate = capabilities(
        verification_status="VERIFIED",
        official_contract_ref="https://official.example/api",
        evidence_sha256="c" * 64,
        reviewed_revision="reviewed-commit-sha",
    )
    errors = validate_adapter_readiness(
        candidate, expected_venue_id="unselected-venue",
        expected_market_type="USDM_FUTURES",
    )
    assert "APPROVED_CAPABILITY_EVIDENCE_PIN_MISSING_OR_INVALID" in errors
    assert "APPROVED_REVIEW_REVISION_PIN_MISSING" in errors


def test_adapter_readiness_passes_only_with_matching_external_pins():
    digest = "c" * 64
    candidate = capabilities(
        verification_status="VERIFIED",
        official_contract_ref="https://official.example/api",
        evidence_sha256=digest,
        reviewed_revision="reviewed-commit-sha",
    )
    errors = validate_adapter_readiness(
        candidate, expected_venue_id="unselected-venue",
        expected_market_type="USDM_FUTURES",
        approved_evidence_sha256=digest,
        approved_review_revision="reviewed-commit-sha",
    )
    assert errors == ()

def test_adapter_capabilities_must_match_exact_venue_and_product():
    candidate = capabilities(
        verification_status="VERIFIED",
        official_contract_ref="https://official.example/api",
        evidence_sha256="c" * 64,
        reviewed_revision="reviewed-commit-sha",
    )
    errors = validate_adapter_readiness(
        candidate, expected_venue_id="different-venue",
        expected_market_type="SPOT",
    )
    assert "CAPABILITY_VENUE_SCOPE_MISMATCH" in errors
    assert "CAPABILITY_MARKET_TYPE_SCOPE_MISMATCH" in errors


def test_partial_fill_snapshot_is_valid_when_identity_and_quantities_match():
    result = snapshot()
    assert result.validation_errors(request()) == ()


def test_snapshot_rejects_wrong_symbol_identity_and_overfill():
    result = snapshot(venue_symbol="ETHUSDT", executed_quantity=Decimal("0.02"))
    errors = result.validation_errors(request())
    assert "RESPONSE_SYMBOL_MISMATCH" in errors
    assert "RESPONSE_OVERFILL_DETECTED" in errors


def test_filled_state_requires_full_quantity_and_fill_price():
    result = snapshot(
        status="FILLED",
        executed_quantity=Decimal("0.009"),
        average_fill_price=None,
    )
    errors = result.validation_errors(request())
    assert "FILLED_QUANTITY_INCONSISTENT" in errors
    assert "FILL_PRICE_MISSING" in errors


def test_unknown_submit_outcome_may_have_no_venue_order_id_but_keeps_provenance():
    result = snapshot(status="UNKNOWN", venue_order_id=None, executed_quantity=Decimal("0"))
    assert result.validation_errors(request()) == ()


def test_response_with_naive_timestamp_is_rejected():
    result = snapshot(observed_at=datetime(2026, 10, 24, 12, 0))
    assert "RESPONSE_TIMESTAMP_NOT_TIMEZONE_AWARE" in result.validation_errors(request())

def test_position_and_account_snapshots_validate_scope_and_provenance():
    position = PositionSnapshotV1(
        venue_id="unselected-venue", market_type="USDM_FUTURES",
        venue_symbol="BTCUSDT", position_quantity=Decimal("-0.01"),
        observed_at=NOW, raw_response_sha256="d" * 64,
    )
    assert position.validation_errors(
        expected_venue_id="unselected-venue",
        expected_market_type="USDM_FUTURES",
        expected_venue_symbol="BTCUSDT",
    ) == ()
    assert "POSITION_SYMBOL_MISMATCH" in position.validation_errors(
        expected_venue_id="unselected-venue",
        expected_market_type="USDM_FUTURES",
        expected_venue_symbol="ETHUSDT",
    )

    balance = BalanceSnapshotV1(
        asset="USDT", total=Decimal("1000"), available=Decimal("900"),
        locked=Decimal("100"), borrowed=Decimal("0"), liability=Decimal("0"),
        observed_at=NOW, raw_response_sha256="e" * 64,
    )
    account = AccountReconciliationSnapshotV1(
        venue_id="unselected-venue", market_type="USDM_FUTURES",
        observed_at=NOW, account_mode="cross", position_mode="one-way",
        balances=(balance,), open_order_ids=("venue-order-1",),
        position_snapshot_sha256="f" * 64, raw_response_sha256="a" * 64,
        reconciliation_ref="read-only-account-snapshot:test",
    )
    assert account.validation_errors(
        expected_venue_id="unselected-venue",
        expected_market_type="USDM_FUTURES",
    ) == ()


def test_account_snapshot_rejects_duplicate_order_ids_and_bad_balance():
    balance = BalanceSnapshotV1(
        asset="USDT", total=Decimal("-1"), available=Decimal("0"),
        locked=Decimal("0"), borrowed=Decimal("0"), liability=Decimal("0"),
        observed_at=NOW, raw_response_sha256="bad",
    )
    account = AccountReconciliationSnapshotV1(
        venue_id="unselected-venue", market_type="USDM_FUTURES",
        observed_at=NOW, account_mode="cross", position_mode="hedge",
        balances=(balance,), open_order_ids=("same", "same"),
        position_snapshot_sha256="f" * 64, raw_response_sha256="a" * 64,
        reconciliation_ref="read-only-account-snapshot:test",
    )
    errors = account.validation_errors(
        expected_venue_id="unselected-venue",
        expected_market_type="USDM_FUTURES",
    )
    assert "DUPLICATE_OPEN_ORDER_IDS" in errors
    assert "BALANCE_TOTAL_INVALID" in errors
    assert "BALANCE_RAW_HASH_INVALID" in errors

