"""Fail-closed news context adapter for Mother Orchestrator v1.

This module is deliberately not wired into live execution. It validates a
versioned brief and exposes only contextual evidence plus a veto flag. News
cannot create a LONG/SHORT decision or authorize execution.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

CONTRACT = "hes.news_brief.v1"
ALLOWED_STATES = {"READY", "DEGRADED", "BLOCKED"}


def _utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Naive timestamps are ambiguous: fail closed instead of assuming UTC.
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def adapt_news_brief(brief: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Return safe, observation-only context. Invalid/unknown input blocks."""
    blocked = {
        "contract": CONTRACT,
        "state": "BLOCKED",
        "veto": True,
        "reason_codes": ["NEWS_BRIEF_INVALID_OR_UNTRUSTED"],
        "items": [],
        "execution_authorized": False,
        "decision_authorized": False,
    }
    if not isinstance(brief, Mapping) or brief.get("contract") != CONTRACT:
        return blocked
    if brief.get("state") not in ALLOWED_STATES:
        return blocked
    items = brief.get("items")
    if not isinstance(items, list):
        return blocked
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        return blocked
    clean_items = []
    for item in items:
        if not isinstance(item, Mapping):
            return blocked
        published = _utc_timestamp(item.get("published_at"))
        if published is None or published > clock:
            return blocked
        source_id = item.get("source_id")
        canonical_url = item.get("canonical_url")
        if not isinstance(source_id, str) or not source_id.strip():
            return blocked
        if not isinstance(canonical_url, str) or not canonical_url.startswith("https://"):
            return blocked
        # Article text is intentionally not copied into orchestration context.
        impact = item.get("impact")
        if impact not in {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}:
            return blocked
        clean_items.append({
            "source_id": source_id,
            "canonical_url": canonical_url,
            "published_at": published.isoformat(),
            "impact": impact,
            "item_hash": item.get("item_hash") if isinstance(item.get("item_hash"), str) else None,
        })
    state = brief["state"]
    high_impact = any(item["impact"] == "HIGH" for item in clean_items)
    degraded = state != "READY"
    reasons = []
    if high_impact:
        reasons.append("HIGH_IMPACT_NEWS_REQUIRES_INDEPENDENT_CONFIRMATION")
    if degraded:
        reasons.append("NEWS_COVERAGE_DEGRADED")
    return {
        "contract": CONTRACT,
        "state": "DEGRADED" if degraded else "READY",
        "veto": high_impact or degraded,
        "reason_codes": reasons,
        "items": clean_items,
        "execution_authorized": False,
        "decision_authorized": False,
    }
