import json

from scripts.ops.hes_runtime_healthcheck_v1 import _check_indicator_forward_paper
from scripts.ops.hes_operational_recovery_v1 import DEPENDENCIES, IGNORABLE_WHEN_INACTIVE, REPAIR_ORDER


def add_collector():
    checks = []
    def add(name, state, detail):
        checks.append({"check": name, "state": state, "detail": detail})
    return checks, add


def write_json(path, payload):
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_forward_observer_health_accepts_empty_bootstrapped_research_baseline(tmp_path):
    report = {
        "schema": "hes_indicator_strategy_forward_paper_report_v1",
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "decision_records": 0,
        "outcome_records": 0,
        "safety": {
            "research_only": True,
            "performance_eligible": False,
            "training_label_eligible": False,
            "decision_authority": False,
            "candidate_generation_authorized": False,
            "risk_gate_bypass": False,
            "execution_enabled": False,
            "orders_placed": False,
        },
    }
    state = {
        "schema": "hes_indicator_strategy_forward_paper_state_v2",
        "bootstrap_mode": "NO_RETROACTIVE_TRADES",
        "last_processed_1m_open_time": 100,
        "last_processed_signal_close_time": 90,
        "processed_1m_bars": 0,
        "active": {},
    }
    write_json(tmp_path / "indicator_strategy_forward_paper_report_v1.json", report)
    write_json(tmp_path / "indicator_strategy_forward_paper_state_v1.json", state)
    checks, add = add_collector()

    _check_indicator_forward_paper(tmp_path, add)

    assert checks
    assert all(row["state"] == "OK" for row in checks)


def test_forward_observer_health_rejects_unsafe_report_flags(tmp_path):
    report = {
        "schema": "hes_indicator_strategy_forward_paper_report_v1",
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "decision_records": 0,
        "outcome_records": 0,
        "safety": {
            "research_only": True,
            "performance_eligible": False,
            "training_label_eligible": False,
            "decision_authority": False,
            "candidate_generation_authorized": False,
            "risk_gate_bypass": False,
            "execution_enabled": True,
            "orders_placed": False,
        },
    }
    state = {
        "schema": "hes_indicator_strategy_forward_paper_state_v2",
        "bootstrap_mode": "NO_RETROACTIVE_TRADES",
        "last_processed_1m_open_time": 100,
        "last_processed_signal_close_time": 90,
        "processed_1m_bars": 0,
        "active": {},
    }
    write_json(tmp_path / "indicator_strategy_forward_paper_report_v1.json", report)
    write_json(tmp_path / "indicator_strategy_forward_paper_state_v1.json", state)
    checks, add = add_collector()

    _check_indicator_forward_paper(tmp_path, add)

    assert any(row["check"] == "indicator_forward:paper_only" and row["state"] == "CRITICAL" for row in checks)


def test_forward_observer_health_rejects_unlinked_or_unsafe_outcome(tmp_path):
    report = {
        "schema": "hes_indicator_strategy_forward_paper_report_v1",
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "decision_records": 0,
        "outcome_records": 1,
        "safety": {
            "research_only": True,
            "performance_eligible": False,
            "training_label_eligible": False,
            "decision_authority": False,
            "candidate_generation_authorized": False,
            "risk_gate_bypass": False,
            "execution_enabled": False,
            "orders_placed": False,
        },
    }
    state = {
        "schema": "hes_indicator_strategy_forward_paper_state_v2",
        "bootstrap_mode": "NO_RETROACTIVE_TRADES",
        "last_processed_1m_open_time": 100,
        "last_processed_signal_close_time": 90,
        "processed_1m_bars": 0,
        "active": {},
    }
    outcome = {
        "event_id": "outcome-1",
        "candidate_event_id": "missing-decision",
        "research_only": True,
        "performance_eligible": False,
        "training_label_eligible": False,
        "decision_authority": False,
        "execution_enabled": False,
        "orders_placed": False,
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "entry_timeframe": "1m",
        "direction": "LONG",
    }
    write_json(tmp_path / "indicator_strategy_forward_paper_report_v1.json", report)
    write_json(tmp_path / "indicator_strategy_forward_paper_state_v1.json", state)
    (tmp_path / "indicator_strategy_forward_paper_outcomes_v1.jsonl").write_text(json.dumps(outcome) + "\n", encoding="utf-8")
    checks, add = add_collector()

    _check_indicator_forward_paper(tmp_path, add)

    assert any(row["check"] == "indicator_forward:indicator_strategy_forward_paper_outcomes_v1.jsonl:paper_only" and row["state"] == "CRITICAL" for row in checks)


def test_forward_observer_is_in_bounded_recovery_after_all_feed_dependencies():
    service = "hes-indicator-strategy-forward-paper.service"
    assert service in REPAIR_ORDER
    assert DEPENDENCIES[service] == (
        "hes-global-market-data-gateio-1m.service",
        "hes-global-market-data-gateio.service",
        "hes-global-market-data-gateio-1h.service",
        "hes-global-market-data-gateio-4h.service",
    )
    assert {
        f"service:{service}",
        "freshness:indicator_strategy_forward_paper_report_v1.json",
        "indicator_forward:report_missing",
        "indicator_forward:state_missing",
    }.issubset(IGNORABLE_WHEN_INACTIVE[service])
