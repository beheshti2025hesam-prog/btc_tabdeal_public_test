"""Append-only 1m precision-entry observation and paper-outcome worker.

This worker is paper-only. It records one event per validated setup/closed 1m candle,
creates at most one paper candidate per setup, and never sends orders.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Mapping

from forward.forward_journal_v1 import ForwardJournalV1
from forward.global_market_data_reader_v1 import read_closed_candles
from forward.precision_entry_engine_v1 import evaluate_precision_entry
from web.strategy_v2_dashboard_view import read_strategy_v2_dashboard

CODE_ROOT = Path(__file__).resolve().parents[1]


def resolve_data_root(*, code_root: Path | None = None, configured_root: str | Path | None = None) -> Path:
    """Keep immutable release code separate from the shared mutable data root."""
    configured = configured_root if configured_root is not None else os.environ.get("HES_DATA_ROOT")
    return Path(configured).expanduser() if configured else Path(code_root or CODE_ROOT)


DATA_ROOT = resolve_data_root()
DATA = DATA_ROOT / "data" / "forward"
EVENTS = ForwardJournalV1(DATA / "precision_entry_events_v1.jsonl")
CANDIDATES = ForwardJournalV1(DATA / "precision_entry_candidates_v1.jsonl")
OUTCOMES = ForwardJournalV1(DATA / "precision_entry_outcomes_v1.jsonl")
REPORT = DATA / "precision_entry_journal_report_v1.json"
MAX_HOLD_SECONDS = 24 * 60 * 60
DAILY_SIGNAL_CAP = 3


def _hash(value: Mapping[str, Any]) -> str:
    raw = json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError(f"blank journal line:{number}")
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"journal row is not an object:{number}")
            rows.append(row)
    return rows


def _utc_day(timestamp: int) -> str:
    return datetime.fromtimestamp(int(timestamp), timezone.utc).date().isoformat()


def build_precision_event(*, setup_context: Mapping[str, Any], candle: Mapping[str, Any],
                          engine_result: Mapping[str, Any], observed_at: datetime) -> dict:
    setup_id = setup_context["setup_id"]
    close_time = int(candle["close_time"])
    # The worker polls more frequently than the 1m candle cadence. Keep the
    # immutable event fingerprint stable across repeated polls of the same
    # closed candle: wall-clock observation time and age_seconds are telemetry,
    # not new market evidence.
    stable_engine_result = dict(engine_result)
    stable_engine_evidence = dict(engine_result.get("evidence", {}))
    stable_engine_evidence.pop("age_seconds", None)
    stable_engine_result["evidence"] = stable_engine_evidence
    base = {
        "schema": "hes_precision_entry_event_v1",
        "event_id": f"hes-precision-event:{setup_id}:{close_time}",
        "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
        "setup_id": setup_id,
        "setup_context": dict(setup_context),
        "setup_context_sha256": setup_context["evidence_sha256"],
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "timeframe": "1m",
        "candle_close_time": close_time,
        # Preserve the exact closed market bar as semantic evidence. This lets
        # replay telemetry vary without hiding a revised OHLCV observation.
        "candle_evidence": dict(candle),
        "decision": engine_result["state"],
        "direction": setup_context["direction"],
        "market_regime": setup_context["market_regime"],
        "reason_codes": list(engine_result.get("reason_codes", [])),
        "engine_evidence": stable_engine_evidence,
        "evidence_sha256": _hash({
            "setup_context_sha256": setup_context["evidence_sha256"],
            "candle": dict(candle),
            "engine_result": stable_engine_result,
        }),
        "execution_enabled": False,
        "orders_placed": False,
    }
    return base


def build_paper_candidate(*, setup_context: Mapping[str, Any], candle: Mapping[str, Any],
                          observed_at: datetime) -> dict:
    setup_id = setup_context["setup_id"]
    direction = setup_context.get("direction")
    market_regime = setup_context.get("market_regime")
    if market_regime not in ("UPTREND", "DOWNTREND") or (direction == "LONG" and market_regime != "UPTREND") or (direction == "SHORT" and market_regime != "DOWNTREND"):
        raise ValueError("PRECISION_ENTRY_MARKET_REGIME_INVALID")
    entry_time = int(candle["close_time"])
    event_id = "hes-precision-paper:" + hashlib.sha256(f"{setup_id}|{entry_time}".encode()).hexdigest()[:32]
    return {
        "schema": "hes_precision_entry_paper_candidate_v1",
        "event_id": event_id,
        "candidate_event_id": event_id,
        "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
        "setup_id": setup_id,
        "setup_context": dict(setup_context),
        "setup_context_sha256": setup_context["evidence_sha256"],
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "timeframe": "1m",
        "direction": direction,
        "market_regime": market_regime,
        "entry_time": entry_time,
        "entry_price": float(candle["close"]),
        "stop_price": float(setup_context["stop_price"]),
        "target_price": float(setup_context["target_price"]),
        "max_hold_seconds": MAX_HOLD_SECONDS,
        "paper_only": True,
        "preapproval_paper_eligible": True,
        "execution_enabled": False,
        "orders_placed": False,
    }


def resolve_candidate(candidate: Mapping[str, Any], candles: list[dict]) -> dict | None:
    """Resolve only from contiguous future 1m bars; same-bar stop+target is a loss."""
    entry_time = int(candidate["entry_time"])
    direction = candidate["direction"]
    market_regime = candidate.get("market_regime")
    if market_regime not in ("UPTREND", "DOWNTREND") or (direction == "LONG" and market_regime != "UPTREND") or (direction == "SHORT" and market_regime != "DOWNTREND"):
        return None
    entry = float(candidate["entry_price"])
    stop = float(candidate["stop_price"])
    target = float(candidate["target_price"])
    deadline = entry_time + int(candidate.get("max_hold_seconds", MAX_HOLD_SECONDS))
    future = [bar for bar in candles if int(bar["close_time"]) > entry_time]
    if not future:
        return None
    expected_open = entry_time
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    for bar in future:
        open_time = int(bar["open_time"])
        close_time = int(bar["close_time"])
        if open_time != expected_open or close_time - open_time != 60:
            return None
        high = float(bar["high"]); low = float(bar["low"]); close = float(bar["close"])
        if direction == "LONG":
            stop_hit = low <= stop
            target_hit = high >= target
        elif direction == "SHORT":
            stop_hit = high >= stop
            target_hit = low <= target
        else:
            return None
        if stop_hit and target_hit:
            outcome, exit_price, reason = "LOSS", stop, "STOP_AND_TARGET_SAME_CANDLE_CONSERVATIVE_LOSS"
        elif stop_hit:
            outcome, exit_price, reason = "LOSS", stop, "STOP_LOSS_HIT"
        elif target_hit:
            outcome, exit_price, reason = "WIN", target, "TAKE_PROFIT_HIT"
        elif close_time >= deadline:
            outcome, exit_price, reason = "TIMEOUT", close, "MAX_HOLD_24H_REACHED"
        else:
            expected_open = close_time
            continue
        gross_r = ((exit_price - entry) / risk) if direction == "LONG" else ((entry - exit_price) / risk)
        base = {
            "schema": "hes_precision_entry_paper_outcome_v1",
            "event_id": "hes-precision-outcome:" + candidate["candidate_event_id"],
            "candidate_event_id": candidate["candidate_event_id"],
            "setup_id": candidate["setup_id"],
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "1m",
            "direction": direction,
            "market_regime": market_regime,
            "outcome": outcome,
            "reason": reason,
            "entry_time": entry_time,
            "entry_price": entry,
            "exit_close_time": close_time,
            "exit_price": exit_price,
            "gross_r": round(gross_r, 8),
            "cost_model_status": "ASSUMPTION_BASED_NOT_VERIFIED",
            "exit_candle": dict(bar),
            "exit_candle_sha256": _hash(dict(bar)),
            "execution_enabled": False,
            "orders_placed": False,
            "evidence_sha256": _hash({"candidate": dict(candidate), "exit_bar": dict(bar), "outcome": outcome}),
        }
        return base
    return None


def _immutable_event_identity(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable identity payload for a precision observation event."""
    normalized = dict(record)
    if normalized.get("schema") == "hes_precision_entry_event_v1":
        # Older rows included these poll-varying values in the payload hash.
        # Exclude the aggregate hash (which included age_seconds historically),
        # but compare explicit candle_evidence and all semantic engine fields.
        # Legacy rows without candle_evidence intentionally fail closed against
        # new rows: their exact OHLCV payload cannot be reconstructed safely.
        normalized.pop("observed_at", None)
        normalized.pop("evidence_sha256", None)
        evidence = normalized.get("engine_evidence")
        if isinstance(evidence, Mapping):
            stable_evidence = dict(evidence)
            stable_evidence.pop("age_seconds", None)
            normalized["engine_evidence"] = stable_evidence
    return normalized


