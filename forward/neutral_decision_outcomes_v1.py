"""Forward-only outcomes for NO_TRADE decisions. Observation only; never trades or tunes policy."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "hes_neutral_decision_outcome_v1"
DEFAULT_HORIZONS = {"1h": 3600, "4h": 14400, "24h": 86400}

def _dt(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)

def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    result = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip(): continue
        try: row = json.loads(line)
        except json.JSONDecodeError as exc: raise ValueError(f"MALFORMED_JSONL:{path.name}:{line_no}") from exc
        if not isinstance(row, dict): raise ValueError(f"INVALID_JSONL_RECORD:{path.name}:{line_no}")
        result.append(row)
    return result

def _price(row: dict[str, Any], key: str) -> float:
    value = float(row[key])
    if value <= 0: raise ValueError("INVALID_CANDLE_PRICE")
    return value

def validate_candles(candles: Iterable[dict[str, Any]], *, symbol: str = "BTC_USDT",
                     source: str = "gateio_public_spot", timeframe_seconds: int = 900) -> list[dict[str, Any]]:
    rows = sorted(list(candles), key=lambda r: int(r["close_time"]))
    previous = None
    for row in rows:
        if row.get("source") != source or row.get("symbol") != symbol or row.get("timeframe") != "15m" or row.get("closed") is not True:
            raise ValueError("CANDLE_SOURCE_SYMBOL_TIMEFRAME_OR_CLOSED_FLAG_INVALID")
        opened, closed = int(row["open_time"]), int(row["close_time"])
        o, h, low, c = (_price(row, k) for k in ("open", "high", "low", "close"))
        volume = float(row.get("volume", -1))
        if closed != opened + timeframe_seconds or low > min(o, c) or h < max(o, c, low) or volume < 0:
            raise ValueError("CANDLE_OHLC_INTERVAL_OR_VOLUME_INVALID")
        if previous is not None and opened != previous: raise ValueError("CANDLE_GAP_OR_DUPLICATE")
        previous = closed
    return rows

def _stable_id(event_id: str, horizon: str) -> str:
    return hashlib.sha256(f"{event_id}|{horizon}|{SCHEMA}".encode()).hexdigest()

def evaluate_no_trade(decision: dict[str, Any], candles: list[dict[str, Any]], *,
                      horizons: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """Evaluate a frozen NO_TRADE record only against candles closed after its timestamp.

    Directionless decisions get market-context metrics only. Candidate outcomes require valid
    direction/entry/SL/TP. Same-candle stop and target touches are ambiguous, never wins.
    """
    if decision.get("decision") != "NO_TRADE": return []
    event_id = str(decision.get("event_id") or "")
    if not event_id: raise ValueError("NO_TRADE_EVENT_ID_REQUIRED")
    observed = _dt(decision["observed_at"])
    after = [r for r in candles if _dt(r["close_time"]) > observed]
    baseline = next((r for r in reversed(candles) if _dt(r["close_time"]) <= observed), None)
    if baseline is None: raise ValueError("NO_CLOSED_CANDLE_AT_DECISION_TIME")
    base_close = _price(baseline, "close")
    direction = decision.get("proposal_direction") or decision.get("direction") or "NONE"
    if direction not in ("LONG", "SHORT"): direction = "NONE"
    vals = [decision.get("proposal_entry", decision.get("entry")),
            decision.get("proposal_stop_loss", decision.get("stop_loss")),
            decision.get("proposal_take_profit", decision.get("take_profit"))]
    trade_geometry = direction in ("LONG", "SHORT") and all(v is not None for v in vals)
    if trade_geometry:
        entry, stop, target = map(float, vals)
        trade_geometry = entry > 0 and stop > 0 and target > 0 and ((stop < entry < target) if direction == "LONG" else (target < entry < stop))
    out = []
    for horizon, seconds in (horizons or DEFAULT_HORIZONS).items():
        cutoff = observed.timestamp() + seconds
        # Include the first closed candle at or after the horizon boundary. This handles
        # decision timestamps that include seconds beyond the candle close timestamp.
        window = []
        for candle in after:
            window.append(candle)
            if _dt(candle["close_time"]).timestamp() >= cutoff: break
        horizon_complete = bool(window and _dt(window[-1]["close_time"]).timestamp() >= cutoff)
        rec = {"schema": SCHEMA, "outcome_id": _stable_id(event_id, horizon),
               "decision_event_id": event_id, "observed_at": observed.isoformat(),
               "horizon": horizon, "horizon_seconds": seconds, "horizon_complete": horizon_complete,
               "source": "gateio_public_spot", "symbol": decision.get("symbol", "BTC_USDT"),
               "timeframe": decision.get("timeframe", "15m"), "decision": "NO_TRADE",
               "decision_reasons": decision.get("gate_reasons") or [decision.get("no_trade_reason")],
               "policy_version": decision.get("policy_version"), "directional_proposal": direction,
               "outcome_class": "PENDING" if not horizon_complete else "DIRECTIONLESS_MARKET_CONTEXT",
               "baseline_close": base_close, "last_close": None, "close_change_pct": None,
               "max_favorable_excursion_pct": None, "max_adverse_excursion_pct": None,
               "hypothetical_trade_outcome": None, "gross_R": None, "net_R": None,
               "cost_model": "UNCONFIGURED_NOT_ESTIMATED", "policy_mutation_enabled": False,
               "execution_enabled": False, "orders_placed": False}
        if not horizon_complete:
            out.append(rec); continue
        last_close = _price(window[-1], "close")
        rec["last_close"] = last_close
        rec["close_change_pct"] = round((last_close / base_close - 1) * 100, 6)
        if direction == "LONG":
            rec["max_favorable_excursion_pct"] = round((max(_price(r, "high") for r in window) / base_close - 1) * 100, 6)
            rec["max_adverse_excursion_pct"] = round((min(_price(r, "low") for r in window) / base_close - 1) * 100, 6)
        elif direction == "SHORT":
            rec["max_favorable_excursion_pct"] = round((1 - min(_price(r, "low") for r in window) / base_close) * 100, 6)
            rec["max_adverse_excursion_pct"] = round((1 - max(_price(r, "high") for r in window) / base_close) * 100, 6)
        if trade_geometry:
            risk = abs(entry - stop); barrier = None
            for candle in window:
                hit_stop = _price(candle, "low") <= stop if direction == "LONG" else _price(candle, "high") >= stop
                hit_target = _price(candle, "high") >= target if direction == "LONG" else _price(candle, "low") <= target
                if hit_stop or hit_target:
                    if hit_stop and hit_target: barrier = ("AMBIGUOUS_SAME_CANDLE", None, candle)
                    elif hit_stop: barrier = ("STOP_LOSS", -1.0, candle)
                    else: barrier = ("TAKE_PROFIT", abs(target-entry)/risk, candle)
                    break
            if barrier:
                rec["outcome_class"] = barrier[0]; rec["hypothetical_trade_outcome"] = barrier[0]
                rec["gross_R"] = barrier[1]; rec["barrier_candle_close_time"] = _dt(barrier[2]["close_time"]).isoformat()
            else:
                move = (last_close-entry) if direction == "LONG" else (entry-last_close)
                rec["outcome_class"] = "TIMEOUT_POSITIVE" if move > 0 else "TIMEOUT_NEGATIVE" if move < 0 else "TIMEOUT_FLAT"
                rec["hypothetical_trade_outcome"] = "TIMEOUT"; rec["gross_R"] = round(move/risk, 6)
            rec.update({"entry": entry, "stop_loss": stop, "take_profit": target})
        out.append(rec)
    return out

def run(root: str | Path = "/opt/hes-trade-agent") -> dict[str, Any]:
    root = Path(root); data = root / "data" / "forward"
    decisions_all = _read_jsonl(data / "trade_journal_v2.jsonl")
    candles = validate_candles(_read_jsonl(data / "global_market_candles_v1.jsonl"))
    decisions = [r for r in decisions_all if r.get("decision") == "NO_TRADE"]
    output_path = data / "neutral_decision_outcomes_v1.jsonl"
    existing = _read_jsonl(output_path); done = {r.get("outcome_id") for r in existing}
    # A bounded candle-retention window can no longer reproduce old baselines.
    # Do not call those decisions unscorable when their immutable, complete
    # horizon records are already present in the append-only outcome ledger.
    existing_complete: dict[str, set[str]] = {}
    for row in existing:
        event_id = row.get("decision_event_id")
        horizon = row.get("horizon")
        if (
            row.get("schema") == SCHEMA
            and row.get("horizon_complete") is True
            and isinstance(event_id, str)
            and horizon in DEFAULT_HORIZONS
            and row.get("outcome_id") == _stable_id(event_id, horizon)
        ):
            existing_complete.setdefault(event_id, set()).add(horizon)

    new = []; pending = 0; unscorable_no_baseline_event_ids = []
    unscorable_no_baseline_missing_horizons = []
    for decision in decisions:
        try:
            evaluated = evaluate_no_trade(decision, candles)
        except ValueError as exc:
            # A missing retained baseline is only an outstanding evidence gap
            # when one or more required horizons are not already complete.
            if str(exc) == "NO_CLOSED_CANDLE_AT_DECISION_TIME":
                event_id = str(decision.get("event_id") or "")
                missing_horizons = sorted(set(DEFAULT_HORIZONS) - existing_complete.get(event_id, set()))
                if missing_horizons:
                    unscorable_no_baseline_event_ids.append(event_id)
                    unscorable_no_baseline_missing_horizons.extend(
                        f"{event_id}|{horizon}" for horizon in missing_horizons
                    )
                continue
            raise
        for record in evaluated:
            if not record["horizon_complete"]:
                pending += 1
            elif record["outcome_id"] not in done:
                new.append(record); done.add(record["outcome_id"])
    if new:
        with output_path.open("a", encoding="utf-8") as handle:
            for row in new: handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
    all_rows = existing + new
    unscorable_digest = (
        hashlib.sha256("\n".join(sorted(unscorable_no_baseline_event_ids)).encode()).hexdigest()
        if unscorable_no_baseline_event_ids else None
    )
    missing_horizons_digest = (
        hashlib.sha256("\n".join(sorted(unscorable_no_baseline_missing_horizons)).encode()).hexdigest()
        if unscorable_no_baseline_missing_horizons else None
    )
    summary = {"schema": "hes_neutral_decision_outcomes_report_v1",
               "status": "PARTIAL_UNSCORABLE" if unscorable_no_baseline_event_ids else "OK",
               "updated_at": datetime.now(timezone.utc).isoformat(), "decision_count": len(decisions),
               "validated_candle_count": len(candles), "outcome_records_total": len(all_rows),
               "new_records_added": len(new), "complete_records": sum(r.get("horizon_complete") is True for r in all_rows),
               "pending_horizons_current_run": pending,
               "unscorable_no_baseline_decisions": len(unscorable_no_baseline_event_ids),
               "unscorable_no_baseline_horizons": len(unscorable_no_baseline_missing_horizons),
               "unscorable_no_baseline_reason": "NO_CLOSED_CANDLE_AT_DECISION_TIME" if unscorable_no_baseline_event_ids else None,
               "unscorable_no_baseline_event_ids_sha256": unscorable_digest,
               "unscorable_no_baseline_missing_horizons_sha256": missing_horizons_digest,
               "retention_boundary_policy": "COUNT_ONLY_WHEN_REQUIRED_HORIZON_OUTCOMES_MISSING",
               "outcome_class_counts": {},
               "output_file": str(output_path), "policy_mutation_enabled": False,
               "execution_enabled": False, "orders_placed": False}
    for row in all_rows:
        k = row.get("outcome_class", "UNKNOWN")
        summary["outcome_class_counts"][k] = summary["outcome_class_counts"].get(k, 0) + 1
    (data / "neutral_decision_outcomes_report_v1.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary

if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
