# HES NO_TRADE Counterfactual Maturity V2 — 2026-11-19

## Purpose
Promote the existing append-only NO_TRADE outcome tracking from market-movement reporting to evidence-qualified, multi-horizon decision-quality review. The objective is to distinguish genuinely prudent NO_TRADE decisions from candidate-generation/confirmation false negatives without creating execution authority.

## Pre-release production baseline (observed 2026-11-19 UTC)
- Immediately before the NO_TRADE V2 release, the active immutable release was `09f660d625df3f8964ba8ddd20c9a9cf8a400f19`.
- `hes-strategy-learning-loop.service` was active and refreshing the existing 1h/4h/24h neutral tracker and 24–48h matured validator.
- That prior release's matured validator did **not** contain the 1m structure-only shadow replay.
- The V2 candidate added the 1m shadow evaluator to the matured validator; its production activation is recorded below.
- Pre-release report snapshot: 96 decisions in the matured cohort; 95 gap-free 24h horizons complete; 1 incomplete; tracker boundary mismatches 0.
- At the pre-release baseline, qualified directional counterfactuals were 0. A gate-rejected proposal reached hypothetical TP, but was diagnostic only—not a missed trade.
- Pre-release safety flags: `policy_mutation_enabled=false`, `execution_enabled=false`, `orders_placed=false`.

## V2 candidate: structure-only 1m shadow replay
- Independently detect a structural candidate from frozen decision-time evidence, separate from the strategy proposal direction.
- Candidate eligibility requires `candidate_valid=PASS`, `structural_event_present=PASS`, direction LONG/SHORT, and regime-direction alignment.
- Entry is the first fully closed Gate.io Spot 1m candle whose open time is at/after the immutable decision timestamp.
- Stop uses decision-time swing low/high; target is frozen at 3R. No future-derived geometry or best-price entry.
- Evaluate 1h/4h/24h only on complete contiguous closed 1m candles. Same-candle stop/target collision is conservatively a stop and retains an ambiguity flag.
- Missing bars remain `SHADOW_DATA_GAP`/`SHADOW_PENDING`; no interpolation.
- Spot-only short price paths are explicitly `NOT_TESTABLE_FROM_SPOT` for executable short economics.
- Candidate events may overlap; target-hit review is deduplicated into descriptive clusters while preserving event-level records.
- Shadow target hits remain `POTENTIAL_OVERFILTERED_CANDIDATE_REVIEW_ONLY`, never `MISSED_PROFIT` or `AVOIDED_LOSS`.

## Observed candidate-only shadow evidence (isolated replay against copied VPS evidence; not production-active)
- 20,269 valid 1m rows; zero invalid open-time records, duplicate open times, or gaps.
- 96 matured decisions: 56 without an independent candidate; 40 with a structure-only candidate.
- 29 candidates had valid shadow geometry; 11 were rejected because the frozen stop was already on the wrong side of the first executable entry.
- Two unique 24h target-hit review clusters were identified, both LONG. These are review cases only; no actual missed-profit claim is made.
- At 24h, the 24 evaluated LONG paths comprised 22 stop hits and 2 target hits. This is a small correlated diagnostic cohort, not a strategy win rate or portfolio performance statistic.
- Cost sensitivity (10/20/30/50 bps round-trip) is explicitly assumption-based; no verified account/instrument cost model exists.
- Evidence counts above are from the exact isolated replay used for PR #535; they must not be mixed with earlier candidate-run counts.

## Required interpretation and safety
- A price move without a frozen directional candidate and valid decision-time geometry is context only.
- A rejected proposal that later reaches TP/SL is not automatically a missed trade/avoided loss; its failed gates remain decisive.
- `MISSED_PROFIT` and `AVOIDED_LOSS` require the full frozen candidate, confirmation, structure, risk and execution-instrument evidence gates.
- Do not infer human fear from NO_TRADE counts.
- No automatic gate relaxation, parameter tuning, strategy promotion, execution enablement, or order placement.
- Preserve original decision and outcome ledgers append-only; use deterministic event/horizon IDs and source hashes.

## Validation
- Exact isolated focused suite: 45 passed.
- Exact-head GitHub Actions for PR #535: 33/33 check runs succeeded.
- Active immutable release focused suite: 31 passed; its source does not include the new 1m shadow module.
- The V2 evaluator was merged to `main` in PRs #535 and #536, then released from a minimal branch based on the prior active production baseline. The exact production release is recorded below.
- Exact-head CI, focused regression, immutable manifest verification, isolated service and symlink rollback rehearsal, endpoint smoke, and controlled learning-loop restart were completed; see the production deployment record below.

## Portability
The matured validator now resolves its data root from `HES_DATA_ROOT` (default `/opt/hes-trade-agent`) so it can be validated on isolated copies and installed at a new VPS path without hard-coded data locations.

