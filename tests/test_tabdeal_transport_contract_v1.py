import json
from pathlib import Path


CONTRACT_PATH = Path(__file__).resolve().parents[1] / "forward" / "tabdeal_transport_contract_v1.json"


def test_transport_contract_matches_read_only_bounded_implementation():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["schema"] == "hes_forward_tabdeal_transport_v1"
    assert contract["mode"] == "READ_ONLY"
    assert contract["url"] == "wss://api1.tabdeal.org/special_margin/broadcast/"
    assert contract["symbol"] == "BTC_USDT"
    assert contract["bounded_session_required"] is True
    assert contract["default_max_runtime_seconds"] == 60
    assert contract["non_trade_frames"] == "IGNORE_WITH_COUNTER"
    assert contract["rejection_reason_required"] is True
    assert contract["transport_metadata_callback"] == "OPTIONAL_SANITIZED_DIAGNOSTICS"
    assert contract["raw_frame_persistence"] is False


def test_transport_contract_keeps_all_side_effects_disabled():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["persistence_enabled"] is False
    assert contract["execution_enabled"] is False
    assert contract["git_write_enabled"] is False
    assert contract["systemd_control_enabled"] is False
    assert contract["strategy_enabled"] is False
    assert contract["collector_enablement"] is False
    assert contract["fail_closed"] is True
