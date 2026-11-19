"""Structure-only NO_TRADE shadow replay. Diagnostic only; never emits trade authority."""
from __future__ import annotations
from bisect import bisect_left
from datetime import datetime
import math
import re

HORIZONS = {"1h": 3600, "4h": 14400, "24h": 86400}
COST_SENSITIVITY_BPS = (10, 20, 30, 50)
_DIRECTION_RE = re.compile(r"candidate_direction:(LONG|SHORT)")

def _decision_candidate(decision):
    gate = decision.get("gate_evidence") or {}
    confirmation = gate.get("confirmation") or {}
    structure = gate.get("structure") or {}
    checks = confirmation.get("checks") or []
    by_name = {x.get("name"): x for x in checks if isinstance(x, dict)}
    ref = str((by_name.get("direction_regime_alignment") or {}).get("evidence_ref", ""))
    match = _DIRECTION_RE.search(ref)
    direction = match.group(1) if match else None
    regime = structure.get("regime") or decision.get("market_regime") or "UNKNOWN"
    regime_ok = ((regime == "UPTREND" and direction == "LONG")
                 or (regime == "DOWNTREND" and direction == "SHORT")
                 or (regime == "RANGE" and direction in ("LONG", "SHORT")))
    detected = ((by_name.get("candidate_valid") or {}).get("state") == "PASS"
                and (by_name.get("structural_event_present") or {}).get("state") == "PASS"
                and direction in ("LONG", "SHORT") and regime_ok)
    return gate, structure, direction, regime, detected

def _valid_candle(row):
    try:
        op = int(row["open_time"]); ct = int(row["close_time"])
        o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        return (row.get("source") == "gateio_public_spot"
                and row.get("symbol") == "BTC_USDT"
                and row.get("timeframe") == "1m"
                and row.get("closed") is True
                and ct - op == 60
                and all(math.isfinite(x) and x > 0 for x in (o, h, l, c))
                and l <= min(o, c) and h >= max(o, c))
    except (KeyError, TypeError, ValueError, OverflowError):
        return False

