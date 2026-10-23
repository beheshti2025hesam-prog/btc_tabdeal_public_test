"""Free-first, deterministic news intelligence for HES Trade Agent.

Ranks supplied news items and emits an evidence-bearing brief for the Mother
Orchestrator. It does not predict prices or place orders. Network collection
is an optional adapter; analysis remains pure and testable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Iterable, Mapping, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen
import json
import re
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class NewsItem:
    title: str
    summary: str = ""
    source: str = "unknown"
    url: str = ""
    published_at: str = ""
    language: str = "en"
    market_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketContext:
    market: str
    symbol: str = ""
    regime: str = "unknown"
    timeframe: str = ""
    observed_at: str = ""
    venue: str = ""


@dataclass(frozen=True)
class NewsFinding:
    item_id: str
    title: str
    source: str
    url: str
    published_at: str
    age_minutes: float | None
    relevance: float
    impact: float
    directional_bias: str
    confidence: float
    categories: tuple[str, ...]
    matched_terms: tuple[str, ...]
    reasons: tuple[str, ...]
    freshness: str
    caveats: tuple[str, ...]


@dataclass(frozen=True)
class NewsBrief:
    schema_version: str
    generated_at: str
    context: Mapping[str, str]
    status: str
    headline: str
    findings: tuple[NewsFinding, ...]
    market_implications: tuple[str, ...]
    mother_agent_summary: str
    suggested_action: str
    veto_flags: tuple[str, ...]
    provenance: Mapping[str, object]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


# Small, inspectable lexicons. Scores are heuristics, not calibrated probabilities.
_CATEGORY_TERMS = {
    "monetary_policy": ("fed", "federal reserve", "interest rate", "rate cut", "rate hike",
                        "central bank", "ecb", "fomc", "powell", "inflation", "cpi", "pce"),
    "regulation": ("regulation", "regulator", "sec", "lawsuit", "ban", "approved", "approval",
                   "etf", "legislation", "sanction", "تحریم", "قانون", "مجوز"),
    "security": ("hack", "exploit", "breach", "stolen", "outage", "vulnerability",
                 "هک", "حمله", "سرقت"),
    "exchange": ("exchange", "trading halted", "withdrawals suspended", "listing", "delisting",
                 "صرافی", "توقف معاملات"),
    "macro": ("recession", "gdp", "jobs report", "nonfarm payroll", "unemployment",
              "treasury yield", "bond yield", "geopolitical", "war", "oil price", "نفت"),
    "crypto_market": ("bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
                      "stablecoin", "liquidation", "fund flows", "on-chain", "بیت کوین"),
    "equities": ("earnings", "revenue", "guidance", "stock buyback", "dividend", "shares"),
    "fx": ("forex", "currency", "exchange rate", "dollar index", "dxy", "eur/usd", "usd/jpy"),
}
_POSITIVE = ("approved", "approval", "inflow", "record high", "adoption", "partnership",
             "rate cut", "beats expectations", "bullish", "recovery", "افزایش پذیرش")
_NEGATIVE = ("hack", "exploit", "breach", "ban", "lawsuit", "outflow", "liquidation",
             "misses expectations", "default", "bankruptcy", "war", "sanction",
             "withdrawals suspended", "bearish", "هک", "ممنوعیت", "ورشکستگی")
_HIGH_IMPACT = ("emergency", "unexpected", "surprise", "halted", "suspended", "hack",
                "exploit", "breach", "rate decision", "cpi", "fomc", "war", "default",
                "bankruptcy", "liquidation", "فوری")
_MARKET_ALIASES = {
    "crypto": ("bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
               "stablecoin", "blockchain", "بیت کوین", "رمزارز"),
    "fx": ("forex", "currency", "dollar", "euro", "yen", "gbp", "eur/usd", "usd/jpy", "dxy"),
    "equities": ("stock", "shares", "equity", "earnings", "nasdaq", "s&p 500", "dow jones"),
    "iran_equities": ("بورس", "شاخص کل", "سازمان بورس", "کدال", "tsetmc"),
    "commodities": ("gold", "silver", "oil", "crude", "copper", "طلا", "نفت"),
}


def _text(item: NewsItem) -> str:
    return f"{item.title} {item.summary}".casefold()


def _contains(text: str, phrase: str) -> bool:
    if len(phrase) <= 4 and phrase.isascii() and phrase.replace("/", "").isalpha():
        return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text) is not None
    return phrase.casefold() in text


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def fetch_rss(url: str, *, source: str, timeout_seconds: float = 5.0,
              max_bytes: int = 1_000_000) -> list[NewsItem]:
    """Fetch one operator-configured RSS/Atom feed with bounded I/O.

    URLs must come from a separately qualified source registry. Errors raise
    ValueError so incomplete coverage cannot masquerade as a complete scan.
    """
    if not url.startswith("https://"):
        raise ValueError("only HTTPS feed URLs are accepted")
    if not 0.1 <= timeout_seconds <= 15:
        raise ValueError("timeout_seconds must be between 0.1 and 15")
    if not 1024 <= max_bytes <= 2_000_000:
        raise ValueError("max_bytes must be between 1024 and 2000000")
    request = Request(url, headers={"User-Agent": "HES-Trade-Agent-News/1.0",
                                    "Accept": "application/rss+xml, application/atom+xml, application/xml"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read(max_bytes + 1)
    except (URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"news source unavailable: {type(exc).__name__}") from exc
    if len(payload) > max_bytes:
        raise ValueError("feed exceeds configured size limit")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("invalid RSS/Atom XML") from exc

    items = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1].casefold() not in {"item", "entry"}:
            continue
        fields = {}
        link = ""
        for element in node.iter():
            name = element.tag.rsplit("}", 1)[-1].casefold()
            if name in {"title", "description", "summary", "content", "pubdate", "published", "updated", "date"} and element.text:
                fields.setdefault(name, element.text.strip())
        for element in node:
            if element.tag.rsplit("}", 1)[-1].casefold() == "link":
                link = element.attrib.get("href", "") or (element.text or "").strip()
                if link:
                    break
        title = fields.get("title", "")
        if title:
            items.append(NewsItem(title=title,
                summary=fields.get("description", fields.get("summary", fields.get("content", ""))),
                source=source, url=link,
                published_at=fields.get("pubdate", fields.get("published", fields.get("updated", fields.get("date", ""))))))
    return items


class NewsIntelligenceBrain:
    """Market-aware news ranking and compact Mother Agent handoff."""

    def __init__(self, *, max_age_hours: float = 72, max_findings: int = 8,
                 high_impact_threshold: float = 0.65):
        if max_age_hours <= 0 or max_findings < 1 or not 0 <= high_impact_threshold <= 1:
            raise ValueError("invalid news-brain configuration")
        self.max_age_hours = max_age_hours
        self.max_findings = max_findings
        self.high_impact_threshold = high_impact_threshold

    def analyze(self, items: Iterable[NewsItem], context: MarketContext,
                *, now: datetime | None = None, source_failures: Sequence[str] = ()) -> NewsBrief:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        candidates: dict[str, tuple[NewsItem, datetime | None]] = {}
        stale_count = 0
        invalid_time_count = 0
        for item in items:
            if not item.title.strip():
                continue
            published = _parse_time(item.published_at)
            if item.published_at and published is None:
                invalid_time_count += 1
            age = (now - published).total_seconds() / 60 if published else None
            if age is not None and age > self.max_age_hours * 60:
                stale_count += 1
                continue
            key = sha256((item.url.strip() or (item.source + "|" + item.title.strip().casefold())).encode("utf-8")).hexdigest()[:16]
            previous = candidates.get(key)
            if previous is None or len(item.summary) > len(previous[0].summary):
                candidates[key] = (item, published)

        findings = []
        for key, (item, published) in candidates.items():
            text = _text(item)
            categories = tuple(category for category, terms in _CATEGORY_TERMS.items()
                               if any(_contains(text, term) for term in terms))
            matched = tuple(sorted({term for terms in _CATEGORY_TERMS.values() for term in terms
                                    if _contains(text, term} | {term for term in _HIGH_IMPACT if _contains(text, term)}))
            explicit_tags = {tag.casefold() for tag in item.market_tags}
            market = context.market.casefold()
            aliases = _MARKET_ALIASES.get(market, (context.symbol.casefold(),) if context.symbol else ())
            market_match = any(term and _contains(text, term) for term in aliases)
            symbol_match = bool(context.symbol and _contains(text, context.symbol.casefold()))
            category_match = (
                market == "crypto" and any(c in categories for c in ("crypto_market", "regulation", "security", "exchange", "monetary_policy", "macro"))
                or market in {"fx", "forex"} and any(c in categories for c in ("fx", "monetary_policy", "macro", "regulation"))
                or market in {"equities", "us_equities"} and any(c in categories for c in ("equities", "monetary_policy", "macro", "regulation"))
                or market in {"iran_equities", "iran_stocks"} and any(c in categories for c in ("equities", "macro", "regulation"))
                or market in {"commodities", "metals"} and any(c in categories for c in ("macro",))
            )
            tagged_match = bool(explicit_tags & {market, context.symbol.casefold()})
            relevance = 0.15 + (0.40 if market_match else 0) + (0.25 if symbol_match else 0) + (0.20 if category_match else 0) + (0.25 if tagged_match else 0)
            relevance = min(1.0, relevance)
            positive = sum(1 for term in _POSITIVE if _contains(text, term))
            negative = sum(1 for term in _NEGATIVE if _contains(text, term))
            bias = "positive" if positive > negative else "negative" if negative > positive else "mixed_or_unknown"
            directional_confidence = min(0.65, abs(positive - negative) * 0.12) if positive != negative else 0.0
            impact = 0.20 + min(0.45, len(categories) * 0.10) + (0.25 if any(_contains(text, term) for term in _HIGH_IMPACT) else 0)
            impact = min(1.0, impact)
            age_minutes = (now - published).total_seconds() / 60 if published else None
            freshness = "unknown" if age_minutes is None else "future_timestamp" if age_minutes < -5 else "fresh" if age_minutes <= 180 else "recent"
            caveats = []
            if age_minutes is None:
                caveats.append("publication_time_unverified")
            if age_minutes is not None and age_minutes < -5:
                caveats.append("publication_time_in_future")
            if not item.url:
                caveats.append("source_url_missing")
            if bias == "mixed_or_unknown":
                caveats.append("direction_not_established_by_rules")
            if not market_match and not symbol_match and not tagged_match:
                caveats.append("market_relevance_is_category_based")
            if item.source.strip().casefold() in {"unknown", ""}:
                caveats.append("source_identity_unverified")
            confidence = min(0.95, 0.20 + 0.35 * relevance + 0.25 * impact + directional_confidence)
            reasons = []
            if market_match: reasons.append("market_keyword_match")
            if symbol_match: reasons.append("symbol_keyword_match")
            if category_match: reasons.append("market_relevant_category")
            if tagged_match: reasons.append("explicit_market_tag")
            if any(_contains(text, term) for term in _HIGH_IMPACT): reasons.append("high_impact_language")
            findings.append(NewsFinding(
                item_id=key, title=item.title.strip(), source=item.source, url=item.url,
                published_at=_iso(published) if published else "",
                age_minutes=round(age_minutes, 1) if age_minutes is not None else None,
                relevance=round(relevance, 3), impact=round(impact, 3), directional_bias=bias,
                confidence=round(confidence, 3), categories=categories, matched_terms=matched[:20],
                reasons=tuple(reasons), freshness=freshness, caveats=tuple(caveats)))

        findings.sort(key=lambda f: (f.impact * f.relevance, f.confidence, f.published_at), reverse=True)
        findings = findings[:self.max_findings]
        high_impact = [f for f in findings if f.impact >= self.high_impact_threshold and f.relevance >= 0.45]
        implications = []
        if high_impact:
            implications.append(f"{len(high_impact)} high-impact item(s) are relevant enough to require a confirmation check.")
        if any("security" in f.categories or "exchange" in f.categories for f in high_impact):
            implications.append("Check venue/asset operational risk and liquidity before considering any signal.")
        if any("monetary_policy" in f.categories or "macro" in f.categories for f in high_impact):
            implications.append("Re-check volatility and spread around macro-event windows; news alone does not set direction.")
        if context.regime in {"unknown", "insufficient_data"}:
            implications.append("Market regime is unknown; do not convert news bias into a directional trade.")
        if source_failures:
            implications.append("News coverage is incomplete because one or more configured sources failed.")
        if not findings:
            implications.append("No sufficiently recent, parseable news items were available for this context.")

        veto_flags = []
        if source_failures: veto_flags.append("NEWS_SOURCE_COVERAGE_INCOMPLETE")
        if any(f.freshness == "future_timestamp" for f in findings): veto_flags.append("NEWS_TIMESTAMP_SUSPECT")
        if any("source_identity_unverified" in f.caveats for f in findings): veto_flags.append("NEWS_SOURCE_UNVERIFIED")
        if high_impact: veto_flags.append("HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION")
        status = "degraded" if source_failures else "no_relevant_news" if not findings else "ok"
        headline = (f"{len(high_impact)} high-impact relevant item(s)" if high_impact else
                    "No high-impact relevant item crossed the review threshold")
        summary_bits = [f"market={context.market}", f"symbol={context.symbol or 'unspecified'}",
                        f"regime={context.regime}", f"news_status={status}",
                        f"relevant_items={len(findings)}", f"high_impact={len(high_impact)}",
                        "directional_claim=unconfirmed"]
        if findings:
            top = findings[0]
            summary_bits.extend((f"top_item={top.title[:180]}", f"top_bias={top.directional_bias}"))
        summary_bits.append("recommendation=confirm_with_price_volume_and_risk_gates")
        return NewsBrief(
            schema_version="hes.news_brief.v1", generated_at=_iso(now),
            context={"market": context.market, "symbol": context.symbol, "regime": context.regime,
                     "timeframe": context.timeframe, "venue": context.venue},
            status=status, headline=headline, findings=tuple(findings),
            market_implications=tuple(implications),
            mother_agent_summary="; ".join(summary_bits),
            suggested_action="NO_TRADE_PENDING_CONFIRMATION" if high_impact or source_failures or context.regime in {"unknown", "insufficient_data"} else "CONTEXT_ONLY",
            veto_flags=tuple(veto_flags),
            provenance={"method": "deterministic_keyword_rules_v1", "sources_seen": len(candidates),
                        "items_returned": len(findings), "stale_items_dropped": stale_count,
                        "invalid_timestamps": invalid_time_count, "source_failures": list(source_failures),
                        "scores_are_probabilities": False, "news_alone_can_authorize_trade": False},
        )
