"""Recover the exact 1,049 evaluated OOS observations from the frozen Run-41 raw snapshot.

Fail-closed: source blob SHA, raw row count, fold counts and final population
must match the frozen evidence contract. No rows are synthesized.
"""
import csv, hashlib, json, sys
from datetime import timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.data_engine.candles import TradeCandleAggregator
from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.reader import RawDataReader
from core.data_engine.validator import RawDataValidator
from core.data_engine.vwap import VWAPCalculator
from core.feature_engine.ema import EMACalculator
from core.feature_engine.quality import FeatureSnapshot
from core.models.trade import CanonicalTrade
from core.risk.boundary import RiskDecision, RiskInput, RiskPolicy
from core.strategy.baseline import BaselineDecision, BaselineStrategy, BaselineStrategyInput

SOURCE_SHA = "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
EXPECTED_RAW_ROWS = 129920
EXPECTED_FOLDS = 8
EXPECTED_EVALUATED = 1049
EXPECTED_FOLD_EVALUATED = [120,132,135,137,138,127,126,134]


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def main():
    path = Path("data/trades.csv")
    actual_sha = git_blob_sha(path)
    if actual_sha != SOURCE_SHA:
        raise AssertionError(f"source blob mismatch: {actual_sha} != {SOURCE_SHA}")

    reader = RawDataReader(active_file=str(path), archive_dir="__no_archive__")
    validator = RawDataValidator()
    normalizer = RawDataNormalizer()
    trades: list[CanonicalTrade] = []
    raw_rows = 0
    invalid = 0
    for row in reader.read_all():
        raw_rows += 1
        if validator.validate_row(row):
            invalid += 1
            continue
        trades.append(normalizer.normalize_row(row))

    if raw_rows != EXPECTED_RAW_ROWS:
        raise AssertionError(f"raw row count mismatch: {raw_rows}")
    trades.sort(key=lambda t: (t.timestamp, t.sequence or -1))

    candles = TradeCandleAggregator(60).aggregate(trades)
    ema = EMACalculator(20).calculate(candles)
    vwap = VWAPCalculator(60).calculate(trades)
    ema_by_end = {(x.symbol, x.timestamp): x.value for x in ema}
    vwap_by_end = {(x.symbol, x.end): x.vwap for x in vwap}

    groups = {}
    for t in trades:
        epoch = int(t.timestamp.timestamp())
        bucket = epoch - epoch % 60
        groups.setdefault((t.symbol, bucket), []).append(t)

    pressure = {}
    candle_seq = {}
    for key, group in groups.items():
        buy = sum(t.quantity for t in group if t.side == "buy")
        sell = sum(t.quantity for t in group if t.side == "sell")
        total = buy + sell
        pressure[key] = (buy / total if total else 0.0, buy - sell)
        seqs = [t.sequence for t in group if t.sequence is not None]
        candle_seq[key] = max(seqs) if seqs else None

    strategy = BaselineStrategy(min_confirmations=3)
    risk = RiskPolicy()
    candidates = []
    for i in range(19, len(candles) - 1):
        candle = candles[i]
        nxt = candles[i + 1]
        if candle.symbol != nxt.symbol or nxt.start != candle.end:
            continue
        key = (candle.symbol, int(candle.start.timestamp()))
        buy_ratio, delta = pressure.get(key, (None, None))
        ema_value = ema_by_end.get((candle.symbol, candle.end))
        vwap_value = vwap_by_end.get((candle.symbol, candle.end))
        seq = candle_seq.get(key)
        if ema_value is None or vwap_value is None or buy_ratio is None:
            continue
        features = FeatureSnapshot(
            symbol=candle.symbol, timeframe_seconds=60, close=candle.close,
            ema=ema_value, vwap=vwap_value, buy_sell_delta=delta,
            buy_ratio=buy_ratio, timestamp=candle.end,
        )
        decision = strategy.evaluate(BaselineStrategyInput(features=features))
        risk_decision = risk.evaluate(RiskInput(decision=decision, equity=1000.0))
        if risk_decision is not RiskDecision.ALLOW_SIGNAL:
            continue
        gross = ((nxt.close - candle.close) / candle.close) * (
            1.0 if decision is BaselineDecision.LONG else -1.0
        )
        net_14bps = gross - 0.0014
        candidates.append({
            "observation_id": f"{candle.symbol}|{candle.end.isoformat()}",
            "fold": None,
            "sequence": seq,
            "feature_timestamp": candle.end.isoformat(),
            "outcome_timestamp": nxt.end.isoformat(),
            "buy_ratio": buy_ratio,
            "delta": delta,
            "trade_count": candle.trade_count,
            "decision": decision.value,
            "entry_price": candle.close,
            "outcome_price": nxt.close,
            "gross_return": gross,
            "net_return_14bps_round_trip": net_14bps,
            "boundary_label_14bps": "WINNER" if net_14bps > 0 else "CONTROL",
        })

    # Reconstruct the exact chronological observation stream, then assign
    # the frozen 8-fold test windows (800/400/400).
    # candidates correspond only to evaluated observations, while the fold
    # protocol operates over all 4,062 observations. Rebuild all observations
    # with the same eligibility rule to preserve exact fold boundaries.
    all_rows = []
    for i in range(19, len(candles) - 1):
        candle = candles[i]; nxt = candles[i + 1]
        if candle.symbol != nxt.symbol or nxt.start != candle.end:
            continue
        key=(candle.symbol,int(candle.start.timestamp()))
        br, delta=pressure.get(key,(None,None))
        ev=ema_by_end.get((candle.symbol,candle.end)); vw=vwap_by_end.get((candle.symbol,nxt.start))
        if ev is None or vw is None or br is None: continue
        features=FeatureSnapshot(symbol=candle.symbol,timeframe_seconds=60,close=candle.close,
                                 ema=ev,vwap=vw,buy_sell_delta=delta,buy_ratio=br,timestamp=candle.end)
        d=strategy.evaluate(BaselineStrategyInput(features=features))
        rd=risk.evaluate(RiskInput(decision=d,equity=1000.0))
        all_rows.append((candle,nxt,d,rd))

    # Sanity contract from the frozen audit.
    if len(all_rows) != 4062:
        raise AssertionError(f"chronological observation count mismatch: {len(all_rows)}")

    selected=[]
    start=0
    fold=0
    fold_counts=[]
    while fold < EXPECTED_FOLDS:
        train_end=start+800; test_start=train_end; test_end=test_start+400
        if test_end > len(all_rows): break
        fold_eval=0
        for idx in range(test_start,test_end):
            candle,nxt,d,rd=all_rows[idx]
            if rd is not RiskDecision.ALLOW_SIGNAL: continue
            gross=((nxt.close-candle.close)/candle.close)*(1.0 if d is BaselineDecision.LONG else -1.0)
            key=(candle.symbol,int(candle.start.timestamp()))
            br,delta=pressure[key]
            row={
                "observation_id":f"{candle.symbol}|{candle.end.isoformat()}",
                "fold":fold,
                "sequence":candle_seq[key],
                "feature_timestamp":candle.end.isoformat(),
                "outcome_timestamp":nxt.end.isoformat(),
                "buy_ratio":br,"delta":delta,"trade_count":candle.trade_count,
                "decision":d.value,"entry_price":candle.close,"outcome_price":nxt.close,
                "gross_return":gross,
                "net_return_14bps_round_trip":gross-0.0014,
                "boundary_label_14bps":"WINNER" if gross-0.0014>0 else "CONTROL",
            }
            selected.append(row); fold_eval += 1
        fold_counts.append(fold_eval)
        fold += 1; start += 400

    if fold != EXPECTED_FOLDS: raise AssertionError(f"fold count mismatch: {fold}")
    if fold_counts != EXPECTED_FOLD_EVALUATED:
        raise AssertionError(f"fold evaluated mismatch: {fold_counts}")
    if len(selected) != EXPECTED_EVALUATED:
        raise AssertionError(f"evaluated population mismatch: {len(selected)}")

    selected.sort(key=lambda r:(r["fold"],r["feature_timestamp"],r["sequence"] or -1))
    payload={
        "artifact":"HES Trade Agent — Exact 1,049 OOS Feature/Evaluation Snapshot v1",
        "status":"HASH_VERIFIED",
        "source_run_id":36489452534,
        "source_commit":"b8c4fe4fa054dbfa4fca17d2f307d269c16335e1",
        "source_blob_sha":SOURCE_SHA,
        "raw_rows":raw_rows,
        "invalid_rows":invalid,
        "chronological_observations":len(all_rows),
        "folds":EXPECTED_FOLDS,
        "fold_evaluated":fold_counts,
        "evaluated_oos":len(selected),
        "candidate_features":["Buy Ratio","Delta (Buy-Sell Delta)","Trade Count"],
        "rows":selected,
    }
    out=Path("evidence/exact_1049_feature_evaluation_snapshot_v1.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps({k:payload[k] for k in ["source_blob_sha","raw_rows","chronological_observations","folds","fold_evaluated","evaluated_oos"]},indent=2))


if __name__=="__main__":
    main()
