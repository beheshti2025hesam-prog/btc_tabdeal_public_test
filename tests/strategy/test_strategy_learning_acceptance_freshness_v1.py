import json
from datetime import datetime, timedelta, timezone

from scripts import run_strategy_learning_loop_v1 as learning


def test_fresh_strategy_acceptance_report_is_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(learning, "DATA", tmp_path)
    acceptance = {"schema": "hes_signal_quality_acceptance_result_v1", "status": "NOT_MET", "resolved_closed_trade_count": 0}
    (tmp_path / "strategy_policy_v2_eval_report.json").write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "signal_quality_acceptance": acceptance,
    }))
    assert learning.read_acceptance() == acceptance


def test_stale_strategy_acceptance_report_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(learning, "DATA", tmp_path)
    acceptance = {"schema": "hes_signal_quality_acceptance_result_v1", "status": "PASS"}
    stale = datetime.now(timezone.utc) - timedelta(hours=2)
    (tmp_path / "strategy_policy_v2_eval_report.json").write_text(json.dumps({
        "updated_at": stale.isoformat(),
        "signal_quality_acceptance": acceptance,
    }))
    assert learning.read_acceptance() == {}


def test_naive_or_invalid_acceptance_timestamp_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(learning, "DATA", tmp_path)
    for stamp in ("2026-11-03T14:00:00", "not-a-time"):
        (tmp_path / "strategy_policy_v2_eval_report.json").write_text(json.dumps({
            "updated_at": stamp,
            "signal_quality_acceptance": {"schema": "hes_signal_quality_acceptance_result_v1", "status": "PASS"},
        }))
        assert learning.read_acceptance() == {}
