"""Fail-closed adapter for the actual NewsBrief.to_mother_payload() contract.

Observation-only: news can veto/raise uncertainty but cannot originate a trade.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "hes.news_brief.v1"


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def adapt_news_brief(brief: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Accept the native news handoff shape; invalid or uncertain input blocks."""
    blocked = {
        "schema_version": SCHEMA_VERSION, "status": "BLOCKED", "veto": True,
        "reason_codes": ["NEWS_BRIEF_INVALID_OR_UNTRUSTED"], "items": [],
        "execution_authorized": False, "decision_authorized": False,
    }
    if not isinstance(brief, Mapping) or brief.get("schema_version") != SCHEMA_VERSION:
        return blocked
    if brief.get("news_alone_can_authorize_trade") is not False:
        return blocked
    status = brief.get("status")
    if status not in {"READY", "DEGRADED", "BLOCKED"}:
        return blocked
    findings = brief.get("top_findings", [])
    if not isinstance(findings, list):
        return blocked
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        return blocked
    clean = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            return blocked
        published = _timestamp(finding.get("published_at"))
        if published is None or published > clock:
            return blocked
        url = finding.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            return blocked
        source = finding.get("source")
        if not isinstance(source, str) or not source.strip():
            return blocked
        impact = finding.get("impact")
        if not isinstance(impact, (int, float)) or isinstance(impact, bool) or not 0 <= impact <= 1:
            return blocked
        clean.append({
            "source": source, "url": url, "published_at": published.isoformat(),
            "impact": float(impact), "freshness": finding.get("freshness", "UNKNOWN"),
            "item_id": finding.get("item_id") if isinstance(finding.get("item_id"), str) else None,
        })
    flags = brief.get("veto_flags", [])
    if not isinstance(flags, (list, tuple)) or any(not isinstance(flag, str) for flag in flags):
        return blocked
    high_impact = any(item["impact"] >= 0.65 for item in clean)
    degraded = status != "READY"
    reasons = list(flags)
    if high_impact:
        reasons.append("HIGH_IMPACT_NEWS_REQUIRES_INDEPENDENT_CONFIRMATION")
    if degraded and not reasons:
        reasons.append("NEWS_COVERAGE_DEGRADED")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "DEGRADED" if degraded else "READY",
        "veto": bool(high_impact or degraded or flags),
        "reason_codes": sorted(set(reasons)),
        "items": clean,
        "execution_authorized": False,
        "decision_authorized": False,
    }
