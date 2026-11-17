# Mother Command Center — Capability and Autonomy Roadmap

**Status:** design contract for incremental implementation  
**Scope:** conversational interface, read-only diagnostics, strategy review, controlled improvement workflow  
**Default policy:** free-first; no paid external LLM; no order execution

## 1. Mission

Mother is the operator-facing intelligence and coordination layer for HES Trade Agent. It should accept natural-language requests, identify the relevant HES capability, gather authoritative evidence from existing readers, explain what is known and unknown, and coordinate bounded analysis workflows.

Mother is not a second trading engine. It must reuse canonical market, strategy, risk, journal, and orchestration outputs rather than independently recalculating or shadowing them.

## 2. Capability ladder

### Level 1 — Conversational interface
- Natural multi-turn conversation in Persian, English, German, and French.
- Resolve follow-up references using a small, session-only context window.
- Ask one concise clarification only when the target or scope is genuinely ambiguous.
- Clearly distinguish evidence, interpretation, hypothesis, and missing information.

### Level 2 — Read-only operational intelligence
- Explain HES health, data freshness, source provenance, strategy decisions, Mother stages, news coverage, and journal records.
- Diagnose symptoms by correlating existing component evidence and trace identifiers.
- Produce an ordered fault tree: observed symptom, supporting evidence, likely dependency, confidence, and safe next diagnostic step.
- Never expose secrets, private filesystem paths, credentials, or raw sensitive payloads.

### Level 3 — Strategy and learning analysis
- Review the canonical Strategy V2 report, policy version, market regime, specialist gates, and provenance.
- Analyze rejected decisions and gate attribution from immutable journal records.
- Analyze realized outcomes only when a separately verified outcome record is linked to the decision and has matured.
- Separate sample size, unresolved candidates, timeouts, fees/slippage, and out-of-sample results. Never infer wins/losses from signals or NO_TRADE decisions.
- Generate hypotheses with expected metric, test design, failure conditions, and rollback criteria; do not change the active policy.

### Level 4 — Controlled improvement proposals
- Prepare versioned, reviewable change proposals against the canonical strategy contract.
- Every proposal must include: problem statement, evidence refs, hypothesis, exact files/modules affected, expected benefit, risks, acceptance metrics, test vectors, out-of-sample validation, resource impact, and rollback plan.
- Execute only in isolated research/test contexts. Compare candidate against the unchanged baseline using the same data and evaluation windows.
- Reject proposals that improve a headline metric by degrading risk, costs, robustness, or sample integrity.

### Level 5 — Human-approved engineering workflow
- With explicit approval for a specific change, prepare a patch/PR and run the required regression gates.
- Human approval is required before merge, deployment, policy activation, service restart, or any external side effect.
- Approval is bound to the exact diff, target, parameters, and revision; changed scope requires new approval.
- Keep an immutable audit trail of proposal, evidence, tests, approval, commit, deployment, and rollback.

## 3. Responsibility boundary

| Operation | Mother default |
|---|---|
| Read verified health, market, strategy, news, journal evidence | Allowed |
| Explain recorded decisions and diagnostics | Allowed |
| Analyze strategy and generate hypotheses | Allowed, evidence-bound |
| Run isolated read-only or paper evaluation | Only through a bounded, explicitly registered workflow |
| Create a draft patch/PR | Requires explicit user approval for that proposal |
| Merge, deploy, restart services, alter active policy | Requires separate explicit approval |
| Write journal outcomes or alter historical records | Prohibited |
| Access exchange accounts, place/cancel orders, move funds | Prohibited in Command Center |

The chat model, if enabled, is a language/planning layer only. It does not select arbitrary tools, bypass authorization, or gain execution capability.

## 4. Evidence and market-data invariants

