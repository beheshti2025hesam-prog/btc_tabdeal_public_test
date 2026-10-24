"""Verified PyTorch checkpoint adapter for Transformer Agent v1."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .transformer_training_v1 import FEATURE_NAMES, CLASS_NAMES, _torch_components


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class TorchCheckpointPredictor:
    """Load a locally verified research checkpoint and expose the contract API.

    The caller must still pass the same artifact hash/version into
    evaluate_transformer_v1; this adapter never promotes or executes trades.
    """

    def __init__(self, checkpoint_path: str | Path, *, expected_sha256: str):
        self.path = Path(checkpoint_path)
        actual_sha = sha256_file(self.path)
        if not isinstance(expected_sha256, str) or actual_sha != expected_sha256.lower():
            raise ValueError("MODEL_ARTIFACT_HASH_MISMATCH")
        torch, Transformer = _torch_components()
        try:
            checkpoint = torch.load(self.path, map_location="cpu", weights_only=True)
        except TypeError:
            # Older torch versions do not accept weights_only. The checkpoint
            # must only be loaded from a trusted local artifact.
            checkpoint = torch.load(self.path, map_location="cpu")
        required = {
            "state_dict", "feature_names", "class_names", "sequence_length",
            "d_model", "heads", "layers", "normalization_mean",
            "normalization_scale", "model_version", "feature_schema_version",
        }
        if not isinstance(checkpoint, dict) or not required.issubset(checkpoint):
            raise ValueError("MODEL_CHECKPOINT_SCHEMA_INVALID")
        if checkpoint["feature_names"] != list(FEATURE_NAMES) or checkpoint["class_names"] != list(CLASS_NAMES):
            raise ValueError("MODEL_FEATURE_OR_CLASS_SCHEMA_MISMATCH")
        if checkpoint["feature_schema_version"] != "ohlcv-sequence-features-v1":
            raise ValueError("MODEL_FEATURE_SCHEMA_VERSION_MISMATCH")
        self.sequence_length = checkpoint["sequence_length"]
        if type(self.sequence_length) is not int or self.sequence_length < 8:
            raise ValueError("MODEL_SEQUENCE_LENGTH_INVALID")
        self.mean = checkpoint["normalization_mean"]
        self.scale = checkpoint["normalization_scale"]
        if len(self.mean) != len(FEATURE_NAMES) or len(self.scale) != len(FEATURE_NAMES):
            raise ValueError("MODEL_NORMALIZATION_SCHEMA_INVALID")
        if any(not math.isfinite(float(x)) for x in self.mean) or any(
            not math.isfinite(float(x)) or float(x) <= 0 for x in self.scale
        ):
            raise ValueError("MODEL_NORMALIZATION_VALUES_INVALID")
        self.model_version = checkpoint["model_version"]
        self.feature_schema_version = checkpoint["feature_schema_version"]
        self.model = Transformer(
            feature_count=len(FEATURE_NAMES),
            d_model=checkpoint["d_model"],
            heads=checkpoint["heads"],
            layers=checkpoint["layers"],
        )
        self.model.load_state_dict(checkpoint["state_dict"], strict=True)
        self.model.eval()
        self.torch = torch
        self.artifact_sha256 = actual_sha

    def predict(self, rows: Sequence[Sequence[float]]) -> Mapping[str, Any]:
        if len(rows) != self.sequence_length:
            raise ValueError("MODEL_SEQUENCE_LENGTH_MISMATCH")
        if any(len(row) != len(FEATURE_NAMES) for row in rows):
            raise ValueError("MODEL_FEATURE_WIDTH_MISMATCH")
        normalized = [
            [(float(value) - float(self.mean[j])) / float(self.scale[j]) for j, value in enumerate(row)]
            for row in rows
        ]
        if any(not math.isfinite(value) for row in normalized for value in row):
            raise ValueError("MODEL_INPUT_NONFINITE")
        tensor = self.torch.tensor([normalized], dtype=self.torch.float32)
        with self.torch.no_grad():
            probabilities = self.torch.softmax(self.model(tensor), dim=1)[0].tolist()
        return {"probabilities": dict(zip(CLASS_NAMES, probabilities))}
