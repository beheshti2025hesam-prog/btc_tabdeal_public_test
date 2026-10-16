"""Bounded live bridge for observation-only forward runs.

Transport -> normalized fresh records -> ForwardObservationPathV1 -> journal.
No execution, no historical inputs, no outcomes, no strategy tuning.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess
from typing import Any, Callable

from .forward_observation_path_v1 import ForwardObservationPathV1
from .signed_sequence_contract_gate_v1 import verify_sequence_contract_evidence
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
        max_records: int = 100_000,
        sequence_contract_envelope_path: str | Path | None = None,
        sequence_contract_key_registry_path: str | Path | None = None,
        trusted_key_registry_sha256: str | None = None,
        expected_commit: str | None = None,
        expected_evidence_path: str | None = None,
        market_scope: str = "tabdeal:futures:BTC_USDT",
        evidence_max_age_seconds: int = 86400,
    ) -> None:
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        # These values are inputs to cryptographic verification, never proof by themselves.
        self.sequence_contract_envelope_path = (
            Path(sequence_contract_envelope_path) if sequence_contract_envelope_path is not None else None
        )
        self.sequence_contract_key_registry_path = (
            Path(sequence_contract_key_registry_path) if sequence_contract_key_registry_path is not None else None
        )
        self.trusted_key_registry_sha256 = trusted_key_registry_sha256
        self.expected_commit = expected_commit
        self.expected_evidence_path = expected_evidence_path
        self.market_scope = market_scope
        self.evidence_max_age_seconds = evidence_max_age_seconds
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

        # Cryptographically verify the exact evidence before creating a session,
        # constructing a transport, or opening a socket. A boolean/reference is not proof.
        try:
            # The trust pin is provisioned by the deployment environment, outside
            # caller-controlled constructor arguments. The constructor value is only
            # a consistency assertion; it can never establish trust on its own.
            protected_registry_sha256 = os.environ.get("HES_TRUSTED_KEY_REGISTRY_SHA256")
            if (
                self.sequence_contract_envelope_path is None
                or self.sequence_contract_key_registry_path is None
                or not isinstance(protected_registry_sha256, str)
                or len(protected_registry_sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in protected_registry_sha256)
                or not isinstance(self.trusted_key_registry_sha256, str)
                or self.trusted_key_registry_sha256 != protected_registry_sha256
                or not isinstance(self.expected_commit, str)
                or not self.expected_commit
                or not isinstance(self.expected_evidence_path, str)
                or not self.expected_evidence_path
                or self.evidence_max_age_seconds <= 0
            ):
                raise ValueError("signed evidence configuration or protected registry pin is incomplete")
            # Trust anchor: derive the running source revision from this checkout.
            # Never let caller configuration define which commit is considered current.
            completed = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD^{commit}"],
                cwd=Path(__file__).resolve().parents[1],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            running_commit = completed.stdout.strip()
            if len(running_commit) != 40 or any(ch not in "0123456789abcdef" for ch in running_commit):
                raise ValueError("unable to establish canonical running commit")
            if self.expected_commit != running_commit:
                raise ValueError("configured expected commit does not match running commit")
            verified_evidence = verify_sequence_contract_evidence(
                envelope_path=self.sequence_contract_envelope_path,
                key_registry_path=self.sequence_contract_key_registry_path,
                expected_commit=running_commit,
                expected_evidence_path=self.expected_evidence_path,
                market_scope=self.market_scope,
                trusted_key_registry_sha256=protected_registry_sha256,
                max_age_seconds=self.evidence_max_age_seconds,
                now=now,
            )
        except Exception as exc:
            return ControlledObservationRunnerResult(
                run_id="NOT_STARTED",
                status="BLOCKED",
                records_received=0,
                journal_path=str(self.journal_path),
                reason=f"UPSTREAM_SEQUENCE_CONTRACT_UNVERIFIED:{type(exc).__name__}",
                snapshot_id=None,
                diagnostics=({
                    "network_started": False,
                    "session_written": False,
                    "signature_verified": False,
                    "sequence_contract_evidence_required": True,
                    "verification_error": type(exc).__name__,
                },),
            )

        # A live WebSocket factory is required. Reject this invalid execution mode
        # before writing a session or constructing any transport.
        if self.ws_factory is None:
            return ControlledObservationRunnerResult(
                run_id="NOT_STARTED",
                status="BLOCKED",
                records_received=0,
                journal_path=str(self.journal_path),
                reason="WS_FACTORY_REQUIRED",
                snapshot_id=None,
                diagnostics=({
                    "network_started": False,
                    "session_written": False,
                    "signature_verified": True,
                    "ws_factory_required": True,
                },),
            )

        # The session is created only after successful Ed25519 verification
        # and validation of the required live transport configuration.

        # Bind the exact verified source attestation to the immutable session record.
        # This makes later audits able to identify which signed evidence authorized this run.
        session = self.session_manager.start(
            started_at=now,
            sequence_contract_evidence=verified_evidence,
        )
        self.session_manager.write_once(session, self.session_path)

        records: list[dict[str, Any]] = []
        record_bound_exceeded = False
        frame_metadata_by_sequence: dict[str, list[dict[str, Any]]] = {}
        metadata_bound_exceeded = False

        def collect_frame_metadata(metadata: dict[str, Any]) -> None:
            nonlocal metadata_bound_exceeded
            value = metadata.get("normalized_sequence", metadata.get("sequence_value"))
            if type(value) not in (int, str):
                return
            key = str(value)
            if key not in frame_metadata_by_sequence and len(frame_metadata_by_sequence) >= 50000:
                # Avoid raising inside a WebSocket callback, where client libraries
                # may swallow callback exceptions and leave a partial run looking successful.
                metadata_bound_exceeded = True
                return
            entries = frame_metadata_by_sequence.setdefault(key, [])
            if len(entries) < 2:
                entries.append(dict(metadata))

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
        result = ForwardObservationPathV1(self.journal_path, max_records=self.max_records).observe(
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