def evaluate_structure_only_shadow(decision, candles_1m):
    gate, structure, direction, regime, detected = _decision_candidate(decision)
    base = {
        "policy": "hes-structure-only-no-trade-shadow-v1",
        "status": "NO_INDEPENDENT_CANDIDATE",
        "direction": direction,
        "proposal_direction": decision.get("proposal_direction") or "NONE",
        "regime": regime,
        "economic_status": "NOT_EXECUTION_EVIDENCE",
        "horizons": {},
        "execution_enabled": False,
        "orders_placed": False,
    }
    if not detected:
        return base
    base["status"] = "SHADOW_GEOMETRY_INVALID"
    try:
        stamp = datetime.fromisoformat(str(decision["observed_at"]).replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("DECISION_TIMESTAMP_NOT_AWARE")
        decision_ts = stamp.timestamp()
        open_times = [int(x["open_time"]) for x in candles_1m]
        entry_idx = bisect_left(open_times, decision_ts)
        if entry_idx >= len(candles_1m):
            base["status"] = "SHADOW_ENTRY_PENDING"
            return base
        entry_row = candles_1m[entry_idx]
        if not _valid_candle(entry_row):
            base["status"] = "SHADOW_ENTRY_CANDLE_INVALID"
            return base
        entry = float(entry_row["open"])
        if not math.isfinite(entry) or entry <= 0:
            base["status"] = "SHADOW_ENTRY_INVALID"
            return base
        base.update({"entry_time": int(entry_row["open_time"]), "entry_price": entry})
        stop_raw = structure.get("last_swing_low") if direction == "LONG" else structure.get("last_swing_high")
        if stop_raw is None:
            base["status"] = "SHADOW_STOP_MISSING"
            return base
        try:
            stop = float(stop_raw)
        except (TypeError, ValueError, OverflowError):
            base["status"] = "SHADOW_STOP_INVALID"
            return base
        if not math.isfinite(stop) or stop <= 0:
            base["status"] = "SHADOW_STOP_INVALID"
            return base
        base["stop_loss"] = stop
        if direction == "LONG" and not stop < entry:
            base["status"] = "SHADOW_STOP_NOT_ON_LOSS_SIDE"
            return base
        if direction == "SHORT" and not stop > entry:
            base["status"] = "SHADOW_STOP_NOT_ON_LOSS_SIDE"
            return base
        risk = abs(entry - stop)
        target = entry + 3 * risk if direction == "LONG" else entry - 3 * risk
        if not math.isfinite(target) or target <= 0:
            base["status"] = "SHADOW_TARGET_INVALID"
            return base
    except (KeyError, TypeError, ValueError, OverflowError, IndexError):
        base["status"] = "SHADOW_DECISION_OR_ENTRY_TIMESTAMP_INVALID"
        return base

    base.update({
        "status": "SHADOW_EVALUATED",
        "entry_time": int(entry_row["open_time"]),
        "entry_price": entry,
        "stop_loss": stop,
        "take_profit": target,
        "risk_distance": risk,
        "gross_rr": 3.0,
        "entry_basis": "first 1m candle open_time >= immutable decision observed_at",
        "stop_basis": "decision-time last_swing_low/last_swing_high",
        "candidate_valid_pass": True,
        "structural_event_pass": True,
        "regime_direction_aligned": True,
    })
    entry_time = int(entry_row["open_time"])
    for horizon, seconds in HORIZONS.items():
        expected = seconds // 60
        cutoff = entry_time + seconds
        window = candles_1m[entry_idx:entry_idx + expected]
        valid = len(window) == expected and all(_valid_candle(x) for x in window)
        contiguous = valid and all(int(b["open_time"]) - int(a["open_time"]) == 60
                                   for a, b in zip(window, window[1:]))
        boundary_ok = valid and int(window[-1]["close_time"]) == cutoff
        if not (valid and contiguous and boundary_ok):
            horizon_reached = bool(window) and int(window[-1].get("open_time", 0)) >= cutoff - 60
            base["horizons"][horizon] = {
                "outcome_class": "SHADOW_DATA_GAP" if horizon_reached or len(window) >= expected else "SHADOW_PENDING",
                "expected_1m_candles": expected,
                "observed_1m_candles": len(window),
                "gross_r": None,
                "gross_return_pct": None,
                "ambiguous_same_candle": False,
                "net_sensitivity_long_only": {},
            }
            continue
        exit_price = float(window[-1]["close"])
        exit_reason = "TIMEOUT"
        ambiguous = False
        for bar in window:
            high = float(bar["high"]); low = float(bar["low"])
            stop_hit = low <= stop if direction == "LONG" else high >= stop
            target_hit = high >= target if direction == "LONG" else low <= target
            if stop_hit or target_hit:
                ambiguous = bool(stop_hit and target_hit)
                if stop_hit:
                    exit_price = stop
                    exit_reason = "STOP_LOSS"
                else:
                    exit_price = target
                    exit_reason = "TAKE_PROFIT"
                break
        pnl_price = (exit_price - entry) if direction == "LONG" else (entry - exit_price)
        gross_r = pnl_price / risk
        gross_fraction = (exit_price / entry - 1) if direction == "LONG" else (entry / exit_price - 1)
        if exit_reason == "STOP_LOSS":
            label = "SHADOW_STOP_HIT"
        elif exit_reason == "TAKE_PROFIT":
            label = "SHADOW_TARGET_HIT"
        elif gross_fraction > 0:
            label = "SHADOW_TIMEOUT_POSITIVE"
        elif gross_fraction < 0:
            label = "SHADOW_TIMEOUT_NEGATIVE"
        else:
            label = "SHADOW_TIMEOUT_FLAT"
        sensitivity = {}
        if direction == "LONG":
            for bps in COST_SENSITIVITY_BPS:
                net_fraction = gross_fraction - bps / 10000
                sensitivity[str(bps)] = {
                    "net_return_pct": round(net_fraction * 100, 6),
                    "net_positive": net_fraction > 0,
                    "cost_is_assumption": True,
                }
        base["horizons"][horizon] = {
            "outcome_class": label,
            "exit_reason": exit_reason,
            "exit_price": exit_price,
            "exit_time": int(window[-1]["close_time"]) if exit_reason == "TIMEOUT" else None,
            "gross_r": round(gross_r, 6),
            "gross_return_pct": round(gross_fraction * 100, 6),
            "ambiguous_same_candle": ambiguous,
            "expected_1m_candles": expected,
            "observed_1m_candles": len(window),
            "net_sensitivity_long_only": sensitivity,
            "short_economics": "NOT_TESTABLE_FROM_SPOT" if direction == "SHORT" else None,
        }
    return base
