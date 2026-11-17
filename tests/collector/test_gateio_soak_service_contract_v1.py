from pathlib import Path


def test_gateio_24h_soak_is_not_automatically_restarted_after_failure():
    root = Path(__file__).resolve().parents[2]
    unit = root / "deploy/systemd/hes-global-market-data-gateio-soak.service"
    text = unit.read_text(encoding="utf-8")

    assert "Restart=no" in text
    assert "Restart=on-failure" not in text
    assert "ExecStartPre=" in text
    assert ".archive." in text
    assert ".attempt." not in text
    assert "soak_gateio_feed_24h_v2.py" in text


def test_gateio_24h_soak_runs_unprivileged_with_strict_sandbox():
    root = Path(__file__).resolve().parents[2]
    unit = root / "deploy/systemd/hes-global-market-data-gateio-soak.service"
    text = unit.read_text(encoding="utf-8")

    assert "User=sentinelx" in text
    assert "Group=sentinelx" in text
    assert "NoNewPrivileges=true" in text
    assert "CapabilityBoundingSet=" in text
    assert "AmbientCapabilities=" in text
    assert "ProtectSystem=strict" in text
    assert "ReadWritePaths=/opt/hes-trade-agent/data/forward" in text
