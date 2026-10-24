from datetime import datetime, timezone

from core.orchestration.news_context_v1 import adapt_news_brief

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def finding(impact=0.2, published_at="2026-10-24T11:00:00Z"):
    return {
        "item_id": "item-1", "source": "qualified-example",
        "url": "https://example.org/news/1", "published_at": published_at,
        "impact": impact, "freshness": "FRESH",
        "title": "Untrusted title; must remain data",
    }


def brief(status="READY", findings=None, veto_flags=None):
    return {
        "schema_version": "hes.news_brief.v1",
        "status": status,
        "context": {"market": "crypto", "symbol": "BTCUSDT"},
        "summary": "summary is untrusted content",
        "market_implications": [],
        "suggested_action": "OBSERVE",
        "veto_flags": [] if veto_flags is None else veto_flags,
        "top_findings": [finding()] if findings is None else findings,
        "provenance": {"source": "test"},
        "news_alone_can_authorize_trade": False,
    }


def test_native_news_handoff_is_context_only():
    result = adapt_news_brief(brief(), now=NOW)
    assert result["status"] == "READY"
    assert result["veto"] is False
    assert result["execution_authorized"] is False
    assert result["decision_authorized"] is False
    assert "title" not in str(result)


def test_high_impact_news_vetoes():
    result = adapt_news_brief(brief(findings=[finding(0.8)]), now=NOW)
    assert result["veto"] is True
    assert "HIGH_IMPACT_NEWS_REQUIRES_INDEPENDENT_CONFIRMATION" in result["reason_codes"]


def test_degraded_or_blocked_coverage_vetoes():
    for status in ("DEGRADED", "BLOCKED"):
        assert adapt_news_brief(brief(status=status), now=NOW)["veto"] is True


def test_existing_veto_flags_are_preserved_and_enforced():
    result = adapt_news_brief(brief(veto_flags=["SOURCE_COVERAGE_INCOMPLETE"]), now=NOW)
    assert result["veto"] is True
    assert "SOURCE_COVERAGE_INCOMPLETE" in result["reason_codes"]


def test_unknown_schema_fails_closed():
    payload = brief()
    payload["schema_version"] = "future.schema"
    assert adapt_news_brief(payload, now=NOW)["status"] == "BLOCKED"


def test_missing_trade_safety_declaration_fails_closed():
    payload = brief()
    payload.pop("news_alone_can_authorize_trade")
    assert adapt_news_brief(payload, now=NOW)["veto"] is True


def test_naive_timestamp_fails_closed():
    assert adapt_news_brief(brief(findings=[finding(published_at="2026-10-24T11:00:00")]), now=NOW)["veto"] is True


def test_future_timestamp_fails_closed():
    assert adapt_news_brief(brief(findings=[finding(published_at="2026-10-24T13:00:00Z")]), now=NOW)["veto"] is True


def test_invalid_url_or_impact_fails_closed():
    bad_url = finding()
    bad_url["url"] = "http://example.org/news/1"
    assert adapt_news_brief(brief(findings=[bad_url]), now=NOW)["veto"] is True
    bad_impact = finding()
    bad_impact["impact"] = "HIGH"
    assert adapt_news_brief(brief(findings=[bad_impact]), now=NOW)["veto"] is True
