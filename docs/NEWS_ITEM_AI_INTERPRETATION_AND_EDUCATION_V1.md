# News Item AI Interpretation & Market Education — V1

Status: **Implemented V1 candidate in PR #501; exact-head CI passed; review and parent acceptance pending**
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

## 11. Candidate implementation status — 2026-11-14

- Implemented on `feat/news-item-interpretation-education-v1`, PR #501, stacked on PR #500.
- Latest exact code/test head: `f200767188e3b7712f44c62021b7e7ed98ef1179`. Exact-head GitHub Actions: **3/3 passed** — full repository pytest (**1,275 passed + 82 subtests**), browser render smoke, and dashboard native-path/API contract (**128 passed + 19 subtests**). The final change adds a distinct localized relevance-scope label in fa/en/de/fr and regression coverage; the full test suite and both dashboard checks were rerun on this exact code/test head.
- V1 remains deterministic/template-based, not a generative LLM. Headline sentiment is not treated as causal market direction: potential price effect stays mixed/unknown until independent event and market evidence can establish direction.
- Internal caveat codes are rendered as localized explanations rather than exposed to users.
- No production release, service restart, policy activation, or execution setting has been changed.
- Mother now fails closed unless every required localized field is non-empty in all four locales, score semantics are explicit, item identity is valid, and `mother_use` explicitly forbids news-only trade authority while requiring independent market confirmation.
- Frontend regression covers per-item rendering, required educational fields, locale re-rendering, safe `textContent` insertion, and the dedicated translated relevance-scope label.
- Remaining release gates: pair-level acceptance of the exact candidate, PR #500 parent acceptance and its separate recovery/strategy/risk gates, semantic translation review, broader market-profile validation, and controlled release regression. No third-party reviewer is assumed; this project is being handled by the user and assistant only.


## 12. Pair-level hardening and market-profile review — 2026-11-14

- The translated market field is deliberately labelled **target market context**, not as proof that the headline affected the target asset. Relevance scope separately distinguishes direct symbol/tag matches, market/category relevance, and unconfirmed relevance.
- Market-family names are localized for crypto, US equities, Iran equities, FX/Forex, commodities and metals. Tickers and canonical venue identifiers remain unchanged.
- Curated economic transmission profiles cover monetary policy, regulation, security/counterparty risk, exchange operations, macroeconomics, crypto flows, equities, FX and commodities in all four locales.
- The source headline is explicitly identified as the source headline and remains in its original language. No unsupported machine translation of arbitrary publisher text is claimed. Educational explanations, market-family names, labels, caveats and disclaimers are localized.
- Frontend validation now requires every required localized content field and every translated label before rendering. An incomplete interpretation falls back to the selected locale's “analysis unavailable” message; it cannot crash the news list or silently render a partial panel.
- Mother validation now checks unique non-empty item IDs, source title/source presence, freshness enum, category shape, finite [0,1] item and interpretation scores, allowed effect/relevance/impact semantics, source-fact/headline equality, all required non-empty localized fields and labels, and explicit context-only/no-trade-authority semantics.
- Mother confirmation evidence refs include the news context digest, snapshot digest, brief digest and each news item ID. The same versioned interpretation is present in the confirmation specialist payload.
- Regression tests cover all market-profile aliases, all nine economic transmission categories across fa/en/de/fr, unknown-market fallback, localized target-context wording, incomplete localized labels, safe rendering, fail-closed Mother validation and item-level provenance.
- Exact tested code/test head: `d6c21e37fad843ea1b77068d703deb93720a4151`. Exact-head GitHub Actions: **3/3 PASS** — full repository pytest **1,279 passed + 82 subtests**; dashboard native-path/API contract **128 passed + 19 subtests**; browser render smoke PASS.
- The current VPS dashboard snapshot still uses the previously deployed news schema and does not yet contain `hes.news_item_interpretation.v1`. This is expected: PR #501 is stacked on the unmerged PR #500 and has not been deployed. The new Mother reader will fail closed on that old snapshot until the controlled release includes the new producer and consumer together.
- No active dashboard release, news collector, service, policy/ruleset, paper execution permission, or live execution setting was changed.


## 13. Event corroboration and coverage-veto hardening — 2026-11-14

- Mother now receives the news brain's validated `event_cluster_assignments` and `high_impact_event_clusters` from the digest-bound brief provenance.
- Each selected news item carries its event-cluster ID and, when the cluster is high-impact, the corroborating item/source counts. The confirmation specialist exposes these fields in its payload and adds item and event-cluster IDs to its evidence references.
- Malformed or duplicate event-cluster assignments and malformed high-impact cluster counts fail closed.
- `NEWS_SOURCE_COVERAGE_INCOMPLETE` is now consumed as a confirmation veto, alongside high-impact, suspect timestamp and unverified source flags. Partial profile coverage without a source failure is not automatically treated as a failure; the monitor's explicit veto semantics remain authoritative.
- Regression tests cover valid event-cluster/corroboration handoff and incomplete-source-coverage veto behavior.
- Latest exact tested code/test head: `bebdbadceb9a3143edd14efa8414d77cead4ae46`. Exact-head GitHub Actions: **3/3 PASS** — full repository pytest **1,280 passed + 82 subtests**; browser render smoke PASS; dashboard native-path/API contract PASS.
- PR #501 remains stacked on PR #500 and is not deployed. The current live News Radar snapshot has no item interpretation object yet, so the new Mother reader correctly rejects it until the producer and consumer are promoted together.