## Post-merge immutable-code-root isolation hardening — 2026-11-19
- A second-pass release rehearsal found that the first V2 candidate conflated the shared mutable data root (`HES_DATA_ROOT`) with the Python code import root. In a VPS where `/opt/hes-trade-agent` is a dirty checkout, inserting that data root into `sys.path` could shadow modules from `/opt/hes-trade-agent/current` and violate immutable-release provenance.
- Follow-up correction separates `CODE_ROOT` (resolved from this validator's immutable release path) from `DATA_ROOT` (shared evidence path). Only `CODE_ROOT` is inserted into `sys.path`; data files remain under `DATA_ROOT/data/forward`.
- Added a regression test that sets an unrelated temporary `HES_DATA_ROOT` and proves strategy-family imports still resolve from the exact code release. Focused suite after correction: 46 passed.
- Replayed current copied VPS evidence with the corrected code: 94 decisions in the 24–48h cohort; 93 complete gap-free 24h horizons; 0 tracker boundary mismatches; 33 independent structure candidates; 29 evaluated shadow geometries; 4 invalid stop geometries; 20,386 closed 1m rows with 0 duplicate open times, 0 gaps and 0 invalid open-time rows. Two 24h LONG target-hit clusters remain review-only; actual missed-profit claim remains false.
- Import provenance was verified: `forward.strategy_family_router_v1` loaded from the isolated exact-commit source tree, not the mutable VPS checkout. No production pointer or service was changed.
- The code-root isolation correction was merged through PR #536 after 32/32 exact-head checks passed; it is included in the production release below.

## Production deployment record — 2026-11-19

- To avoid implicitly deploying the separately gated Documentation Library implementation from PR #532, the production release was built from the active baseline `09f660d625df3f8964ba8ddd20c9a9cf8a400f19` plus only the NO_TRADE V2 files, through PR #538 on `release/production-baseline-2026-11-19`.
- Release commit: `4c9a0f30c9aac67c6d711fe3699f55820a9b1322`. The merge tree exactly matched the tested PR head. The release contains 774 tracked files.
- Immutable release path: `/opt/hes-trade-agent/releases/4c9a0f30c9aac67c6d711fe3699f55820a9b1322`.
- Manifest verification: PASS, 774 files checked. Manifest SHA-256: `d78a8b50ae96d6e08077ef67c633610c8fb9f61acf5d7c0a9e0b72d2c69fd3b1`.
- Exact release-branch validation: 46 focused NO_TRADE tests passed; full repository suite 1,606 passed plus 84 subtests; 3/3 release-branch CI checks passed. PR #535 and #536 exact heads also passed their required 32/32 checks.
- A transient systemd rehearsal ran the candidate Learning Loop against a copied data root. It completed a cycle and reported `learning_code_release_id=4c9a0f30c9aac67c6d711fe3699f55820a9b1322`, `mode=READ_ONLY_HYPOTHESIS_ONLY`, and all policy/execution/order flags false.
- Candidate symlink activation and rollback were rehearsed in a separate staging symlink. The candidate reported its own release ID; after atomic rollback the prior release ID was reported. The rehearsal symlink was removed. The production `current` pointer was not changed during this rehearsal.
- Controlled production promotion: at 2026-11-19 14:15:49 UTC, `/opt/hes-trade-agent/current` was atomically switched from `09f660d625df3f8964ba8ddd20c9a9cf8a400f19` to `4c9a0f30c9aac67c6d711fe3699f55820a9b1322`. Only `hes-strategy-learning-loop.service` was restarted. The dashboard service and market-data collectors were not restarted.
- Post-start provenance: `strategy_learning_v1_report.json` identified the new release SHA. The report remained `READ_ONLY_HYPOTHESIS_ONLY`; `policy_mutation_enabled=false`, `execution_enabled=false`, `orders_placed=false`.
- First production V2 report after promotion: 94 matured decisions; 93 complete gap-free 24h horizons; 0 tracker-boundary mismatches; 34 independent candidates; 30 evaluated shadow geometries; 4 invalid stop geometries; 2 LONG 24h target-hit review clusters. `actual_missed_profit_claim=false`.
- At that report snapshot, the 1m feed contained 20,405 closed rows with zero duplicate open times, gaps or invalid open-time records. The Gate.io 1m collector and integrity timer remained active.
- Post-deploy dashboard smoke: `/healthz`, `/api/strategy-v2` and `/api/journal` returned HTTP 200; dashboard health remained `NO_TRADE_ONLY`, with `execution_enabled=false` and `orders_placed=false`.
- Canonical journal SHA-256 and lock inode/ownership/mode were unchanged across the controlled pointer switch and Learning Loop restart. The journal remained append-only and was not modified by the validator.
- The Learning Loop completed a second post-deploy cycle at 14:21:12 UTC, confirming the recurring five-minute refresh under the new immutable release.
- No trading activation, order placement, strategy promotion or automatic gate tuning occurred. The two target-hit clusters remain review-only; they are not proven missed trades or realized profit.
