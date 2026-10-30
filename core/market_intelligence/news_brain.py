"""Free-first, deterministic news intelligence for HES Trade Agent.

Ranks supplied news items and emits an evidence-bearing brief for the Mother
Orchestrator. It does not predict prices or place orders. Network collection
is an optional adapter; analysis remains pure and testable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Iterable, Mapping, Sequence
from urllib.error import URLError
from urllib.request import Request, urlopen, HTTPRedirectHandler, build_opener
from urllib.parse import urlsplit, urljoin
from pathlib import Path
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
    source_id: str = ""
    feed_payload_sha256: str = ""
    retrieved_at: str = ""
    raw_item_sha256: str = ""


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

    def to_mother_payload(self) -> dict:
        """Return the compact, explicit handoff consumed by Mother Agent."""
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "context": dict(self.context),
            "summary": self.mother_agent_summary,
            "market_implications": list(self.market_implications),
            "suggested_action": self.suggested_action,
            "veto_flags": list(self.veto_flags),
            "top_findings": [asdict(item) for item in self.findings[:3]],
            "provenance": dict(self.provenance),
            "news_alone_can_authorize_trade": False,
        }


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
               "stablecoin", "blockchain", "binance", "coinbase", "kraken", "bybit", "okx", "بیت کوین", "رمزارز"),
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
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_source_registry(path: str | Path) -> dict:
    """Load and validate the operator-maintained news-source registry.

    An enabled source must have passed a separate qualification review. This
    loader does not promote candidates or make network requests.
    """
    try:
        registry = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("news source registry unreadable or invalid JSON") from exc
    if registry.get("schema_version") != "hes.news_sources.v1":
        raise ValueError("unsupported news source registry schema")
    sources = registry.get("sources")
    if not isinstance(sources, list):
        raise ValueError("registry sources must be a list")
    seen = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("each source must be an object")
        source_id = source.get("id")
        url = source.get("url", "")
        if not isinstance(source_id, str) or not source_id or source_id in seen:
            raise ValueError("source ids must be unique non-empty strings")
        seen.add(source_id)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(f"source {source_id} must use HTTPS")
        if source.get("host") != parsed.hostname:
            raise ValueError(f"source {source_id} host does not match URL")
        if not isinstance(source.get("enabled"), bool):
            raise ValueError(f"source {source_id} enabled must be boolean")
        if source["enabled"] and source.get("qualification_status") != "qualified":
            raise ValueError(f"source {source_id} cannot be enabled before qualification")
        source_type = source.get("type", "rss")
        if source_type not in {"rss", "gate_announcements"}:
            raise ValueError(f"source {source_id} has unsupported source type")
        if source_type == "gate_announcements" and (parsed.hostname != "api.gateio.ws" or parsed.path != "/api/v4/ann/list_article"):
            raise ValueError(f"source {source_id} has an unapproved Gate announcement endpoint")
        if not isinstance(source.get("markets"), list) or not source["markets"]:
            raise ValueError(f"source {source_id} must declare market coverage")
    return registry


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_rss(url: str, *, source: str, source_id: str = "", timeout_seconds: float = 5.0,
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
        # Do not follow redirects: the final host must never silently escape
        # the operator-qualified registry host boundary.
        with build_opener(_RejectRedirects()).open(request, timeout=timeout_seconds) as response:
            payload = response.read(max_bytes + 1)
    except (URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"news source unavailable: {type(exc).__name__}") from exc
    if len(payload) > max_bytes:
        raise ValueError("feed exceeds configured size limit")
    payload_digest = sha256(payload).hexdigest()
    retrieved_at = _iso(datetime.now(timezone.utc))
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
            # Feed-provided links are evidence references only; retain HTTPS URLs.
            if link:
                parsed_link = urlsplit(link)
                if parsed_link.scheme != "https" or not parsed_link.hostname:
                    link = ""
            items.append(NewsItem(title=title,
                summary=fields.get("description", fields.get("summary", fields.get("content", ""))),
                source=source, url=link,
                published_at=fields.get("pubdate", fields.get("published", fields.get("updated", fields.get("date", "")))),
                source_id=source_id or source, feed_payload_sha256=payload_digest,
                retrieved_at=retrieved_at,
                raw_item_sha256=sha256(ET.tostring(node, encoding="utf-8")).hexdigest()))
    return items



def fetch_gate_announcements(url: str, *, source: str, source_id: str,
                             language: str = "en", days: int = 3, page_size: int = 50,
                             timeout_seconds: float = 5.0, max_bytes: int = 1_000_000) -> list[NewsItem]:
    """Fetch Gate.io's documented public announcement list (no API key required)."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "api.gateio.ws" or parsed.path != "/api/v4/ann/list_article":
        raise ValueError("unapproved Gate announcement endpoint")
    if language not in {"en", "cn"} or type(days) is not int or not 1 <= days <= 7:
        raise ValueError("invalid Gate announcement language or time window")
    if type(page_size) is not int or not 1 <= page_size <= 50:
        raise ValueError("invalid Gate announcement page size")
    if not 0.1 <= timeout_seconds <= 15 or not 1024 <= max_bytes <= 2_000_000:
        raise ValueError("invalid Gate announcement I/O limits")
    body = {"page": "1", "size": str(page_size), "lang": language,
            "timer": str(days), "filter_empty_content": 1}
    request = Request(url, data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
                      headers={"User-Agent": "HES-Trade-Agent-News/1.0",
                               "Accept": "application/json",
                               "Content-Type": "application/json"}, method="POST")
    try:
        with build_opener(_RejectRedirects()).open(request, timeout=timeout_seconds) as response:
            payload = response.read(max_bytes + 1)
    except (URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"news source unavailable: {type(exc).__name__}") from exc
    if len(payload) > max_bytes:
        raise ValueError("Gate announcement response exceeds configured size limit")
    digest = sha256(payload).hexdigest()
    retrieved_at = _iso(datetime.now(timezone.utc))
    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid Gate announcement JSON") from exc
    if not isinstance(document, dict) or not isinstance(document.get("data"), dict):
        raise ValueError("Gate announcement response schema is invalid")
    if document.get("code") != 0:
        raise ValueError("Gate announcement API returned a non-zero business code")
    rows = document["data"].get("list")
    if not isinstance(rows, list):
        raise ValueError("Gate announcement response list is invalid")
    items = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("title"), str) or not row["title"].strip():
            continue
        published_at = ""
        raw_timestamp = row.get("release_timestamp")
        try:
            timestamp = int(raw_timestamp)
            if timestamp > 0 and timestamp <= int(datetime.now(timezone.utc).timestamp()) + 30 * 24 * 3600:
                published_at = _iso(datetime.fromtimestamp(timestamp, timezone.utc))
        except (TypeError, ValueError, OverflowError, OSError):
            pass
        article_path = row.get("url", "")
        article_url = ""
        if isinstance(article_path, str) and article_path.startswith("/announcements/article/") and ".." not in article_path:
            candidate = urljoin("https://www.gate.io", article_path)
            parsed_article = urlsplit(candidate)
            if parsed_article.scheme == "https" and parsed_article.hostname == "www.gate.io":
                article_url = candidate
        item_digest = sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        items.append(NewsItem(
            title=row["title"].strip(), summary=str(row.get("brief") or ""),
            source=source, url=article_url, published_at=published_at,
            language=language, source_id=source_id, feed_payload_sha256=digest,
            retrieved_at=retrieved_at, raw_item_sha256=item_digest,
        ))
    return items


