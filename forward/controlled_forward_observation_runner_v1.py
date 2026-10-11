"""Bounded live bridge for observation-only forward runs.

Transport -> normalized fresh records -> ForwardObservationPathV1 -> journal.
No execution, no historical inputs, no outcomes, no strategy tuning.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .forward_observation_path_v1 import ForwardObservationPathV1
from .observation_session_manager_v1 import ObservationSessionManagerV1
from .sequence_integrity_diagnostic_journal_v1 import SequenceIntegrityDiagnosticJournalV1
from .tabdeal_transport_v1 import TabdealReadOnlyTransportV1, WS_URL, SYMBOL
from .sequence_capability_registry_v1 import RegistryError, load_verified_contract
from .source_attestation_verifier_v1 import AttestationError, verify_attestation

# Trust paths are code-owned, not caller-selectable. The checked-in Tabdeal
# record is conservative, so production remains blocked until reviewed evidence
# and a new pinned registry revision explicitly authorize sequence gap detection.
_SEQUENCE_REGISTRY_PATH = Path(__file__).with_name("sequence_capability_registry_v1.json")
_SEQUENCE_REGISTRY_LOCK_PATH = Path(__file__).with_name("sequence_capability_registry_v1.lock.json")
_SEQUENCE_SCOPE = {
    "venue": "tabdeal",
    "product": "fapi-futures-margin",
    "transport": "websocket",
    "endpoint": WS_URL,
    "channel_or_topic": f"{SYMBOL} raw-text subscription",
    "message_type": "trade-envelope",
    "field_path": "trade.sequence",
    "protocol_version": "unknown",
}


def _safe_evidence_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise AttestationError("BLOCK: evidence path missing")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise AttestationError("BLOCK: unsafe evidence path")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise AttestationError("BLOCK: evidence path escapes trust directory") from exc
    return resolved


def _verify_registry_source_attestations(
    registry_path: str | Path, expected_scope: dict[str, str]
) -> None:
    """Verify detached source attestations before the runner may create a session or socket."""
    registry_file = Path(registry_path)
    try:
        registry = json.loads(registry_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AttestationError("BLOCK: registry unreadable for attestation lookup") from exc
    if not isinstance(registry, dict) or not isinstance(registry.get("records"), list):
        raise AttestationError("BLOCK: registry records unavailable")
    matches = [
        item for item in registry["records"]
        if isinstance(item, dict)
        and all(item.get(key) == expected_scope[key] for key in expected_scope)
    ]
    if len(matches) != 1:
        raise AttestationError("BLOCK: attestation scope is not uniquely registered")
    evidence = matches[0].get("source_evidence")
    if not isinstance(evidence, list) or not evidence:
        raise AttestationError("BLOCK: source evidence missing")
    for item in evidence:
        if not isinstance(item, dict):
            raise AttestationError("BLOCK: malformed source evidence")
        snapshot_path = _safe_evidence_path(registry_file.parent, item.get("source_snapshot_file"))
        attestation_path = _safe_evidence_path(registry_file.parent, item.get("source_attestation_file"))
        verified = verify_attestation(
            snapshot_path=snapshot_path,
            attestation_path=attestation_path,
            expected_context=expected_scope,
        )
        if verified["snapshot_sha256"] != item.get("source_content_sha256"):
            raise AttestationError("BLOCK: registry and attestation snapshot digests differ")
        if verified["requested_url"] != item.get("url"):
            raise AttestationError("BLOCK: registry and attestation requested URLs differ")
        if verified["final_url"] != item.get("final_url"):
            raise AttestationError("BLOCK: registry and attestation final URLs differ")


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
        # Deprecated compatibility inputs: deliberately ignored. Trust is read
        # only from the code-owned, hash-pinned registry and exact adapter scope.
        sequence_contract_verified: bool = False,
        sequence_contract_evidence_ref: str | None = None,
    ) -> None:
        if max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        # Do not let caller-supplied booleans or evidence-reference strings grant trust.
        self.sequence_contract_verified = False
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

        # Do not open a socket or create even a session record until the upstream
        # sequence semantics are verified against an authoritative evidence reference.
        try:
            # Detached provenance must pass before registry claims can authorize
            # anything; this gate runs before session writes and socket creation.
            _verify_registry_source_attestations(_SEQUENCE_REGISTRY_PATH, _SEQUENCE_SCOPE)
            sequence_contract = load_verified_contract(
                _SEQUENCE_REGISTRY_PATH, _SEQUENCE_REGISTRY_LOCK_PATH, _SEQUENCE_SCOPE
            )
            sequence_contract_authorized = sequence_contract.gap_detection_authorized
        except (OSError, RegistryError, AttestationError, ValueError):
            sequence_contract_authorized = False

        if not sequence_contract_authorized:
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

        session = self.session_manager.start(started_at=now)
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
