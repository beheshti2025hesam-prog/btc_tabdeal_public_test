import importlib.util
from pathlib import Path
MODULE = Path(__file__).resolve().parents[2] / "forward" / "neutral_decision_outcomes_v1.py"
spec = importlib.util.spec_from_file_location("neutral_decision_outcomes_v1", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def candle(t, o, h, low, c):
    return {"source":"gateio_public_spot","symbol":"BTC_USDT","timeframe":"15m","closed":True,
            "open_time":t,"close_time":t+900,"open":o,"high":h,"low":low,"close":c,"volume":1}

def test_directionless_no_trade_is_not_mislabelled_as_missed_trade():
    candles=[candle(0,100,101,99,100),candle(900,100,102,99,101),candle(1800,101,103,100,102),candle(2700,102,104,101,103)]
    d={"event_id":"e1","observed_at":"1970-01-01T00:15:00+00:00","decision":"NO_TRADE","direction":"NONE","proposal_direction":"NONE","symbol":"BTC_USDT"}
    out=mod.evaluate_no_trade(d,candles,horizons={"30m":1800})[0]
    assert out["outcome_class"]=="DIRECTIONLESS_MARKET_CONTEXT"
    assert out["hypothetical_trade_outcome"] is None and out["close_change_pct"] is not None

def test_rejected_short_candidate_same_bar_is_ambiguous():
    candles=[candle(0,100,101,99,100),candle(900,100,101,99,100),candle(1800,100,106,88,103)]
    d={"event_id":"e2","observed_at":"1970-01-01T00:30:00+00:00","decision":"NO_TRADE","proposal_direction":"SHORT","proposal_entry":100,"proposal_stop_loss":105,"proposal_take_profit":90,"symbol":"BTC_USDT"}
    out=mod.evaluate_no_trade(d,candles,horizons={"15m":900})[0]
    assert out["outcome_class"]=="AMBIGUOUS_SAME_CANDLE" and out["gross_R"] is None

def test_not_matured_horizon_stays_pending():
    candles=[candle(0,100,101,99,100),candle(900,100,101,99,100)]
    d={"event_id":"e3","observed_at":"1970-01-01T00:15:00+00:00","decision":"NO_TRADE","direction":"NONE"}
    out=mod.evaluate_no_trade(d,candles,horizons={"4h":14400})[0]
    assert out["outcome_class"]=="PENDING" and out["horizon_complete"] is False

def test_invalid_candle_gap_fails_closed():
    try: mod.validate_candles([candle(0,100,101,99,100),candle(1800,100,101,99,100)])
    except ValueError as exc: assert "GAP_OR_DUPLICATE" in str(exc)
    else: raise AssertionError("gap must fail closed")

def test_costs_and_live_execution_are_never_invented_or_enabled():
    candles=[candle(0,100,101,99,100),candle(900,100,101,99,100),candle(1800,100,101,99,100),candle(2700,100,101,99,100)]
    d={"event_id":"e4","observed_at":"1970-01-01T00:15:00+00:00","decision":"NO_TRADE","direction":"NONE"}
    out=mod.evaluate_no_trade(d,candles,horizons={"30m":1800})[0]
    assert out["net_R"] is None and out["policy_mutation_enabled"] is False and out["execution_enabled"] is False


def test_evaluate_no_trade_still_fails_closed_without_a_baseline():
    candles=[candle(0,100,101,99,100),candle(900,100,101,99,100)]
    decision={"event_id":"too-old","observed_at":"1969-12-31T23:45:00+00:00","decision":"NO_TRADE","direction":"NONE"}
    try:
        mod.evaluate_no_trade(decision,candles,horizons={"15m":900})
    except ValueError as exc:
        assert str(exc)=="NO_CLOSED_CANDLE_AT_DECISION_TIME"
    else:
        raise AssertionError("missing baseline must never be fabricated")


def test_run_skips_retention_boundary_decision_and_continues_valid_records(tmp_path):
    import json
    data=tmp_path/"data"/"forward"
    data.mkdir(parents=True)
    decisions=[
        {"event_id":"too-old","observed_at":"1969-12-31T23:45:00+00:00","decision":"NO_TRADE","direction":"NONE","symbol":"BTC_USDT","timeframe":"15m"},
        {"event_id":"recent","observed_at":"1970-01-01T00:15:00+00:00","decision":"NO_TRADE","direction":"NONE","symbol":"BTC_USDT","timeframe":"15m"},
    ]
    candles=[candle(t,100,101,99,100+t/100000) for t in (0,900,1800,2700,3600)]
    (data/"trade_journal_v2.jsonl").write_text("".join(json.dumps(row)+"\n" for row in decisions),encoding="utf-8")
    (data/"global_market_candles_v1.jsonl").write_text("".join(json.dumps(row)+"\n" for row in candles),encoding="utf-8")

    summary=mod.run(tmp_path)
    assert summary["status"]=="PARTIAL_UNSCORABLE"
    assert summary["decision_count"]==2
    assert summary["unscorable_no_baseline_decisions"]==1
    assert summary["unscorable_no_baseline_reason"]=="NO_CLOSED_CANDLE_AT_DECISION_TIME"
    assert len(summary["unscorable_no_baseline_event_ids_sha256"])==64
    assert summary["new_records_added"]==1
    assert summary["pending_horizons_current_run"]==2
    assert summary["execution_enabled"] is False and summary["orders_placed"] is False

    outcomes=[json.loads(line) for line in (data/"neutral_decision_outcomes_v1.jsonl").read_text().splitlines() if line.strip()]
    assert len(outcomes)==1
    assert outcomes[0]["decision_event_id"]=="recent"
    assert outcomes[0]["horizon"]=="1h"
    assert outcomes[0]["outcome_class"]=="DIRECTIONLESS_MARKET_CONTEXT"
    assert outcomes[0]["execution_enabled"] is False and outcomes[0]["orders_placed"] is False
    report=json.loads((data/"neutral_decision_outcomes_report_v1.json").read_text())
    assert report["status"]=="PARTIAL_UNSCORABLE"


def test_run_does_not_mark_retention_boundary_unscorable_when_all_horizons_are_already_complete(tmp_path):
    import json
    data = tmp_path / "data" / "forward"
    data.mkdir(parents=True)
    decision = {
        "event_id": "already-scored-old",
        "observed_at": "1969-12-31T23:45:00+00:00",
        "decision": "NO_TRADE",
        "direction": "NONE",
        "symbol": "BTC_USDT",
        "timeframe": "15m",
    }
    candles = [candle(t, 100, 101, 99, 100 + t / 100000) for t in (0, 900, 1800, 2700, 3600)]
    (data / "trade_journal_v2.jsonl").write_text(json.dumps(decision) + "\n", encoding="utf-8")
    (data / "global_market_candles_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in candles), encoding="utf-8"
    )
    existing = []
    for horizon in mod.DEFAULT_HORIZONS:
        existing.append({
            "schema": mod.SCHEMA,
            "outcome_id": mod._stable_id(decision["event_id"], horizon),
            "decision_event_id": decision["event_id"],
            "horizon": horizon,
            "horizon_complete": True,
            "outcome_class": "DIRECTIONLESS_MARKET_CONTEXT",
        })
    (data / "neutral_decision_outcomes_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in existing), encoding="utf-8"
    )

    summary = mod.run(tmp_path)
    assert summary["status"] == "OK"
    assert summary["unscorable_no_baseline_decisions"] == 0
    assert summary["unscorable_no_baseline_horizons"] == 0
    assert summary["new_records_added"] == 0
    assert summary["complete_records"] == 3


def test_run_counts_only_missing_horizons_for_old_unscorable_decisions(tmp_path):
    import json
    data = tmp_path / "data" / "forward"
    data.mkdir(parents=True)
    decision = {
        "event_id": "partially-scored-old",
        "observed_at": "1969-12-31T23:45:00+00:00",
        "decision": "NO_TRADE",
        "direction": "NONE",
        "symbol": "BTC_USDT",
        "timeframe": "15m",
    }
    candles = [candle(t, 100, 101, 99, 100 + t / 100000) for t in (0, 900, 1800, 2700, 3600)]
    (data / "trade_journal_v2.jsonl").write_text(json.dumps(decision) + "\n", encoding="utf-8")
    (data / "global_market_candles_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in candles), encoding="utf-8"
    )
    existing = []
    for horizon in ("1h", "4h"):
        existing.append({
            "schema": mod.SCHEMA,
            "outcome_id": mod._stable_id(decision["event_id"], horizon),
            "decision_event_id": decision["event_id"],
            "horizon": horizon,
            "horizon_complete": True,
            "outcome_class": "DIRECTIONLESS_MARKET_CONTEXT",
        })
    (data / "neutral_decision_outcomes_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in existing), encoding="utf-8"
    )

    summary = mod.run(tmp_path)
    assert summary["status"] == "PARTIAL_UNSCORABLE"
    assert summary["unscorable_no_baseline_decisions"] == 1
    assert summary["unscorable_no_baseline_horizons"] == 1
    assert len(summary["unscorable_no_baseline_event_ids_sha256"]) == 64
    assert len(summary["unscorable_no_baseline_missing_horizons_sha256"]) == 64
