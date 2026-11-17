from pathlib import Path


def test_gateio_market_data_services_are_strictly_read_only_outside_evidence_dir():
    root = Path(__file__).resolve().parents[2]
    units = (
        "deploy/systemd/hes-global-market-data-gateio.service",
        "deploy/systemd/hes-global-market-data-gateio-1h.service",
        "deploy/systemd/hes-global-market-data-gateio-4h.service",
        "deploy/systemd/hes-global-market-data-gateio-1m.service.candidate",
        "deploy/systemd/hes-global-market-data-gateio-soak.service",
    )
    for relative in units:
        text = (root / relative).read_text(encoding="utf-8")
        assert "User=sentinelx" in text, relative
        assert "Group=sentinelx" in text, relative
        assert "NoNewPrivileges=true" in text, relative
        assert "ProtectSystem=strict" in text, relative
        assert "ReadWritePaths=/opt/hes-trade-agent/data/forward" in text, relative