def append_immutable_event(journal: ForwardJournalV1, record: Mapping[str, Any]) -> bool:
    """Idempotent append: same semantic event is replay; changed evidence is conflict."""
    existing = _read_jsonl(journal.path)
    for prior in existing:
        if prior.get("event_id") == record.get("event_id"):
            if _immutable_event_identity(prior) != _immutable_event_identity(record):
                raise ValueError("IMMUTABLE_JOURNAL_EVENT_ID_CONFLICT")
            return False
    return journal.append_event(record)


def _atomic_report(payload: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    temp = REPORT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, REPORT)


def run_cycle(*, now: datetime | None = None) -> dict:
    current = now or datetime.now(timezone.utc)
    now_s = int(current.timestamp())
    bars = read_closed_candles("1m", root=DATA_ROOT, now=now_s)
    candidate_rows = _read_jsonl(CANDIDATES.path)
    outcome_rows = _read_jsonl(OUTCOMES.path)
    outcome_ids = {row.get("candidate_event_id") for row in outcome_rows}

    # Resolve already-open paper candidates even if the upstream 15m report is stale/unavailable.
    for candidate in candidate_rows:
        if candidate.get("candidate_event_id") in outcome_ids:
            continue
        outcome = resolve_candidate(candidate, bars)
        if outcome is not None and append_immutable_event(OUTCOMES, outcome):
            outcome_rows.append(outcome)
            outcome_ids.add(candidate["candidate_event_id"])

    strategy_error = None
    try:
        strategy = read_strategy_v2_dashboard(
            report_path=DATA / "strategy_policy_v2_eval_report.json",
            journal_path=DATA / "trade_journal_v2.jsonl",
            now=current,
        )
        paper_setup = strategy.get("paper_setup") or {}
        latest_gate = strategy.get("latest_gate_evidence") or {}
    except Exception as exc:
        strategy_error = type(exc).__name__ + ":" + str(exc)[:180]
        paper_setup = {}
        latest_gate = {}

    engine = None
    appended_event = False
    appended_candidate = False
    if paper_setup.get("validated") is True:
        context = paper_setup.get("context")
        direction = paper_setup.get("direction")
        engine = evaluate_precision_entry(
            setup_direction=direction,
            candles_1m=bars,
            setup_validated_15m=True,
            risk_gate_state=(latest_gate.get("risk") or {}).get("state", "UNKNOWN"),
            now_s=now_s,
            setup_context=context,
        )
        setup_seen = any(row.get("setup_id") == context.get("setup_id") for row in candidate_rows)
        day_count = sum(_utc_day(int(row["entry_time"])) == _utc_day(int(bars[-1]["close_time"])) for row in candidate_rows)
        if engine.get("state") == "READY" and setup_seen:
            engine = {**engine, "state":"BLOCKED", "reason_codes":list(engine.get("reason_codes",[]))+["DUPLICATE_SETUP_SUPPRESSED"]}
        elif engine.get("state") == "READY" and day_count >= DAILY_SIGNAL_CAP:
            engine = {**engine, "state":"BLOCKED", "reason_codes":list(engine.get("reason_codes",[]))+["DAILY_SIGNAL_CAP_REACHED"]}
        event = build_precision_event(
            setup_context=context, candle=bars[-1], engine_result=engine, observed_at=current
        )
        appended_event = append_immutable_event(EVENTS, event)
        if engine.get("state") == "READY":
            candidate = build_paper_candidate(setup_context=context, candle=bars[-1], observed_at=current)
            appended_candidate = append_immutable_event(CANDIDATES, candidate)
            if appended_candidate:
                candidate_rows.append(candidate)

    oldest_available_open = int(bars[0]["open_time"]) if bars else None
    outside_retention = sum(
        1 for row in candidate_rows
        if row.get("candidate_event_id") not in outcome_ids
        and oldest_available_open is not None
        and int(row.get("entry_time", 0)) < oldest_available_open
    )
    wins = sum(row.get("outcome") == "WIN" for row in outcome_rows)
    losses = sum(row.get("outcome") == "LOSS" for row in outcome_rows)
    timeouts = sum(row.get("outcome") == "TIMEOUT" for row in outcome_rows)
    resolved = wins + losses
    report = {
        "schema": "hes_precision_entry_journal_report_v1",
        "updated_at": current.isoformat(),
        "status": "BLOCKED" if strategy_error else ("NO_TRADE" if paper_setup.get("validated") is not True else (engine or {}).get("state", "BLOCKED")),
        "paper_setup_validated": paper_setup.get("validated") is True,
        "paper_setup_reason": paper_setup.get("reason_code"),
        "strategy_run_provenance": ((paper_setup.get("context") or {}).get("strategy_run_provenance") if isinstance(paper_setup.get("context"),dict) else None),
        "strategy_report_error": strategy_error,
        "latest_engine_state": (engine or {}).get("state", "NOT_EVALUATED"),
        "latest_reason_codes": (engine or {}).get("reason_codes", []) if not strategy_error else [strategy_error],
        "event_count": len(_read_jsonl(EVENTS.path)),
        "candidate_count": len(candidate_rows),
        "outcome_count": len(outcome_rows),
        "wins": wins, "losses": losses, "timeouts": timeouts,
        "resolved_win_rate_pct": round(100.0 * wins / resolved, 2) if resolved else None,
        "unresolved_candidates": max(0, len(candidate_rows) - len(outcome_rows)),
        "unresolved_outside_retention_window": outside_retention,
        "outcome_resolution_integrity": "PARTIAL_HISTORY_UNAVAILABLE" if outside_retention else "CONTIGUOUS_WINDOW_AVAILABLE",
        "daily_signal_cap": DAILY_SIGNAL_CAP,
        "daily_signal_cap_is_quota": False,
        "latest_event_appended": appended_event,
        "latest_candidate_appended": appended_candidate,
        "cost_model_status": "ASSUMPTION_BASED_NOT_VERIFIED",
        "execution_enabled": False,
        "orders_placed": False,
        "limitations": [
            "Precision READY is a paper-entry observation, never an exchange order.",
            "A same-1m-candle stop and target touch is conservatively scored as a loss.",
            "Outcome resolution requires contiguous future 1m candles; gaps remain unresolved.",
            "Gross R is reported before verified exchange fees/slippage.",
        ],
    }
    _atomic_report(report)
    return report


def main() -> None:
    while True:
        try:
            run_cycle()
        except Exception as exc:
            now = datetime.now(timezone.utc)
            _atomic_report({
                "schema": "hes_precision_entry_journal_report_v1",
                "updated_at": now.isoformat(), "status": "BLOCKED",
                "reason_codes": [type(exc).__name__ + ":" + str(exc)[:180]],
                "execution_enabled": False, "orders_placed": False,
            })
        time.sleep(15)


if __name__ == "__main__":
    main()
