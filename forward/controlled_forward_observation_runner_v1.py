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
from .source_evidence_registry_v1 import SourceEvidenceRegistryError, verify_source_evidence_bundle

DEFAULT_SOURCE_EVIDENCE_REGISTRY_PATH = Path(__file__).resolve().parents[1] / "evidence" / "source_evidence_registry_v1.json"


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
        max_records: int = 100_000,
        sequence_contract_verified: bool = False,
        sequence_contract_evidence_ref: str | None = None,
        source_completeness_verified: bool = False,
        source_completeness_evidence_ref: str | None = None,
        source_ordering_verified: bool = False,
        source_ordering_evidence_ref: str | None = None,
        source_evidence_registry_path: str | Path | None = None,
    ) -> None:
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        self.sequence_contract_verified = sequence_contract_verified is True and bool(
            isinstance(sequence_contract_evidence_ref, str) and sequence_contract_evidence_ref.strip()
        )
        self.sequence_contract_evidence_ref = sequence_contract_evidence_ref
        self.source_completeness_verified = source_completeness_verified is True and bool(
            isinstance(source_completeness_evidence_ref, str) and source_completeness_evidence_ref.strip()
        )
        self.source_completeness_evidence_ref = source_completeness_evidence_ref
        self.source_ordering_verified = source_ordering_verified is True and bool(
            isinstance(source_ordering_evidence_ref, str) and source_ordering_evidence_ref.strip()
        )
        self.source_ordering_evidence_ref = source_ordering_evidence_ref
        self.source_evidence_registry_path = Path(source_evidence_registry_path) if source_evidence_registry_path is not None else DEFAULT_SOURCE_EVIDENCE_REGISTRY_PATH
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

        # Do not open a socket or create even a session record until both exact-feed
        # sequence semantics and source completeness have reviewed evidence references.
        if not self.sequence_contract_verified:
            return ControlledObservationRunnerResult(
                run_id="NOT_STARTED",
                status="BLOCKED",
                records_received=0,
                journal_path=str(self.journal_path),
                reason="UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED",
                snapshot_id=None,
                diagnostics=({
                    "network_started": False,
                    "session_written": False,
                    "sequence_contract_evidence_required": True,
                },),
            )
        if not self.source_completeness_verified:
            return ControlledObservationRunnerResult(
                run_id="NOT_STARTED",
                status="BLOCKED",
                records_received=0,
                journal_path=str(self.journal_path),
                reason="SOURCE_COMPLETENESS_UNVERIFIED",
                snapshot_id=None,
                diagnostics=({
                    "network_started": False,
                    "session_written": False,
                    "source_completeness_evidence_required": True,
                },),
            )

        if not self.source_ordering_verified:
            return ControlledObservationRunnerResult(
                run_id="NOT_STARTED",
                status="BLOCKED",
                records_received=0,
                journal_path=str(self.journal_path),
                reason="SOURCE_ORDERING_UNVERIFIED",
                snapshot_id=None,
                diagnostics=({
                    "network_started": False,
                    "session_written": False,
                    "source_ordering_evidence_required": True,
                },),
            )

        # Non-empty caller strings/booleans are not evidence. Resolve all three
        # claims against the release-pinned registry before any session/network I/O.
        try:
            verify_source_evidence_bundle(
                self.source_evidence_registry_path,
                sequence_contract_ref=self.sequence_contract_evidence_ref or "",
                source_completeness_ref=self.source_completeness_evidence_ref or "",
                source_ordering_ref=self.source_ordering_evidence_ref or "",
                source_scope="tabdeal-futures:BTC_USDT",
            )
        except SourceEvidenceRegistryError as exc:
            return ControlledObservationRunnerResult(
                run_id="NOT_STARTED",
                status="BLOCKED",
                records_received=0,
                journal_path=str(self.journal_path),
                reason=exc.code,
                snapshot_id=None,
                diagnostics=({
                    "network_started": False,
                    "session_written": False,
                    "source_evidence_registry_verified": False,
                },),
            )

        session = self.session_manager.start(started_at=now)
        self.session_manager.write_once(session, self.session_path)

        records: list[dict[str, Any]] = []
        record_bound_exceeded = False
        frame_metadata: list[dict[str, Any]] = []
        metadata_bound_exceeded = False

        def collect_frame_metadata(metadata: dict[str, Any]) -> None:
            nonlocal metadata_bound_exceeded
            # Keep one fingerprint per received frame. Never group or key events
            # by sequence: the provider does not define it as an event identity.
            if len(frame_metadata) >= min(self.max_records, 50000):
                # Avoid raising inside a WebSocket callback, where client libraries
                # may swallow callback exceptions and leave a partial run looking successful.
                metadata_bound_exceeded = True
                return
            frame_metadata.append(dict(metadata))

        def collect(record: dict[str, Any]) -> None:
            nonlocal record_bound_exceeded
            if len(records) >= self.max_records:
                record_bound_exceeded = True
                return
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
                    "frame_metadata_record_limit": min(self.max_records, 50000),
                    "observation_written": False,
                },),
            )

        if record_bound_exceeded:
            return ControlledObservationRunnerResult(
                run_id=session.run_id,
                status="BLOCKED",
                records_received=len(records),
                journal_path=str(self.journal_path),
                reason="FORWARD_RECORD_BOUND_EXCEEDED",
                snapshot_id=None,
                diagnostics=({"max_records": self.max_records},),
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
        result = ForwardObservationPathV1(
            self.journal_path,
            max_records=self.max_records,
            sequence_contract_verified=self.sequence_contract_verified,
            sequence_contract_evidence_ref=self.sequence_contract_evidence_ref,
            source_completeness_verified=self.source_completeness_verified,
            source_completeness_evidence_ref=self.source_completeness_evidence_ref,
            source_ordering_verified=self.source_ordering_verified,
            source_ordering_evidence_ref=self.source_ordering_evidence_ref,
            source_evidence_registry_path=self.source_evidence_registry_path,
        ).observe(
            records,
            as_of=observed_at,
            forward_run_id=session.run_id,
        )
        diagnostics = tuple(result.diagnostics)
        if frame_metadata:
            diagnostics = (*diagnostics, {
                "transport_frame_metadata_records": len(frame_metadata),
                "sequence_used_for_identity_or_grouping": False,
            })
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
