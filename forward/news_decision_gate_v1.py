"""Optional fail-closed adapter from news intelligence to final decisions.

The core DecisionEngine stays independent of news providers. The Mother
Orchestrator may apply this boundary after the normal decision result and
before journaling/dispatch. This adapter never places orders.
"""
from __future__ import annotations

from core.market_intelligence.news_brain import NewsBrief
from forward.decision_engine_v1 import DecisionResult


def apply_news_veto(decision: DecisionResult, brief: NewsBrief) -> DecisionResult:
    """Return NO_TRADE when news context is unsafe or unqualified.

    A valid context-only brief leaves the original decision untouched. Any
    unknown schema/action/status fails closed for directional decisions.
    Existing NO_TRADE decisions are preserved unchanged.
    """
    if decision.decision == "NO_TRADE":
        return decision

    allowed_schema = brief.schema_version == "hes.news_brief.v1"
    allowed_status = brief.status in {"ok", "no_relevant_news"}
    allowed_action = brief.suggested_action == "CONTEXT_ONLY"
    flags = list(brief.veto_flags)
    profile_status = brief.provenance.get("source_profile_status", "unknown")
    if profile_status not in {"qualified_complete", "complete"} and "NEWS_SOURCE_COVERAGE_INCOMPLETE" not in flags:
        flags.append("NEWS_SOURCE_COVERAGE_INCOMPLETE")
    if brief.status == "degraded" and "NEWS_SOURCE_COVERAGE_INCOMPLETE" not in flags:
        flags.append("NEWS_SOURCE_COVERAGE_INCOMPLETE")

    if allowed_schema and allowed_status and allowed_action and not flags:
        return decision

    reasons = list(decision.reason_codes)
    reasons.append("NEWS_GATE_VETO")
    if not allowed_schema:
        reasons.append("NEWS_BRIEF_SCHEMA_UNSUPPORTED")
    if not allowed_status:
        reasons.append("NEWS_STATUS_NOT_ACCEPTABLE")
    if not allowed_action:
        reasons.append("NEWS_REQUIRES_CONFIRMATION")
    reasons.extend(flag for flag in flags if flag not in reasons)

    # URLs are source evidence supplied by the feed, not invented identifiers.
    refs = list(decision.evidence_refs)
    refs.extend("news:" + finding.url for finding in brief.findings[:3] if finding.url)
    return DecisionResult(
        observed_at=decision.observed_at,
        decision="NO_TRADE",
        reason_codes=tuple(dict.fromkeys(reasons)),
        evidence_refs=tuple(dict.fromkeys(refs)),
        quality_score=decision.quality_score,
    )
