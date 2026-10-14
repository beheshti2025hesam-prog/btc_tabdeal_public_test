"""Fail-closed boundary from fresh Tabdeal trades to closed 15m candles."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable

from .candle_normalizer_v1 import Candle15m, IntervalGap
from .forward_tabdeal_ingestion_v1 import ingest_closed_candles
from .sequence_integrity_v1 import SequenceEvent, SequenceIntegrityV1


class SequenceCandleResult:
    def __init__(
        self,
        candles: tuple[Candle15m, ...],
        gaps: tuple[IntervalGap, ...],
        events: tuple[SequenceEvent, ...],
    ) -> None:
        self.candles = candles
        self.gaps = gaps
        self.events = events

    @property
    def safe_for_decision(self) -> bool:
        return not any(
            event.status in {"REJECT_STREAM", "ANOMALY"} for event in self.events
        )


class SequenceAwareCandleIngestionV1:
    """Sequence-check first; only capability-authorized records reach candles.

    The current Tabdeal broadcast contract does not establish sequence
    uniqueness or ordering. Records explicitly marked UNKNOWN_OPAQUE must not
    enter the integer sequence state machine or candle/evidence path.
    """

    def __init__(self, *, max_sequence_records: int = 100_000) -> None:
        self.sequence = SequenceIntegrityV1(max_records=max_sequence_records)

    def ingest(
        self,
        records: Iterable[dict[str, Any]],
        *,
        as_of: datetime,
    ) -> SequenceCandleResult:
        safe: list[dict[str, Any]] = []
        events: list[SequenceEvent] = []

        for record in records:
            # Only an explicit, registry-backed verification marker may reach
            # the integer sequence state machine. Missing and opaque semantics
            # are equally unknown; numeric appearance is not evidence.
            if record.get("sequence_semantics") != "VERIFIED_MONOTONIC":
                raw = record.get("raw_payload")
                digest = record.get("raw_payload_sha256")
                if raw is not None:
                    raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
                    calculated = hashlib.sha256(raw_bytes).hexdigest()
                    if digest != calculated:
                        events.append(SequenceEvent(
                            -1, "REJECT_STREAM", "RAW_PAYLOAD_DIGEST_MISMATCH",
                            {"expected": digest, "calculated": calculated},
                        ))
                        return SequenceCandleResult((), (), tuple(events))
                fingerprint = hashlib.sha256(json.dumps(
                    {
                        "source": record.get("source"),
                        "symbol": record.get("symbol"),
                        "sequence": record.get("sequence"),
                        "sequence_semantics": record.get("sequence_semantics"),
                        "raw_payload_sha256": digest,
                    }, sort_keys=True, separators=(",", ":"), default=str,
                ).encode("utf-8")).hexdigest()
                events.append(SequenceEvent(
                    -1, "REJECT_STREAM", "SEQUENCE_SEMANTICS_UNVERIFIED",
                    {"record_fingerprint_sha256": fingerprint},
                ))
                return SequenceCandleResult((), (), tuple(events))

            try:
                event = self.sequence.observe(record)
            except (TypeError, ValueError):
                events.append(SequenceEvent(
                    -1, "REJECT_STREAM", "INVALID_SEQUENCE_VALUE",
                ))
                return SequenceCandleResult((), (), tuple(events))
            events.append(event)
            if event.status == "ACCEPTED":
                safe.append(record)
            elif event.status == "IDEMPOTENT_DUPLICATE":
                continue
            else:
                return SequenceCandleResult((), (), tuple(events))

        candles, gaps = ingest_closed_candles(safe, as_of=as_of)
        return SequenceCandleResult(candles, gaps, tuple(events))
