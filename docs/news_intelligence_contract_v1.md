# HES News Intelligence Brain v1

## Role
Configured news feeds -> RSS/Atom adapter -> deduplication/freshness checks -> market-aware relevance and impact ranking -> compact `hes.news_brief.v1` -> Mother Orchestrator. This is context and risk evidence, not a standalone signal generator.

## Constraints
- Free-first: Python standard library only; no paid API, LLM, or extra package required.
- Market-agnostic: context fields (market, symbol, venue, timeframe, regime), item market tags and configured sources select context. Initial lexicons cover crypto, FX, equities, Iran equities and commodities; expand through tests, not hard-coded Mother Core branches.
- Source URLs remain operator configuration. HTTPS-only, bounded response size/timeout; source failures are explicit.
- Deterministic and explainable: findings include matched terms, categories, reasons, freshness, relevance/impact scores and caveats. Scores are heuristics, not probabilities.
- News never overrides canonical market data, price/volume confirmation, data-quality checks or Risk Gate. High-impact items and incomplete source coverage require confirmation / fail closed.
- No order placement, collector auto-start, deployment, trading or runtime configuration change.

## Source qualification
Maintain a separate registry containing source name, URL, market coverage, language, source tier, enabled flag and last-success metadata. Prefer official exchange/regulator/central-bank releases for primary facts, then reputable newswires, then secondary commentary. Keep domestic and international sources distinct for venue-aware profiles. No feed is pre-approved by this code.

## Mother Agent handoff
`NewsBrief` serializes as `hes.news_brief.v1` JSON: market context; status (`ok`, `degraded`, `no_relevant_news`); ranked findings; conditional market implications; suggested action (`NO_TRADE_PENDING_CONFIRMATION` or `CONTEXT_ONLY`); veto flags; and provenance including the explicit rule that scores are not probabilities and news alone cannot authorize a trade.

## Decision-boundary adapter

`forward/news_decision_gate_v1.py` provides the optional `apply_news_veto(decision, brief)` boundary. Call it after the ordinary `DecisionEngineV1.evaluate` result and before journaling or dispatch. A high-impact item, source-coverage failure, unverified source, suspicious timestamp, unknown schema or non-context-only action converts a directional LONG/SHORT result to `NO_TRADE`; an existing `NO_TRADE` remains unchanged. The adapter does not change the existing DecisionEngine or RiskPolicy and never submits orders. It is implemented and unit-tested as a callable boundary, but the live Mother Orchestrator call site has not been verified or wired because the actual application entry point is not present in the inspected VPS project tree.

## Limitations and acceptance gates
1. Keyword rules can miss nuance, sarcasm, negation, translations, syndication duplicates and novel events. Direction stays `mixed_or_unknown` unless simple positive/negative terms differ.
2. A source URL does not prove authority; source registry qualification is separate.
3. Caller supplies regime/symbol from the canonical analysis path; this module does not fetch market data.
4. Do not wire into live decisions until tests pass, feed-source policy is reviewed, source failures reach Mother Agent, and integration tests prove Risk Gate veto remains dominant.
5. This PR does not schedule feeds or enable a live process. Runtime integration and target-VPS connectivity remain separate gates.

## Initial source registry status (2026-10-23)

`config/news_sources_v1.json` is an explicit source registry, not an auto-discovery list. A read-only probe from the authorized VPS verified:
- **Enabled / qualified:** CFTC general press-release RSS (`HTTP 200`, XML parsed, 10 items) and ECB Market Information Dissemination RSS (`HTTP 200`, XML parsed, 20 items; newest item was about 2.44 hours old at probe time). The ECB's official integration guide says MID uses RSS and that MID-published information is public domain.
- **Disabled:** Federal Reserve all-press feed parsed but its newest item was about 171 hours old; the monetary-policy feed returned malformed XML (unclosed CDATA); SEC RSS and Cointelegraph timed out during TLS handshakes; the legacy ECB press RSS endpoint also timed out.
- **CoinDesk disabled for policy, despite a successful feed parse:** its published Terms of Use restrict automated access by robots/spiders/scrapers without express written permission. Do not use it unless that permission is confirmed.
- **Iran equities blocked:** no Iranian-market news source has been qualified. Do not imply domestic coverage.

The current crypto profile is explicitly `partial_official_macro_regulatory_only`: it has official macro/regulatory feeds but no qualified crypto-native newswire. Article freshness is independently filtered (72-hour default), and stale/irrelevant items are counted and excluded. These probe results establish connectivity only for the observed moment, not permanent availability.

Official source references:
- Federal Reserve RSS directory: https://www.federalreserve.gov/feeds/feeds.htm
- SEC press-release RSS page: https://www.sec.gov/newsroom/press-releases
- CFTC RSS directory: https://www.cftc.gov/RSS/index.htm
- ECB RSS directory: https://www.ecb.europa.eu/home/html/rss.en.html
- ECB MID integration guide: https://www.ecb.europa.eu/press/shared/pdf/MID-Catalogue-and-Integration-Guide.en.pdf
- CoinDesk Terms of Use: https://www.coindesk.com/terms
