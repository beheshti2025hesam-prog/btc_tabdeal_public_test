from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_private_snapshot_service_is_one_shot_credential_scoped_and_hardened():
    unit = (ROOT / "deploy/systemd/hes-tabdeal-private-readonly-snapshot.service").read_text()
    assert "Type=oneshot" in unit
    assert "User=hes-tabdeal-reader" in unit
    assert "Group=hes-tabdeal-reader" in unit
    assert "LoadCredentialEncrypted=tabdeal_api_key:/etc/credstore.encrypted/hes-tabdeal-api-key" in unit
    assert "LoadCredentialEncrypted=tabdeal_api_secret:/etc/credstore.encrypted/hes-tabdeal-api-secret" in unit
    assert "StateDirectory=hes-tabdeal-readonly" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6" in unit
    assert "TimeoutStartSec=60" in unit


def test_private_snapshot_script_uses_get_only_client_and_never_persists_raw_trade_rows():
    script = (ROOT / "scripts/run_tabdeal_private_readonly_snapshot_v1.py").read_text()
    assert "client.get_account" in script
    assert "client.get_balance" in script
    assert "client.get_user_trades" in script
    assert "client.get_income" in script
    assert "client.get_force_orders" in script
    assert "client.post" not in script
    assert "client.delete" not in script
    assert '"raw_user_trades_persisted": False' in script
    assert '"raw_income_persisted": False' in script
    assert '"write_endpoints_called": False' in script


def test_snapshot_runner_uses_end_time_only_until_start_time_filter_is_fixed():
    script = (ROOT / "scripts/run_tabdeal_private_readonly_snapshot_v1.py").read_text()
    assert "endTime=end_ms" in script
    assert "startTime=" not in script
    assert "END_TIME_ONLY_CAPPED_NO_LOWER_BOUND_COMPLETENESS_UNKNOWN" in script
