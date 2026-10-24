"""Train/evaluate a small causal Transformer from canonical OHLCV CSV only.

This is a reproducible research pipeline, not a profitability guarantee. It
refuses trade-tape CSVs and requires the operator to declare the upstream
global OHLCV source. Labels use future close returns; chronological splits are
purged by the forecast horizon and scaling is fitted on training rows only.
PyTorch is an optional runtime dependency installed by the dedicated workflow.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence


OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
FEATURE_NAMES = (
    "close_return",
    "candle_body",
    "candle_range",
    "upper_wick",
    "lower_wick",
    "log_volume_ratio",
)
CLASS_NAMES = ("SHORT", "NEUTRAL", "LONG")


@dataclass(frozen=True)
class OHLCVRow:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class PreparedData:
    timestamps: tuple[str, ...]
    features: tuple[tuple[float, ...], ...]
    labels: tuple[int, ...]
    target_indices: tuple[int, ...]
    source_sha256: str
    source_id: str
    interval: str
    neutral_band_bps: float
    horizon: int


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_positive(value: str, field: str, line: int, *, allow_zero: bool = False) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"line {line}: invalid {field}") from exc
    if not math.isfinite(parsed) or (parsed < 0 if allow_zero else parsed <= 0):
        raise ValueError(f"line {line}: invalid {field}")
    return parsed


def load_ohlcv_csv(path: str | Path, *, source_id: str, interval: str) -> tuple[OHLCVRow, ...]:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must explicitly identify the global OHLCV provider")
    if not isinstance(interval, str) or not interval.strip():
        raise ValueError("interval must be explicit")
    rows: list[OHLCVRow] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not set(OHLCV_COLUMNS).issubset(reader.fieldnames):
            raise ValueError("input must be canonical OHLCV CSV; trade-tape columns are not accepted")
        if {"price", "amount", "side", "sequence"}.issubset(reader.fieldnames):
            raise ValueError("trade-tape data is forbidden; provide global OHLCV candles")
        for line, item in enumerate(reader, start=2):
            stamp = item.get("timestamp", "")
            try:
                parsed_stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"line {line}: invalid timestamp") from exc
            if parsed_stamp.tzinfo is None or parsed_stamp.utcoffset() is None:
                raise ValueError(f"line {line}: timestamp must include timezone")
            row = OHLCVRow(
                timestamp=parsed_stamp.isoformat(),
                open=_finite_positive(item["open"], "open", line),
                high=_finite_positive(item["high"], "high", line),
                low=_finite_positive(item["low"], "low", line),
                close=_finite_positive(item["close"], "close", line),
                volume=_finite_positive(item["volume"], "volume", line, allow_zero=True),
            )
            if row.high < max(row.open, row.close, row.low) or row.low > min(row.open, row.close, row.high):
                raise ValueError(f"line {line}: OHLC bounds invalid")
            if rows and parsed_stamp <= datetime.fromisoformat(rows[-1].timestamp):
                raise ValueError(f"line {line}: timestamps must be strictly increasing")
            rows.append(row)
    if len(rows) < 50:
        raise ValueError(f"need at least 50 chronological OHLCV candles; got {len(rows)}")
    return tuple(rows)


def prepare_dataset(
    rows: Sequence[OHLCVRow],
    *,
    source_sha256: str,
    source_id: str,
    interval: str,
    horizon: int,
    neutral_band_bps: float,
    sequence_length: int,
) -> PreparedData:
    if type(horizon) is not int or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    if type(sequence_length) is not int or sequence_length < 8:
        raise ValueError("sequence_length must be an integer >= 8")
    if not math.isfinite(neutral_band_bps) or neutral_band_bps < 0:
        raise ValueError("neutral_band_bps must be finite and non-negative")
    if len(rows) <= sequence_length + horizon + 20:
        raise ValueError("insufficient candles for sequence, horizon, and chronological splits")

    features: list[tuple[float, ...]] = []
    for i, row in enumerate(rows):
        prev_close = rows[i - 1].close if i else row.close
        prev_volume = rows[i - 1].volume if i else row.volume
        scale = max(row.close, 1e-12)
        close_return = row.close / max(prev_close, 1e-12) - 1.0
        candle_range = (row.high - row.low) / scale
        body = (row.close - row.open) / scale
        upper_wick = (row.high - max(row.open, row.close)) / scale
        lower_wick = (min(row.open, row.close) - row.low) / scale
        volume_ratio = math.log((row.volume + 1e-12) / (prev_volume + 1e-12))
        vector = (close_return, body, candle_range, upper_wick, lower_wick, volume_ratio)
        if not all(math.isfinite(v) for v in vector):
            raise ValueError(f"non-finite features at row {i}")
        features.append(vector)

    band = neutral_band_bps / 10_000.0
    sample_labels: list[int] = []
    sample_indices: list[int] = []
    for target_index in range(sequence_length - 1, len(rows) - horizon):
        future_return = rows[target_index + horizon].close / rows[target_index].close - 1.0
        # SHORT=0, NEUTRAL=1, LONG=2. Labels are defined before model fitting.
        label = 0 if future_return < -band else (2 if future_return > band else 1)
        sample_labels.append(label)
        sample_indices.append(target_index)
    return PreparedData(
        timestamps=tuple(row.timestamp for row in rows),
        features=tuple(features),
        labels=tuple(sample_labels),
        target_indices=tuple(sample_indices),
        source_sha256=source_sha256,
        source_id=source_id,
        interval=interval,
        neutral_band_bps=neutral_band_bps,
        horizon=horizon,
    )


def chronological_splits(data: PreparedData, *, train_fraction: float = 0.70, validation_fraction: float = 0.15) -> dict[str, tuple[int, ...]]:
    if not (0.50 <= train_fraction <= 0.85 and 0.05 <= validation_fraction <= 0.25
            and train_fraction + validation_fraction < 1.0):
        raise ValueError("invalid chronological split fractions")
    count = len(data.target_indices)
    train_cut = int(len(data.timestamps) * train_fraction)
    validation_cut = int(len(data.timestamps) * (train_fraction + validation_fraction))
    # A sample belongs to a split only when its complete label horizon ends
    # before that split's boundary. This purges boundary labels from leakage.
    train = tuple(i for i, t in enumerate(data.target_indices) if t + data.horizon < train_cut)
    validation = tuple(i for i, t in enumerate(data.target_indices) if train_cut <= t and t + data.horizon < validation_cut)
    test = tuple(i for i, t in enumerate(data.target_indices) if t >= validation_cut)
    if min(len(train), len(validation), len(test)) < 10:
        raise ValueError("insufficient samples in one or more purged chronological splits")
    if data.target_indices[train[-1]] + data.horizon >= data.target_indices[validation[0]]:
        raise ValueError("training/validation target windows overlap")
    if data.target_indices[validation[-1]] + data.horizon >= data.target_indices[test[0]]:
        raise ValueError("validation/test target windows overlap")
    return {"train": train, "validation": validation, "test": test}


def _torch_components():
    try:
        import torch
        from torch import nn
    except ImportError as exc:
        raise RuntimeError("PyTorch is required only for training/inference; install a supported torch build") from exc

    class CausalTransformer(nn.Module):
        def __init__(self, feature_count: int, d_model: int = 24, heads: int = 4, layers: int = 2):
            super().__init__()
            self.input_projection = nn.Linear(feature_count, d_model)
            layer = nn.TransformerEncoderLayer(
                d_model=d_model, nhead=heads, dim_feedforward=48, dropout=0.1,
                batch_first=True, norm_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=layers, enable_nested_tensor=False)
            self.output = nn.Sequential(nn.LayerNorm(d_model), nn.Linear(d_model, 3))

        def forward(self, x):
            x = self.input_projection(x)
            length = x.shape[1]
            # Upper triangular mask prevents every position seeing future tokens.
            mask = torch.triu(torch.ones(length, length, device=x.device, dtype=torch.bool), diagonal=1)
            encoded = self.encoder(x, mask=mask)
            return self.output(encoded[:, -1, :])

    return torch, CausalTransformer


def train_and_evaluate(
    data: PreparedData,
    *,
    sequence_length: int,
    output_dir: str | Path,
    epochs: int = 20,
    batch_size: int = 64,
    seed: int = 17,
) -> dict:
    if type(epochs) is not int or not 1 <= epochs <= 300:
        raise ValueError("epochs must be between 1 and 300")
    if type(batch_size) is not int or not 1 <= batch_size <= 2048:
        raise ValueError("batch_size must be between 1 and 2048")
    torch, CausalTransformer = _torch_components()
    torch.manual_seed(seed)
    splits = chronological_splits(data)
    train_ids = splits["train"]
    val_ids = splits["validation"]
    test_ids = splits["test"]

    # Fit normalization exclusively on unique candle rows before the train cut.
    train_cut = max(data.target_indices[i] for i in train_ids) + 1
    train_rows = data.features[:train_cut]
    mean = [sum(row[j] for row in train_rows) / len(train_rows) for j in range(len(FEATURE_NAMES))]
    scale = []
    for j, mu in enumerate(mean):
        variance = sum((row[j] - mu) ** 2 for row in train_rows) / len(train_rows)
        scale.append(max(math.sqrt(variance), 1e-8))

    def make_batch(sample_ids):
        x = []
        y = []
        for sample_id in sample_ids:
            end = data.target_indices[sample_id]
            window = data.features[end - sequence_length + 1:end + 1]
            x.append([[(v - mean[j]) / scale[j] for j, v in enumerate(row)] for row in window])
            y.append(data.labels[sample_id])
        return torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.long)

    x_train, y_train = make_batch(train_ids)
    x_val, y_val = make_batch(val_ids)
    x_test, y_test = make_batch(test_ids)
    model = CausalTransformer(len(FEATURE_NAMES))
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=0.01)
    criterion = torch.nn.CrossEntropyLoss()
    best_state = None
    best_val_loss = float("inf")
    for _ in range(epochs):
        model.train()
        order = torch.randperm(len(x_train))
        for start in range(0, len(order), batch_size):
            ids = order[start:start + batch_size]
            optimizer.zero_grad(set_to_none=True)
            loss = criterion(model(x_train[ids]), y_train[ids])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        model.eval()
        with torch.no_grad():
            val_loss = float(criterion(model(x_val), y_val).item())
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
    if best_state is None:
        raise RuntimeError("training did not produce a checkpoint")
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        logits = model(x_test)
        probs = torch.softmax(logits, dim=1)
        predictions = probs.argmax(dim=1)
        accuracy = float((predictions == y_test).float().mean().item())
        class_metrics = {}
        for class_index, name in enumerate(CLASS_NAMES):
            selected = y_test == class_index
            class_metrics[name] = {
                "support": int(selected.sum().item()),
                "recall": float(((predictions == class_index) & selected).sum().item() / max(int(selected.sum().item()), 1)),
            }
        # Expected calibration error, ten equal-width confidence bins.
        confidence, _ = probs.max(dim=1)
        ece = 0.0
        for lower in [i / 10 for i in range(10)]:
            upper = lower + 0.1
            mask = (confidence >= lower) & ((confidence < upper) if upper < 1 else (confidence <= upper))
            count = int(mask.sum().item())
            if count:
                accuracy_bin = float((predictions[mask] == y_test[mask]).float().mean().item())
                confidence_bin = float(confidence[mask].mean().item())
                ece += count / len(y_test) * abs(accuracy_bin - confidence_bin)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    model_path = out / "transformer_candidate.pt"
    torch.save({
        "state_dict": model.state_dict(),
        "feature_names": list(FEATURE_NAMES),
        "class_names": list(CLASS_NAMES),
        "sequence_length": sequence_length,
        "d_model": 24,
        "heads": 4,
        "layers": 2,
        "normalization_mean": mean,
        "normalization_scale": scale,
        "model_version": "hes-transformer-candidate-v1",
        "feature_schema_version": "ohlcv-sequence-features-v1",
    }, model_path)
    model_sha = sha256_file(model_path)
    manifest = {
        "status": "RESEARCH_CANDIDATE_NOT_PROMOTED",
        "model_version": "hes-transformer-candidate-v1",
        "model_sha256": model_sha,
        "source_id": data.source_id,
        "source_sha256": data.source_sha256,
        "interval": data.interval,
        "rows": len(data.timestamps),
        "samples": len(data.target_indices),
        "sequence_length": sequence_length,
        "forecast_horizon_candles": data.horizon,
        "neutral_band_bps": data.neutral_band_bps,
        "label_map": {"SHORT": 0, "NEUTRAL": 1, "LONG": 2},
        "feature_names": list(FEATURE_NAMES),
        "splits": {name: len(ids) for name, ids in splits.items()},
        "split_boundaries": {
            "train_last_feature_timestamp": data.timestamps[train_cut - 1],
            "validation_first_sample_timestamp": data.timestamps[data.target_indices[val_ids[0]]],
            "test_first_sample_timestamp": data.timestamps[data.target_indices[test_ids[0]]],
        },
        "metrics": {
            "test_accuracy": accuracy,
            "test_expected_calibration_error_10_bins": ece,
            "test_class_metrics": class_metrics,
            "best_validation_cross_entropy": best_val_loss,
        },
        "seed": seed,
        "epochs_max": epochs,
        "no_trade_or_execution": True,
        "promotion_decision": "HOLD",
    }
    manifest_path = out / "transformer_training_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_sha256"] = sha256_file(manifest_path)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="CSV exported from the canonical global OHLCV provider")
    parser.add_argument("--source-id", required=True, help="explicit provider/dataset identifier")
    parser.add_argument("--interval", required=True, help="candle interval, e.g. 15m")
    parser.add_argument("--horizon", type=int, required=True, help="forecast horizon in candles")
    parser.add_argument("--neutral-band-bps", type=float, required=True, help="neutral label band in basis points; must be selected from fee/slippage policy")
    parser.add_argument("--sequence-length", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--output-dir", default="artifacts/transformer-candidate")
    args = parser.parse_args(argv)
    rows = load_ohlcv_csv(args.input, source_id=args.source_id, interval=args.interval)
    data = prepare_dataset(
        rows, source_sha256=sha256_file(args.input), source_id=args.source_id,
        interval=args.interval, horizon=args.horizon,
        neutral_band_bps=args.neutral_band_bps, sequence_length=args.sequence_length,
    )
    manifest = train_and_evaluate(
        data, sequence_length=args.sequence_length, output_dir=args.output_dir, epochs=args.epochs,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
