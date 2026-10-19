#!/usr/bin/env python3
"""Fixed 8-fold OOS candidate contrast audit on the immutable fresh snapshot.

Execution-free: no threshold search, fitting, ranking-based selection,
promotion, or live execution.
"""
import csv, json, math, statistics, os
import sys
from pathlib import Path
from collections import Counter, defaultdict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
EMA_PERIOD = 20
TRAIN = 800
TEST = 400
STEP = 400
FOLDS = 8
THRESHOLD = 0.0014

# Candidate Performance Study lineage: immutable Boundary-Proof fresh snapshot.
SNAPSHOT_DATA_BLOB_SHA = os.environ["FRESH_BLOB_SHA"]
SNAPSHOT_SOURCE_COMMIT = os.environ["FRESH_SOURCE_COMMIT"]

FEATURES = ["ema_distance_pct", "vwap_distance_pct", "buy_ratio", "buy_sell_delta", "trade_count"]

def rel(a, b):
    return (a - b) / b if b else 0.0

def q(v, p):
    s = sorted(v)
    x = (len(s) - 1) * p
    lo, hi = math.floor(x), math.ceil(x)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (x - lo)

def stats(v):
    return {
        "n": len(v),
        "mean": statistics.fmean(v),
        "median": statistics.median(v),
        "std": statistics.stdev(v) if len(v) > 1 else 0.0,
        "min": min(v),
        "q10": q(v, .1),
        "q25": q(v, .25),
        "q50": q(v, .5),
        "q75": q(v, .75),
        "q90": q(v, .9),
        "max": max(v),
    }

def smd(a, b):
    va = statistics.pvariance(a) if len(a) > 1 else 0
    vb = statistics.pvariance(b) if len(b) > 1 else 0
    d = math.sqrt((va + vb) / 2)
    return (statistics.fmean(a) - statistics.fmean(b)) / d if d else 0.0

def load():
    reader = RawDataReader(active_file=CSV_PATH, archive_dir="__no_archive__")
    val = RawDataValidator()
    norm = RawDataNormalizer()
    trades = []
    total = invalid = 0
    for row in reader.read_all():
        total += 1
        if val.validate_row(row):
            invalid += 1
        else:
            trades.append(norm.normalize_row(row))
    trades.sort(key=lambda t: (t.timestamp, t.sequence or -1))
    return trades, total, invalid

