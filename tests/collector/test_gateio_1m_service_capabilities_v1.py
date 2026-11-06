from pathlib import Path


def test_gateio_1m_feed_runs_without_linux_capabilities():
    root = Path(__file__).resolve().parents[2]
    unit = root / "deploy/systemd/hes-global-market-data-gateio-1m.service.candidate"
    text = unit.read_text(encoding="utf-8")

    assert "User=sentinelx" in text
    assert "Group=sentinelx" in text
    assert "NoNewPrivileges=true" in text
    assert "CapabilityBoundingSet=" in text
    assert "AmbientCapabilities=" in text
    assert "ProtectSystem=strict" in text
    assert "ReadWritePaths=/opt/hes-trade-agent/data/forward" in text
