import json
from pathlib import Path


def test_native_feature_contract_is_draft_and_not_runtime_enabled():
    contract = json.loads(Path("forward/wallex_native_feature_context_contract_v1.json").read_text())
    assert contract["schema"] == "HES_WALLEX_NATIVE_FEATURE_CONTEXT_CONTRACT_V1"
    assert contract["status"] == "DRAFT_NOT_RUNTIME_ENABLED"
    assert contract["fail_closed"] is True
    assert contract["execution_enabled"] is False
    assert contract["output"]["signal_generation"] is False
    assert contract["output"]["trade_decision"] is False
    assert contract["output"]["historical_inputs_allowed"] is False
    assert contract["output"]["future_outcomes_allowed"] is False


def test_native_contract_requires_raw_response_replay_and_lineage():
    contract = json.loads(Path("forward/wallex_native_feature_context_contract_v1.json").read_text())
    evidence = contract["required_input"]["raw_response_evidence"]
    assert evidence["required_for_acceptance"] is True
    assert evidence["exact_raw_body_sha256_verified"] is True
    assert evidence["replay_parse_must_reproduce_candle_set"] is True
    assert evidence["observation_must_reference_raw_evidence"] is True
    assert "raw_response_replay_matches_exact_normalized_candle_set" in contract["promotion_gates"]
    assert "end_to_end_lineage_from_raw_response_to_feature_context" in contract["promotion_gates"]


def test_native_contract_never_maps_to_legacy_or_fabricates_sequence():
    contract = json.loads(Path("forward/wallex_native_feature_context_contract_v1.json").read_text())
    prohibited = set(contract["prohibited"])
    assert "wire_into_legacy_runtime_bridge" in prohibited
    assert "wire_into_controlled_forward_observation_runner" in prohibited
    assert "fabricate_sequence_ids" in prohibited
    assert "synthesize_missing_candles" in prohibited
    assert contract["source"]["sequence_semantics"] == "NOT_APPLICABLE_NATIVE_OHLCV"
    assert contract["source"]["accepted_resolutions"]["1"]["timeframe"] == "1m"
    assert contract["source"]["accepted_resolutions"]["60"]["timeframe"] == "1h"
    assert contract["source"]["accepted_resolutions"]["1D"]["timeframe"] == "1D"


def test_native_contract_does_not_admit_legacy_15m_as_native_resolution():
    contract = json.loads(Path("forward/wallex_native_feature_context_contract_v1.json").read_text())
    assert all(x["timeframe"] != "15m" for x in contract["source"]["accepted_resolutions"].values())
