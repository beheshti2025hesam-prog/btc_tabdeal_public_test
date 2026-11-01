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
