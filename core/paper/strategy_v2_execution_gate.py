"""Fail-closed readiness gate for Strategy V2 paper simulation.

This gate can authorize only a paper intent. It never creates a position,
submits an order, mutates capital, or calls a venue adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
import json
import math

from forward.activation_gate_v1 import validate_activation
from forward.integration_gate_v1 import ForwardIntegrationGateV1

EXPECTED_RECOVERY_CANDIDATE_HEAD = "309ebf36c0ad18752516f928ebc6e0944a632ec9"
RECOVERY_SCHEMA = "hes.gateio_1m_recovery_24h_evidence.v1"
RECOVERY_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()


def _strict_int(value: Any, minimum: int | None = None) -> bool:
    return (
        isinstance(value, int) and not isinstance(value, bool)
        and (minimum is None or value >= minimum)
    )


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_gateio_1m_recovery_evidence(
    evidence_path: str | Path,
    *,
    data_root: str | Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify the official release-bound 24h soak v3 and its durable artifacts."""
    root = Path(data_root).expanduser().resolve()
    path = Path(evidence_path)
    if not path.is_absolute():
        path = root / path
    evidence_root = (root / "data/forward").resolve()
    if (
        path.is_symlink() or not path.resolve().is_relative_to(evidence_root)
        or not path.is_file() or path.stat().st_mode & 0o222
    ):
        return {"status": "BLOCKED", "reason": "RECOVERY_EVIDENCE_MISSING_OR_UNSAFE_PATH"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": "BLOCKED", "reason": "RECOVERY_EVIDENCE_INVALID_JSON"}
    if not isinstance(payload, Mapping) or payload.get("schema") != RECOVERY_SCHEMA:
        return {"status": "BLOCKED", "reason": "RECOVERY_EVIDENCE_SCHEMA_MISMATCH"}
    if payload.get("status") != "PASS":
        return {"status": "BLOCKED", "reason": "RECOVERY_SOAK_NOT_PASSED"}
    if payload.get("candidate_head") != EXPECTED_RECOVERY_CANDIDATE_HEAD:
        return {"status": "BLOCKED", "reason": "RECOVERY_CANDIDATE_HEAD_MISMATCH"}
    if not isinstance(payload.get("run_id"), str) or not payload["run_id"]:
        return {"status": "BLOCKED", "reason": "RECOVERY_RUN_ID_MISSING"}
    if not _strict_int(payload.get("duration_seconds"), 86400):
        return {"status": "BLOCKED", "reason": "RECOVERY_SOAK_DURATION_INSUFFICIENT"}
    if not _strict_int(payload.get("samples"), 1400):
        return {"status": "BLOCKED", "reason": "RECOVERY_SOAK_SAMPLE_COUNT_INSUFFICIENT"}
    if not _strict_int(payload.get("new_closed_candles"), 1400):
        return {"status": "BLOCKED", "reason": "RECOVERY_SOAK_CANDLE_COUNT_INSUFFICIENT"}
    max_age = payload.get("max_observed_candle_age_seconds")
    if isinstance(max_age, bool) or not isinstance(max_age, (int, float)) or not 0 <= max_age <= 120:
        return {"status": "BLOCKED", "reason": "RECOVERY_SOAK_FRESHNESS_LIMIT_EXCEEDED"}

    observed_now = now or datetime.now(timezone.utc)
    if observed_now.tzinfo is None or observed_now.utcoffset() is None:
        return {"status": "BLOCKED", "reason": "RECOVERY_VERIFICATION_CLOCK_INVALID"}
    try:
        finished = datetime.fromisoformat(str(payload.get("finished_at")))
        started = datetime.fromisoformat(str(payload.get("started_at")))
        if (
            finished.tzinfo is None or finished.utcoffset() is None
            or started.tzinfo is None or started.utcoffset() is None
        ):
            raise ValueError("timezone required")
        finished_utc = finished.astimezone(timezone.utc)
        started_utc = started.astimezone(timezone.utc)
        age = (observed_now.astimezone(timezone.utc) - finished_utc).total_seconds()
        wall_duration = (finished_utc - started_utc).total_seconds()
    except (TypeError, ValueError):
        return {"status": "BLOCKED", "reason": "RECOVERY_EVIDENCE_TIMESTAMP_INVALID"}
    if age < 0 or age > RECOVERY_MAX_AGE_SECONDS:
        return {"status": "BLOCKED", "reason": "RECOVERY_EVIDENCE_EXPIRED_OR_FUTURE"}
    if wall_duration < 86300 or wall_duration > 86500:
        return {"status": "BLOCKED", "reason": "RECOVERY_EVIDENCE_WALL_CLOCK_DURATION_INVALID"}

    evidence_hash = payload.get("evidence_sha256")
    unsigned = {key: value for key, value in payload.items() if key != "evidence_sha256"}
    if not isinstance(evidence_hash, str) or evidence_hash != _canonical_hash(unsigned):
        return {"status": "BLOCKED", "reason": "RECOVERY_EVIDENCE_HASH_MISMATCH"}

    # Bind the evidence to the exact immutable candidate release and soak script.
    release_dir = root / "releases" / EXPECTED_RECOVERY_CANDIDATE_HEAD
    manifest_path = release_dir / "HES_RELEASE_MANIFEST_v1.json"
    sidecar_path = release_dir / "HES_RELEASE_MANIFEST_v1.sha256"
    soak_script = release_dir / "scripts/soak_gateio_feed_24h_v2.py"
    market_reader = release_dir / "forward/global_market_data_reader_v1.py"
    if (
        not release_dir.is_dir()
        or release_dir.is_symlink()
        or release_dir.stat().st_mode & 0o222
        or manifest_path.is_symlink()
        or sidecar_path.is_symlink()
        or soak_script.is_symlink()
        or market_reader.is_symlink()
        or not manifest_path.is_file()
        or not sidecar_path.is_file()
        or not soak_script.is_file()
        or not market_reader.is_file()
        or manifest_path.stat().st_mode & 0o222
        or sidecar_path.stat().st_mode & 0o222
        or market_reader.stat().st_mode & 0o222
    ):
        return {"status": "BLOCKED", "reason": "RECOVERY_IMMUTABLE_RELEASE_MISSING_OR_WRITABLE"}
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        manifest_sha = sha256(manifest_bytes).hexdigest()
        sidecar_fields = sidecar_path.read_text(encoding="utf-8").strip().split()
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": "BLOCKED", "reason": "RECOVERY_RELEASE_MANIFEST_INVALID"}
    if (
        manifest.get("commit_sha") != EXPECTED_RECOVERY_CANDIDATE_HEAD
        or not isinstance(manifest.get("files"), list)
        or not manifest.get("files")
        or manifest.get("file_count") != len(manifest["files"])
        or sidecar_fields != [manifest_sha, "HES_RELEASE_MANIFEST_v1.json"]
        or manifest_sha != payload.get("release_manifest_sha256")
    ):
        return {"status": "BLOCKED", "reason": "RECOVERY_RELEASE_MANIFEST_PROVENANCE_MISMATCH"}
    file_hashes = {
        item.get("path"): item.get("sha256")
        for item in manifest["files"] if isinstance(item, Mapping)
    }
    script_sha = _file_sha256(soak_script)
    reader_sha = _file_sha256(market_reader)
    if (
        script_sha != payload.get("soak_script_sha256")
        or script_sha != file_hashes.get("scripts/soak_gateio_feed_24h_v2.py")
        or reader_sha != file_hashes.get("forward/global_market_data_reader_v1.py")
    ):
        return {"status": "BLOCKED", "reason": "RECOVERY_RELEASE_CODE_HASH_MISMATCH"}

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return {"status": "BLOCKED", "reason": "RECOVERY_EVIDENCE_ARTIFACTS_MISSING"}
    allowed_root = (root / "data/forward/gateio_1m_recovery_24h").resolve()
    if not allowed_root.is_dir() or allowed_root.is_symlink() or allowed_root.stat().st_mode & 0o222:
        return {"status": "BLOCKED", "reason": "RECOVERY_ARTIFACT_DIRECTORY_NOT_IMMUTABLE"}
    artifact_paths: dict[str, Path] = {}
    artifact_hashes: dict[str, str] = {}
    for name in ("candle_ledger", "sample_ledger", "collector_log"):
        item = artifacts.get(name)
        if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
            return {"status": "BLOCKED", "reason": f"RECOVERY_ARTIFACT_{name.upper()}_MISSING"}
        unresolved = root / item["path"]
        if unresolved.is_symlink():
            return {"status": "BLOCKED", "reason": f"RECOVERY_ARTIFACT_{name.upper()}_PATH_UNSAFE"}
        artifact_path = unresolved.resolve()
        if (
            not artifact_path.is_relative_to(allowed_root)
            or not artifact_path.is_file()
            or artifact_path.stat().st_mode & 0o222
        ):
            return {"status": "BLOCKED", "reason": f"RECOVERY_ARTIFACT_{name.upper()}_PATH_UNSAFE"}
        digest = _file_sha256(artifact_path)
        if digest != item.get("sha256"):
            return {"status": "BLOCKED", "reason": f"RECOVERY_ARTIFACT_{name.upper()}_HASH_MISMATCH"}
        artifact_paths[name] = artifact_path
        artifact_hashes[name] = digest
    if artifact_paths["collector_log"].stat().st_size == 0:
        return {"status": "BLOCKED", "reason": "RECOVERY_COLLECTOR_LOG_EMPTY"}

    try:
        records = [
            json.loads(line)
            for line in artifact_paths["sample_ledger"].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": "BLOCKED", "reason": "RECOVERY_SOAK_LEDGER_INVALID_JSONL"}
    sample_rows = [row for row in records if isinstance(row, Mapping) and row.get("schema") == "hes_gateio_soak_sample_v3"]
    summary_rows = [row for row in records if isinstance(row, Mapping) and row.get("schema") == "hes_gateio_soak_summary_v3"]
    if any(
        not isinstance(row, Mapping)
        or row.get("schema") not in ("hes_gateio_soak_sample_v3", "hes_gateio_soak_summary_v3")
        for row in records
    ):
        return {"status": "BLOCKED", "reason": "RECOVERY_SOAK_LEDGER_UNKNOWN_RECORD"}
    if len(summary_rows) != 1 or not records or records[-1] is not summary_rows[0]:
        return {"status": "BLOCKED", "reason": "RECOVERY_SOAK_SUMMARY_MISSING_OR_DUPLICATED"}
    if len(sample_rows) != payload["samples"]:
        return {"status": "BLOCKED", "reason": "RECOVERY_SAMPLE_LEDGER_COUNT_MISMATCH"}
    required_services = {
        "hes-global-market-data-gateio.service",
        "hes-global-market-data-gateio-1m.service",
        "hes-global-market-data-gateio-1m-integrity.timer",
        "hes-global-market-data-gateio-1h.service",
        "hes-global-market-data-gateio-4h.service",
    }

    summary = summary_rows[0]
    if (
        summary.get("run_id") != payload["run_id"]
        or summary.get("code_release_id") != EXPECTED_RECOVERY_CANDIDATE_HEAD
        or summary.get("release_manifest_sha256") != manifest_sha
        or summary.get("soak_script_sha256") != script_sha
        or summary.get("samples") != len(sample_rows)
        or summary.get("duration_seconds") != payload["duration_seconds"]
        or summary.get("passed") is not True
        or summary.get("execution_enabled") is not False
        or summary.get("orders_placed") is not False
        or not isinstance(summary.get("timeframes"), list)
        or set(summary.get("timeframes", [])) != {"1m", "15m", "1h", "4h"}
        or not isinstance(summary.get("services"), list)
        or set(summary.get("services", [])) != required_services
    ):
        return {"status": "BLOCKED", "reason": "RECOVERY_SOAK_SUMMARY_PROVENANCE_OR_ACCEPTANCE_MISMATCH"}

    max_age_by_tf = {"1m": 120, "15m": 1080, "1h": 3780, "4h": 14580}
    previous_elapsed = -1
    previous_observed = None
    previous_close_1m = None
    first_close_1m = None
    max_sample_age = 0.0
    for index, sample in enumerate(sample_rows, 1):
        if (
            not _strict_int(sample.get("sample"), 1)
            or sample.get("sample") != index
            or sample.get("run_id") != payload["run_id"]
            or sample.get("code_release_id") != EXPECTED_RECOVERY_CANDIDATE_HEAD
            or sample.get("release_manifest_sha256") != manifest_sha
            or sample.get("soak_script_sha256") != script_sha
            or sample.get("source") != "gateio_public_spot"
            or sample.get("symbol") != "BTC_USDT"
            or sample.get("ok") is not True
            or sample.get("execution_enabled") is not False
            or sample.get("orders_placed") is not False
        ):
            return {"status": "BLOCKED", "reason": f"RECOVERY_SAMPLE_IDENTITY_OR_STATUS_INVALID:{index}"}
        elapsed = sample.get("elapsed_seconds")
        if not _strict_int(elapsed, 0) or elapsed < previous_elapsed:
            return {"status": "BLOCKED", "reason": f"RECOVERY_SAMPLE_CLOCK_NOT_MONOTONIC:{index}"}
        if previous_elapsed >= 0 and elapsed - previous_elapsed > 120:
            return {"status": "BLOCKED", "reason": f"RECOVERY_SAMPLE_INTERVAL_GAP:{index}"}
        previous_elapsed = elapsed
        try:
            observed = datetime.fromisoformat(str(sample.get("observed_at")))
            if observed.tzinfo is None or observed.utcoffset() is None:
                raise ValueError("timezone required")
            observed = observed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return {"status": "BLOCKED", "reason": f"RECOVERY_SAMPLE_TIMESTAMP_INVALID:{index}"}
        if previous_observed is not None and observed <= previous_observed:
            return {"status": "BLOCKED", "reason": f"RECOVERY_SAMPLE_WALL_CLOCK_NOT_MONOTONIC:{index}"}
        previous_observed = observed
        timeframe_details = sample.get("timeframes")
        if not isinstance(timeframe_details, Mapping) or set(timeframe_details) != {"1m", "15m", "1h", "4h"}:
            return {"status": "BLOCKED", "reason": f"RECOVERY_SAMPLE_TIMEFRAMES_MISSING:{index}"}
        services = sample.get("services")
        if not isinstance(services, Mapping) or set(services) != required_services or any(v != "active" for v in services.values()):
            return {"status": "BLOCKED", "reason": f"RECOVERY_SAMPLE_SERVICE_NOT_ACTIVE:{index}"}
        for timeframe, max_age_limit in max_age_by_tf.items():
            detail = timeframe_details.get(timeframe)
            if not isinstance(detail, Mapping):
                return {"status": "BLOCKED", "reason": f"RECOVERY_SAMPLE_TIMEFRAME_INVALID:{timeframe}:{index}"}
            bars = detail.get("bars")
            candle_age = detail.get("age_seconds")
            close_time = detail.get("last_close_time")
            close = detail.get("close")
            if (
                not _strict_int(bars, 200)
                or isinstance(candle_age, bool)
                or not isinstance(candle_age, (int, float))
                or not 0 <= candle_age <= max_age_limit
                or not _strict_int(close_time, 0)
                or isinstance(close, bool)
                or not isinstance(close, (int, float))
                or not math.isfinite(float(close))
                or close <= 0
                or close_time > int(observed.timestamp())
                or abs((observed.timestamp() - close_time) - candle_age) > 3
            ):
                return {"status": "BLOCKED", "reason": f"RECOVERY_SAMPLE_CANDLE_INVALID:{timeframe}:{index}"}
        close_1m = sample["timeframes"]["1m"]["last_close_time"]
        if first_close_1m is None:
            first_close_1m = close_1m
        if previous_close_1m is not None and close_1m < previous_close_1m:
            return {"status": "BLOCKED", "reason": f"RECOVERY_1M_CLOSE_TIME_REGRESSED:{index}"}
        previous_close_1m = close_1m
        max_sample_age = max(max_sample_age, float(sample["timeframes"]["1m"]["age_seconds"]))

    if previous_elapsed < 86400:
        return {"status": "BLOCKED", "reason": "RECOVERY_SAMPLE_LEDGER_DURATION_INSUFFICIENT"}
    if first_close_1m is None or previous_close_1m is None:
        return {"status": "BLOCKED", "reason": "RECOVERY_SAMPLE_1M_COVERAGE_MISSING"}
    new_closed = (previous_close_1m - first_close_1m) // 60
    if new_closed != payload["new_closed_candles"] or new_closed < 1400:
        return {"status": "BLOCKED", "reason": "RECOVERY_SAMPLE_1M_CANDLE_COUNT_MISMATCH"}
    if abs(max_sample_age - float(max_age)) > 1:
        return {"status": "BLOCKED", "reason": "RECOVERY_SAMPLE_MAX_AGE_MISMATCH"}
    if started_utc != datetime.fromisoformat(str(sample_rows[0]["observed_at"])).astimezone(timezone.utc):
        return {"status": "BLOCKED", "reason": "RECOVERY_START_TIMESTAMP_MISMATCH"}
    if abs((finished_utc - previous_observed).total_seconds()) > 120:
        return {"status": "BLOCKED", "reason": "RECOVERY_FINISH_TIMESTAMP_MISMATCH"}

    try:
        candle_rows = [
            json.loads(line)
            for line in artifact_paths["candle_ledger"].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": "BLOCKED", "reason": "RECOVERY_CANDLE_LEDGER_INVALID_JSONL"}
    if not candle_rows:
        return {"status": "BLOCKED", "reason": "RECOVERY_CANDLE_LEDGER_EMPTY"}
    opens = []
    for index, candle in enumerate(candle_rows, 1):
        if (
            candle.get("schema") != "hes_global_candle_v1"
            or candle.get("source") != "gateio_public_spot"
            or candle.get("symbol") != "BTC_USDT"
            or candle.get("timeframe") != "1m"
            or candle.get("closed") is not True
        ):
            return {"status": "BLOCKED", "reason": f"RECOVERY_CANDLE_IDENTITY_INVALID:{index}"}
        open_time, close_time = candle.get("open_time"), candle.get("close_time")
        if not _strict_int(open_time, 0) or open_time % 60 or not _strict_int(close_time, 0) or close_time != open_time + 60:
            return {"status": "BLOCKED", "reason": f"RECOVERY_CANDLE_TIME_INVALID:{index}"}
        try:
            values = [float(candle[key]) for key in ("open", "high", "low", "close", "volume", "quote_volume")]
        except (KeyError, TypeError, ValueError):
            return {"status": "BLOCKED", "reason": f"RECOVERY_CANDLE_OHLCV_INVALID:{index}"}
        if (
            not all(math.isfinite(value) for value in values)
            or min(values[:4]) <= 0 or min(values[4:]) < 0
            or values[1] < max(values[0], values[2], values[3])
            or values[2] > min(values[0], values[1], values[3])
        ):
            return {"status": "BLOCKED", "reason": f"RECOVERY_CANDLE_OHLCV_RANGE_INVALID:{index}"}
        opens.append(open_time)
    if len(opens) != len(set(opens)) or opens != sorted(opens):
        return {"status": "BLOCKED", "reason": "RECOVERY_CANDLE_DUPLICATE_OR_ORDER_INVALID"}
    if any(opens[i] - opens[i - 1] != 60 for i in range(1, len(opens))):
        return {"status": "BLOCKED", "reason": "RECOVERY_CANDLE_GAP_DETECTED"}

    final_stats = payload.get("final_stats")
    final_age = finished_utc.timestamp() - candle_rows[-1]["close_time"]
    if (
        not isinstance(final_stats, Mapping)
        or final_stats.get("rows") != len(candle_rows)
        or final_stats.get("last_open_time") != opens[-1]
        or final_stats.get("last_close_time") != candle_rows[-1]["close_time"]
        or final_stats.get("gaps") != 0
        or final_stats.get("duplicates") != 0
        or isinstance(final_stats.get("age_seconds"), bool)
        or not isinstance(final_stats.get("age_seconds"), (int, float))
        or not 0 <= final_stats["age_seconds"] <= 120
        or abs(float(final_stats["age_seconds"]) - final_age) > 2
        or abs(final_age) > 120
        or opens[-1] + 60 != previous_close_1m
        or final_stats.get("sha256") != artifact_hashes["candle_ledger"]
    ):
        return {"status": "BLOCKED", "reason": "RECOVERY_FINAL_CANDLE_STATS_MISMATCH"}

    return {
        "status": "VERIFIED",
        "reason": "RECOVERY_SOAK_EVIDENCE_VERIFIED",
        "candidate_head": EXPECTED_RECOVERY_CANDIDATE_HEAD,
        "run_id": payload["run_id"],
        "duration_seconds": payload["duration_seconds"],
        "samples": payload["samples"],
        "new_closed_candles": payload["new_closed_candles"],
        "max_observed_candle_age_seconds": max_age,
        "release_manifest_sha256": manifest_sha,
        "soak_script_sha256": script_sha,
        "evidence_sha256": evidence_hash,
        "artifacts": artifact_hashes,
    }


@dataclass(frozen=True)
class PaperExecutionGateResult:
    ready: bool
    status: str
    paper_intent: str | None
    reason_codes: tuple[str, ...]
    activation_active: bool
    integration_safe: bool
    checks: Mapping[str, bool]
    activation_errors: tuple[str, ...]
    integration_reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "hes.paper_execution_gate.v1",
            "mode": "PAPER_SIMULATION_ONLY",
            "ready": self.ready,
            "status": self.status,
            "paper_intent": self.paper_intent,
            "reason_codes": list(self.reason_codes),
            "activation_active": self.activation_active,
            "activation_errors": list(self.activation_errors),
            "integration_safe": self.integration_safe,
            "integration_reason": self.integration_reason,
            "checks": dict(self.checks),
            "execution_enabled": False,
            "orders_placed": False,
            "capital_mutated": False,
            "venue_adapter_called": False,
            "position_created": False,
        }


class PaperExecutionGateV1:
    """Readiness gate only; never runs PaperSession or calls an execution adapter."""

    def evaluate(
        self,
        *,
        policy: Mapping[str, Any],
        ruleset: Mapping[str, Any],
        data_live: bool,
        structure_safe: bool,
        sequence_safe: bool,
        clock_safe: bool,
        health_safe: bool,
        recovery_safe: bool,
        proposal_decision: str,
        confirmation_state: str,
        risk_state: str,
        precision_entry_ready: bool,
        execution_enabled: bool = False,
        historical_inputs_allowed: bool = False,
        future_outcomes_allowed: bool = False,
    ) -> PaperExecutionGateResult:
        activation = validate_activation(policy, ruleset)
        integration = ForwardIntegrationGateV1().evaluate(
            data_live=data_live,
            structure_safe=structure_safe,
            sequence_safe=sequence_safe,
            clock_safe=clock_safe,
            health_safe=health_safe,
            recovery_safe=recovery_safe,
            execution_enabled=execution_enabled,
            historical_inputs_allowed=historical_inputs_allowed,
            future_outcomes_allowed=future_outcomes_allowed,
        )
        direction = proposal_decision if proposal_decision in ("LONG", "SHORT") else "NONE"
        checks = {
            "policy_and_ruleset_active": activation.active,
            "forward_integration_safe": integration.safe,
            "directional_strategy_candidate": direction in ("LONG", "SHORT"),
            "confirmation_evaluated": confirmation_state != "NOT_EVALUATED",
            "confirmation_matches_direction": confirmation_state == (f"CONFIRMED_{direction}" if direction != "NONE" else ""),
            "risk_gate_evaluated": risk_state != "NOT_EVALUATED",
            "risk_gate_approved": risk_state == "RISK_APPROVED",
            "precision_entry_1m_ready": precision_entry_ready is True,
            "live_execution_disabled": execution_enabled is False,
            "historical_inputs_disabled": historical_inputs_allowed is False,
            "future_outcomes_disabled": future_outcomes_allowed is False,
        }
        reasons = list(activation.errors)
        if not integration.safe:
            reasons.append("INTEGRATION_GATE_BLOCKED:" + integration.reason)
        if not checks["directional_strategy_candidate"]:
            reasons.append("STRATEGY_NO_DIRECTIONAL_CANDIDATE")
        if not checks["confirmation_evaluated"]:
            reasons.append("CONFIRMATION_NOT_EVALUATED_UPSTREAM_BLOCKED")
        elif not checks["confirmation_matches_direction"]:
            reasons.append("CONFIRMATION_NOT_APPROVED_FOR_DIRECTION")
        if not checks["risk_gate_evaluated"]:
            reasons.append("RISK_GATE_NOT_EVALUATED_UPSTREAM_BLOCKED")
        elif not checks["risk_gate_approved"]:
            reasons.append("RISK_GATE_NOT_APPROVED")
        if not checks["precision_entry_1m_ready"]:
            reasons.append("PRECISION_ENTRY_1M_FEED_NOT_READY")
        if execution_enabled:
            reasons.append("LIVE_EXECUTION_FORBIDDEN")
        if historical_inputs_allowed:
            reasons.append("HISTORICAL_INPUTS_FORBIDDEN")
        if future_outcomes_allowed:
            reasons.append("FUTURE_OUTCOMES_FORBIDDEN")
        ready = all(checks.values()) and not reasons
        intent = f"ENTER_{direction}" if ready else None
        return PaperExecutionGateResult(
            ready=ready,
            status="READY_FOR_PAPER_SIMULATION" if ready else "BLOCKED",
            paper_intent=intent,
            reason_codes=tuple(dict.fromkeys(reasons)),
            activation_active=activation.active,
            integration_safe=integration.safe,
            checks=checks,
            activation_errors=activation.errors,
            integration_reason=integration.reason,
        )
