from pathlib import Path


def test_gateio_24h_soak_is_not_automatically_restarted_after_failure():
    root = Path(__file__).resolve().parents[2]
    unit = root / "deploy/systemd/hes-global-market-data-gateio-soak.service"
    text = unit.read_text(encoding="utf-8")
    dependencies = [
        line for line in text.splitlines()
        if line.startswith("Wants=") or line.startswith("After=")
    ]

    assert "Restart=no" in text
    assert "Restart=on-failure" not in text
    assert "ExecStartPre=" in text
    assert ".archive." in text
    assert ".attempt." not in text
    assert "ExecStart=/opt/hes-trade-agent/.venv/bin/python -u /opt/hes-trade-agent/current/scripts/soak_gateio_feed_24h_v2.py" in text
    assert "WorkingDirectory=/opt/hes-trade-agent/current" in text
    assert dependencies == ["Wants=network-online.target", "After=network-online.target"]
    # The soak must observe feed state, not start missing feeds and mask an outage.
    assert "hes-global-market-data-gateio.service" not in "\n".join(dependencies)
