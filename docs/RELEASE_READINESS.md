# HES Trade Agent — Release Readiness & Delivery Control

**Checkpoint date:** 2026-10-26  
**Target delivery:** 2026-11-19  
**Release disposition:** **HOLD — NO_TRADE_ONLY**  
**Scope:** Documentation and release-control contract; this document does not authorize merge, deployment, service activation, credentials, or trading.

## 1. Purpose and source of truth

This is the release decision checklist for the existing HES Trade Agent repository. It is not a second implementation plan or a replacement application. Before changing code, search the existing repository, PR dependency stack, tests, workflows, and checkpoints; reuse existing contracts and components. Extend an existing path only when a documented gap requires it.

- GitHub repository and immutable commit/CI evidence are technical truth.
- Master Checkpoint is the concise project map and current decision record.
- Chat is discussion history, not proof that a change, test, deployment, or runtime action happened.
- One VPS exists. Never plan against or invent a second VPS.
- Fixed target: **2026-11-19**. Risk checkpoint: **2026-10-26**; overdue/open gates must be escalated as schedule risk, not silently waived.

## 2. Locked architecture and non-negotiable boundaries

1. Use one validated global market-data path for charts, candles, and analysis. The chart and analysis must consume the same validated batch/provenance; do not add a parallel frontend or second candle path.
2. The exchange adapter is for execution and order status only. Do not reopen exchange candle/volume/sequence reconciliation unless new evidence demonstrates an execution-relevant defect.
3. Existing dashboard candidate: `web/dashboard.py`; PR #346 and downstream integration candidates are not proof that the production frontend repository/path is identified or deployed.
4. Missing, stale, gapped, malformed, mismatched, or unapproved evidence fails closed.
5. Strategy/structure/confirmation/risk/execution-mapping approvals are independent. Unknown risk context or unapproved symbol mapping means **NO_TRADE**.
6. Paper, shadow, soak, and CI evidence are distinct. A test passing on a candidate SHA does not prove production readiness or profitability.
7. No secrets, live orders, account actions, service changes, VPS mutation, deployment, or production activation as part of documentation work.

## 3. Current evidence and honest status

The 2026-10-25 checkpoint reports 414/414 tests and short sampled-feed checks. These are historical reported results, not fresh verification for this checkpoint. Do not relabel them as newly rerun.

Open evidence gaps recorded in the current project record:
- exact remote commit/runtime lineage and clean-worktree state on the sole VPS;
- completed, independently audited 24-hour data-only observation and reconnect/restart fault-injection evidence;
- current VPS service/health and permitted deployment target verification;
- proof of the real production frontend entry/repository and end-to-end canonical batch → analysis → risk path;
- approved risk context and execution symbol/instrument mapping;
- independent review and reconciliation of stacked/overlapping Draft PRs, including #297, #346, #362 and related candidates;
- controlled OS/package-source audit and safe update plan where applicable.

A candidate PR's own test counts and claims must be checked against exact head SHA, workflow conclusion, artifact/hash/provenance, and relevant test scope. Do not treat skipped checks as passes.

## 4. Release gates (all required; no implicit waivers)

| Gate | Required evidence | Failure disposition |
|---|---|---|
| G0 — Scope & lineage | Actual repository, branch, exact SHA, dependency ancestry, clean/known worktree | HOLD; no guessed SHA |
| G1 — Build & tests | Required CI on exact proposed head; full relevant regression and negative tests | HOLD; fix on candidate branch |
| G2 — Data integrity | Canonical source identity, closed/fresh candles, same-batch chart/analysis, gaps/duplicates/numeric/provenance rejection | NO_TRADE |
| G3 — Runtime resilience | Disconnect/reconnect and restart/fault injection; bounded recovery; durable logs and hashes | HOLD until independently audited |
| G4 — Frontend integration | Real entrypoint identified; browser evidence shows candles; displayed chart and analysis share the same validated batch | HOLD; no parallel app |
| G5 — Decision safety | Structure/confirmation/risk providers approved; unknown/missing values fail closed; negative tests block bypass | NO_TRADE |
| G6 — Execution boundary | Venue contract, symbol mapping, instrument rules, idempotency, order-status/fill reconciliation, paper/shadow and fault evidence | Execution OFF |
| G7 — Operations/security | Sole VPS identity and access verified; source/package integrity reviewed; rollback/health/SSH/firewall checks documented | No change/deploy |
| G8 — Review & release | Independent review, non-overlapping PR stack, all required checks green, operator/rollback plan, explicit release decision | Do not merge/deploy |

