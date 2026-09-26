"""HES Trade Agent - Feature/Input temporal alignment contract v1.

Deterministic safety boundary between Data Intelligence outputs and downstream
Feature Engine snapshots. This contract validates temporal/window alignment
and provenance metadata; it does not create or rank trading signals.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FeatureTemporalInput:
    symbol: str
    timeframe_seconds: int
    window_start: datetime
    window_end: datetime
    feature_timestamp: datetime
    source: str
    source_timestamp: datetime | None = None


class FeatureTemporalAlignment:
    """Validate one feature input against its source candle/window."""

    def validate(self, item: FeatureTemporalInput) -> tuple[str, ...]:
        violations: list[str] = []

        if not item.symbol:
            violations.append("missing_symbol")
        if item.timeframe_seconds <= 0:
            violations.append("invalid_timeframe")

        timestamps = (
            ("window_start", item.window_start),
            ("window_end", item.window_end),
            ("feature_timestamp", item.feature_timestamp),
        )
        for name, value in timestamps:
            if value.tzinfo is None or value.utcoffset() is None:
                violations.append(f"invalid_{name}")

        if not item.source:
            violations.append("missing_source")
        elif item.source_timestamp is not None and (
            item.source_timestamp.tzinfo is None
            or item.source_timestamp.utcoffset() is None
        ):
            violations.append("invalid_source_timestamp")

        if not violations:
            duration = (item.window_end - item.window_start).total_seconds()
            if duration != item.timeframe_seconds:
                violations.append("window_duration_mismatch")
            if item.window_end <= item.window_start:
                violations.append("invalid_window_order")
            if item.feature_timestamp != item.window_end:
                violations.append("feature_timestamp_mismatch")

            if item.source_timestamp is not None:
                if item.source_timestamp > item.feature_timestamp:
                    violations.append("source_timestamp_in_future")

        return tuple(violations)

    def check(self, item: FeatureTemporalInput) -> bool:
        return not self.validate(item)
