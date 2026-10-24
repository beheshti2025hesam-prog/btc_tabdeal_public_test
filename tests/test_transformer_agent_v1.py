from datetime import datetime, timedelta, timezone

from forward.transformer_agent_v1 import evaluate_transformer_v1


class Predictor:
    def __init__(self, probabilities=None, error=None):
        self.probabilities = probabilities or {"LONG": 0.72, "SHORT": 0.18, "NEUTRAL": 0.10}
        self.error = error

    def predict(self, rows):
        if self.error:
            raise RuntimeError(self.error)
        return {"probabilities": self.probabilities}


def sample(**overrides):
    end = datetime(2026, 10, 24, 10, 32, tzinfo=timezone.utc)
    rows = [[float(i), float(i + 1)] for i in range(32)]
    timestamps = [(end - timedelta(minutes=32 - i)).isoformat() for i in range(32)]
    args = dict(
        rows=rows,
        feature_names=["return_1", "volume_z"],
        timestamps=timestamps,
        observation_time=end.isoformat(),
        source_sha256="a" * 64,
        model_sha256="b" * 64,
        model_version="transformer-candidate-001",
        feature_schema_version="features-v1",
        predictor=Predictor(),
    )
    args.update(overrides)
    return args


def test_valid_model_output_is_evidence_only_and_has_lineage():
    result = evaluate_transformer_v1(**sample())
    assert result.status == "EVIDENCE_ONLY"
    assert result.direction == "LONG"
    assert result.confidence == 0.72
    assert len(result.evidence["sequence_sha256"]) == 64
    assert result.evidence["model_sha256"] == "b" * 64


def test_short_window_abstains_before_inference():
    args = sample(rows=[[1.0, 2.0]], timestamps=["2026-10-24T10:31:00+00:00"])
    result = evaluate_transformer_v1(**args)
    assert result.status == "ABSTAIN"
    assert "SEQUENCE_TOO_SHORT" in result.reasons


def test_future_timestamp_is_rejected_as_lookahead():
    args = sample(timestamps=[*(sample()["timestamps"][:-1]), "2026-10-24T10:33:00+00:00"])
    result = evaluate_transformer_v1(**args)
    assert result.status == "ABSTAIN"
    assert "LOOKAHEAD_TIMESTAMP" in result.reasons


def test_nonmonotonic_or_duplicate_timestamps_are_rejected():
    ts = sample()["timestamps"]
    ts[5] = ts[4]
    result = evaluate_transformer_v1(**sample(timestamps=ts))
    assert result.status == "ABSTAIN"
    assert "TIMESTAMPS_NOT_STRICTLY_INCREASING" in result.reasons


def test_stale_sequence_is_rejected():
    args = sample(observation_time="2026-10-24T12:00:00+00:00")
    result = evaluate_transformer_v1(**args)
    assert result.status == "ABSTAIN"
    assert "SEQUENCE_STALE" in result.reasons


def test_bad_feature_shape_or_nonfinite_values_are_rejected():
    rows = sample()["rows"]
    rows[4] = [float("nan"), 1.0]
    result = evaluate_transformer_v1(**sample(rows=rows))
    assert result.status == "ABSTAIN"
    assert "FEATURE_VALUE_NONFINITE_OR_NONNUMERIC" in result.reasons


def test_bad_hash_or_missing_model_metadata_abstains():
    result = evaluate_transformer_v1(**sample(model_sha256="bad", model_version=""))
    assert result.status == "ABSTAIN"
    assert "MODEL_HASH_INVALID" in result.reasons
    assert "MODEL_VERSION_MISSING" in result.reasons


def test_malformed_probabilities_abstain():
    predictor = Predictor({"LONG": 0.8, "SHORT": 0.8, "NEUTRAL": 0.1})
    result = evaluate_transformer_v1(**sample(predictor=predictor))
    assert result.status == "ABSTAIN"
    assert "PROBABILITIES_NOT_NORMALIZED" in result.reasons


def test_neutral_or_low_confidence_never_becomes_directional_signal():
    predictor = Predictor({"LONG": 0.45, "SHORT": 0.35, "NEUTRAL": 0.20})
    result = evaluate_transformer_v1(**sample(predictor=predictor, minimum_confidence=0.60))
    assert result.status == "ABSTAIN"
    assert result.direction == "UNKNOWN"


def test_model_runtime_failure_abstains():
    result = evaluate_transformer_v1(**sample(predictor=Predictor(error="runtime unavailable")))
    assert result.status == "ABSTAIN"
    assert result.direction == "UNKNOWN"
    assert "MODEL_INFERENCE_FAILED" in result.reasons


def test_invalid_configuration_fails_closed_without_type_error():
    result = evaluate_transformer_v1(**sample(minimum_rows="32", max_age_seconds=-1))
    assert result.status == "ABSTAIN"
    assert "MINIMUM_ROWS_INVALID" in result.reasons
    assert "MAX_AGE_INVALID" in result.reasons


def test_non_sequence_rows_fail_closed_without_type_error():
    result = evaluate_transformer_v1(**sample(rows=7, timestamps=[]))
    assert result.status == "ABSTAIN"
    assert result.direction == "UNKNOWN"


def test_boolean_probabilities_are_not_accepted_as_numeric_scores():
    predictor = Predictor({"LONG": True, "SHORT": 0.0, "NEUTRAL": 0.0})
    result = evaluate_transformer_v1(**sample(predictor=predictor))
    assert result.status == "ABSTAIN"
    assert result.direction == "UNKNOWN"