class NewsIntelligenceBrain:
    """Market-aware news ranking and compact Mother Agent handoff."""

    def __init__(self, *, max_age_hours: float = 72, max_findings: int = 8,
                 high_impact_threshold: float = 0.65, min_relevance: float = 0.35):
        if max_age_hours <= 0 or max_findings < 1 or not 0 <= high_impact_threshold <= 1 or not 0 <= min_relevance <= 1:
            raise ValueError("invalid news-brain configuration")
        self.max_age_hours = max_age_hours
        self.max_findings = max_findings
        self.high_impact_threshold = high_impact_threshold
        self.min_relevance = min_relevance

    def run_from_registry(self, registry_path: str | Path, context: MarketContext,
                          *, now: datetime | None = None) -> NewsBrief:
        """Collect from enabled market sources, then build the Mother Agent brief.

        No enabled source is treated as incomplete coverage, not as evidence
        that no news exists. Per-source failures are retained in provenance.
        """
        registry = load_source_registry(registry_path)
        registry_sha256 = sha256(Path(registry_path).read_bytes()).hexdigest()
        profile = registry.get("market_profiles", {}).get(context.market, {})
        allowed_ids = set(profile.get("source_ids", []))
        sources = [source for source in registry["sources"]
                   if source["enabled"] and source["id"] in allowed_ids
                   and context.market in source["markets"]]
        if not sources:
            brief = self.analyze([], context, now=now,
                                 source_failures=[f"no_enabled_sources_for_market:{context.market}"])
            brief = self._attach_profile_status(brief, profile)
            return replace(brief, provenance={**brief.provenance, "registry_sha256": registry_sha256})
        items = []
        failures = []
        for source in sources:
            try:
                if source.get("type", "rss") == "gate_announcements":
                    request_options = source.get("request", {})
                    items.extend(fetch_gate_announcements(
                        source["url"], source=source["name"], source_id=source["id"],
                        language=request_options.get("language", "en"),
                        days=request_options.get("days", 3),
                        page_size=request_options.get("page_size", 50),
                    ))
                else:
                    items.extend(fetch_rss(source["url"], source=source["name"], source_id=source["id"]))
            except ValueError as exc:
                failures.append(f"{source['id']}:{str(exc).split(':', 1)[0]}")
        brief = self.analyze(items, context, now=now, source_failures=failures)
        brief = self._attach_profile_status(brief, profile)
        return replace(brief, provenance={**brief.provenance, "registry_sha256": registry_sha256})

    @staticmethod
    def _attach_profile_status(brief: NewsBrief, profile: Mapping[str, object]) -> NewsBrief:
        """Expose partial market-source coverage without claiming completeness."""
        status = str(profile.get("status", "unknown"))
        note = str(profile.get("note", ""))
        provenance = dict(brief.provenance)
        provenance["source_profile_status"] = status
        if note:
            provenance["source_profile_note"] = note
        implications = list(brief.market_implications)
        if status not in {"qualified_complete", "complete"}:
            implications.append("News-source coverage profile is not complete: " + (note or status))
        summary = brief.mother_agent_summary + f"; source_profile_status={status}"
        return replace(brief, provenance=provenance,
                       market_implications=tuple(implications),
                       mother_agent_summary=summary)

    def analyze(self, items: Iterable[NewsItem], context: MarketContext,
                *, now: datetime | None = None, source_failures: Sequence[str] = ()) -> NewsBrief:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        candidates: dict[str, tuple[NewsItem, datetime | None]] = {}
        stale_count = 0
        irrelevant_count = 0
        invalid_time_count = 0
        source_evidence: dict[tuple[str, str, str, str], dict[str, str]] = {}
        for item in items:
            if item.feed_payload_sha256:
                key = (item.source_id or item.source, item.feed_payload_sha256,
                       item.raw_item_sha256, item.retrieved_at)
                source_evidence[key] = {"source_id": key[0], "feed_payload_sha256": key[1],
                                        "raw_item_sha256": key[2], "retrieved_at": key[3]}
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
                                    if _contains(text, term)} | {term for term in _HIGH_IMPACT if _contains(text, term)}))
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
            if relevance < self.min_relevance:
                irrelevant_count += 1
                continue
            positive = sum(1 for term in _POSITIVE if _contains(text, term))
            negative = sum(1 for term in _NEGATIVE if _contains(text, term))
            bias = "positive" if positive > negative else "negative" if negative > positive else "mixed_or_unknown"
            directional_confidence = min(0.65, abs(positive - negative) * 0.12) if positive != negative else 0.0
            impact = 0.20 + min(0.45, len(categories) * 0.10) + (0.25 if any(_contains(text, term) for term in _HIGH_IMPACT) else 0)
            impact = min(1.0, impact)
            age_minutes = (now - published).total_seconds() / 60 if published else None
            freshness = "unknown" if age_minutes is None else "future_timestamp" if age_minutes < 0 else "fresh" if age_minutes <= 180 else "recent"
            caveats = []
            if age_minutes is None:
                caveats.append("publication_time_unverified")
            if age_minutes is not None and age_minutes < 0:
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
        if invalid_time_count: veto_flags.append("NEWS_TIMESTAMP_INVALID")
        if any(f.freshness == "unknown" for f in findings): veto_flags.append("NEWS_TIMESTAMP_UNVERIFIED")
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
            suggested_action="NO_TRADE_PENDING_CONFIRMATION" if veto_flags or context.regime in {"unknown", "insufficient_data"} else "CONTEXT_ONLY",
            veto_flags=tuple(veto_flags),
            provenance={"method": "deterministic_keyword_rules_v1", "sources_seen": len(candidates),
                        "items_returned": len(findings), "stale_items_dropped": stale_count,
                        "irrelevant_items_dropped": irrelevant_count,
                        "invalid_timestamps": invalid_time_count, "source_failures": list(source_failures),
                        "source_evidence": list(source_evidence.values()),
                        "scores_are_probabilities": False, "news_alone_can_authorize_trade": False},
        )
