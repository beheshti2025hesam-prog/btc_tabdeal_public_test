# News Item AI Interpretation & Market Education — V1

Status: **Accepted product requirement / implementation pending**
Recorded: 2026-11-14
Owner: HES Trade Agent project
Target surface: Dashboard → News Radar → each individual news item

## 1. Product requirement

Every displayed news item must have an interpretation panel directly beneath that item. The panel serves two purposes using one shared, evidence-backed analysis:

1. **Economic education for the user:** explain in clear, natural language what happened, why it matters economically, and through which mechanism it may affect the selected market.
2. **Mother Orchestrator context:** expose the same structured interpretation to Mother and specialist agents so it can be considered alongside market structure, price/volume, regime, risk, and confirmation evidence.

This is an item-level capability, not only a single summary at the top of the News Radar.

## 2. Four application languages

The complete interpretation must be available in all four current dashboard locales:

- Persian (`fa`)
- English (`en`)
- German (`de`)
- French (`fr`)

Use the dashboard's selected locale by default. Switching locale must change the interpretation and educational explanation without changing the underlying analysis, evidence, confidence, impact classification, or Mother handoff.

The canonical analysis must be language-neutral structured data. Localized text is a presentation layer. Translation must preserve financial meaning, uncertainty, direction, time horizon, and caveats; do not translate numeric values, symbols, source identifiers, or evidence hashes.

## 3. Required per-item content

Each item interpretation must expose the following fields (where a field cannot be established, state that explicitly rather than inventing it):

1. **What happened:** concise, source-faithful event description.
2. **Why it matters:** plain-language economic explanation and relevant mechanism.
3. **Affected market(s):** market family, relevant assets/symbols, and venue where applicable. Distinguish directly affected markets from indirect/cross-market transmission.
4. **Potential market effect:** positive / negative / mixed / uncertain, with explicit distinction between potential pressure and confirmed price action.
5. **Transmission channel:** e.g. monetary policy/liquidity, regulation, security/counterparty, exchange operations, supply/demand, risk appetite, rates/FX, earnings, commodities.
6. **Time horizon:** immediate (minutes–hours), short term (1–3 days), medium term (weeks), or unknown; do not infer a horizon without event evidence.
7. **What to monitor:** relevant price/volume/volatility/spread/liquidity, related assets, official follow-up, and confirmation conditions.
8. **Uncertainty and caveats:** source quality, publication freshness, corroboration, relevance, missing context, and reasons the impact could differ.
9. **Educational concept:** explain any relevant economic/financial term in simple language, with a concise example where useful.
10. **Evidence references:** original headline, publisher/source, URL, publication time, retrieval time, item/event IDs, and content hashes already captured by the news pipeline.

The panel should be readable and compact by default, with details expandable; avoid flooding the dashboard.

## 4. Market-awareness and analytical boundaries

- Respect the existing multi-market / venue-aware news architecture and each market profile. Do not assume every headline applies to BTC or crypto.
- For crypto, distinguish asset-wide, macro, regulatory, security, and venue-operational effects.
- For Iran equities, FX, foreign equities, commodities, and future markets, identify relevant market-specific channels only when the source and configured profile support them.
- Explicitly identify unrelated/conflicting asset mentions; do not transfer an ETH/SOL/company-specific event to BTC without a supported causal link.
- A venue announcement can affect venue operations/listing/liquidity but is not a substitute for Gate.io canonical candles, indicators, or chart data.
- Never turn a news headline or its translated interpretation into a trade signal by itself. News is contextual evidence only; Mother must require independent market structure, price/volume, regime, confirmation, and risk gates.
- High-impact, stale, unverified, contradictory, or incomplete news may add a veto/confirmation requirement. It must not authorize entry or execution.

## 5. Mother Agent integration

The same canonical per-item interpretation must be included in a versioned, validated news-to-Mother payload. Mother and relevant specialists should be able to consume:
- event identity and cluster/corroboration,
- affected markets/assets/venues and relevance,
- event category and transmission channel,
- potential direction and impact magnitude as qualitative labels,
- time horizon,
- confidence/uncertainty and source freshness,
- confirmation observations and veto flags.

