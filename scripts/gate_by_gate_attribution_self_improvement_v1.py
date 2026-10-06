#!/usr/bin/env python3
"""Gate-by-Gate Attribution + Self-Improvement diagnostic v1.

Research-only. Replays the locked protocol and records why each OOS
observation was rejected, plus non-causal diagnostics for executed losses.
It never changes thresholds, reselects winners, deletes records, tunes
parameters, or authorizes execution.
"""
import json, math, os, statistics
from collections import Counter, defaultdict
from pathlib import Path

from core.data_engine.candles import TradeCandleAggregator
from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.reader import RawDataReader
from core.data_engine.validator import RawDataValidator
from core.data_engine.vwap import VWAPCalculator
from core.feature_engine.ema import EMACalculator
from core.feature_engine.quality import FeatureSnapshot
from core.strategy.baseline import BaselineStrategy, BaselineStrategyInput, BaselineDecision
from core.risk.boundary import RiskPolicy, RiskInput, RiskDecision

CSV_PATH = os.environ.get("HES_FROZEN_CSV", "data/trades.csv")
TRAIN, TEST, STEP, FOLDS = 800, 400, 400, 8
THRESHOLD = 0.0014
EQUITY = 1000.0

def finite(x):
    return x is not None and math.isfinite(x)

def rel(a, b):
    return (a - b) / b if b else None

def load_trades():
    reader = RawDataReader(active_file=CSV_PATH, archive_dir="__no_archive__")
    validator, normalizer = RawDataValidator(), RawDataNormalizer()
    valid, invalid = [], 0
    for row in reader.read_all():
        errors = validator.validate_row(row)
        if errors:
            invalid += 1
        else:
            valid.append(normalizer.normalize_row(row))
    valid.sort(key=lambda t: (t.timestamp, t.sequence or -1))
    return valid, invalid

def confirmation_trace(fs, trend=None, structure_bias=None, min_confirmations=3):
    violations = []
    if not fs.symbol:
        violations.append("missing_symbol")
    if fs.timeframe_seconds <= 0:
        violations.append("invalid_timeframe")
    if fs.timestamp is not None and (fs.timestamp.tzinfo is None or fs.timestamp.utcoffset() is None):
        violations.append("invalid_timestamp")
    for name, value in (("close", fs.close), ("ema", fs.ema), ("vwap", fs.vwap)):
        if value is None:
            violations.append("missing_" + name)
        elif not finite(value) or value <= 0:
            violations.append("invalid_" + name)
    if fs.buy_sell_delta is not None and not finite(fs.buy_sell_delta):
        violations.append("invalid_buy_sell_delta")
    if fs.buy_ratio is not None and (not finite(fs.buy_ratio) or not 0 <= fs.buy_ratio <= 1):
        violations.append("invalid_buy_ratio")
    quality_pass = not violations
    if not quality_pass:
        return {
            "quality_pass": False, "quality_reasons": violations,
            "long_score": 0, "short_score": 0, "decision": "NO_TRADE",
            "confirmation_pass": False, "confirmation_reasons": ["feature_quality_failed"]
        }

    biases = (trend, structure_bias)
    if "long" in biases and "short" in biases:
        return {"quality_pass": True, "quality_reasons": [],
                "long_score": 0, "short_score": 0, "decision": "NO_TRADE",
                "confirmation_pass": False, "confirmation_reasons": ["conflicting_biases"]}
    if trend not in (None, "long", "short") or structure_bias not in (None, "long", "short"):
        return {"quality_pass": True, "quality_reasons": [],
                "long_score": 0, "short_score": 0, "decision": "NO_TRADE",
                "confirmation_pass": False, "confirmation_reasons": ["invalid_bias"]}

    long_score = short_score = 0
    reasons = []
    close, ema, vwap, buy_ratio = fs.close, fs.ema, fs.vwap, fs.buy_ratio
    if close > ema:
        long_score += 1
    elif close < ema:
        short_score += 1
    if close > vwap:
        long_score += 1
    elif close < vwap:
        short_score += 1
    if buy_ratio is not None:
        if buy_ratio > 0.5:
            long_score += 1
        elif buy_ratio < 0.5:
            short_score += 1
    for bias in biases:
        if bias == "long":
            long_score += 1
        elif bias == "short":
            short_score += 1

    decision = "NO_TRADE"
    if long_score >= min_confirmations and long_score > short_score:
        decision = "LONG"
    elif short_score >= min_confirmations and short_score > long_score:
        decision = "SHORT"
    else:
        reasons.append("insufficient_or_tied_confirmation")

    if decision == "LONG" and "short" in biases:
        decision, reasons = "NO_TRADE", ["long_signal_conflicts_with_short_bias"]
    if decision == "SHORT" and "long" in biases:
        decision, reasons = "NO_TRADE", ["short_signal_conflicts_with_long_bias"]

    return {
        "quality_pass": True, "quality_reasons": [],
        "long_score": long_score, "short_score": short_score,
        "decision": decision,
        "confirmation_pass": decision != "NO_TRADE",
        "confirmation_reasons": reasons
    }

