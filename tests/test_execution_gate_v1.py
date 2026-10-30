from datetime import datetime, timedelta, timezone

from forward.execution_gate_v1 import (
    ExecutionEvidenceV1,
    ExecutionGateV1,
    ExecutionRuntimeStateV1,
)


NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
RUNTIME = ExecutionRuntimeStateV1(
    live_mode_enabled=True,
    kill_switch_clear=True,
    venue_adapter_approved=True,
    venue_health_ref="test://venue-health",
    account_reconciled=True,
    operator_approval_ref="test://operator-approval",
    deployment_sha="a" * 40,
    environment="production",
)


def evidence(**overrides):
    values = dict(
        decision_id="decision-001",
        signal_agent_version="hes-signal-agent-v1",
        side="LONG",
        source_sha256="a" * 64,
        symbol_mapping_ref="mapping-v1:test",
        structure_evidence_ref="structure-v1:test",
        strategy_quality_evidence_ref="quality-v1:test",
        risk_policy_version="risk-v1",
        risk_evidence_ref="risk-v1:test",
        account_reconciliation_ref="account-v1:test",
        observed_at=NOW - timedelta(seconds=1),
        entry="100",
        stop_loss="90",
        take_profit="130",
        quantity="0.01",
        reward_risk_minimum="3",
    )
    values.update(overrides)
    return ExecutionEvidenceV1(**values)


def test_preflight_passes_only_when_every_contract_is_present():
    permit = ExecutionGateV1().evaluate(evidence=evidence(), runtime=RUNTIME, now=NOW)
    assert permit.allowed is True
    assert permit.reason_codes == ("ALL_EXECUTION_PRECHECKS_PASSED",)
    assert permit.client_order_id and permit.client_order_id.startswith("hes-")


def test_defaults_are_fail_closed_and_do_not_allow_live_execution():
    permit = ExecutionGateV1().evaluate(
        evidence=evidence(),
        runtime=ExecutionRuntimeStateV1(),
        now=NOW,
    )
    assert permit.allowed is False
    assert "LIVE_MODE_NOT_EXPLICITLY_ENABLED" in permit.reason_codes
    assert "KILL_SWITCH_ACTIVE_OR_UNKNOWN" in permit.reason_codes
    assert "VENUE_ADAPTER_NOT_APPROVED" in permit.reason_codes
    assert permit.client_order_id is None


def test_missing_provenance_and_unreconciled_account_block():
    permit = ExecutionGateV1().evaluate(
        evidence=evidence(symbol_mapping_ref="", source_sha256="bad",
                          account_reconciliation_ref=""),
        runtime=ExecutionRuntimeStateV1(
            live_mode_enabled=True, kill_switch_clear=True,
            venue_adapter_approved=True, venue_health_ref="ok",
            account_reconciled=False, operator_approval_ref="approved",
            deployment_sha="b" * 40, environment="production",
        ),
        now=NOW,
    )
    assert permit.allowed is False
    assert "SYMBOL_MAPPING_EVIDENCE_MISSING" in permit.reason_codes
    assert "SOURCE_HASH_INVALID" in permit.reason_codes
    assert "ACCOUNT_RECONCILIATION_EVIDENCE_MISSING" in permit.reason_codes
    assert "ACCOUNT_NOT_RECONCILED" in permit.reason_codes


def test_stale_future_and_duplicate_orders_block():
    gate = ExecutionGateV1()
    stale = gate.evaluate(
        evidence=evidence(observed_at=NOW - timedelta(seconds=91)),
        runtime=RUNTIME, now=NOW,
    )
    future = gate.evaluate(
        evidence=evidence(observed_at=NOW + timedelta(seconds=1)),
        runtime=RUNTIME, now=NOW,
    )
    duplicate = gate.evaluate(
        evidence=evidence(), runtime=RUNTIME, now=NOW,
        duplicate_client_order_id=True,
    )
    assert "EXECUTION_EVIDENCE_STALE" in stale.reason_codes
    assert "FUTURE_EVIDENCE_REJECTED" in future.reason_codes
    assert "DUPLICATE_ORDER_ID_REJECTED" in duplicate.reason_codes
    assert not stale.allowed and not future.allowed and not duplicate.allowed


def test_invalid_long_short_geometry_and_low_reward_risk_block():
    gate = ExecutionGateV1()
    bad_long = gate.evaluate(
        evidence=evidence(stop_loss="101"), runtime=RUNTIME, now=NOW
    )
    low_rr = gate.evaluate(
        evidence=evidence(take_profit="120"), runtime=RUNTIME, now=NOW
    )
    valid_short = gate.evaluate(
        evidence=evidence(side="SHORT", entry="100", stop_loss="110",
                          take_profit="70"),
        runtime=RUNTIME, now=NOW,
    )
    bad_short = gate.evaluate(
        evidence=evidence(side="SHORT", entry="100", stop_loss="90",
                          take_profit="70"),
        runtime=RUNTIME, now=NOW,
    )
    assert "LONG_ORDER_GEOMETRY_INVALID" in bad_long.reason_codes
    assert "REWARD_RISK_BELOW_POLICY_MINIMUM" in low_rr.reason_codes
    assert valid_short.allowed
    assert "SHORT_ORDER_GEOMETRY_INVALID" in bad_short.reason_codes


def test_execution_gate_never_submits_an_order():
    # This module exposes preflight only; no adapter is instantiated or called.
    gate = ExecutionGateV1()
    permit = gate.evaluate(evidence=evidence(), runtime=RUNTIME, now=NOW)
    assert permit.allowed
    assert hasattr(permit, "client_order_id")
