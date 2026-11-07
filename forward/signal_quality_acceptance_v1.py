"""Fail-closed evaluator for the versioned HES signal-quality acceptance contract."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

CONTRACT_RELATIVE_PATH = Path("docs/execution/SIGNAL_QUALITY_ACCEPTANCE_CONTRACT_V1.json")
PRECISION_15M_SETUP_CANDIDATES = Path("data/forward/strategy_policy_v2_eval_candidates.jsonl")
PRECISION_EVENTS = Path("data/forward/precision_entry_events_v1.jsonl")
PRECISION_CANDIDATES = Path("data/forward/precision_entry_candidates_v1.jsonl")
PRECISION_OUTCOMES = Path("data/forward/precision_entry_outcomes_v1.jsonl")
PRECISION_COST_MODEL = Path("data/forward/precision_entry_cost_model_v1.json")
PRECISION_OOS = Path("data/forward/precision_entry_independent_oos_evidence_v1.json")


def _finite_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _valid_sha256(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value.lower())
    )


def _canonical_hash_excluding(value: dict, field: str) -> str:
    payload = {key: item for key, item in value.items() if key != field}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _hash_matches(value: dict, field: str) -> bool:
    try:
        return _valid_sha256(value.get(field)) and value.get(field) == _canonical_hash_excluding(value, field)
    except (TypeError, ValueError):
        return False


def _read_jsonl(path: Path):
    if not path.exists():
        return None, []
    raw = path.read_bytes()
    rows = []
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"blank precision ledger row:{path.name}:{number}")
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"precision ledger row is not an object:{path.name}:{number}")
        rows.append(row)
    return hashlib.sha256(raw).hexdigest(), rows


def _read_json(path: Path):
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def load_contract(root: str | Path) -> tuple[dict, str]:
    path = Path(root) / CONTRACT_RELATIVE_PATH
    raw = path.read_bytes()
    contract = json.loads(raw.decode("utf-8"))
    if contract.get("schema") != "hes_signal_quality_acceptance_v1":
        raise ValueError("unsupported signal-quality contract schema")
    if contract.get("version") != "1.0.0":
        raise ValueError("unsupported signal-quality contract version")
    gate = contract.get("paper_performance_gate", {})
    constraints = contract.get("signal_constraints", {})
    if gate.get("win_rate_operator") != ">" or float(gate.get("win_rate_pct", -1)) != 90.0:
        raise ValueError("contract must preserve strict >90% win-rate rule")
    if int(gate.get("minimum_resolved_closed_trades", 0)) != 100:
        raise ValueError("contract must preserve 100-trade minimum")
    if int(constraints.get("max_actionable_signals_per_utc_day", 0)) != 3:
        raise ValueError("contract must preserve three-signals-per-day cap")
    if constraints.get("no_signal_quota") is not True or constraints.get("no_trade_is_valid_output") is not True:
        raise ValueError("contract must preserve no-quota / NO_TRADE semantics")
    if gate.get("performance_cohort") not in (
        "PRECISION_ENTRY_PAPER_ELIGIBLE",
        "PREAPPROVAL_PAPER_ELIGIBLE",
        "GATE_APPROVED_ONLY",
    ):
        raise ValueError("unsupported performance cohort")
    if (
        gate.get("exclude_unresolved_and_ambiguous_from_win_rate") is not True
        or gate.get("require_independent_out_of_sample_evidence") is not True
        or gate.get("no_historical_reselection_or_threshold_tuning_to_pass_gate") is not True
    ):
        raise ValueError("contract evidence / anti-overfit invariants are unsafe")
    expected_artifacts = {
        "fifteen_minute_setup_candidates": str(PRECISION_15M_SETUP_CANDIDATES),
        "events": str(PRECISION_EVENTS),
        "candidates": str(PRECISION_CANDIDATES),
        "outcomes": str(PRECISION_OUTCOMES),
        "verified_cost_model": str(PRECISION_COST_MODEL),
        "independent_out_of_sample": str(PRECISION_OOS),
    }
    if contract.get("precision_artifacts") != expected_artifacts:
        raise ValueError("precision artifact paths do not match the acceptance reader")
    activation = contract.get("activation", {})
    execution = contract.get("execution_boundary", {})
    if (
        activation.get("all_performance_and_safety_gates_required") is not True
        or activation.get("explicit_user_authorization_required") is not True
        or activation.get("until_then") != "PAPER_ONLY"
        or execution.get("live_execution_enabled") is not False
        or execution.get("orders_placed") is not False
    ):
        raise ValueError("contract activation / execution boundary is unsafe")
    return contract, hashlib.sha256(raw).hexdigest()


def _utc_day(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        stamp = float(value)
        if not math.isfinite(stamp):
            raise ValueError("non-finite candidate timestamp")
        if stamp > 100_000_000_000:  # milliseconds
            stamp /= 1000.0
        return datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("empty candidate timestamp")
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid candidate timestamp") from exc
        if dt.tzinfo is None:
            raise ValueError("naive candidate timestamp is not allowed")
        return dt.astimezone(timezone.utc).date().isoformat()
    raise ValueError("candidate timestamp missing or unsupported")


def _precision_candidate_valid(row: dict) -> bool:
    if (
        row.get("schema") != "hes_precision_entry_paper_candidate_v1"
        or row.get("timeframe") != "1m"
        or row.get("source") != "gateio_public_spot"
        or row.get("symbol") != "BTC_USDT"
        or row.get("direction") not in ("LONG", "SHORT")
        or row.get("market_regime") not in ("UPTREND", "DOWNTREND")
        or (row.get("direction") == "LONG" and row.get("market_regime") != "UPTREND")
        or (row.get("direction") == "SHORT" and row.get("market_regime") != "DOWNTREND")
        or row.get("paper_only") is not True
        or row.get("preapproval_paper_eligible") is not True
        or row.get("execution_enabled") is not False
        or row.get("orders_placed") is not False
    ):
        return False
    event_id = row.get("candidate_event_id")
    if not isinstance(event_id, str) or not event_id.strip() or row.get("event_id") != event_id:
        return False
    if not isinstance(row.get("setup_id"), str) or not row["setup_id"].strip():
        return False
    if not _valid_sha256(row.get("setup_context_sha256")):
        return False
    entry_time = row.get("entry_time")
    if type(entry_time) is not int or entry_time <= 0 or entry_time % 60 != 0:
        return False
    if type(row.get("max_hold_seconds")) is not int or row.get("max_hold_seconds") != 86400:
        return False
    entry, stop, target = row.get("entry_price"), row.get("stop_price"), row.get("target_price")
    if not all(_finite_number(value) and value > 0 for value in (entry, stop, target)):
        return False
    if row["direction"] == "LONG":
        if not stop < entry < target:
            return False
    elif not target < entry < stop:
        return False
    risk = abs(entry - stop)
    if risk <= 0 or abs(target - entry) / risk < 3.0:
        return False
    return _valid_setup_context(
        row.get("setup_context"),
        setup_id=row["setup_id"],
        digest=row["setup_context_sha256"],
        direction=row["direction"],
        market_regime=row["market_regime"],
        timestamp=entry_time,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
    )


def _canonical_hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _valid_setup_context(
    context: dict,
    *,
    setup_id: str,
    digest: str,
    direction: str,
    market_regime: str,
    timestamp: int,
    entry_price: float | None = None,
    stop_price: float | None = None,
    target_price: float | None = None,
) -> bool:
    if not isinstance(context, dict):
        return False
    if (
        context.get("schema") != "hes_strategy_entry_context_v1"
        or context.get("setup_id") != setup_id
        or context.get("evidence_sha256") != digest
        or not _valid_sha256(digest)
        or context.get("source") != "strategy_policy_v2"
        or context.get("market_data_source") != "gateio_public_spot"
        or context.get("symbol") != "BTC_USDT"
        or context.get("timeframe") != "15m"
        or context.get("direction") != direction
        or context.get("market_regime") != market_regime
        or context.get("setup_validated_15m") is not True
        or context.get("risk_gate_state") != "RISK_APPROVED"
        or context.get("confirmation_state") != "CONFIRMED_" + direction
        or context.get("execution_enabled") is not False
        or context.get("orders_placed") is not False
        or context.get("entry_zone_policy") != "FAVORABLE_SIDE_RISK_FRACTION_V1"
        or isinstance(context.get("entry_zone_fraction_of_risk"), bool)
        or not _finite_number(context.get("entry_zone_fraction_of_risk"))
        or not math.isclose(float(context.get("entry_zone_fraction_of_risk", -1)), 0.25, rel_tol=0, abs_tol=1e-12)
        or not _valid_sha256(context.get("gate_evidence_sha256"))
        or not isinstance(context.get("policy_version"), str)
        or not context.get("policy_version")
        or type(context.get("observed_at")) is not int
        or type(context.get("valid_until")) is not int
        or not context["observed_at"] <= timestamp <= context["valid_until"]
    ):
        return False
    try:
        if _canonical_hash({k: v for k, v in context.items() if k != "evidence_sha256"}) != digest:
            return False
        low, high, planned, stop, target = (
            float(context[k]) for k in ("entry_zone_low", "entry_zone_high", "planned_entry_price", "stop_price", "target_price")
        )
        if not all(math.isfinite(v) and v > 0 for v in (low, high, planned, stop, target)):
            return False
        risk = abs(planned - stop)
        if risk <= 0:
            return False
        width = risk * 0.25
        expected = (planned - width, planned) if direction == "LONG" else (planned, planned + width)
        if not math.isclose(low, expected[0], rel_tol=1e-10, abs_tol=1e-9) or not math.isclose(high, expected[1], rel_tol=1e-10, abs_tol=1e-9):
            return False
        if direction == "LONG" and not stop < low <= planned == high < target:
            return False
        if direction == "SHORT" and not target < low == planned <= high < stop:
            return False
        if abs(target - planned) / risk < 3.0:
            return False
        if not _finite_number(context.get("planned_rr")) or not math.isclose(float(context["planned_rr"]), abs(target - planned) / risk, rel_tol=1e-9, abs_tol=1e-9):
            return False
        if entry_price is not None:
            entry = float(entry_price)
            stop_value = float(stop_price)
            target_value = float(target_price)
            if not low <= entry <= high or not math.isclose(stop_value, stop, rel_tol=1e-10, abs_tol=1e-9) or not math.isclose(target_value, target, rel_tol=1e-10, abs_tol=1e-9):
                return False
            entry_risk = abs(entry - stop)
            if entry_risk <= 0 or abs(target - entry) / entry_risk < 3.0:
                return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        return False


def _precision_event_valid(row: dict) -> bool:
    if (
        row.get("schema") != "hes_precision_entry_event_v1"
        or row.get("source") != "gateio_public_spot"
        or row.get("symbol") != "BTC_USDT"
        or row.get("timeframe") != "1m"
        or row.get("direction") not in ("LONG", "SHORT")
        or row.get("market_regime") not in ("UPTREND", "DOWNTREND")
        or (row.get("direction") == "LONG" and row.get("market_regime") != "UPTREND")
        or (row.get("direction") == "SHORT" and row.get("market_regime") != "DOWNTREND")
        or row.get("execution_enabled") is not False
        or row.get("orders_placed") is not False
        or not isinstance(row.get("event_id"), str)
        or not row.get("event_id")
        or not isinstance(row.get("setup_id"), str)
        or not row.get("setup_id")
        or not _valid_sha256(row.get("setup_context_sha256"))
        or not _valid_setup_context(
            row.get("setup_context"),
            setup_id=row.get("setup_id"),
            digest=row.get("setup_context_sha256"),
            direction=row.get("direction"),
            market_regime=row.get("market_regime"),
            timestamp=row.get("candle_close_time"),
        )
        or not _valid_sha256(row.get("evidence_sha256"))
        or type(row.get("candle_close_time")) is not int
        or row.get("candle_close_time", 0) <= 0
        or row.get("candle_close_time", 0) % 60 != 0
        or not isinstance(row.get("decision"), str)
    ):
        return False
    return True


def _precision_event_matches_candidate(event: dict, candidate: dict) -> bool:
    return (
        event.get("decision") == "READY"
        and event.get("setup_id") == candidate.get("setup_id")
        and event.get("candle_close_time") == candidate.get("entry_time")
        and event.get("direction") == candidate.get("direction")
        and event.get("market_regime") == candidate.get("market_regime")
        and event.get("setup_context_sha256") == candidate.get("setup_context_sha256")
        and event.get("setup_context") == candidate.get("setup_context")
    )


def _outcome_exit_evidence_valid(row: dict, candidate: dict) -> bool:
    bar = row.get("exit_candle")
    if not isinstance(bar, dict):
        return False
    if (
        bar.get("schema") != "hes_global_candle_v1"
        or bar.get("source") != "gateio_public_spot"
        or bar.get("symbol") != "BTC_USDT"
        or bar.get("timeframe") != "1m"
        or bar.get("closed") is not True
        or type(bar.get("open_time")) is not int
        or type(bar.get("close_time")) is not int
        or bar.get("close_time") != row.get("exit_close_time")
        or bar.get("close_time") - bar.get("open_time") != 60
        or bar.get("open_time") < candidate.get("entry_time", 0)
        or row.get("exit_candle_sha256") != _canonical_hash(bar)
        or row.get("evidence_sha256") != _canonical_hash({
            "candidate": dict(candidate),
            "exit_bar": bar,
            "outcome": row.get("outcome"),
        })
    ):
        return False
    try:
        open_price, high, low, close = (float(bar[k]) for k in ("open", "high", "low", "close"))
        if not all(math.isfinite(v) for v in (open_price, high, low, close)):
            return False
        if high < max(open_price, low, close) or low > min(open_price, high, close):
            return False
        direction = candidate["direction"]
        stop = float(candidate["stop_price"])
        target = float(candidate["target_price"])
        if direction == "LONG":
            stop_hit, target_hit = low <= stop, high >= target
        else:
            stop_hit, target_hit = high >= stop, low <= target
        if stop_hit and target_hit:
            expected, price, reason = "LOSS", stop, "STOP_AND_TARGET_SAME_CANDLE_CONSERVATIVE_LOSS"
        elif stop_hit:
            expected, price, reason = "LOSS", stop, "STOP_LOSS_HIT"
        elif target_hit:
            expected, price, reason = "WIN", target, "TAKE_PROFIT_HIT"
        elif bar["close_time"] >= candidate["entry_time"] + candidate["max_hold_seconds"]:
            expected, price, reason = "TIMEOUT", close, "MAX_HOLD_24H_REACHED"
        else:
            return False
        return (
            row.get("outcome") == expected
            and row.get("reason") == reason
            and _finite_number(row.get("exit_price"))
            and abs(float(row["exit_price"]) - price) <= 1e-9
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _precision_ledger_metrics(root: str | Path) -> dict:
    base = Path(root)
    setup_hash, raw_15m_setups = _read_jsonl(base / PRECISION_15M_SETUP_CANDIDATES)
    event_hash, raw_events = _read_jsonl(base / PRECISION_EVENTS)
    candidate_hash, raw_candidates = _read_jsonl(base / PRECISION_CANDIDATES)
    outcome_hash, raw_outcomes = _read_jsonl(base / PRECISION_OUTCOMES)
    missing_ledger = any(value is None for value in (setup_hash, event_hash, candidate_hash, outcome_hash))
    cost_model = _read_json(base / PRECISION_COST_MODEL) or {}
    fee_verified = (
        cost_model.get("status") == "VERIFIED"
        and cost_model.get("fees_slippage_verified") is True
        and _valid_sha256(cost_model.get("evidence_sha256"))
        and _hash_matches(cost_model, "model_sha256")
        and _finite_number(cost_model.get("fee_fraction_per_side"))
        and _finite_number(cost_model.get("slippage_fraction_per_side"))
        and cost_model.get("fee_fraction_per_side", -1) >= 0
        and cost_model.get("slippage_fraction_per_side", -1) >= 0
    )
    fee_fraction = float(cost_model.get("fee_fraction_per_side", 0)) if fee_verified else 0.0
    slippage_fraction = float(cost_model.get("slippage_fraction_per_side", 0)) if fee_verified else 0.0

    candidates = []
    candidate_by_id = {}
    seen_setup_ids = set()
    invalid_candidates = 0
    duplicate_candidate_ids = 0
    duplicate_setup_ids = 0
    for row in raw_candidates:
        if not _precision_candidate_valid(row):
            invalid_candidates += 1
            continue
        candidate_id = row["candidate_event_id"]
        if candidate_id in candidate_by_id:
            duplicate_candidate_ids += 1
            continue
        if row["setup_id"] in seen_setup_ids:
            duplicate_setup_ids += 1
            continue
        seen_setup_ids.add(row["setup_id"])
        candidate_by_id[candidate_id] = row
        candidates.append(row)

    setup_contexts_by_digest = {}
    invalid_15m_setup_records = 0
    for setup_row in raw_15m_setups:
        if not isinstance(setup_row, dict):
            invalid_15m_setup_records += 1
            continue
        if setup_row.get("preapproval_paper_eligible") is not True:
            continue
        context = setup_row.get("entry_context")
        gate = setup_row.get("gate_evidence")
        if not isinstance(context, dict) or not isinstance(gate, dict):
            invalid_15m_setup_records += 1
            continue
        setup_id = context.get("setup_id")
        digest = context.get("evidence_sha256")
        direction = context.get("direction")
        regime = context.get("market_regime")
        observed_at = context.get("observed_at")
        gate_payload = {k: v for k, v in gate.items() if k != "entry_context"}
        if (
            setup_row.get("schema") != "hes_strategy_policy_v2_paper_candidate"
            or setup_row.get("evaluation_mode") != "PREAPPROVAL_PAPER_ONLY"
            or setup_row.get("source") != "gateio_public_spot"
            or setup_row.get("symbol") != "BTC_USDT"
            or setup_row.get("execution_enabled") is not False
            or setup_row.get("orders_placed") is not False
            or gate.get("entry_context") != context
            or not _valid_setup_context(
                context, setup_id=setup_id, digest=digest, direction=direction,
                market_regime=regime, timestamp=observed_at,
            )
            or context.get("gate_evidence_sha256") != _canonical_hash(gate_payload)
        ):
            invalid_15m_setup_records += 1
            continue
        setup_contexts_by_digest.setdefault(digest, []).append(setup_row)

    events_by_setup_time = {}
    seen_event_ids = set()
    invalid_events = 0
    for event in raw_events:
        event_id = event.get("event_id") if isinstance(event, dict) else None
        if not _precision_event_valid(event) or event_id in seen_event_ids:
            invalid_events += 1
            continue
        seen_event_ids.add(event_id)
        events_by_setup_time.setdefault((event["setup_id"], event["candle_close_time"]), []).append(event)

    candidate_setup_link_missing = 0
    ambiguous_15m_setup_links = 0
    for candidate in candidates:
        setup_matches = setup_contexts_by_digest.get(candidate["setup_context_sha256"], [])
        if not setup_matches:
            candidate_setup_link_missing += 1
        elif len(setup_matches) > 1:
            ambiguous_15m_setup_links += 1
        elif setup_matches[0].get("entry_context") != candidate.get("setup_context"):
            candidate_setup_link_missing += 1

    candidate_event_link_missing = 0
    ambiguous_candidate_event_links = 0
    for candidate in candidates:
        matches = [
            event for event in events_by_setup_time.get((candidate["setup_id"], candidate["entry_time"]), [])
            if _precision_event_matches_candidate(event, candidate)
        ]
        if not matches:
            candidate_event_link_missing += 1
        elif len(matches) > 1:
            ambiguous_candidate_event_links += 1

    wins = losses = breakevens = timeouts = unmatched = ambiguous = unscorable = 0
    gross_wins = gross_losses = gross_timeouts = 0
    net_r_entries = []
    long_short_split = {}
    regime_split = {}
    seen_outcome_ids = set()
    seen_candidate_outcomes = set()
    for row in raw_outcomes:
        event_id = row.get("event_id")
        candidate_id = row.get("candidate_event_id")
        if not isinstance(event_id, str) or not event_id.strip() or event_id in seen_outcome_ids:
            unscorable += 1
            continue
        seen_outcome_ids.add(event_id)
        candidate = candidate_by_id.get(candidate_id) if isinstance(candidate_id, str) else None
        if candidate is None:
            unmatched += 1
            continue
        if candidate_id in seen_candidate_outcomes:
            ambiguous += 1
            continue
        seen_candidate_outcomes.add(candidate_id)
        if (
            row.get("schema") != "hes_precision_entry_paper_outcome_v1"
            or row.get("setup_id") != candidate.get("setup_id")
            or row.get("source") != "gateio_public_spot"
            or row.get("symbol") != "BTC_USDT"
            or row.get("timeframe") != "1m"
            or row.get("direction") != candidate.get("direction")
            or row.get("market_regime") != candidate.get("market_regime")
            or row.get("entry_time") != candidate.get("entry_time")
            or not _valid_sha256(row.get("evidence_sha256"))
            or not _outcome_exit_evidence_valid(row, candidate)
            or row.get("execution_enabled") is not False
            or row.get("orders_placed") is not False
            or not _finite_number(row.get("entry_price"))
            or not _finite_number(row.get("exit_price"))
            or row.get("entry_price") != candidate.get("entry_price")
            or row.get("outcome") not in ("WIN", "LOSS", "TIMEOUT")
            or not _finite_number(row.get("gross_r"))
            or type(row.get("exit_close_time")) is not int
            or row.get("exit_close_time", 0) <= candidate.get("entry_time", 0)
        ):
            unscorable += 1
            continue
        risk = abs(candidate["entry_price"] - candidate["stop_price"])
        expected_gross_r = (
            (row["exit_price"] - candidate["entry_price"]) / risk
            if candidate["direction"] == "LONG"
            else (candidate["entry_price"] - row["exit_price"]) / risk
        )
        if abs(expected_gross_r - row["gross_r"]) > 1e-6:
            unscorable += 1
            continue
        if row["outcome"] == "WIN":
            if row["gross_r"] <= 0:
                unscorable += 1
                continue
            gross_wins += 1
        elif row["outcome"] == "LOSS":
            if row["gross_r"] >= 0:
                unscorable += 1
                continue
            gross_losses += 1
        else:
            gross_timeouts += 1

        if not fee_verified:
            continue
        cost_r = (candidate["entry_price"] + row["exit_price"]) * (fee_fraction + slippage_fraction) / risk
        net_r = row["gross_r"] - cost_r
        net_r_entries.append((row["exit_close_time"], net_r, candidate["direction"], candidate["market_regime"], row["outcome"]))
        direction_bucket = long_short_split.setdefault(candidate["direction"], {"wins": 0, "losses": 0, "breakevens": 0, "timeouts": 0})
        regime_bucket = regime_split.setdefault(candidate["market_regime"], {"wins": 0, "losses": 0, "breakevens": 0, "timeouts": 0})
        if row["outcome"] == "TIMEOUT":
            timeouts += 1
            direction_bucket["timeouts"] += 1
            regime_bucket["timeouts"] += 1
        elif net_r > 1e-12:
            wins += 1
            direction_bucket["wins"] += 1
            regime_bucket["wins"] += 1
        elif net_r < -1e-12:
            losses += 1
            direction_bucket["losses"] += 1
            regime_bucket["losses"] += 1
        else:
            breakevens += 1
            direction_bucket["breakevens"] += 1
            regime_bucket["breakevens"] += 1

    resolved = wins + losses + breakevens
    win_rate = round(100.0 * wins / resolved, 2) if resolved else None
    net_expectancy = round(sum(item[1] for item in net_r_entries) / len(net_r_entries), 6) if net_r_entries else None
    positive_r = sum(item[1] for item in net_r_entries if item[1] > 0)
    negative_r = abs(sum(item[1] for item in net_r_entries if item[1] < 0))
    profit_factor = round(positive_r / negative_r, 6) if negative_r > 0 else None
    equity = peak = maximum_drawdown = 0.0
    for _, net_r, _, _, _ in sorted(net_r_entries):
        equity += net_r
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, peak - equity)
    maximum_drawdown = round(maximum_drawdown, 6) if net_r_entries else None
    independent_oos = _read_json(base / PRECISION_OOS)
    cost_file = base / PRECISION_COST_MODEL
    oos_file = base / PRECISION_OOS
    return {
        "candidate_rows": candidates,
        "fifteen_minute_setup_record_count": len(raw_15m_setups),
        "invalid_15m_setup_records": invalid_15m_setup_records,
        "candidate_setup_link_missing": candidate_setup_link_missing,
        "ambiguous_15m_setup_links": ambiguous_15m_setup_links,
        "event_count": len(raw_events),
        "invalid_event_records": invalid_events,
        "candidate_event_link_missing": candidate_event_link_missing,
        "ambiguous_candidate_event_links": ambiguous_candidate_event_links,
        "candidate_count": len(raw_candidates),
        "valid_candidate_count": len(candidates),
        "outcome_count": len(raw_outcomes),
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "timeouts": timeouts,
        "gross_wins": gross_wins,
        "gross_losses": gross_losses,
        "gross_timeouts": gross_timeouts,
        "resolved": resolved,
        "win_rate_pct": win_rate,
        "net_expectancy_after_costs": net_expectancy,
        "profit_factor_after_costs": profit_factor,
        "maximum_drawdown": maximum_drawdown,
        "long_short_split": long_short_split,
        "regime_split": regime_split,
        "unresolved_candidates": max(0, len(candidates) - len(seen_candidate_outcomes)),
        "invalid_candidate_records": invalid_candidates,
        "duplicate_candidate_ids": duplicate_candidate_ids,
        "duplicate_setup_ids": duplicate_setup_ids,
        "unmatched_outcome_records": unmatched,
        "ambiguous_outcome_links": ambiguous,
        "unscorable_outcomes": unscorable,
        "ledger_missing": missing_ledger,
        "cost_model": cost_model,
        "independent_oos": independent_oos,
        "source_sha256": {
            "fifteen_minute_setup_candidates": setup_hash,
            "events": event_hash,
            "candidates": candidate_hash,
            "outcomes": outcome_hash,
            "cost_model": hashlib.sha256(cost_file.read_bytes()).hexdigest() if cost_file.exists() else None,
            "independent_oos": hashlib.sha256(oos_file.read_bytes()).hexdigest() if oos_file.exists() else None,
        },
    }


def _oos_report_completeness_reasons(report: dict, cost_model: dict) -> list[str]:
    reasons = []
    window = report.get("evaluation_window_utc")
    if not isinstance(window, dict):
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    else:
        try:
            start = datetime.fromisoformat(str(window["start"]).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(window["end"]).replace("Z", "+00:00"))
            if start.tzinfo is None or end.tzinfo is None or end <= start:
                raise ValueError("invalid OOS window")
        except (KeyError, TypeError, ValueError):
            reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")

    count_fields = ("wins", "losses", "breakevens", "timeouts")
    if any(type(report.get(field)) is not int or report[field] < 0 for field in count_fields):
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    elif sum(report[field] for field in count_fields[:3]) != report.get("resolved_closed_trade_count"):
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")

    if not isinstance(report.get("long_short_split"), dict) or not report["long_short_split"]:
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    if not isinstance(report.get("regime_split"), dict) or not report["regime_split"]:
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    for field in ("net_expectancy_after_costs", "profit_factor_after_costs", "maximum_drawdown"):
        if not _finite_number(report.get(field)):
            reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    if _finite_number(report.get("profit_factor_after_costs")) and report["profit_factor_after_costs"] <= 1:
        reasons.append("INDEPENDENT_OOS_PROFIT_FACTOR_NOT_ABOVE_1")
    if _finite_number(report.get("net_expectancy_after_costs")) and report["net_expectancy_after_costs"] <= 0:
        reasons.append("INDEPENDENT_OOS_NET_EXPECTANCY_NOT_POSITIVE")
    if _finite_number(report.get("maximum_drawdown")) and report["maximum_drawdown"] < 0:
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")

    try:
        report_hash_valid = (
            _valid_sha256(report.get("report_sha256"))
            and report.get("report_sha256") == _canonical_hash_excluding(report, "report_sha256")
        )
    except (TypeError, ValueError, OverflowError):
        report_hash_valid = False
    if not report_hash_valid:
        reasons.append("INDEPENDENT_OOS_PROVENANCE_MISSING")

    fee_report = report.get("fee_and_slippage_model")
    if (
        not isinstance(fee_report, dict)
        or fee_report.get("status") != "VERIFIED"
        or fee_report.get("evidence_sha256") != cost_model.get("evidence_sha256")
    ):
        reasons.append("INDEPENDENT_OOS_COST_MODEL_MISMATCH")
    out_sample = report.get("out_of_sample_results")
    if not isinstance(out_sample, dict) or out_sample.get("status") != "PASS":
        reasons.append("INDEPENDENT_OOS_REPORT_INCOMPLETE")
    else:
        resolved = report.get("resolved_closed_trade_count")
        expected_rate = (
            round(100.0 * report["wins"] / resolved, 2)
            if type(resolved) is int and resolved > 0
            else None
        )
        if (
            not _finite_number(report.get("win_rate_pct"))
            or expected_rate is None
            or abs(float(report["win_rate_pct"]) - expected_rate) > 0.01
            or out_sample.get("resolved_closed_trade_count") != resolved
            or not _finite_number(out_sample.get("win_rate_pct"))
            or abs(float(out_sample["win_rate_pct"]) - expected_rate) > 0.01
        ):
            reasons.append("INDEPENDENT_OOS_METRICS_INCONSISTENT")
    return reasons


def daily_signal_counts(candidates: list[dict], *, performance_cohort: str) -> dict:
    """Count only cohort-qualified actionable candidates; the daily limit is never a quota."""
    counts: dict[str, int] = {}
    seen: set[str] = set()
    invalid = 0
    for row in candidates:
        if not isinstance(row, dict):
            invalid += 1
            continue
        if performance_cohort == "PRECISION_ENTRY_PAPER_ELIGIBLE":
            actionable = _precision_candidate_valid(row)
            timestamp = row.get("entry_time")
        elif performance_cohort == "PREAPPROVAL_PAPER_ELIGIBLE":
            actionable = row.get("preapproval_paper_eligible") is True
            timestamp = row.get("candidate_time", row.get("observed_at"))
        elif performance_cohort == "GATE_APPROVED_ONLY":
            actionable = row.get("final_gate_decision") in ("LONG", "SHORT")
            timestamp = row.get("candidate_time", row.get("observed_at"))
        else:
            raise ValueError("unsupported performance cohort")
        if not actionable:
            continue
        event_id = row.get("candidate_event_id") or row.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip() or event_id in seen:
            invalid += 1
            continue
        seen.add(event_id)
        try:
            day = _utc_day(timestamp)
        except (TypeError, ValueError, OverflowError, OSError):
            invalid += 1
            continue
        counts[day] = counts.get(day, 0) + 1
    return {
        "counts_by_utc_day": dict(sorted(counts.items())),
        "max_signals_in_any_utc_day": max(counts.values(), default=0),
        "invalid_actionable_records": invalid,
    }


def evaluate_acceptance(
    *,
    root: str | Path,
    data_root: str | Path | None = None,
    metrics: dict,
    candidates: list[dict],
    independent_oos: dict | None = None,
) -> dict:
    """Evaluate claims conservatively; precision claims are derived from the 1m ledger."""
    contract, digest = load_contract(root)
    gate = contract["paper_performance_gate"]
    cap = contract["signal_constraints"]["max_actionable_signals_per_utc_day"]
    minimum = int(gate["minimum_resolved_closed_trades"])
    target = float(gate["win_rate_pct"])
    reasons = []
    cohort = gate.get("performance_cohort", "GATE_APPROVED_ONLY")

    precision_summary = None
    if cohort == "PRECISION_ENTRY_PAPER_ELIGIBLE":
        # Contract/code live in the immutable release; mutable ledgers live in the shared data root.
        precision = _precision_ledger_metrics(data_root if data_root is not None else root)
        resolved = precision["resolved"]
        win_rate = precision["win_rate_pct"]
        unscorable = precision["unscorable_outcomes"]
        unmatched = precision["unmatched_outcome_records"]
        ambiguous = precision["ambiguous_outcome_links"] + precision["duplicate_candidate_ids"]
        candidates_for_cap = precision["candidate_rows"]
        cost = precision["cost_model"]
        independent_oos = precision["independent_oos"]
        if precision["ledger_missing"]:
            reasons.append("PRECISION_ENTRY_LEDGER_MISSING")
        if precision["invalid_candidate_records"]:
            reasons.append("INVALID_PRECISION_CANDIDATE_RECORDS")
        if precision["invalid_15m_setup_records"]:
            reasons.append("INVALID_15M_SETUP_CONTEXT_RECORDS")
        if precision["candidate_setup_link_missing"]:
            reasons.append("PRECISION_15M_SETUP_CONTEXT_LINK_MISSING")
        if precision["ambiguous_15m_setup_links"]:
            reasons.append("AMBIGUOUS_PRECISION_15M_SETUP_LINKS")
        if precision["invalid_event_records"]:
            reasons.append("INVALID_PRECISION_EVENT_RECORDS")
        if precision["candidate_event_link_missing"]:
            reasons.append("PRECISION_CANDIDATE_EVENT_LINK_MISSING")
        if precision["ambiguous_candidate_event_links"]:
            reasons.append("AMBIGUOUS_PRECISION_CANDIDATE_EVENT_LINKS")
        if precision["duplicate_candidate_ids"]:
            reasons.append("AMBIGUOUS_PRECISION_CANDIDATE_IDS")
        if precision["duplicate_setup_ids"]:
            reasons.append("DUPLICATE_PRECISION_SETUP_CANDIDATES")
        if precision["net_expectancy_after_costs"] is None or precision["net_expectancy_after_costs"] <= 0:
            reasons.append("NET_EXPECTANCY_AFTER_COSTS_NOT_POSITIVE")
        if precision["profit_factor_after_costs"] is None or precision["profit_factor_after_costs"] <= 1:
            reasons.append("PROFIT_FACTOR_AFTER_COSTS_NOT_ABOVE_1")
        precision_summary = {
            "fifteen_minute_setup_records": precision["fifteen_minute_setup_record_count"],
            "invalid_15m_setup_records": precision["invalid_15m_setup_records"],
            "candidate_setup_link_missing": precision["candidate_setup_link_missing"],
            "ambiguous_15m_setup_links": precision["ambiguous_15m_setup_links"],
            "event_records": precision["event_count"],
            "invalid_event_records": precision["invalid_event_records"],
            "candidate_event_link_missing": precision["candidate_event_link_missing"],
            "ambiguous_candidate_event_links": precision["ambiguous_candidate_event_links"],
            "candidate_records": precision["candidate_count"],
            "valid_candidate_records": precision["valid_candidate_count"],
            "outcome_records": precision["outcome_count"],
            "wins": precision["wins"],
            "losses": precision["losses"],
            "breakevens": precision["breakevens"],
            "timeouts": precision["timeouts"],
            "gross_wins": precision["gross_wins"],
            "gross_losses": precision["gross_losses"],
            "gross_timeouts": precision["gross_timeouts"],
            "resolved_closed_trades": resolved,
            "win_rate_pct": win_rate,
            "net_expectancy_after_costs": precision["net_expectancy_after_costs"],
            "profit_factor_after_costs": precision["profit_factor_after_costs"],
            "maximum_drawdown": precision["maximum_drawdown"],
            "long_short_split": precision["long_short_split"],
            "regime_split": precision["regime_split"],
            "unresolved_candidates": precision["unresolved_candidates"],
            "invalid_candidate_records": precision["invalid_candidate_records"],
            "unmatched_outcome_records": unmatched,
            "ambiguous_outcome_links": ambiguous,
            "duplicate_setup_ids": precision["duplicate_setup_ids"],
            "unscorable_outcomes": unscorable,
            "source_sha256": precision["source_sha256"],
        }
    else:
        if cohort == "PREAPPROVAL_PAPER_ELIGIBLE":
            resolved = int(metrics.get("preapproval_paper_resolved", metrics.get("resolved", 0)) or 0)
            win_rate = metrics.get("preapproval_paper_win_rate_pct", metrics.get("win_rate_pct"))
            unscorable = int(metrics.get("preapproval_paper_unscorable_outcomes", metrics.get("unscorable_outcomes", 0)) or 0)
        elif cohort == "GATE_APPROVED_ONLY":
            resolved = int(metrics.get("eligible_resolved", metrics.get("resolved", 0)) or 0)
            win_rate = metrics.get("eligible_win_rate_pct", metrics.get("win_rate_pct"))
            unscorable = int(metrics.get("eligible_unscorable_outcomes", metrics.get("unscorable_outcomes", 0)) or 0)
        else:
            raise ValueError("unsupported performance cohort in acceptance contract")
        unmatched = int(metrics.get("unmatched_outcome_records", metrics.get("unmatched_outcomes", 0)) or 0)
        ambiguous = int(metrics.get("ambiguous_legacy_timestamp_matches", metrics.get("ambiguous_outcomes", 0)) or 0)
        candidates_for_cap = candidates
        cost = metrics.get("cost_model", {})

    if resolved < minimum:
        reasons.append("MINIMUM_RESOLVED_TRADES_NOT_MET")
    if not _finite_number(win_rate):
        reasons.append("INVALID_IN_SAMPLE_WIN_RATE")
    elif float(win_rate) <= target:
        reasons.append("STRICT_WIN_RATE_GT_90_NOT_MET")
    if unmatched:
        reasons.append("UNMATCHED_OUTCOMES_PRESENT")
    if ambiguous:
        reasons.append("AMBIGUOUS_OUTCOME_LINKS_PRESENT")
    if unscorable:
        reasons.append("UNSCORABLE_OUTCOMES_PRESENT")

    daily = daily_signal_counts(candidates_for_cap, performance_cohort=cohort)
    if daily["invalid_actionable_records"]:
        reasons.append("INVALID_ACTIONABLE_SIGNAL_RECORDS")
    if daily["max_signals_in_any_utc_day"] > cap:
        reasons.append("DAILY_SIGNAL_CAP_EXCEEDED")

    if (
        cost.get("status") != "VERIFIED"
        or cost.get("fees_slippage_verified") is not True
        or not _valid_sha256(cost.get("evidence_sha256"))
        or not _finite_number(cost.get("fee_fraction_per_side"))
        or not _finite_number(cost.get("slippage_fraction_per_side"))
        or cost.get("fee_fraction_per_side", -1) < 0
        or cost.get("slippage_fraction_per_side", -1) < 0
    ):
        reasons.append("VERIFIED_FEE_SLIPPAGE_MODEL_MISSING")

    if not isinstance(independent_oos, dict) or independent_oos.get("status") != "PASS":
        reasons.append("INDEPENDENT_OUT_OF_SAMPLE_EVIDENCE_MISSING")
    else:
        oos_count = independent_oos.get("resolved_closed_trade_count")
        if type(oos_count) is not int or oos_count < 0:
            reasons.append("INDEPENDENT_OOS_SAMPLE_INVALID")
        elif oos_count < minimum:
            reasons.append("INDEPENDENT_OOS_SAMPLE_TOO_SMALL")
        oos_wr = independent_oos.get("win_rate_pct")
        if not _finite_number(oos_wr):
            reasons.append("INDEPENDENT_OOS_WIN_RATE_INVALID")
        elif float(oos_wr) <= target:
            reasons.append("INDEPENDENT_OOS_WIN_RATE_NOT_ABOVE_90")
        if not _valid_sha256(independent_oos.get("evidence_sha256")):
            reasons.append("INDEPENDENT_OOS_PROVENANCE_MISSING")
        reasons.extend(_oos_report_completeness_reasons(independent_oos, cost))

    return {
        "schema": "hes_signal_quality_acceptance_result_v1",
        "contract_version": contract["version"],
        "contract_sha256": digest,
        "performance_cohort": cohort,
        "status": "PASS" if not reasons else "NOT_MET",
        "target_win_rate_operator": ">",
        "target_win_rate_pct": target,
        "minimum_resolved_closed_trades": minimum,
        "resolved_closed_trade_count": resolved,
        "observed_win_rate_pct": win_rate,
        "target_met_on_in_sample_metrics": bool(
            resolved >= minimum
            and _finite_number(win_rate)
            and float(win_rate) > target
            and not unmatched
            and not ambiguous
            and not unscorable
        ),
        "daily_signal_cap": cap,
        "daily_signal_counts": daily,
        "unmatched_outcome_records": unmatched,
        "ambiguous_outcome_links": ambiguous,
        "unscorable_outcomes": unscorable,
        "invalid_15m_setup_records": precision_summary.get("invalid_15m_setup_records", 0) if precision_summary else 0,
        "candidate_setup_link_missing": precision_summary.get("candidate_setup_link_missing", 0) if precision_summary else 0,
        "ambiguous_15m_setup_links": precision_summary.get("ambiguous_15m_setup_links", 0) if precision_summary else 0,
        "invalid_precision_event_records": precision_summary.get("invalid_event_records", 0) if precision_summary else 0,
        "candidate_event_link_missing": precision_summary.get("candidate_event_link_missing", 0) if precision_summary else 0,
        "ambiguous_candidate_event_links": precision_summary.get("ambiguous_candidate_event_links", 0) if precision_summary else 0,
        "independent_oos_status": independent_oos.get("status") if isinstance(independent_oos, dict) else "MISSING",
        "cost_model_status": cost.get("status", "MISSING"),
        "precision_entry_ledger": precision_summary,
        "net_expectancy_after_costs": precision_summary.get("net_expectancy_after_costs") if precision_summary else None,
        "profit_factor_after_costs": precision_summary.get("profit_factor_after_costs") if precision_summary else None,
        "maximum_drawdown": precision_summary.get("maximum_drawdown") if precision_summary else None,
        "long_short_split": precision_summary.get("long_short_split") if precision_summary else None,
        "regime_split": precision_summary.get("regime_split") if precision_summary else None,
        "reasons": reasons,
        "execution_enabled": False,
        "orders_placed": False,
    }