def main():
    trades, rows_read, rows_invalid = load()
    candles = TradeCandleAggregator(60).aggregate(trades)
    ema = EMACalculator(EMA_PERIOD).calculate(candles)
    vwap = VWAPCalculator(60).calculate(trades)

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
        pressure[k] = (
            buy / total if total else 0.0,
            buy - sell,
            len(g),
            min(seq) if seq else None,
            max(seq) if seq else None,
        )

    em = {(x.symbol, x.timestamp): x.value for x in ema}
    vw = {(x.symbol, x.end): x.vwap for x in vwap}
    strat = BaselineStrategy(min_confirmations=3)
    risk = RiskPolicy()
    observations = []

    for i in range(EMA_PERIOD - 1, len(candles) - 1):
        c, n = candles[i], candles[i + 1]
        if c.symbol != n.symbol or n.start != c.end:
            continue
        p = pressure.get((c.symbol, int(c.start.timestamp())))
        ev = em.get((c.symbol, c.end))
        vv = vw.get((c.symbol, c.end))
        if p is None or ev is None or vv is None:
            continue

        br, delta, count, s0, s1 = p
        fs = FeatureSnapshot(
            symbol=c.symbol, timeframe_seconds=60, close=c.close, ema=ev, vwap=vv,
            buy_sell_delta=delta, buy_ratio=br, timestamp=c.end
        )
        decision = strat.evaluate(BaselineStrategyInput(features=fs))
        rd = risk.evaluate(RiskInput(decision=decision, equity=1000.0))
        evaluated = (
            decision in (BaselineDecision.LONG, BaselineDecision.SHORT)
            and rd is RiskDecision.ALLOW_SIGNAL
        )
        gross = None
        if evaluated:
            sign = 1 if decision is BaselineDecision.LONG else -1
            gross = sign * (n.close - c.close) / c.close

        observations.append({
            "timestamp": c.end.isoformat(),
            "sequence_first": s0,
            "sequence_last": s1,
            "entry_price": c.close,
            "exit_price": n.close,
            "gross_return": gross,
            "direction": decision.value,
            "evaluated": evaluated,
            "ema_distance_pct": rel(c.close, ev),
            "vwap_distance_pct": rel(c.close, vv),
            "buy_ratio": br,
            "buy_sell_delta": delta,
            "trade_count": count,
            "candle_index": i,
        })

    rows = []
    fold_meta = []
    for fold in range(FOLDS):
        a = fold * STEP + TRAIN
        b = a + TEST
        test = observations[a:b]
        ev = [r for r in test if r["evaluated"]]
        total = sum(r["gross_return"] for r in ev)
        regime = "uptrend" if total >= .01 else "downtrend" if total <= -.01 else "range"
        fold_meta.append({
            "fold_index": fold,
            "observations": len(test),
            "evaluated": len(ev),
            "gross_return": total,
            "regime": regime,
        })
        for r in ev:
            x = dict(r)
            x["fold_index"] = fold
            x["fold_regime"] = regime
            rows.append(x)

    oos_observations = observations[TRAIN:TRAIN + FOLDS * STEP]
    # Preserve the fixed 8-fold boundaries without inventing observations across
    # timestamp gaps. A sparse fresh snapshot can therefore yield fewer than
    # FOLDS*TEST contiguous observations; the actual OOS population is evidence.
    expected_oos = FOLDS * TEST
    actual_oos = len(oos_observations)
    assert actual_oos > 0, "fresh snapshot produced no OOS observations"

    winners = [r for r in rows if r["gross_return"] > THRESHOLD]
    controls = [r for r in rows if r["gross_return"] <= THRESHOLD]
    assert len(winners) + len(controls) == len(rows)
    assert winners, "fresh snapshot produced no winners"

    contrasts = {}
    for f in FEATURES:
        a = [r[f] for r in winners]
        b = [r[f] for r in controls]
        contrasts[f] = {
            "winners": stats(a),
            "controls": stats(b),
            "smd": smd(a, b),
            "control_values_inside_winner_range": sum(min(a) <= x <= max(a) for x in b),
            "winner_range": [min(a), max(a)],
        }

    stability = {"fold_exclusion": {}, "leave_one_winner_out": {}, "regime_direction": {}}
    for fold in sorted(set(r["fold_index"] for r in rows)):
        wf = [r for r in winners if r["fold_index"] != fold]
        cf = [r for r in controls if r["fold_index"] != fold]
        stability["fold_exclusion"][str(fold)] = {
            "winner_count_remaining": len(wf),
            "control_count_remaining": len(cf),
            "winner_gross_sum_remaining": sum(r["gross_return"] for r in wf),
            "feature_smd_without_fold": {
                k: smd([r[k] for r in wf], [r[k] for r in cf])
                for k in FEATURES
            } if wf and cf else {},
        }

    for w in winners:
        rest = [r for r in winners if r is not w]
        stability["leave_one_winner_out"][w["timestamp"]] = {
            "fold_index": w["fold_index"],
            "removed_gross_return": w["gross_return"],
            "remaining_winner_count": len(rest),
            "remaining_winner_gross_sum": sum(r["gross_return"] for r in rest),
            "feature_smd_without_sample": {
                k: smd([r[k] for r in rest], [r[k] for r in controls])
                for k in FEATURES
            },
        }

    for key in ("direction", "fold_regime"):
        stability["regime_direction"][key] = {}
        vals = sorted(set(r[key] for r in rows))
        for val in vals:
            wf = [r for r in winners if r[key] == val]
            cf = [r for r in controls if r[key] == val]
            stability["regime_direction"][key][val] = {
                "winner_count": len(wf),
                "control_count": len(cf),
                "winner_gross_sum": sum(r["gross_return"] for r in wf),
            }

    result = {
        "protocol": {
            "train": TRAIN, "test": TEST, "step": STEP, "folds": FOLDS,
            "gross_threshold": THRESHOLD,
            "snapshot_data_blob_sha": SNAPSHOT_DATA_BLOB_SHA,
            "snapshot_source_commit": SNAPSHOT_SOURCE_COMMIT,
        },
        "population": {
            "rows_read": rows_read,
            "rows_invalid": rows_invalid,
            "candles": len(candles),
            "observations": len(observations),
            "evaluated_oos": len(rows),
            "oos_window": {
                "requested_observations": expected_oos,
                "available_observations": actual_oos,
                "shortfall": expected_oos - actual_oos,
                "gap_policy": "preserve fixed fold boundaries; do not synthesize observations across timestamp gaps",
            },
        },
        "counts": {
            "winners_gt_14bps": len(winners),
            "controls_le_14bps": len(controls),
        },
        "folds": fold_meta,
        "categorical": {
            "direction_winners": dict(Counter(r["direction"] for r in winners)),
            "direction_controls": dict(Counter(r["direction"] for r in controls)),
            "fold_winners": dict(Counter(r["fold_index"] for r in winners)),
            "fold_controls": dict(Counter(r["fold_index"] for r in controls)),
            "regime_winners": dict(Counter(r["fold_regime"] for r in winners)),
            "regime_controls": dict(Counter(r["fold_regime"] for r in controls)),
        },
        "feature_contrast": contrasts,
        "stability": stability,
        "winners": winners,
    }
    Path("14_vs_1035_contrast_audit.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    with open("14_vs_1035_winners.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(winners[0]))
        w.writeheader()
        w.writerows(winners)

    print(json.dumps({
        "counts": result["counts"],
        "evaluated_oos": len(rows),
        "categorical": result["categorical"],
        "smd": {k: v["smd"] for k, v in contrasts.items()},
    }, indent=2))

if __name__ == "__main__":
    main()