def main():
    trades, invalid_raw = load_trades()
    candles = TradeCandleAggregator(60).aggregate(trades)
    ema = EMACalculator(20).calculate(candles)
    vwap = VWAPCalculator(60).calculate(trades)
    em = {(x.symbol, x.timestamp): x.value for x in ema}
    vw = {(x.symbol, x.end): x.vwap for x in vwap}

    grouped = defaultdict(list)
    for t in trades:
        e = int(t.timestamp.timestamp())
        grouped[(t.symbol, e - e % 60)].append(t)
    pressure = {}
    for k, g in grouped.items():
        buy = sum(t.quantity for t in g if t.side == "buy")
        sell = sum(t.quantity for t in g if t.side == "sell")
        total = buy + sell
        seq = [t.sequence for t in g if t.sequence is not None]
        pressure[k] = (buy / total if total else 0.0, buy - sell, len(g),
                        min(seq) if seq else None, max(seq) if seq else None)

    strategy = BaselineStrategy(min_confirmations=3)
    risk = RiskPolicy()
    all_obs, oos = [], []

    for i in range(19, len(candles) - 1):
        c, n = candles[i], candles[i + 1]
        if c.symbol != n.symbol or n.start != c.end:
            continue
        p = pressure.get((c.symbol, int(c.start.timestamp())))
        ev, vv = em.get((c.symbol, c.end)), vw.get((c.symbol, c.end))
        fs = FeatureSnapshot(
            symbol=c.symbol, timeframe_seconds=60, close=c.close, ema=ev, vwap=vv,
            buy_sell_delta=p[1] if p else None, buy_ratio=p[0] if p else None,
            timestamp=c.end
        )
        trace = confirmation_trace(fs)
        decision = strategy.evaluate(BaselineStrategyInput(features=fs))
        rd = risk.evaluate(RiskInput(decision=decision, equity=EQUITY))
        # Independent trace must agree with production strategy/risk contracts.
        assert trace["decision"] == decision.value
        risk_pass = rd is RiskDecision.ALLOW_SIGNAL
        evaluated = decision in (BaselineDecision.LONG, BaselineDecision.SHORT) and risk_pass
        gross = None
        if evaluated:
            sign = 1 if decision is BaselineDecision.LONG else -1
            gross = sign * (n.close - c.close) / c.close

        fold = None
        if TRAIN <= i < TRAIN + FOLDS * STEP:
            fold = (i - TRAIN) // STEP

        row = {
            "timestamp": c.end.isoformat(), "candle_index": i,
            "sequence_first": p[3] if p else None, "sequence_last": p[4] if p else None,
            "entry_price": c.close, "exit_price": n.close,
            "gross_return": gross, "direction": decision.value,
            "evaluated": evaluated, "fold_index": fold,
            "ema_distance_pct": rel(c.close, ev), "vwap_distance_pct": rel(c.close, vv),
            "buy_ratio": p[0] if p else None, "buy_sell_delta": p[1] if p else None,
            "trade_count": p[2] if p else None,
            "gates": {
                "data_quality": {"status": "PASS" if trace["quality_pass"] else "FAIL",
                                 "reasons": trace["quality_reasons"]},
                "confirmation": {"status": "PASS" if trace["confirmation_pass"] else "FAIL",
                                  "reasons": trace["confirmation_reasons"],
                                  "long_score": trace["long_score"],
                                  "short_score": trace["short_score"]},
                "risk": {"status": "PASS" if risk_pass else "FAIL",
                         "reasons": [] if risk_pass else ["risk_policy_veto"]},
                "decision": "EXECUTE" if evaluated else "NO_TRADE"
            }
        }
        all_obs.append(row)
        if fold is not None:
            row["fold_regime"] = None
            oos.append(row)

    # Frozen regime labeling: same aggregate fold gross-return rule as producer.
    for f in range(FOLDS):
        ev = [r for r in oos if r["fold_index"] == f and r["evaluated"]]
        total = sum(r["gross_return"] for r in ev)
        regime = "uptrend" if total >= .01 else "downtrend" if total <= -.01 else "range"
        for r in oos:
            if r["fold_index"] == f:
                r["fold_regime"] = regime

    # Rejection attribution.
    rejection_counts = Counter()
    rejection_reasons = Counter()
    for r in oos:
        if r["evaluated"]:
            continue
        g = r["gates"]
        if g["data_quality"]["status"] == "FAIL":
            primary = "DATA_QUALITY"
            reasons = g["data_quality"]["reasons"]
        elif g["confirmation"]["status"] == "FAIL":
            primary = "CONFIRMATION"
            reasons = g["confirmation"]["reasons"]
        elif g["risk"]["status"] == "FAIL":
            primary = "RISK"
            reasons = g["risk"]["reasons"]
        else:
            primary, reasons = "DECISION", ["no_trade"]
        rejection_counts[primary] += 1
        for x in reasons:
            rejection_reasons[f"{primary}:{x}"] += 1

    executed = [r for r in oos if r["evaluated"]]
    losses = [r for r in executed if r["gross_return"] <= 0]
    winners = [r for r in executed if r["gross_return"] > THRESHOLD]

    def mean(rows, key):
        vals = [r[key] for r in rows if isinstance(r.get(key), (int, float)) and math.isfinite(r[key])]
        return statistics.fmean(vals) if vals else None

    loss_patterns = []
    for dim in ("direction", "fold_regime", "fold_index"):
        groups = defaultdict(list)
        for r in losses:
            groups[str(r.get(dim))].append(r)
        for value, rows in sorted(groups.items()):
            if len(rows) >= 5:
                loss_patterns.append({
                    "dimension": dim, "value": value, "loss_count": len(rows),
                    "mean_loss_return": mean(rows, "gross_return"),
                    "mean_ema_distance": mean(rows, "ema_distance_pct"),
                    "mean_vwap_distance": mean(rows, "vwap_distance_pct"),
                    "mean_buy_ratio": mean(rows, "buy_ratio"),
                    "diagnostic_status": "HYPOTHESIS_ONLY"
                })

    result = {
        "artifact_type": "GATE_BY_GATE_ATTRIBUTION_SELF_IMPROVEMENT_V1",
        "status": "RESEARCH_ONLY__NO_MUTATION",
        "protocol": {"train": TRAIN, "test": TEST, "step": STEP, "folds": FOLDS,
                     "gross_threshold": THRESHOLD},
        "source": {
            "raw_blob_sha": os.environ.get("LOCKED_RAW_BLOB_SHA", ""),
            "raw_source_commit": os.environ.get("LOCKED_RAW_SOURCE_COMMIT", ""),
            "protocol_contract_blob_sha": os.environ.get("PROTOCOL_CONTRACT_BLOB_SHA", ""),
            "full_candidate_base_sha256": os.environ.get("FULL_CANDIDATE_BASE_SHA256", "")
        },
        "population": {
            "raw_rows_invalid": invalid_raw,
            "oos_opportunities": len(oos),
            "oos_evaluated": len(executed),
            "oos_rejected": len(oos) - len(executed),
            "winner_gt_14bps": len(winners),
            "losses_le_0": len(losses)
        },
        "gate_attribution": {
            "primary_rejection_counts": dict(rejection_counts),
            "reason_counts": dict(rejection_reasons),
            "rejection_rate": (len(oos)-len(executed))/len(oos) if oos else None
        },
        "loss_self_improvement": {
            "losses_analyzed": len(losses),
            "pattern_diagnostics": loss_patterns,
            "candidate_action": "NO_CHANGE",
            "reason": "Diagnostics may generate hypotheses, but no parameter/threshold mutation is authorized by this artifact."
        },
        "invariants": {
            "threshold_changed": False, "winner_reselected": False,
            "records_deleted": False, "tuning": False, "promotion": False,
            "live_execution": False, "causal_claims": False
        },
        "records": oos
    }
    Path("gate_by_gate_attribution_self_improvement_v1.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({
        "population": result["population"],
        "primary_rejection_counts": result["gate_attribution"]["primary_rejection_counts"],
        "candidate_action": result["loss_self_improvement"]["candidate_action"]
    }, indent=2))

if __name__ == "__main__":
    main()
