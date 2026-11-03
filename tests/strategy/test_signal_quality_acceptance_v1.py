import json
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
    candidates = []
    outcomes = []
    total = wins + losses + timeouts
    for index in range(total):
        entry_time = START + (index // per_day) * 86400 + (index % per_day) * 60
        candidate_id = f"precision-candidate-{index:04d}"
        setup_id = f"precision-setup-{index:04d}"
        candidates.append({
            "schema": "hes_precision_entry_paper_candidate_v1",
            "event_id": candidate_id,
            "candidate_event_id": candidate_id,
            "setup_id": setup_id,
            "setup_context_sha256": "a" * 64,
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "1m",
            "direction": "LONG",
            "entry_time": entry_time,
            "entry_price": 100.0,
            "stop_price": 99.0,
            "target_price": 103.0,
            "paper_only": True,
            "preapproval_paper_eligible": True,
            "execution_enabled": False,
            "orders_placed": False,
        })
        if index < wins:
            outcome = "WIN"
            exit_price = 103.0
            gross_r = 3.0
        elif index < wins + losses:
            outcome = "LOSS"
            exit_price = 99.0
            gross_r = -1.0
        else:
            outcome = "TIMEOUT"
            exit_price = 100.2
            gross_r = 0.2
        outcomes.append({
            "schema": "hes_precision_entry_paper_outcome_v1",
            "event_id": f"precision-outcome-{index:04d}",
            "candidate_event_id": candidate_id,
            "setup_id": setup_id,
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "1m",
            "direction": "LONG",
            "entry_time": entry_time,
            "entry_price": 100.0,
            "exit_close_time": entry_time + 60,
            "exit_price": exit_price,
            "gross_r": gross_r,
            "outcome": outcome,
            "evidence_sha256": "e" * 64,
            "execution_enabled": False,
            "orders_placed": False,
        })

    (base / "precision_entry_candidates_v1.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in candidates),
        encoding="utf-8",
    )
    (base / "precision_entry_outcomes_v1.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in outcomes),
        encoding="utf-8",
    )
    (base / "precision_entry_cost_model_v1.json").write_text(
        json.dumps({
            "status": "VERIFIED",
            "fees_slippage_verified": True,
            "fee_fraction_per_side": 0.001,
            "slippage_fraction_per_side": 0.0005,
            "evidence_sha256": cost_hash,
        }),
        encoding="utf-8",
    )
    (base / "precision_entry_independent_oos_evidence_v1.json").write_text(
        json.dumps({
            "status": "PASS",
            "resolved_closed_trade_count": 100,
            "win_rate_pct": oos_win_rate,
            "wins": 91,
            "losses": 9,
            "breakevens": 0,
            "timeouts": 0,
            "evaluation_window_utc": {"start": "2026-09-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
            "long_short_split": {"LONG": {"wins": 50, "losses": 5}, "SHORT": {"wins": 41, "losses": 4}},
            "regime_split": {"UPTREND": {"wins": 55, "losses": 5}, "DOWNTREND": {"wins": 36, "losses": 4}},
            "net_expectancy_after_costs": 0.25,
            "profit_factor_after_costs": 2.1,
            "maximum_drawdown": 0.08,
            "fee_and_slippage_model": {"status": "VERIFIED", "evidence_sha256": "c" * 64},
            "out_of_sample_results": {"status": "PASS", "resolved_closed_trade_count": 100, "win_rate_pct": oos_win_rate},
            "evidence_sha256": oos_hash,
        }),
        encoding="utf-8",
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
