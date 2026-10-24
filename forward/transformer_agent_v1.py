"""Fail-closed, model-agnostic Transformer Agent inference boundary.

This module does not implement a Transformer architecture or train a model.
It adapts an already-trained model behind a small predictor protocol, validates
causal sequence/provenance, and emits evidence for downstream evaluation.
It never emits an executable trade order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from typing import Any, Mapping, Protocol, Sequence


AGENT_VERSION = "hes-transformer-agent-v1"
SUPPORTED_DIRECTIONS = {"LONG", "SHORT", "NEUTRAL"}


class SequencePredictor(Protocol):
    """Adapter contract for an existing trained model/runtime."""

    def predict(self, rows: Sequence[Sequence[float]]) -> Mapping[str, Any]:
        """Return {'probabilities': {'LONG': p, 'SHORT': p, 'NEUTRAL': p}}."""


@dataclass(frozen=True)
class TransformerResultV1:
    status: str
    direction: str
    confidence: float | None
    probabilities: Mapping[str, float] | None
    reasons: tuple[str, ...]
    evidence: Mapping[str, Any]


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def evaluate_transformer_v1(
    *,
    rows: Sequence[Sequence[float]],
    feature_names: Sequence[str],
    timestamps: Sequence[str],
    observation_time: str,
    source_sha256: str,
    model_sha256: str,
    model_version: str,
    feature_schema_version: str,
    predictor: SequencePredictor,
    minimum_rows: int = 32,
    minimum_confidence: float = 0.60,
    max_age_seconds: int = 900,
) -> TransformerResultV1:
    """Validate a causal window and adapt inference output to evidence-only result."""
    reasons: list[str] = []
    obs = _aware(observation_time)
    if obs is None:
        reasons.append("OBSERVATION_TIME_INVALID")
    if not isinstance(source_sha256, str) or len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256.lower()):
        reasons.append("SOURCE_HASH_INVALID")
    if not isinstance(model_sha256, str) or len(model_sha256) != 64 or any(c not in "0123456789abcdef" for c in model_sha256.lower()):
        reasons.append("MODEL_HASH_INVALID")
    if not isinstance(model_version, str) or not model_version.strip():
        reasons.append("MODEL_VERSION_MISSING")
    if not isinstance(feature_schema_version, str) or not feature_schema_version.strip():
        reasons.append("FEATURE_SCHEMA_VERSION_MISSING")
    if not isinstance(feature_names, Sequence) or isinstance(feature_names, (str, bytes)) or not feature_names:
        reasons.append("FEATURE_NAMES_MISSING")
    elif any(not isinstance(name, str) or not name.strip() for name in feature_names) or len(set(feature_names)) != len(feature_names):
        reasons.append("FEATURE_NAMES_INVALID")
    rows_valid = isinstance(rows, Sequence) and not isinstance(rows, (str, bytes))
    rows_len = len(rows) if rows_valid else 0
    min_rows_valid = isinstance(minimum_rows, int) and not isinstance(minimum_rows, bool) and minimum_rows >= 1
    max_age_valid = isinstance(max_age_seconds, int) and not isinstance(max_age_seconds, bool) and max_age_seconds >= 0
    confidence_valid = (
        isinstance(minimum_confidence, (int, float))
        and not isinstance(minimum_confidence, bool)
        and math.isfinite(minimum_confidence)
        and 0.0 <= minimum_confidence <= 1.0
    )
    if not min_rows_valid:
        reasons.append("MINIMUM_ROWS_INVALID")
    if not max_age_valid:
        reasons.append("MAX_AGE_INVALID")
    if not confidence_valid:
        reasons.append("CONFIDENCE_THRESHOLD_INVALID")
    if not rows_valid or (min_rows_valid and rows_len < minimum_rows):
        reasons.append("SEQUENCE_TOO_SHORT")
    timestamps_valid = isinstance(timestamps, Sequence) and not isinstance(timestamps, (str, bytes))
    if not timestamps_valid or len(timestamps) != rows_len:
        reasons.append("TIMESTAMP_ROW_COUNT_MISMATCH")
    elif obs is not None:
        parsed = [_aware(t) for t in timestamps]
        if any(t is None for t in parsed):
            reasons.append("TIMESTAMP_INVALID")
        else:
            valid = [t for t in parsed if t is not None]
            if any(valid[i] >= valid[i + 1] for i in range(len(valid) - 1)):
                reasons.append("TIMESTAMPS_NOT_STRICTLY_INCREASING")
            if valid and valid[-1] > obs:
                reasons.append("LOOKAHEAD_TIMESTAMP")
            if valid and max_age_valid and (obs - valid[-1]).total_seconds() > max_age_seconds:
                reasons.append("SEQUENCE_STALE")

    width = len(feature_names) if isinstance(feature_names, Sequence) and not isinstance(feature_names, (str, bytes)) else 0
    if not reasons:
        for row in rows:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes)) or len(row) != width:
                reasons.append("FEATURE_ROW_SHAPE_INVALID")
                break
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)) for v in row):
                reasons.append("FEATURE_VALUE_NONFINITE_OR_NONNUMERIC")
                break

    base_evidence = {
        "agent_version": AGENT_VERSION,
        "model_version": model_version if isinstance(model_version, str) else None,
        "model_sha256": model_sha256 if isinstance(model_sha256, str) else None,
        "feature_schema_version": feature_schema_version if isinstance(feature_schema_version, str) else None,
        "source_sha256": source_sha256 if isinstance(source_sha256, str) else None,
        "observation_time": observation_time if isinstance(observation_time, str) else None,
        "sequence_rows": len(rows) if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)) else None,
        "feature_names": list(feature_names) if isinstance(feature_names, Sequence) and not isinstance(feature_names, (str, bytes)) else None,
    }
    if reasons:
        return TransformerResultV1("ABSTAIN", "UNKNOWN", None, None, tuple(dict.fromkeys(reasons)), base_evidence)

    try:
        raw = predictor.predict(rows)
        probs_raw = raw.get("probabilities") if isinstance(raw, Mapping) else None
        if not isinstance(probs_raw, Mapping) or set(probs_raw.keys()) != SUPPORTED_DIRECTIONS:
            raise ValueError("PROBABILITY_SCHEMA_INVALID")
        if any(isinstance(probs_raw[key], bool) for key in SUPPORTED_DIRECTIONS):
            raise ValueError("PROBABILITY_VALUE_INVALID")
        if any(
            isinstance(probs_raw[key], bool)
            or not isinstance(probs_raw[key], (int, float))
            for key in SUPPORTED_DIRECTIONS
        ):
            raise ValueError("PROBABILITY_VALUE_INVALID")
        probs = {key: float(probs_raw[key]) for key in SUPPORTED_DIRECTIONS}
        if any(not math.isfinite(p) or p < 0.0 or p > 1.0 for p in probs.values()):
            raise ValueError("PROBABILITY_VALUE_INVALID")
        if abs(sum(probs.values()) - 1.0) > 1e-6:
            raise ValueError("PROBABILITIES_NOT_NORMALIZED")
    except Exception as exc:
        reason = str(exc) if str(exc).startswith("PROBABILITY_") or str(exc) == "PROBABILITIES_NOT_NORMALIZED" else "MODEL_INFERENCE_FAILED"
        return TransformerResultV1("ABSTAIN", "UNKNOWN", None, None, (reason,), base_evidence)

    direction = max(probs, key=probs.get)
    confidence = probs[direction]
    evidence = dict(base_evidence)
    evidence["sequence_sha256"] = _digest({"timestamps": list(timestamps), "rows": [list(row) for row in rows]})
    evidence["probabilities"] = probs
    evidence["inference_mode"] = "INJECTED_MODEL_ADAPTER"
    if direction == "NEUTRAL" or confidence < minimum_confidence:
        return TransformerResultV1("ABSTAIN", "UNKNOWN", confidence, probs, ("CONFIDENCE_BELOW_POLICY_OR_NEUTRAL",), evidence)
    return TransformerResultV1("EVIDENCE_ONLY", direction, confidence, probs, (), evidence)
