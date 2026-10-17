# HES Trade Agent — Weighted Acceptance Evidence Score

Audit date: 2026-10-18 (+03:30)  
Repository: `beheshti2025hesam-prog/btc_tabdeal_public_test`  
Scoring baseline code/test SHA: `65b58f57987ccf8c60ebe005cbd5b66ce438dc4a`  
Pull request: [#308](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/pull/308) — OPEN / DRAFT / NOT MERGED  
Safety disposition: **HOLD / NO TRADE**

## What this percentage means

This is an **acceptance-evidence maturity score**, not a claim that the same percentage of features is finished, profitable, or safe to operate. A workstream earns points only for evidence already present. Unknown or unverified acceptance gates do not earn points. The score does not override hard release gates: operational acceptance remains unpassed, so the project stays HOLD / NO TRADE regardless of the numeric score.

Weights are risk-and-effort estimates for project-wide planning, not measured historical effort. They are explicit and sum to 100; revise them only with a documented project-scope/effort rationale.

## Scoring scale

- **0/4 — No usable acceptance evidence** for the workstream.
- **1/4 — Artifacts or static evidence exist**, but behavior is not demonstrated sufficiently.
- **2/4 — Implementation and focused tests/evidence exist**, but end-to-end or adversarial acceptance remains open.
- **3/4 — Exact-commit CI and relevant integration evidence pass**, with bounded, explicitly documented residuals.
- **4/4 — Independent acceptance completed** against all defined gates, with reproducible evidence and no open release-critical blockers.

For each workstream, earned points = weight × maturity level ÷ 4. The project score is the sum of earned points. An unverified criterion is not silently counted as passed.

## Weighted workstream register

| Workstream | Weight | Level / 4 | Earned points | Evidence and remaining acceptance gate |
|---|---:|---:|---:|---|
| Core/domain architecture | 10 | 2 | 5.00 | Core/domain modules and tests exist. Full project-DNA capability map, contracts, and end-to-end integration audit remain open. |
| Data ingestion and collectors | 12 | 2 | 6.00 | Collector/ingestion adapters and focused tests exist; exact-head integration CI includes ingestion tests. Reproducible live capture, durable-write verification, and real disconnect/gap recovery remain unaccepted. |
| Sequence integrity | 12 | 2 | 6.00 | Strict non-negative integer/ASCII-digit parsing, duplicate/conflict handling, ordering checks, state bounds, and regression tests exist. New adversarial regressions now run in forward integration CI. Hash-valid semantic-invalidity, source artifact deletion/reordering/tampering, state rotation/recovery, and full downstream veto proof remain open. |
| Decision and risk gate | 12 | 2 | 6.00 | Decision/firewall/risk code and tests exist. End-to-end proof that every invalid, stale, conflicting, or anomalous input vetoes all signal/risk/decision paths remains open. |
| Strategy and feature engineering | 10 | 2 | 5.00 | Strategy/feature tests and backtest workflows exist. Costs/slippage, fully specified out-of-sample acceptance, and blind-forward evidence are not all accepted. |
| Evidence and source identity | 8 | 2 | 4.00 | The 42-record reconciliation artifact and SHA-256 lock are checked by a green workflow. That workflow validates manifest structure/counts/uniqueness and locks manifest bytes; it does **not** independently fetch and re-hash all original source blobs. Independent human review remains absent. |
| CI and reproducibility | 6 | 3 | 4.50 | On baseline SHA `65b58f57987ccf8c60ebe005cbd5b66ce438dc4a`, GitHub API returned **26/26 completed successful check runs** whose `head_sha` exactly matched the baseline. Forward integration CI passed **142 tests**, including the newly added sequence-adversarial and collector-sequence tests. This is not independent project acceptance. |
| Live exchange protocol | 10 | 1 | 2.50 | REST schema observations and protocol notes exist. Raw WebSocket message captures, Spot depth snapshot bridging/resynchronization, Futures U/u/pu continuity, and disconnect/reconnect semantics remain open. |
| Runtime, deployment, and security | 6 | 1 | 1.50 | Runtime/deployment files exist. Configuration, permissions, persistence, monitoring, recovery, and the full operational security boundary have not been independently accepted. |
| Evaluation and learning loop | 5 | 1 | 1.25 | Evaluation/forward workflows and files exist. End-to-end attribution from rejected/lost decisions to evidence-backed diagnosis, without bypassing evidence locks, remains unverified. |
| Multi-agent / multi-market transferability | 3 | 1 | 0.75 | Generalized architecture artifacts exist. Role/capability matrix, adapter contract, and additional-market/venue integration proof remain open. |
| User interface / command center | 2 | 0 | 0.00 | The audited tree summary does not establish the actual UI entrypoint or prove it is advisory-only. Identify and verify before scoring. |
| Operational acceptance | 4 | 0 | 0.00 | Not passed. Independent review, all release-critical gates, staged observation, and explicit release approval are outstanding. |
| **Total** | **100** |  | **42.50 / 100** | **Evidence maturity: 42.5%. Release: NOT ACCEPTED.** |

## Reproducibility of the score

```text
score = sum(weight_i * maturity_i / 4)
      = 42.50 points out of 100
```

The score can be recalculated directly from the register. The workstream weights are planning judgments; the evidence levels are bounded by the cited repository state and the listed open gates. Do not relabel this score “feature completion,” “production readiness,” or “trading readiness.”

## Exact-commit CI record

- Baseline code/test SHA: `65b58f57987ccf8c60ebe005cbd5b66ce438dc4a`
- Exact-head GitHub check-runs: 26 completed, 26 success, 0 pending, 0 failed.
- Forward integration workflow: [run 39067120539](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/39067120539) — **142 passed**; explicit execution/historical firewall scan passed; collector and execution startup are forbidden in that workflow.
- A prior run on the immediately preceding workflow-edit commit failed at test collection because `websocket-client` was not installed in that job. The workflow dependency was corrected, and the subsequent baseline SHA above passed. The initial failure is retained as evidence of the actual fix, not hidden.
- The baseline check-run `head_sha` values were verified via GitHub’s check-runs API, rather than inferring exact-head status from the pull-request merge commit.

## Remaining blockers before any release decision

1. Obtain independent review of source identity and critical decision/risk boundaries.
2. Extend adversarial tests for hash-valid semantic invalidity and artifact deletion, reordering, payload mutation, and manifest tampering.
3. Prove out-of-order/anomalous records cannot reach signal, risk, or decision inputs before reconciliation.
4. Demonstrate authorized raw WebSocket protocol behavior, including reconnect and gap recovery; REST schemas alone are insufficient.
5. Complete runtime/security and UI advisory-only boundary reviews.
6. Complete staged observation and explicit release approval only after all applicable gates pass.

**Disposition remains `HOLD / NO TRADE`.** Green CI and a 42.5% evidence-maturity score do not authorize merging, live collection, execution, or trading.
