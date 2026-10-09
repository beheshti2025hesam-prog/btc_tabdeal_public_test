"""Bounded live bridge for observation-only forward runs.

Transport -> normalized fresh records -> ForwardObservationPathV1 -> journal.
No execution, no historical inputs, no outcomes, no strategy tuning.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .forward_observation_path_v1 import ForwardObservationPathV1
from .observation_session_manager_v1 import ObservationSessionManagerV1
from .sequence_integrity_diagnostic_journal_v1 import SequenceIntegrityDiagnosticJournalV1
from .tabdeal_transport_v1 import TabdealReadOnlyTransportV1


@dataclass(frozen=True)
class ControlledObservationRunnerResult:
    run_id: str
    status: str
    records_received: int
    journal_path: str
    reason: str
    snapshot_id: str | None
    diagnostics: tuple[dict[str, Any], ...] = ()


class ControlledForwardObservationRunnerV1:
    """Run one bounded, read-only observation session.

    The transport is injected so tests cannot accidentally require a network.
    A live caller may inject websocket.WebSocketApp as ws_factory.
    """

    def __init__(
        self,
        *,
        journal_path: str | Path,
        session_path: str | Path,
        policy_id: str = "HES_FORWARD_OBSERVATION_POLICY_V1",
        policy_version: str = "1",
        transport_factory: Callable[..., Any] = TabdealReadOnlyTransportV1,
        ws_factory: Callable[..., Any] | None = None,
        max_runtime_seconds: float = 60.0,
        diagnostics_path: str | Path | None = None,
    ) -> None:
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        self.journal_path = Path(journal_path)
        self.session_path = Path(session_path)
        self.diagnostics_path = (
            Path(diagnostics_path) if diagnostics_path is not None
            else self.session_path.with_name("sequence_integrity_diagnostics_v1.jsonl")
        )
        self.session_manager = ObservationSessionManagerV1(
            policy_id=policy_id,
            policy_version=policy_version,
        )
        self.transport_factory = transport_factory
        self.ws_factory = ws_factory
        self.max_runtime_seconds = float(max_runtime_seconds)

    def run(self, *, started_at: datetime | None = None) -> ControlledObservationRunnerResult:
        now = started_at or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        now = now.astimezone(timezone.utc)

        session = self.session_manager.start(started_at=now)
        self.session_manager.write_once(session, self.session_path)

        records: list[dict[str, Any]] = []
        frame_metadata_by_sequence: dict[str, list[dict[str, Any]]] = {}
        metadata_bound_exceeded = False

        def collect_frame_metadata(metadata: dict[str, Any]) -> None:
            nonlocal metadata_bound_exceeded
            value = metadata.get("sequence_value")
            if type(value) not in (int, str):
                return
            key = str(value)
            if key not in frame_metadata_by_sequence and len(frame_metadata_by_sequence) >= 50000:
                # Do not raise from a WebSocket callback: some clients swallow
                # callback exceptions and could otherwise leave a partial run
                # looking successful. Record the condition and block after the
                # bounded transport returns, before observation/snapshot writes.
                metadata_bound_exceeded = True
                return
            entries = frame_metadata_by_sequence.setdefault(key, [])
            # Keep only the first two frames for each sequence: enough to compare
            # the original and conflicting frame without unbounded per-key growth.
            if len(entries) < 2:
                entries.append(dict(metadata))

        def collect(record: dict[str, Any]) -> None:
            # Transport records are already normalized and fresh. Re-wrap only
            # to satisfy the path adapter's explicit frame contract.
            records.append({
                "type": "trade",
                **record,
            })

        kwargs: dict[str, Any] = {
            "as_of_provider": lambda: datetime.now(timezone.utc),
            "on_record": collect,
            "on_frame_metadata": collect_frame_metadata,
            "max_runtime_seconds": self.max_runtime_seconds,
        }
        if self.ws_factory is None:
            raise ValueError("ws_factory must be supplied explicitly for a live run")
        kwargs["ws_factory"] = self.ws_factory

        try:
            transport = self.transport_factory(**kwargs)
            transport.run_once()
        except Exception as exc:
            return ControlledObservationRunnerResult(
                run_id=session.run_id,
                status="BLOCKED",
                records_received=len(records),
                journal_path=str(self.journal_path),
                reason=f"TRANSPORT_ERROR:{type(exc).__name__}",
                snapshot_id=None,
            )

        if metadata_bound_exceeded:
            return ControlledObservationRunnerResult(
                run_id=session.run_id,
                status="BLOCKED",
                records_received=len(records),
                journal_path=str(self.journal_path),
                reason="TRANSPORT_METADATA_BOUND_EXCEEDED",
                snapshot_id=None,
                diagnostics=({
                    "reason": "TRANSPORT_METADATA_BOUND_EXCEEDED",
                    "distinct_sequence_limit": 50000,
                    "observation_written": False,
                },),
            )

        if not records:
            return ControlledObservationRunnerResult(
                run_id=session.run_id,
                status="WAITING",
                records_received=0,
                journal_path=str(self.journal_path),
                reason="NO_FRESH_RECORDS",
                snapshot_id=None,
            )

        observed_at = datetime.now(timezone.utc)
        result = ForwardObservationPathV1(self.journal_path).observe(
            records,
            as_of=observed_at,
            forward_run_id=session.run_id,
        )
        diagnostics = tuple(
            {
                **event,
                "transport_frame_fingerprints": frame_metadata_by_sequence.get(str(event.get("sequence")), []),
            }
            if event.get("reason") == "CONFLICTING_DUPLICATE_SEQUENCE"
            else event
            for event in result.diagnostics
        )
        if result.status == "BLOCKED" and result.reason == "SEQUENCE_UNSAFE":
            try:
                persisted = SequenceIntegrityDiagnosticJournalV1(self.diagnostics_path).append_blocked_run(
                    run_id=session.run_id,
                    observed_at_utc=observed_at.isoformat(),
                    reason=result.reason,
                    diagnostics=diagnostics,
                )
                if persisted is not None:
                    diagnostics = (*diagnostics, {
                        "diagnostic_journal": str(self.diagnostics_path),
                        "diagnostic_record_sha256": persisted["record_sha256"],
                        "diagnostic_persistence": "PERSISTED",
                    })
            except Exception as exc:
                # Preserve the safety block even if diagnostics storage is unavailable.
                diagnostics = (*diagnostics, {
                    "diagnostic_persistence": "FAILED",
                    "diagnostic_error_type": type(exc).__name__,
                })

        return ControlledObservationRunnerResult(
            run_id=session.run_id,
            status=result.status,
            records_received=len(records),
            journal_path=str(self.journal_path),
            reason=result.reason,
            snapshot_id=result.snapshot_id,
            diagnostics=diagnostics,
        )