The existing numeric heuristic scores are not calibrated probabilities and must never be presented as probabilities. Add explicit semantics for every score/label. Keep provenance and a content digest so the UI and Mother consume the same analysis version. Mother should cite the event IDs in its reasoning/decision trace and explain when news was ignored, stale, irrelevant, or vetoed.

## 6. Free-first implementation

- Keep the feature within the existing free-first architecture.
- Do not introduce a paid LLM, paid translation API, or external model dependency.
- Prefer the existing local deterministic NewsIntelligenceBrain and curated multilingual templates/glossary for V1. If a local model is later evaluated, it must be optional, offline/free, bounded, testable, and never the sole source of market direction.
- Never silently call an external translation/AI service.
- Cache localized rendering by canonical item/event ID, context, schema version, and locale to avoid repeated work.

## 7. Safety and quality requirements

- Clearly label interpretation as analysis/education, not financial advice or a guaranteed forecast.
- Preserve source-faithful facts separately from model inference.
- Distinguish fact, inference, scenario, and unknown.
- Do not invent causal links, affected assets, target prices, probability, or time horizon.
- A missing or invalid interpretation must display “analysis unavailable” in the selected locale; it must not suppress the original news item or fabricate fallback content.
- Escape untrusted headline/source text in the browser; never render publisher content as HTML.
- Validate the canonical schema and localized field completeness; fail closed for Mother consumption if the analysis digest/schema is invalid.
- Preserve the existing execution boundary: news cannot create direction or authorize orders.

## 8. Acceptance tests

1. Every displayed news item has its own interpretation panel directly beneath it.
2. All required fields are present or explicitly marked unknown/not established.
3. Persian, English, German, and French outputs are complete, natural, and semantically equivalent.
4. Locale switching changes only presentation text, never canonical analysis or Mother payload.
5. A headline relevant to another asset is not misattributed to the selected symbol.
6. Macro, security, regulation, venue, and asset-specific events use the correct transmission channel.
7. Stale, future-dated, missing-source, uncorroborated, and conflicting evidence is disclosed and tested.
8. Mother receives the same item-level canonical interpretation and event IDs that the user sees.
9. Mother can use the information as context/veto only; news-only LONG/SHORT or execution is impossible.
10. No paid API, external LLM, or paid translation service is required.
11. Existing News Radar, market-data, Mother, dashboard, and full regression suites pass.
12. No production release or active service changes until the feature is reviewed, tested, and promoted through the existing release gates.

## 9. Implementation sequence

1. Extend the canonical news finding/brief schema with a versioned item-level interpretation object.
2. Implement deterministic, evidence-grounded explanation builders and a curated glossary/templates for `fa/en/de/fr`.
3. Add schema validation, provenance/digest binding, and fail-closed behavior.
4. Extend the Mother handoff and read-only Command Center evidence/decision trace.
5. Render a compact expandable interpretation directly under each dashboard news item, following the selected locale.
6. Add unit, integration, multilingual parity, browser-render, security, and Mother-consumption tests.
7. Run full regression and review; keep the production release unchanged until all gates pass.

## 10. Existing baseline and reuse

Reuse, do not rebuild:
- `core/market_intelligence/news_brain.py` — `NewsIntelligenceBrain`, `NewsFinding`, `NewsBrief`, source provenance and Mother payload.
- `core/market_intelligence/news_monitor.py` — signed/digest-checked snapshots and append-only news event ledger.
- `web/dashboard.py` — `/api/news` and existing News Radar panel.
- `web/static/dashboard.js` — existing item renderer and four-locale translation catalog.
- `web/mother_chat_v1.py` — bounded read-only news evidence handoff.
- Existing source registry and market profiles.

Current implementation is a deterministic keyword/rule-based baseline, not a general-purpose generative LLM. The new educational explanation layer must accurately describe its evidence and uncertainty and must not claim capabilities it does not have.