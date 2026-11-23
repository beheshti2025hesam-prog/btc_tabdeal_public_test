from datetime import datetime, timezone
from dataclasses import replace
from types import SimpleNamespace

import pytest

import forward.strategy_family_paper_lane_v1 as lane
from forward.indicator_strategy_family_v1 import IndicatorCandidate


def _rows(tf):
    return [{
        "open_time": 1_700_000_000 + i * {"15m": 900, "1h": 3600, "4h": 14400}[tf],
        "open": "100", "high": "102", "low": "98", "close": "101",
        "volume": "10", "quote_volume": "1000", "closed": True,
    } for i in range(220)]


def _inputs():
    return {
        "source": lane.SOURCE, "symbol": lane.SYMBOL,
        "timeframes": {tf: _rows(tf) for tf in lane.TIMEFRAMES},
    }


def _candidate():
    return IndicatorCandidate(
        "indicator_strategy", "indicator-v1", "trend_confirmation", "SHORT",
        "BEARISH", 1_700_000_000, 10.0, 30.0,
        ("HTF_ALIGNMENT", "EMA_STACK"), {"adx_14": 25.0},
    )


def _patch_engines(monkeypatch, *, confirmation_state="CONFIRMED_SHORT", risk_state="RISK_APPROVED"):
    monkeypatch.setattr(lane, "build_snapshot", lambda *a, **k: SimpleNamespace(regime=SimpleNamespace(label="BEARISH")))
    monkeypatch.setattr(lane, "evaluate_indicator_family", lambda *a, **k: [_candidate()])
    monkeypatch.setattr(lane, "geometry", lambda *a, **k: {
        "entry": 100.0, "stop_loss": 110.0, "take_profit": 70.0, "rr": 3.0,
    })
    check = SimpleNamespace(name="structural_event_present", state="PASS", evidence_ref="event:bearish")
    confirmation = SimpleNamespace(
        state=confirmation_state, passed_count=3, required_count=3,
        reason_codes=("ALL_REQUIRED_CONFIRMATIONS_PASSED",), checks=(check,),
    )
    captured = {}
    def fake_confirmation(**kwargs):
        captured["proposal"] = kwargs["proposal"]
        return {"confirmation": confirmation}
    monkeypatch.setattr(lane, "evaluate_confirmation_evidence", fake_confirmation)
    risk_check = SimpleNamespace(name="risk_reward_gate_passed", state="PASS", evidence_ref="risk:3R")
    risk = SimpleNamespace(state=risk_state, reason_codes=("ALL_RISK_GATES_PASSED",) if risk_state == "RISK_APPROVED" else ("CONFIRMATION_NOT_VALID",), checks=(risk_check,))
    sizing = SimpleNamespace(approved=True, quantity=1.0, notional=100.0, risk_budget=0.5)
    def fake_risk(**kwargs):
        effective = risk
        if kwargs["confirmation"].state not in ("CONFIRMED_LONG", "CONFIRMED_SHORT"):
            effective = SimpleNamespace(state="RISK_REJECTED", reason_codes=("CONFIRMATION_NOT_VALID",), checks=(risk_check,))
        return {"risk": effective, "sizing": sizing, "risk_context_ok": True,
                "geometry_ok": True, "rr_ok": True, "config": {}}
    monkeypatch.setattr(lane, "evaluate_risk_evidence", fake_risk)
    return captured


def test_family_paper_lane_generates_candidate_but_never_execution(monkeypatch):
    captured = _patch_engines(monkeypatch)
    result = lane.evaluate_strategy_family_paper_lane(
        data=_inputs(), structure={"status": "OBSERVED", "regime": "DOWNTREND", "events": ["BOS_BEARISH"]},
        observed_at=datetime.now(timezone.utc), precision_entry_1m={"status": "READY"},
        news_context={"status": "READY", "veto_flags": []},
    )
    candidate = result["selected_candidate"]
    assert captured["proposal"].quality_score is None
    assert result["status"] == "CONFIRMED_RISK_APPROVED_PAPER_ONLY"
    assert candidate["direction"] == "SHORT" and candidate["rr"] == 3.0
    assert candidate["parent_family_id"] == "trend_breakout"
    assert candidate["paper_lane_activation_state"] == "PAPER_SHADOW_ACTIVE"
    assert candidate["live_activation_state"] == "CANDIDATE_LOCKED_NOT_ACTIVE"
    assert result["paper_lane_activation_state"] == "PAPER_SHADOW_ACTIVE"
    assert candidate["entry_semantics"] == "CLOSED_15M_REFERENCE_NOT_EXECUTION_FILL"
    assert candidate["paper_candidate_generation_authorized"] is True
    assert candidate["decision_authority"] is False
    assert candidate["execution_enabled"] is False and candidate["orders_placed"] is False


