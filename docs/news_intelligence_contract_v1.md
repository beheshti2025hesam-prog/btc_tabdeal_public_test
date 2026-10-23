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

## Limitations and acceptance gates
1. Keyword rules can miss nuance, sarcasm, negation, translations, syndication duplicates and novel events. Direction stays `mixed_or_unknown` unless simple positive/negative terms differ.
2. A source URL does not prove authority; source registry qualification is separate.
3. Caller supplies regime/symbol from the canonical analysis path; this module does not fetch market data.
4. Do not wire into live decisions until tests pass, feed-source policy is reviewed, source failures reach Mother Agent, and integration tests prove Risk Gate veto remains dominant.
5. This PR does not schedule feeds or enable a live process. Runtime integration and target-VPS connectivity remain separate gates.
