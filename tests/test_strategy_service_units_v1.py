from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_paper_evaluator_service_uses_immutable_current_release():
    unit = (ROOT / "deploy/systemd/hes-strategy-paper-evaluator.service").read_text()
    assert "WorkingDirectory=/opt/hes-trade-agent/current" in unit
    assert "ExecStart=/opt/hes-trade-agent/.venv/bin/python -u /opt/hes-trade-agent/current/scripts/run_strategy_policy_v2_forward_eval.py" in unit
    assert "Environment=HES_DATA_ROOT=/opt/hes-trade-agent" in unit
    assert "ReadWritePaths=/opt/hes-trade-agent/data/forward /opt/hes-trade-agent/logs" in unit
    assert "ProtectSystem=strict" in unit
    assert "ExecStart=/opt/hes-trade-agent/scripts/" not in unit


def test_learning_loop_service_uses_immutable_current_release():
    unit = (ROOT / "deploy/systemd/hes-strategy-learning-loop.service").read_text()
    assert "WorkingDirectory=/opt/hes-trade-agent/current" in unit
    assert "ExecStart=/opt/hes-trade-agent/.venv/bin/python -u /opt/hes-trade-agent/current/scripts/run_strategy_learning_loop_v1.py" in unit
    assert "Environment=HES_DATA_ROOT=/opt/hes-trade-agent" in unit
    assert "ReadWritePaths=/opt/hes-trade-agent/data/forward /opt/hes-trade-agent/logs" in unit
    assert "ProtectSystem=strict" in unit
    assert "ExecStart=/opt/hes-trade-agent/scripts/" not in unit


def test_readonly_dashboard_waits_for_all_canonical_gateio_timeframes():
    unit = (ROOT / "deploy/systemd/hes-readonly-dashboard.service").read_text()
    expected = (
        "hes-global-market-data-gateio.service",
        "hes-global-market-data-gateio-1h.service",
        "hes-global-market-data-gateio-4h.service",
    )
    for service in expected:
        assert service in unit.split("After=", 1)[1].splitlines()[0]
        assert service in unit.split("Wants=", 1)[1].splitlines()[0]
    assert "Environment=HES_GLOBAL_MARKET_DATA_ROOT=/opt/hes-trade-agent" in unit
    assert "Environment=HES_STRATEGY_V2_REPORT_PATH=/opt/hes-trade-agent/data/forward/strategy_policy_v2_eval_report.json" in unit
    assert "ConditionPathExists=/opt/hes-trade-agent/data/forward/strategy_policy_v2_eval_report.json" in unit
    assert "Environment=HES_TRADE_JOURNAL_PATH=/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl" in unit
    assert "Environment=HES_NEWS_MONITOR_SNAPSHOT=/var/lib/hes-news-monitor/news_brief_latest.json" in unit
    assert "ReadOnlyPaths=/opt/hes-trade-agent/releases /opt/hes-trade-agent/data/forward" in unit
    assert "ReadWritePaths=" not in unit


def test_news_monitor_state_is_scoped_to_systemd_state_directory():
    dropin = (ROOT / "deploy/systemd/hes-readonly-dashboard.service.d/30-hes-news-monitor-state.conf").read_text()
    assert "StateDirectory=hes-news-monitor" in dropin
    assert "StateDirectoryMode=0750" in dropin
    assert "ReadWritePaths=/opt/hes-trade-agent" not in dropin