def test_legacy_range_variant_never_enters_mother_candidate_lane(monkeypatch):
    _patch_engines(monkeypatch)
    trend = _candidate()
    legacy_range = replace(trend, variant_id="range_mean_reversion", direction="LONG", regime="RANGE")
    monkeypatch.setattr(lane, "evaluate_indicator_family", lambda *a, **k: [trend, legacy_range])
    result = lane.evaluate_strategy_family_paper_lane(
        data=_inputs(), structure={"status": "OBSERVED", "regime": "DOWNTREND", "events": ["BOS_BEARISH"]},
        observed_at=datetime.now(timezone.utc), precision_entry_1m={"status": "READY"},
        news_context={"status": "READY", "veto_flags": []},
    )
    assert result["candidate_count"] == 1
    assert result["selected_candidate"]["variant_id"] == "trend_confirmation"
    research = result["research_families"]["range_mean_reversion"]
    assert research["status"] == "RESEARCH_ONLY_NOT_PROMOTED"
    assert research["legacy_indicator_variant_observed"] is True
    assert research["candidate_generation_authorized"] is False
    assert research["decision_authority"] is False
    assert research["execution_enabled"] is False


def test_range_only_indicator_candidate_does_not_become_signal(monkeypatch):
    _patch_engines(monkeypatch)
    legacy_range = replace(_candidate(), variant_id="range_mean_reversion", direction="LONG", regime="RANGE")
    monkeypatch.setattr(lane, "evaluate_indicator_family", lambda *a, **k: [legacy_range])
    result = lane.evaluate_strategy_family_paper_lane(
        data=_inputs(), structure={"status": "OBSERVED", "regime": "RANGE", "events": []},
        observed_at=datetime.now(timezone.utc), precision_entry_1m={"status": "READY"},
        news_context={"status": "READY", "veto_flags": []},
    )
    assert result["status"] == "NO_CANDIDATE"
    assert result["selected_candidate"] is None
    assert result["candidate_count"] == 0
    assert result["research_families"]["range_mean_reversion"]["status"] == "RESEARCH_ONLY_NOT_PROMOTED"


def test_news_veto_overrides_confirmation_and_risk(monkeypatch):
    _patch_engines(monkeypatch)
    result = lane.evaluate_strategy_family_paper_lane(
        data=_inputs(), structure={"status": "OBSERVED", "regime": "DOWNTREND", "events": ["BOS_BEARISH"]},
        observed_at=datetime.now(timezone.utc), precision_entry_1m={"status": "READY"},
        news_context={"status": "READY", "veto_flags": ["HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION"]},
    )
    candidate = result["selected_candidate"]
    assert result["status"] == "BLOCKED_NEWS_VETO"
    assert candidate["confirmation"]["state"] == "UNCONFIRMED"
    assert candidate["risk"]["state"] == "RISK_REJECTED"
    assert candidate["execution_enabled"] is False


def test_missing_news_context_and_precision_remain_fail_closed(monkeypatch):
    _patch_engines(monkeypatch)
    result = lane.evaluate_strategy_family_paper_lane(
        data=_inputs(), structure={"status": "OBSERVED", "regime": "DOWNTREND", "events": ["BOS_BEARISH"]},
        observed_at=datetime.now(timezone.utc), precision_entry_1m={"status": "BLOCKED"},
        news_context=None,
    )
    assert result["status"] == "BLOCKED_NEWS_VETO"
    assert "NEWS_CONTEXT_NOT_READY" in result["selected_candidate"]["news_veto_flags"]


def test_noncanonical_source_and_missing_history_block(monkeypatch):
    data = _inputs(); data["source"] = "other"
    result = lane.evaluate_strategy_family_paper_lane(
        data=data, structure={}, observed_at=datetime.now(timezone.utc),
        precision_entry_1m={}, news_context={"status": "READY", "veto_flags": []},
    )
    assert result["status"] == "BLOCKED"
    assert result["reason_codes"] == ["NON_CANONICAL_MARKET_IDENTITY"]
    data = _inputs(); data["timeframes"]["15m"] = data["timeframes"]["15m"][:219]
    result = lane.evaluate_strategy_family_paper_lane(
        data=data, structure={}, observed_at=datetime.now(timezone.utc),
        precision_entry_1m={}, news_context={"status": "READY", "veto_flags": []},
    )
    assert result["status"] == "BLOCKED"
    assert "INSUFFICIENT_CLOSED_CANDLES" in result["reason_codes"][0]
