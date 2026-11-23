from datetime import datetime, timezone, timedelta
from forward.trade_journal_view_v1 import _decision_verification

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)

def matured(**overrides):
    row = {
        "validation_status": "VALIDATED_24H",
        "gate_qualification": {"status": "QUALIFIED", "geometry_valid": True,
            "confirmation_state": "CONFIRMED_LONG", "risk_state": "RISK_APPROVED"},
        "independent_candidate_attribution": {"candidate_generation_authorized": True},
        "structure_only_shadow": {"candidate_valid_pass": True,
            "economic_status": "EXECUTION_INSTRUMENT_VERIFIED",
            "horizons": {"24h": {"observed_1m_candles": 1440,
                "expected_1m_candles": 1440, "ambiguous_same_candle": False,
                "outcome_class": "SHADOW_STOP_HIT"}}},
    }
    row.update(overrides)
    return row

def test_missing_maturity_is_pending_before_24h():
    result = _decision_verification("e1", NOW - timedelta(hours=2), {}, NOW)
    assert result["state"] == "PENDING"

def test_incomplete_horizon_is_pending():
    row = matured(validation_status="INCOMPLETE_FORWARD_COVERAGE")
    assert _decision_verification("e1", NOW-timedelta(days=2), {"e1": row}, NOW)["state"] == "PENDING"

def test_unqualified_rejected_setup_is_not_classified_as_missed_profit():
    row = matured()
    row["gate_qualification"]["status"] = "REJECTED"
    row["structure_only_shadow"]["horizons"]["24h"]["outcome_class"] = "SHADOW_TARGET_HIT"
    result = _decision_verification("e1", NOW-timedelta(days=2), {"e1": row}, NOW)
    assert result["state"] == "POTENTIAL_ONLY"
    assert result["missed_profit"] == "POTENTIAL_NOT_COUNTED"

def test_only_fully_qualified_stop_path_gets_green_check():
    result = _decision_verification("e1", NOW-timedelta(days=2), {"e1": matured()}, NOW)
    assert result["state"] == "CORRECT" and result["missed_profit"] == "NO"

def test_only_fully_qualified_target_path_gets_red_cross():
    row = matured()
    row["structure_only_shadow"]["horizons"]["24h"]["outcome_class"] = "SHADOW_TARGET_HIT"
    result = _decision_verification("e1", NOW-timedelta(days=2), {"e1": row}, NOW)
    assert result["state"] == "INCORRECT"
    assert result["missed_profit"] == "YES_HYPOTHETICAL"

def test_missing_instrument_proof_blocks_green_or_red():
    row = matured()
    row["structure_only_shadow"]["economic_status"] = "NOT_EXECUTION_EVIDENCE"
    row["structure_only_shadow"]["horizons"]["24h"]["outcome_class"] = "SHADOW_TARGET_HIT"
    result = _decision_verification("e1", NOW-timedelta(days=2), {"e1": row}, NOW)
    assert result["state"] == "POTENTIAL_ONLY"
    assert result["missed_profit"] != "YES_HYPOTHETICAL"
