"""Live, read-only Mother dashboard backed by the seven runtime specialists and a same-snapshot consensus resolver.

Unlike the legacy report projection, this path loads the current validated
Gate.io candle ledger and invokes the existing HES evaluators on every request.
It never uses a pre-generated Strategy V2 report as a specialist result.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import os

from core.orchestration.mother_v1 import MotherOrchestratorV1
from core.orchestration.mother_runtime_specialists_v1 import (
    LiveMarketContextV1,
    live_specialists_v1,
    specialist_registry_v1,
)
from core.orchestration.witness_v1 import MotherAuditWitnessV1

SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"


class MotherRuntimeDashboardError(ValueError):
    """The live Mother runtime could not produce a verifiable observation."""


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _news_canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _load_news_context(*, observed_at: datetime) -> dict[str, Any]:
    """Load digest-verified item interpretations for Mother; never infer from stale news."""
    path = Path(os.environ.get("HES_NEWS_MONITOR_SNAPSHOT", "/var/lib/hes-news-monitor/news_brief_latest.json"))
    try:
        raw = path.read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError("NEWS_SNAPSHOT_TOO_LARGE")
        snapshot = json.loads(raw.decode("utf-8"))
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != "hes.news_monitor_snapshot.v1":
            raise ValueError("NEWS_SNAPSHOT_SCHEMA_INVALID")
        unsigned = dict(snapshot)
        snapshot_digest = unsigned.pop("snapshot_sha256", None)
        actual_snapshot_digest = hashlib.sha256(_news_canonical_bytes(unsigned)).hexdigest()
        if not isinstance(snapshot_digest, str) or snapshot_digest != actual_snapshot_digest:
            raise ValueError("NEWS_SNAPSHOT_DIGEST_MISMATCH")
        monitor = snapshot.get("monitor")
        brief = snapshot.get("brief")
        brief_digest = snapshot.get("brief_sha256")
        if not isinstance(monitor, dict) or monitor.get("status") not in {"OK", "DEGRADED"}:
            raise ValueError("NEWS_MONITOR_NOT_READY")
        if not isinstance(brief, dict) or brief.get("schema_version") != "hes.news_brief.v1":
            raise ValueError("NEWS_BRIEF_INVALID")
        if not isinstance(brief_digest, str) or hashlib.sha256(_news_canonical_bytes(brief)).hexdigest() != brief_digest:
            raise ValueError("NEWS_BRIEF_DIGEST_MISMATCH")
        stamp = datetime.fromisoformat(str(monitor.get("last_poll_at", "")).replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("NEWS_TIMESTAMP_INVALID")
        age_seconds = (observed_at - stamp.astimezone(timezone.utc)).total_seconds()
        max_age = max(600, int(os.environ.get("HES_NEWS_MONITOR_INTERVAL_SECONDS", "300")) * 3)
        if age_seconds < -30 or age_seconds > max_age:
            raise ValueError("NEWS_SNAPSHOT_STALE_OR_FUTURE")
        findings = brief.get("findings", [])
        if not isinstance(findings, list):
            raise ValueError("NEWS_FINDINGS_INVALID")
        selected = []
        for item in findings[:5]:
            if not isinstance(item, dict):
                raise ValueError("NEWS_FINDING_INVALID")
            interpretation = item.get("interpretation")
            if not isinstance(interpretation, dict) or interpretation.get("schema_version") != "hes.news_item_interpretation.v1":
                raise ValueError("NEWS_INTERPRETATION_MISSING")
            localized = interpretation.get("localized")
            required_localized_fields = {
                "what_happened", "why_it_matters", "affected_market",
                "relevance_scope", "potential_effect", "transmission_channel",
                "time_horizon", "what_to_monitor", "educational_concept",
                "uncertainty", "disclaimer",
            }
            if not isinstance(localized, dict) or not {"fa", "en", "de", "fr"}.issubset(localized):
                raise ValueError("NEWS_INTERPRETATION_LOCALES_INCOMPLETE")
            for locale in ("fa", "en", "de", "fr"):
                rendered = localized.get(locale)
                if not isinstance(rendered, dict) or any(
                    not isinstance(rendered.get(field), str) or not rendered[field].strip()
                    for field in required_localized_fields
                ):
                    raise ValueError("NEWS_INTERPRETATION_CONTENT_INCOMPLETE:" + locale)
            if interpretation.get("potential_effect") not in {"positive", "negative", "mixed_or_unknown"}:
                raise ValueError("NEWS_INTERPRETATION_EFFECT_INVALID")
            if interpretation.get("scores_are_probabilities") is not False:
                raise ValueError("NEWS_INTERPRETATION_SCORE_SEMANTICS_INVALID")
            mother_use = interpretation.get("mother_use")
            if (
                not isinstance(mother_use, dict)
                or mother_use.get("news_alone_can_authorize_trade") is not False
                or mother_use.get("requires_independent_market_confirmation") is not True
            ):
                raise ValueError("NEWS_INTERPRETATION_AUTHORITY_INVALID")
            item_id = item.get("item_id")
            if not isinstance(item_id, str) or not item_id.strip():
                raise ValueError("NEWS_FINDING_ID_INVALID")
            selected.append({
                "item_id": item_id,
                "title": item.get("title"),
                "source": item.get("source"),
                "published_at": item.get("published_at"),
                "freshness": item.get("freshness"),
                "impact": item.get("impact"),
                "relevance": item.get("relevance"),
                "directional_bias": item.get("directional_bias"),
                "categories": item.get("categories", []),
                "interpretation": interpretation,
            })
        context = {
            "status": "READY",
            "coverage_status": str(monitor.get("source_profile_status") or "UNKNOWN"),
            "monitor_status": str(monitor.get("status")),
            "snapshot_sha256": snapshot_digest,
            "brief_sha256": brief_digest,
            "observed_at": stamp.astimezone(timezone.utc).isoformat(),
            "age_seconds": round(age_seconds, 1),
            "veto_flags": list(brief.get("veto_flags", [])) if isinstance(brief.get("veto_flags"), list) else [],
            "findings": selected,
            "news_alone_can_authorize_trade": False,
        }
        context["context_sha256"] = _canonical_hash(context)
        return context
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError) as exc:
        return {
            "status": "BLOCKED",
            "reason_code": str(exc) if isinstance(exc, ValueError) and str(exc).startswith("NEWS_") else "NEWS_CONTEXT_UNAVAILABLE_OR_INVALID",
            "findings": [],
            "veto_flags": [],
            "news_alone_can_authorize_trade": False,
        }


def read_mother_runtime_dashboard(
    *,
    data_root: str | Path = "/opt/hes-trade-agent",
    journal_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise MotherRuntimeDashboardError("MOTHER_RUNTIME_CLOCK_NOT_TIMEZONE_AWARE")
    observed = observed.astimezone(timezone.utc)
    market = LiveMarketContextV1(data_root=data_root, observed_at=observed, journal_path=journal_path)

    # Load the canonical persisted market input once. Every specialist below
    # shares this memoized snapshot; no specialist makes a second REST request.
    try:
        market.load()
    except Exception:
        # The data-quality specialist will re-surface the failure as a blocked
        # stage; hashes remain valid so the independent witness can verify it.
        pass

    snapshot_sha = market.snapshot_sha256 or _canonical_hash({
        "source": SOURCE, "symbol": SYMBOL, "observed_at": observed.isoformat(),
    })
    registry = specialist_registry_v1()
    news_context = _load_news_context(observed_at=observed)
    evidence_sha = _canonical_hash({
        "snapshot_sha256": snapshot_sha,
        "news_context_sha256": news_context.get("context_sha256"),
        "news_snapshot_sha256": news_context.get("snapshot_sha256"),
        "news_brief_sha256": news_context.get("brief_sha256"),
        "specialist_registry": registry,
        "runtime_mode": "LIVE_DATA_RUNTIME_SPECIALISTS",
    })
    request_id = "hes-mother-live-" + observed.strftime("%Y%m%dT%H%M%S") + "-" + snapshot_sha[:16]
    context = {
        "scope": {"venue": "gateio", "product": "spot", "symbol": SYMBOL, "timeframe": "15m"},
        "observed_at": observed.isoformat(),
        "snapshot_sha256": snapshot_sha,
        "evidence_sha256": evidence_sha,
        "request_id": request_id,
        "news_context": news_context,
    }
    result = MotherOrchestratorV1(live_specialists_v1(market)).run(context)
    envelope = result.as_dict()
    witness = MotherAuditWitnessV1().verify(envelope)
    if not witness.verified:
        raise MotherRuntimeDashboardError("MOTHER_RUNTIME_WITNESS_REJECTED:" + "|".join(witness.reason_codes))

    summary = market.summary()
    stages = envelope["stages"]
    return {
        "schema": "hes.mother_runtime_dashboard.v1",
        "runtime_mode": "LIVE_DATA_RUNTIME_SPECIALISTS",
        "status": result.status,
        "decision": result.decision,
        "reason_codes": list(result.reason_codes),
        "trace_id": result.trace_id,
        "audit_sha256": result.audit_sha256,
        "source": SOURCE,
        "symbol": SYMBOL,
        "timeframe": "15m",
        "observed_at": observed.isoformat(),
        "request_id": request_id,
        "snapshot_sha256": snapshot_sha,
        "market_data_provenance": summary.get("market_data_provenance"),
        "market_regime": summary.get("market_regime", "UNKNOWN"),
        "strategy_proposal": summary.get("strategy_proposal"),
        "precision_entry": summary.get("precision_entry"),
        "recovery_evidence": summary.get("recovery_evidence"),
        "paper_execution_gate": summary.get("paper_execution_gate"),
        "sequence_validation": summary.get("sequence_validation"),
        "registered_specialists": registry,
        "executed_specialists": [row["agent"] for row in stages],
        "registered_count": len(registry),
        "executed_count": len(stages),
        "stages": stages,
        "consensus": result.consensus,
        "news_context": {
            "status": news_context.get("status"),
            "coverage_status": news_context.get("coverage_status", "UNKNOWN"),
            "context_sha256": news_context.get("context_sha256"),
            "snapshot_sha256": news_context.get("snapshot_sha256"),
            "brief_sha256": news_context.get("brief_sha256"),
            "age_seconds": news_context.get("age_seconds"),
            "veto_flags": list(news_context.get("veto_flags", [])),
            "finding_count": len(news_context.get("findings", [])),
            "reason_code": news_context.get("reason_code"),
            "news_alone_can_authorize_trade": False,
        },
        "witness": witness.as_dict(),
        "execution_authorized": False,
        "execution_enabled": False,
        "orders_placed": False,
        "journal_write": False,
        "outcomes_inferred": False,
        "external_llm_used": False,
    }
