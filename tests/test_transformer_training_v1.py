from datetime import datetime, timedelta, timezone
import csv
import json

import pytest

from forward.transformer_training_v1 import (
    FEATURE_NAMES,
    OHLCVRow,
    chronological_splits,
    load_ohlcv_csv,
    prepare_dataset,
    train_and_evaluate,
)
from forward.transformer_torch_adapter_v1 import TorchCheckpointPredictor
from forward.transformer_agent_v1 import evaluate_transformer_v1


def synthetic_rows(count=180):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    price = 100.0
    for i in range(count):
        previous = price
        price *= 1.0 + (0.001 if (i // 7) % 2 == 0 else -0.0007)
        high = max(previous, price) * 1.002
        low = min(previous, price) * 0.998
        rows.append(OHLCVRow(
            timestamp=(start + timedelta(minutes=15 * i)).isoformat(),
            open=previous, high=high, low=low, close=price, volume=100.0 + (i % 11),
        ))
    return tuple(rows)


def make_data(rows=None):
    rows = rows or synthetic_rows()
    return prepare_dataset(
        rows,
        source_sha256="a" * 64,
        source_id="synthetic-test-fixture-not-market-evidence",
        interval="15m",
        horizon=3,
        neutral_band_bps=5.0,
        sequence_length=16,
    )


def test_trade_tape_csv_is_rejected(tmp_path):
    path = tmp_path / "trades.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "price", "amount", "side", "sequence", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerow({"timestamp":"2026-01-01T00:00:00+00:00","price":100,"amount":1,"side":"buy","sequence":1,"open":100,"high":101,"low":99,"close":100,"volume":1})
    with pytest.raises(ValueError, match="trade-tape"):
        load_ohlcv_csv(path, source_id="provider", interval="15m")


def test_dataset_has_explicit_three_class_labels_and_purged_chronological_splits():
    data = make_data()
    assert set(data.labels).issubset({0, 1, 2})
    assert len(data.features[0]) == len(FEATURE_NAMES)
    splits = chronological_splits(data)
    train_last = data.target_indices[splits["train"][-1]]
    val_first = data.target_indices[splits["validation"][0]]
    val_last = data.target_indices[splits["validation"][-1]]
    test_first = data.target_indices[splits["test"][0]]
    assert train_last + data.horizon < val_first
    assert val_last + data.horizon < test_first


def test_training_artifact_loads_and_emits_probabilities_for_existing_contract(tmp_path):
    pytest.importorskip("torch")
    data = make_data()
    manifest = train_and_evaluate(data, sequence_length=16, output_dir=tmp_path, epochs=1, batch_size=32, round_trip_cost_bps=10.0)
    assert manifest["status"] == "RESEARCH_CANDIDATE_NOT_PROMOTED"
    assert manifest["promotion_decision"] == "HOLD"
    assert manifest["source_id"] == "synthetic-test-fixture-not-market-evidence"
    assert manifest["model_sha256"]
    saved = json.loads((tmp_path / "transformer_training_manifest.json").read_text())
    assert saved["metrics"]["test_accuracy"] >= 0.0
    assert saved["strategy_backtest"]["status"] == "RESEARCH_ONLY_NOT_PROMOTED"
    assert saved["strategy_backtest"]["round_trip_cost_bps"] == 10.0
    assert "max_drawdown_fraction" in saved["strategy_backtest"]

    predictor = TorchCheckpointPredictor(
        tmp_path / "transformer_candidate.pt",
        expected_sha256=manifest["model_sha256"],
    )
    last_end = data.target_indices[-1]
    rows = data.features[last_end - 15:last_end + 1]
    timestamps = data.timestamps[last_end - 15:last_end + 1]
    result = evaluate_transformer_v1(
        rows=rows,
        feature_names=FEATURE_NAMES,
        timestamps=timestamps,
        observation_time=timestamps[-1],
        source_sha256=data.source_sha256,
        model_sha256=manifest["model_sha256"],
        model_version=predictor.model_version,
        feature_schema_version=predictor.feature_schema_version,
        predictor=predictor,
        minimum_rows=16,
        minimum_confidence=0.0,
        max_age_seconds=60 * 60,
    )
    assert result.status in {"EVIDENCE_ONLY", "ABSTAIN"}
    assert result.direction in {"LONG", "SHORT", "UNKNOWN"}
    assert result.evidence.get("sequence_sha256")


def test_ohlcv_csv_rejects_missing_candle_interval(tmp_path):
    rows = synthetic_rows(70)
    path = tmp_path / "gapped.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for index, row in enumerate(rows):
            stamp = datetime.fromisoformat(row.timestamp)
            if index >= 30:
                stamp += timedelta(minutes=15)
            writer.writerow({
                "timestamp": stamp.isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            })
    with pytest.raises(ValueError, match="candle gap/overlap"):
        load_ohlcv_csv(path, source_id="synthetic-test", interval="15m")


def test_ohlcv_csv_rejects_timestamps_not_aligned_to_candle_interval(tmp_path):
    rows = synthetic_rows(70)
    path = tmp_path / "misaligned.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for row in rows:
            stamp = datetime.fromisoformat(row.timestamp) + timedelta(minutes=1)
            writer.writerow({
                "timestamp": stamp.isoformat(),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
            })
    with pytest.raises(ValueError, match="not aligned"):
        load_ohlcv_csv(path, source_id="synthetic-test", interval="15m")


def test_strategy_backtest_rejects_invalid_cost_policy():
    data = make_data()
    with pytest.raises(ValueError, match="round_trip_cost_bps"):
        train_and_evaluate(data, sequence_length=16, output_dir="unused-test-output", epochs=1, round_trip_cost_bps=-1.0)