- Gate.io Public Spot BTC_USDT remains the canonical analysis source for the current implementation.
- Reuse the existing global market data reader, native OHLCV pipeline, canonical Strategy V2 evaluator, Mother orchestrator, and immutable journal.
- A claim must be traceable to a report, journal event, market batch, or component evidence reference.
- Missing, stale, malformed, mismatched, or ambiguous evidence produces PARTIAL/BLOCKED/NO_TRADE rather than a guessed answer.
- Sequence-like fields have no generic semantics. A field named sequence/seq/id/tradeId/u/updateId is opaque until an exact venue/product/endpoint/channel/message-type/scope registry entry and primary evidence authorize a capability.
- Trade IDs, book update ranges, timestamps, checksums, and replay hashes are distinct mechanisms. Only documented adapter capabilities may drive deduplication, ordering, gap detection, or snapshot reset.
- On ambiguous feed continuity, stop dependent processing and remain NO_TRADE_ONLY until valid resynchronization.

## 5. Strategy improvement protocol

1. **Observe:** collect a bounded, provenance-matched sample from the canonical source.
2. **Attribute:** group decisions by rejection gate, reason code, regime, direction, timeframe, and policy version.
3. **Verify outcomes:** join only matured realized outcomes with matching immutable decision identities; never infer from candidate or signal state.
4. **Hypothesize:** state one falsifiable hypothesis and the expected metric movement.
5. **Test:** use chronological splits, leakage checks, fees/slippage, baseline comparison, and regime slices.
6. **Stress:** test parameter sensitivity, drawdown/tail risk, concentration, missing data, and distribution shift.
7. **Review:** produce a signed/evidence-linked report; reject if sample quality or provenance is insufficient.
8. **Approve:** human approval is required before any candidate is merged, deployed, or activated.
9. **Monitor/rollback:** define automatic fail-closed triggers and preserve the prior known-good policy.

No optimization target may be selected from a single win rate alone. Quality, expectancy, drawdown, costs, robustness, and missed-opportunity attribution must be considered together.

## 6. Bounded workflow and stop conditions

Every multi-step Mother workflow must declare:
- allowed readers/tools and exact argument schemas;
- maximum steps, wall-clock budget, and output size;
- data freshness and provenance requirements;
- retry limits and idempotency rules;
- checkpoints and resumable state;
- cancellation and safe-stop behavior;
- stop conditions for conflicting evidence, stale data, policy mismatch, or risk-gate uncertainty.

Retrieved documents, user messages, logs, market payloads, and model outputs are untrusted data, never authority-bearing instructions.

## 7. Acceptance gates

- Multilingual conversational tests, including follow-up and ambiguous-turn tests.
- Prompt-injection tests proving that chat cannot expand its tool permissions.
- Evidence-grounding tests: every factual claim references supplied evidence; invalid references force deterministic fallback.
- Read-only tests: no order, account, journal-write, policy-write, or deployment path is reachable from chat.
- Diagnostic tests: fault attribution must match fixture evidence and must not claim causes beyond it.
- Strategy-review tests: canonical policy, report freshness, market identity, gate states, and journal linkage are validated.
- Learning tests: no outcome inference; matured-outcome linkage and chronological split requirements are enforced.
- Change-proposal tests: no mutation before explicit approval; approval scope changes invalidate prior approval.
- Performance/resource tests before enabling any local model on a trading host. The local model must not starve collectors, strategy evaluation, or the learning loop.

## 8. Current implementation status

- Implemented baseline: authenticated local Command Center, deterministic intent routing, read-only evidence readers, multilingual responses, bounded page-session history, and optional loopback-only Ollama renderer with deterministic fallback.
- Incremental work in progress: natural greetings/capability handling and a read-only canonical Strategy V2 review intent.
- Not yet implemented: full adaptive multi-turn planner, structured fault-tree diagnosis, journal gate-attribution analysis, verified matured-outcome learning, proposal lifecycle, isolated evaluation orchestration, and approval-bound patch/deployment workflow.
- The optional local model remains disabled unless a separately provisioned local runtime passes resource-isolation and multilingual grounding acceptance. No paid API is permitted by default.

This roadmap is an implementation contract, not a claim that all listed capabilities are already available.