A gate may be marked PASS only when the evidence is linked and tied to the exact SHA/run. “Implemented”, “reported”, “skipped”, and “not checked” are not PASS.

## 5. Delivery plan — protect 2026-11-19

### By 2026-10-26 (risk checkpoint)
- Reconcile the active PR stack and identify the smallest non-overlapping dependency path.
- Verify whether the sole VPS/desktop connection is actually available; capture runtime identity and SHA before touching anything.
- Mark every gate PASS / FAIL / BLOCKED with evidence. No deadline-based waiver.

### 2026-10-27 to 2026-11-02 — establish reproducible evidence
- Resolve repository/runtime lineage and exact-head CI.
- Complete the controlled source/reader/dashboard tests, including negative cases.
- Start/continue a read-only 24-hour observation only when its exact code lineage is known; preserve raw logs and hashes.
- Identify the real frontend and allowed deployment target. No deployment yet.

### 2026-11-03 to 2026-11-09 — integration and resilience
- Complete independent soak audit and reconnect/restart fault injection.
- Prove same-batch chart/analysis provenance in the actual intended runtime.
- Complete risk-context and venue/symbol mapping evidence; keep NO_TRADE wherever unknown.
- Review OS/package integrity and prepare a rollback-tested operational plan.

### 2026-11-10 to 2026-11-15 — release candidate
- Reconcile PR ancestry/overlaps; run required CI against the final release-candidate SHA.
- Complete independent safety review and paper/shadow checks where authorized.
- Produce release notes, known limitations, configuration/secret handling instructions, health checks, rollback procedure, and operator runbook.

### 2026-11-16 to 2026-11-18 — go/no-go
- Freeze scope; only release-blocking fixes allowed.
- Re-run required checks on the exact final SHA and verify artifacts/hashes.
- Perform explicit go/no-go review. If any mandatory gate is open, do not represent the app as production-ready; report the specific blocker and recovery plan.

### 2026-11-19 — target delivery
- Deliver only the scope that has passed the release gates and whose deployment/runtime evidence is verified.
- Trading remains disabled unless separately and explicitly approved after all execution gates pass. A software delivery date is not trading authorization.

## 6. Anti-duplication and long-life maintenance rules

- Search for an existing module, API route, schema, test, workflow, and documentation page before creating another.
- Extend the canonical path; do not create a second dashboard, candle model, data adapter for analysis, or competing checkpoint.
- Keep decisions in this file/checkpoint and link the underlying PR/CI evidence rather than copying long implementation narratives.
- Every evidence record should include date/time, exact commit SHA, workflow/run URL, artifact/hash where applicable, result, scope, and limitations.
- Version contracts when semantics change; never silently reinterpret historical data or retrofit new code claims onto old runs.
- Use explicit statuses: **PASS**, **FAIL**, **BLOCKED**, **NOT RUN**, **SKIPPED**. Unknown is not success.
- No arbitrary thresholds or strategy tuning to make a gate pass. Changes to decision policy require fresh forward-only/out-of-sample evidence and independent review.
- Prefer deterministic offline tests; live checks must be bounded, read-only unless separately authorized, and must never place orders.
- Keep dependencies, credentials, and deployment configuration minimal; document ownership, update cadence, rollback, and end-of-life decisions.

## 7. Release decision at this checkpoint

**HOLD / NO_TRADE_ONLY.** The available repository record does not establish all mandatory release gates as passed. In particular, the 24-hour independently audited soak, production frontend/runtime lineage, approved risk context, execution mapping, and independent PR-stack review remain unresolved or unverified. The delivery target remains 2026-11-19; prioritize evidence that closes these blockers and do not spend time re-solving already-settled candle sequence semantics.
