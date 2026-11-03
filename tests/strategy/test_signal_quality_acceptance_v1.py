import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

from forward.signal_quality_acceptance_v1 import (
    daily_signal_counts,
    evaluate_acceptance,
    load_contract,
)


START = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())


def write_artifacts(
    root,
    *,
    wins=91,
    losses=9,
    timeouts=0,
    per_day=3,
    cost_hash="c" * 64,
    oos_win_rate=91.0,
    oos_hash="b" * 64,
):
    base = root / "data" / "forward"
    base.mkdir(parents=True, exist_ok=True)
    events, candidates, outcomes, setups = [], [], [], []
    total = wins + losses + timeouts

    def canonical(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
        ).hexdigest()

    for index in range(total):
        candidate_time = START + (index // per_day) * 86400 + (index % per_day) * 900
        entry_time = candidate_time + 60
        candidate_id = f"precision-candidate-{index:04d}"
        setup_id = f"hes-setup-BTC_USDT-15m-{candidate_time}-LONG"
        gate = {
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "15m",
            "structure": {"status": "OBSERVED", "regime": "UPTREND"},
            "confirmation": {"state": "CONFIRMED_LONG"},
            "risk": {"state": "RISK_APPROVED"},
            "final_decision": "NO_TRADE",
        }
        context_base = {
            "schema": "hes_strategy_entry_context_v1",
            "setup_id": setup_id,
            "source": "strategy_policy_v2",
            "market_data_source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "15m",
            "direction": "LONG",
            "observed_at": candidate_time,
            "valid_until": candidate_time + 900,
            "planned_entry_price": 100.0,
            "entry_zone_low": 99.75,
            "entry_zone_high": 100.0,
            "entry_zone_policy": "FAVORABLE_SIDE_RISK_FRACTION_V1",
            "entry_zone_fraction_of_risk": 0.25,
            "stop_price": 99.0,
            "target_price": 103.0,
            "planned_rr": 3.0,
            "risk_gate_state": "RISK_APPROVED",
            "confirmation_state": "CONFIRMED_LONG",
            "market_regime": "UPTREND",
            "policy_version": "test-policy-v1",
            "gate_evidence_sha256": canonical(gate),
            "setup_validated_15m": True,
            "execution_enabled": False,
            "orders_placed": False,
        }
        context = {**context_base, "evidence_sha256": canonical(context_base)}
        gate["entry_context"] = context
        setups.append({
            "schema": "hes_strategy_policy_v2_paper_candidate",
            "event_id": f"hes-v2-candidate-BTC_USDT-15m-{candidate_time}",
            "candidate_event_id": f"hes-v2-candidate-BTC_USDT-15m-{candidate_time}",
            "candidate_time": candidate_time,
            "evaluation_mode": "PREAPPROVAL_PAPER_ONLY",
            "preapproval_paper_eligible": True,
            "entry_context": context,
            "gate_evidence": gate,
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "execution_enabled": False,
            "orders_placed": False,
        })
        candidate_row = {
            "schema": "hes_precision_entry_paper_candidate_v1",
            "event_id": candidate_id,
            "candidate_event_id": candidate_id,
            "setup_id": setup_id,
            "setup_context": context,
            "setup_context_sha256": context["evidence_sha256"],
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "1m",
            "direction": "LONG",
            "market_regime": "UPTREND",
            "entry_time": entry_time,
            "entry_price": 100.0,
            "stop_price": 99.0,
            "target_price": 103.0,
            "max_hold_seconds": 86400,
            "paper_only": True,
            "preapproval_paper_eligible": True,
            "execution_enabled": False,
            "orders_placed": False,
        }
        candidates.append(candidate_row)
        events.append({
            "schema": "hes_precision_entry_event_v1",
            "event_id": f"hes-precision-event:{setup_id}:{entry_time}",
            "observed_at": "2026-10-01T00:00:00+00:00",
            "setup_id": setup_id,
            "setup_context": context,
            "setup_context_sha256": context["evidence_sha256"],
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "1m",
            "candle_close_time": entry_time,
            "decision": "READY",
            "direction": "LONG",
            "market_regime": "UPTREND",
            "reason_codes": [],
            "engine_evidence": {},
            "evidence_sha256": "f" * 64,
            "execution_enabled": False,
            "orders_placed": False,
        })

        if index < wins:
            outcome, exit_price, gross_r = "WIN", 103.0, 3.0
            exit_close_time = entry_time + 60
            exit_bar = {"schema":"hes_global_candle_v1","source":"gateio_public_spot","symbol":"BTC_USDT","timeframe":"1m","closed":True,"open_time":exit_close_time-60,"close_time":exit_close_time,"open":"100.0","high":"103.5","low":"99.5","close":"103.0","volume":"1.0"}
            reason = "TAKE_PROFIT_HIT"
        elif index < wins + losses:
            outcome, exit_price, gross_r = "LOSS", 99.0, -1.0
            exit_close_time = entry_time + 60
            exit_bar = {"schema":"hes_global_candle_v1","source":"gateio_public_spot","symbol":"BTC_USDT","timeframe":"1m","closed":True,"open_time":exit_close_time-60,"close_time":exit_close_time,"open":"100.0","high":"101.0","low":"98.5","close":"99.0","volume":"1.0"}
            reason = "STOP_LOSS_HIT"
        else:
            outcome, exit_price, gross_r = "TIMEOUT", 100.2, 0.2
            exit_close_time = entry_time + 86400
            exit_bar = {"schema":"hes_global_candle_v1","source":"gateio_public_spot","symbol":"BTC_USDT","timeframe":"1m","closed":True,"open_time":exit_close_time-60,"close_time":exit_close_time,"open":"100.0","high":"100.5","low":"99.5","close":"100.2","volume":"1.0"}
            reason = "MAX_HOLD_24H_REACHED"
        outcomes.append({
            "schema": "hes_precision_entry_paper_outcome_v1",
            "event_id": f"precision-outcome-{index:04d}",
            "candidate_event_id": candidate_id,
            "setup_id": setup_id,
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "1m",
            "direction": "LONG",
            "market_regime": "UPTREND",
            "entry_time": entry_time,
            "entry_price": 100.0,
            "exit_close_time": exit_close_time,
            "exit_price": exit_price,
            "gross_r": gross_r,
            "outcome": outcome,
            "reason": reason,
            "exit_candle": exit_bar,
            "exit_candle_sha256": canonical(exit_bar),
            "evidence_sha256": canonical({"candidate": candidate_row, "exit_bar": exit_bar, "outcome": outcome}),
            "execution_enabled": False,
            "orders_placed": False,
        })

    (base / "strategy_policy_v2_eval_candidates.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in setups), encoding="utf-8"
    )
    (base / "precision_entry_events_v1.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in events), encoding="utf-8"
    )
    (base / "precision_entry_candidates_v1.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in candidates), encoding="utf-8"
    )
    (base / "precision_entry_outcomes_v1.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in outcomes), encoding="utf-8"
    )
    cost_model = {
        "status": "VERIFIED",
        "fees_slippage_verified": True,
        "fee_fraction_per_side": 0.001,
        "slippage_fraction_per_side": 0.0005,
        "evidence_sha256": cost_hash,
    }
    cost_model["model_sha256"] = canonical(cost_model)
    (base / "precision_entry_cost_model_v1.json").write_text(
        json.dumps(cost_model, sort_keys=True), encoding="utf-8"
    )
    oos_report = {
        "status": "PASS",
        "resolved_closed_trade_count": 100,
        "win_rate_pct": oos_win_rate,
        "wins": 91,
        "losses": 9,
        "breakevens": 0,
        "timeouts": 0,
        "evaluation_window_utc": {"start": "2026-09-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
        "long_short_split": {"LONG": {"wins": 91, "losses": 9}, "SHORT": {"wins": 0, "losses": 0}},
        "regime_split": {"UPTREND": {"wins": 91, "losses": 9}, "DOWNTREND": {"wins": 0, "losses": 0}},
        "net_expectancy_after_costs": 0.25,
        "profit_factor_after_costs": 2.1,
        "maximum_drawdown": 0.08,
        "fee_and_slippage_model": {"status": "VERIFIED", "evidence_sha256": cost_hash},
        "out_of_sample_results": {"status": "PASS", "resolved_closed_trade_count": 100, "win_rate_pct": oos_win_rate},
        "evidence_sha256": oos_hash,
    }
    try:
        oos_report["report_sha256"] = canonical(oos_report)
    except ValueError:
        # Deliberately malformed numeric fixtures must still reach the fail-closed validator.
        oos_report["report_sha256"] = "0" * 64
    (base / "precision_entry_independent_oos_evidence_v1.json").write_text(
        json.dumps(oos_report, sort_keys=True), encoding="utf-8"
    )
    return base, candidates, outcomes

def evaluate(root):
    root = Path(root)
    contract = root / "docs" / "execution" / "SIGNAL_QUALITY_ACCEPTANCE_CONTRACT_V1.json"
    if not contract.exists():
        source = Path(__file__).resolve().parents[2] / "docs" / "execution" / contract.name
        contract.parent.mkdir(parents=True, exist_ok=True)
        contract.write_bytes(source.read_bytes())
    return evaluate_acceptance(
        root=root,
        metrics={},  # precision cohort is derived from its own append-only ledgers
        candidates=[],  # 15m baseline candidates must never count as precision entries
        independent_oos=None,
    )


def test_contract_uses_precision_entry_cohort_and_fixed_acceptance_rules():
    contract, digest = load_contract(__import__("pathlib").Path(__file__).resolve().parents[2])
    gate = contract["paper_performance_gate"]
    assert gate["performance_cohort"] == "PRECISION_ENTRY_PAPER_ELIGIBLE"
    assert gate["win_rate_operator"] == ">"
    assert gate["win_rate_pct"] == 90
    assert gate["minimum_resolved_closed_trades"] == 100
    assert contract["signal_constraints"]["max_actionable_signals_per_utc_day"] == 3
    assert len(digest) == 64


def test_one_hundred_resolved_precision_trades_over_90_percent_can_pass(tmp_path):
    write_artifacts(tmp_path)
    result = evaluate(tmp_path)
    assert result["status"] == "PASS", result
    assert result["resolved_closed_trade_count"] == 100
    assert result["observed_win_rate_pct"] == 91.0
    assert result["daily_signal_counts"]["max_signals_in_any_utc_day"] == 3
    assert result["execution_enabled"] is False
    assert result["orders_placed"] is False


def test_exactly_ninety_percent_does_not_pass(tmp_path):
    write_artifacts(tmp_path, wins=90, losses=10)
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert "STRICT_WIN_RATE_GT_90_NOT_MET" in result["reasons"]


def test_fewer_than_one_hundred_resolved_trades_does_not_pass(tmp_path):
    write_artifacts(tmp_path, wins=91, losses=8, timeouts=1)
    result = evaluate(tmp_path)
    assert result["resolved_closed_trade_count"] == 99
    assert result["precision_entry_ledger"]["timeouts"] == 1
    assert "MINIMUM_RESOLVED_TRADES_NOT_MET" in result["reasons"]


def test_four_actionable_precision_entries_in_one_utc_day_are_blocked(tmp_path):
    write_artifacts(tmp_path, per_day=4)
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert result["daily_signal_counts"]["max_signals_in_any_utc_day"] == 4
    assert "DAILY_SIGNAL_CAP_EXCEEDED" in result["reasons"]


def test_fifteen_minute_preapproval_candidates_do_not_count_as_precision_entries():
    rows = [{
        "preapproval_paper_eligible": True,
        "candidate_time": START,
        "event_id": "15m-baseline-only",
    }]
    result = daily_signal_counts(rows, performance_cohort="PRECISION_ENTRY_PAPER_ELIGIBLE")
    assert result["max_signals_in_any_utc_day"] == 0


def test_non_finite_or_non_numeric_oos_win_rate_fails_closed(tmp_path):
    for value in (float("nan"), float("inf"), float("-inf"), True, "91.0"):
        write_artifacts(tmp_path, oos_win_rate=value)
        result = evaluate(tmp_path)
        assert result["status"] == "NOT_MET"
        assert "INDEPENDENT_OOS_WIN_RATE_INVALID" in result["reasons"]


def test_cost_model_requires_a_valid_content_hash(tmp_path):
    write_artifacts(tmp_path, cost_hash="not-a-sha256")
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert "VERIFIED_FEE_SLIPPAGE_MODEL_MISSING" in result["reasons"]


def test_independent_oos_requires_valid_provenance_hash(tmp_path):
    write_artifacts(tmp_path, oos_hash="not-a-sha256")
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert "INDEPENDENT_OOS_PROVENANCE_MISSING" in result["reasons"]


def test_unmatched_outcome_is_not_counted(tmp_path):
    base, _, outcomes = write_artifacts(tmp_path)
    unmatched = dict(outcomes[0])
    unmatched["event_id"] = "unmatched-outcome"
    unmatched["candidate_event_id"] = "candidate-does-not-exist"
    with (base / "precision_entry_outcomes_v1.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(unmatched) + "\n")
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert result["unmatched_outcome_records"] == 1
    assert "UNMATCHED_OUTCOMES_PRESENT" in result["reasons"]


def test_duplicate_outcome_link_is_ambiguous_and_blocked(tmp_path):
    base, _, outcomes = write_artifacts(tmp_path)
    duplicate = dict(outcomes[0])
    duplicate["event_id"] = "duplicate-outcome-event"
    with (base / "precision_entry_outcomes_v1.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(duplicate) + "\n")
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert result["ambiguous_outcome_links"] == 1
    assert "AMBIGUOUS_OUTCOME_LINKS_PRESENT" in result["reasons"]


def test_missing_precision_ledger_fails_closed(tmp_path):
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert "PRECISION_ENTRY_LEDGER_MISSING" in result["reasons"]
    assert result["resolved_closed_trade_count"] == 0


def test_malformed_candidate_is_not_accepted_as_actionable(tmp_path):
    base, candidates, _ = write_artifacts(tmp_path)
    candidates[0]["execution_enabled"] = True
    (base / "precision_entry_candidates_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in candidates),
        encoding="utf-8",
    )
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert "INVALID_PRECISION_CANDIDATE_RECORDS" in result["reasons"]


def test_independent_oos_report_must_include_all_required_metrics(tmp_path):
    base, _, _ = write_artifacts(tmp_path)
    path = base / "precision_entry_independent_oos_evidence_v1.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report.pop("regime_split")
    path.write_text(json.dumps(report), encoding="utf-8")
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert "INDEPENDENT_OOS_REPORT_INCOMPLETE" in result["reasons"]


def test_oos_report_cost_model_hash_must_match_verified_cost_model(tmp_path):
    base, _, _ = write_artifacts(tmp_path)
    path = base / "precision_entry_independent_oos_evidence_v1.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["fee_and_slippage_model"]["evidence_sha256"] = "d" * 64
    path.write_text(json.dumps(report), encoding="utf-8")
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert "INDEPENDENT_OOS_COST_MODEL_MISMATCH" in result["reasons"]


def test_duplicate_setup_candidate_is_blocked(tmp_path):
    base, candidates, _ = write_artifacts(tmp_path)
    candidates[1]["setup_id"] = candidates[0]["setup_id"]
    context = dict(candidates[1]["setup_context"])
    context["setup_id"] = candidates[0]["setup_id"]
    context_base = {k: v for k, v in context.items() if k != "evidence_sha256"}
    context["evidence_sha256"] = hashlib.sha256(
        json.dumps(context_base, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    ).hexdigest()
    candidates[1]["setup_context"] = context
    candidates[1]["setup_context_sha256"] = context["evidence_sha256"]
    (base / "precision_entry_candidates_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in candidates),
        encoding="utf-8",
    )
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert "DUPLICATE_PRECISION_SETUP_CANDIDATES" in result["reasons"]


def test_outcome_gross_r_must_match_candidate_and_exit_prices(tmp_path):
    base, _, outcomes = write_artifacts(tmp_path)
    outcomes[0]["gross_r"] = 2.5
    (base / "precision_entry_outcomes_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in outcomes),
        encoding="utf-8",
    )
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert result["unscorable_outcomes"] == 1
    assert "UNSCORABLE_OUTCOMES_PRESENT" in result["reasons"]


def test_oos_win_rate_must_match_the_reported_win_loss_counts(tmp_path):
    base, _, _ = write_artifacts(tmp_path)
    path = base / "precision_entry_independent_oos_evidence_v1.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["win_rate_pct"] = 95.0
    report["out_of_sample_results"]["win_rate_pct"] = 95.0
    path.write_text(json.dumps(report), encoding="utf-8")
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert "INDEPENDENT_OOS_METRICS_INCONSISTENT" in result["reasons"]


def test_verified_costs_are_applied_to_the_official_win_rate(tmp_path):
    base, _, _ = write_artifacts(tmp_path)
    cost_path = base / "precision_entry_cost_model_v1.json"
    cost = json.loads(cost_path.read_text(encoding="utf-8"))
    cost["fee_fraction_per_side"] = 0.02
    cost["slippage_fraction_per_side"] = 0.02
    cost.pop("model_sha256", None)
    canonical_cost = json.dumps(cost, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    cost["model_sha256"] = __import__("hashlib").sha256(canonical_cost).hexdigest()
    cost_path.write_text(json.dumps(cost, sort_keys=True), encoding="utf-8")
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert result["observed_win_rate_pct"] == 0.0
    assert "STRICT_WIN_RATE_GT_90_NOT_MET" in result["reasons"]


def test_candidate_and_outcome_market_regime_must_match(tmp_path):
    base, _, outcomes = write_artifacts(tmp_path)
    outcomes[0]["market_regime"] = "DOWNTREND"
    (base / "precision_entry_outcomes_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in outcomes),
        encoding="utf-8",
    )
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert result["unscorable_outcomes"] == 1
    assert "UNSCORABLE_OUTCOMES_PRESENT" in result["reasons"]


def test_cost_adjusted_metrics_and_attribution_are_reported(tmp_path):
    write_artifacts(tmp_path)
    result = evaluate(tmp_path)
    assert result["net_expectancy_after_costs"] > 0
    assert result["profit_factor_after_costs"] > 1
    assert result["maximum_drawdown"] >= 0
    assert result["long_short_split"]["LONG"]["wins"] == 91
    assert result["regime_split"]["UPTREND"]["wins"] == 91


def test_precision_candidate_requires_direction_aligned_market_regime(tmp_path):
    base, candidates, _ = write_artifacts(tmp_path)
    candidates[0]["market_regime"] = "DOWNTREND"
    (base / "precision_entry_candidates_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in candidates), encoding="utf-8"
    )
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert "INVALID_PRECISION_CANDIDATE_RECORDS" in result["reasons"]


def test_precision_candidate_requires_matching_ready_event(tmp_path):
    base, _, _ = write_artifacts(tmp_path)
    path = base / "precision_entry_events_v1.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows.pop(0)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert result["candidate_event_link_missing"] == 1
    assert "PRECISION_CANDIDATE_EVENT_LINK_MISSING" in result["reasons"]


def test_outcome_exit_candle_and_evidence_hash_must_match(tmp_path):
    base, _, outcomes = write_artifacts(tmp_path)
    outcomes[0]["exit_candle"]["high"] = "100.5"
    (base / "precision_entry_outcomes_v1.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in outcomes), encoding="utf-8"
    )
    result = evaluate(tmp_path)
    assert result["status"] == "NOT_MET"
    assert result["unscorable_outcomes"] == 1
    assert "UNSCORABLE_OUTCOMES_PRESENT" in result["reasons"]


def test_acceptance_reads_contract_from_release_and_ledgers_from_shared_data_root(tmp_path):
    code_root = tmp_path / "release"
    shared_root = tmp_path / "shared"
    contract_source = Path(__file__).resolve().parents[2] / "docs" / "execution" / "SIGNAL_QUALITY_ACCEPTANCE_CONTRACT_V1.json"
    contract_target = code_root / "docs" / "execution" / contract_source.name
    contract_target.parent.mkdir(parents=True, exist_ok=True)
    contract_target.write_bytes(contract_source.read_bytes())
    write_artifacts(shared_root)
    result = evaluate_acceptance(
        root=code_root,
        data_root=shared_root,
        metrics={},
        candidates=[],
        independent_oos=None,
    )
    assert result["status"] == "PASS", result
    assert result["resolved_closed_trade_count"] == 100


def test_strategy_and_learning_helpers_preserve_strictly_greater_than_90_percent():
    from scripts.run_strategy_policy_v2_forward_eval import win_rate_target_met as evaluator_target
    from scripts.run_strategy_learning_loop_v1 import win_rate_target_met as learning_target
    metrics = {"eligible_resolved": 100, "eligible_win_rate_pct": 90.0,
               "unmatched_outcome_records": 0, "ambiguous_legacy_timestamp_matches": 0,
               "eligible_unscorable_outcomes": 0}
    assert evaluator_target(metrics, minimum_resolved=100, target_pct=90.0, cohort="eligible") is False
    metrics["eligible_win_rate_pct"] = 90.01
    assert evaluator_target(metrics, minimum_resolved=100, target_pct=90.0, cohort="eligible") is True
    assert learning_target(resolved=100, win_rate_pct=90.0, unmatched_outcomes=0,
                           ambiguous_outcomes=0, unscorable_outcomes=0,
                           minimum_resolved=100, target_pct=90.0) is False
    assert learning_target(resolved=100, win_rate_pct=90.01, unmatched_outcomes=0,
                           ambiguous_outcomes=0, unscorable_outcomes=0,
                           minimum_resolved=100, target_pct=90.0) is True