## 14. Real-browser news panel regression — 2026-11-14

- Extended the existing Playwright dashboard smoke to inject a versioned news snapshot fixture and verify one expandable interpretation panel per item.
- Browser assertions verify the English, German, Persian and French headings/field labels and content re-render after locale changes.
- An incomplete localized item must show the locale-specific unavailable message rather than partial content.
- A hostile headline containing an `img/onerror` payload remains literal text: no image element is created and no injected handler executes.
- The full browser smoke also continues to verify chart, persisted-feed and no-live-execution contracts.
- Latest exact code/test head: `ff0d818aad49c196a84745aefc0b74b43e64a158`. Exact-head CI **3/3 PASS** — full repository pytest **1,280 passed + 82 subtests**, browser render smoke PASS (including the new news-panel assertions), dashboard native-path/API contract PASS.


## 15. NewsBrain market-profile coverage — 2026-11-14

- Extended the market relevance aliases so US equities, Iran equities, Forex and metals/commodities resolve their intended market-family vocabulary rather than relying only on a target symbol match.
- Added commodity event terms and Persian equities vocabulary to the existing deterministic classifier; the existing curated economic education profiles are now reachable from these market contexts.
- Added end-to-end NewsIntelligenceBrain tests for crypto, US equities, Iran equities, Forex and metals. Each fixture must survive relevance filtering, select its expected economic category, retain market/category-level relevance (not claim a direct symbol match), and provide all four localized educational fields.
- This is still deterministic, evidence-bounded classification; it does not infer an asset-specific causal price direction from a category keyword.


## 16. Exact-head cross-market regression result — 2026-11-14

- Latest code/test head: `a5fbf47357018171453448b4dded1e00af3aedf9`.
- Documentation-only head: `d4c42df13d69fdd3887418e49c63370d25901233`.
- GitHub Actions ran on the latest branch update and all three required workflows passed: full repository pytest **1,281 passed + 82 subtests**, browser render smoke PASS, dashboard native-path/API contract PASS.
- Cross-market NewsIntelligenceBrain tests now exercise crypto, US equities, Iran equities, Forex and metals. They verify relevance survives filtering, the intended economic category is selected, and no direct symbol impact is asserted without a symbol match.


## 17. Mother Command Center chat integration — 2026-11-14

- The read-only `NEWS_CONTEXT` intent now consumes the same per-item interpretation in fa/en/de/fr and exposes target-market context, economic mechanism, transmission channel, time horizon, what to monitor, educational concept, uncertainty, potential effect and relevance scope as evidence claims.
- Chat consumption requires the exact interpretation schema, matching source headline, allowed effect/relevance semantics, explicit context-only/no-trade-authority contract, and a complete localized field/label set for the selected language.
- Stale/unverified freshness is not used to produce an explanation. News veto flags and partial source coverage are surfaced and downgrade the response to PARTIAL; malformed brief/findings/locale containers and invalid authority semantics fail closed.
- The French news-status label was reviewed to use natural wording (`Flux d’actualités`).
- Tests cover Persian, English, German and French chat responses, complete educational claims, incomplete translations, invalid trade authority, stale items, veto flags and malformed brief/findings/locale containers.
- Exact tested implementation head before the final malformed-brief assertion-only test commit: `e4ea891b5c10c0497271668b03cb690361f524f7`; CI 3/3 PASS with **1,284 passed + 82 subtests**. A final test-only commit adds the malformed-brief assertion and is being revalidated on the latest branch head.


## 18. Final chat and presentation regression — 2026-11-14

- Mother Command Center chat now exposes all useful educational claims from the same interpretation: target-market context, economic mechanism, transmission channel, time horizon, what to monitor, educational concept, uncertainty, potential effect and relevance scope.
- Chat validates the selected locale's complete fields/labels, source headline identity, allowed semantics and context-only authority contract. Stale items are not used; veto flags and partial coverage downgrade the response; malformed brief/findings/locale payloads fail closed.
- Added tests for fa/en/de/fr chat output, invalid authority, incomplete/malformed translations, malformed brief/findings, stale-item suppression and veto surfacing.
- Added responsive interpretation-panel styling for desktop/mobile, RTL alignment and visible keyboard focus.
- Latest exact tested code/test head: `ec59d9ac5d6a5bb62b3cbbd3bc759f83ebcf6d65`. Exact-head GitHub Actions **3/3 PASS** — full repository pytest **1,284 passed + 82 subtests**, browser render smoke PASS, dashboard native-path/API contract PASS.
- The prior note about revalidation is superseded by this exact-head PASS.


## 19. RTL and responsive browser acceptance — 2026-11-14

- Extended Playwright assertions to verify interpretation rows follow RTL when Persian is selected while the chart remains LTR.
- At a 390px mobile viewport the interpretation rows collapse to one column; at a 1440px desktop viewport they use the intended two-column layout.
- Exact tested code/test head: `cadef2ec71dffbe0118fe8dd3b6991adb3858931`. Exact-head CI **3/3 PASS** — full repository pytest **1,284 passed + 82 subtests**, browser smoke PASS including RTL/mobile/desktop assertions, dashboard native-path/API PASS.
