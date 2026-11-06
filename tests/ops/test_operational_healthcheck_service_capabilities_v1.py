from pathlib import Path


def test_operational_healthcheck_uses_only_read_search_capability():
    root = Path(__file__).resolve().parents[2]
    unit = root / "deploy/systemd/hes-operational-healthcheck.service"
    text = unit.read_text(encoding="utf-8")

    assert "User=root" in text
    assert "Group=root" in text
    assert "NoNewPrivileges=true" in text
    assert "CapabilityBoundingSet=CAP_DAC_READ_SEARCH" in text
    assert "AmbientCapabilities=CAP_DAC_READ_SEARCH" in text
    assert "ProtectSystem=strict" in text
    assert "StateDirectory=hes-operational-health" in text
    assert "ReadWritePaths=/var/lib/hes-operational-health" in text
