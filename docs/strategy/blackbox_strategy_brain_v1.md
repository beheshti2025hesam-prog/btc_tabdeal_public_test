# HES Blackbox Strategy Brain V1

## Mission
Blackbox is HES's proprietary, evidence-derived strategy research brain. Its strategy hypotheses must emerge from HES's own timestamped Gate.io market observations, gate-attributed decisions, matured paper outcomes, counterfactual NO_TRADE reviews, and reproducible model experiments. It is not a repackaged indicator preset and it must not claim novelty beyond what has been demonstrated.

## Reuse before invention
Blackbox must reuse the existing Gate.io data readers, candle/feature pipeline, market-regime models, strategy-family journals, learning loop, Adaptive Hybrid evidence, market-structure and Order Block providers, and external confirmation/risk gates. It must not create a parallel candle store, outcome ledger, generic sequence comparator, or independent execution stack.

## Brain design
1. **Context encoder:** causal, closed-candle, multi-timeframe state with source/session provenance and a common as-of timestamp.
2. **Regime memory:** consume existing unsupervised regime labels as descriptive context only; do not treat clusters as predictive labels.
3. **Pattern discovery:** propose candidate motifs and conditional hypotheses from structure, volatility, liquidity, volume, and strategy-family evidence. Every hypothesis records discovery window, source hashes, feature definition, and falsification rule.
4. **Outcome learner:** learn only from gate-approved, matured, provenance-complete paper outcomes. Rejected proposals and NO_TRADE counterfactuals remain separate datasets and cannot be mixed into trade win-rate labels.
5. **Meta-policy research:** compare Blackbox hypotheses with constituent families and Adaptive Hybrid using chronological purged walk-forward and locked out-of-sample evaluation, verified costs, slippage, drawdown, calibration, and opportunity coverage.
6. **Decision proposal:** research-only LONG/SHORT/NO_TRADE proposals. The independent confirmation and Risk Gate remain mandatory and cannot be bypassed or trained away.
7. **Memory and evolution:** immutable model registry, versioned feature schema, append-only experiment ledger, deterministic replay, drift checks, rollback, and bounded compute/storage budgets.

## Initial implementation boundary (0.1)
The initial implementation is a read-only readiness evaluator. It verifies the hashes and safety metadata of the existing HES regime and movement model artifacts and reads the canonical strategy-learning report. It emits no trade candidate and always returns NO_TRADE. This is intentional: the current movement classifier is a coarse market-direction forecast, not a trade-outcome model, and the matured gate-approved outcome count is currently zero.

## Promotion gates
- Minimum 100 resolved gate-approved matured outcomes is only an initial data sufficiency floor, not sufficient evidence for promotion.
- Require multiple independent market periods and regimes, chronological purged walk-forward, locked OOS, independent forward paper observation, verified venue costs and slippage, positive net expectancy, controlled drawdown, calibrated confidence, and baseline superiority.
- Require an adequate sample in both directions; spot-only evidence cannot establish derivatives short economics.
- Three actionable signals per UTC day is a ceiling, not a quota.
- A >90% win rate is a target for evaluation, never a promise or a reason to overfit.
- All models and candidate policies default to research-only. No policy mutation, production promotion, risk bypass, or execution without separate explicit acceptance.

## Current known evidence
- Regime K-means V2: 12,858 feature rows, one contiguous BTC_USDT Gate.io 1m window; descriptive clusters only.
- Supervised movement V1: 12,860 samples; 60-minute UP/DOWN/NEUTRAL forecast. Walk-forward accuracy lift over mean-majority baseline was only about 1.18 percentage points; this is not trade expectancy and does not establish a reliable trading edge.
- Canonical strategy-learning report at the inspected snapshot: 0 gate-approved resolved outcomes; 29 candidate records; 2,356 decisions. No supervised trade-policy labels are currently eligible.
- Therefore Blackbox is a defined research architecture with a verified readiness gate, not yet a trained proprietary trading strategy.

## Operational contract
- Data source: existing Gate.io public Spot BTC_USDT market data.
- Execution venue: existing user-selected exchange adapter only; no exchange role is inferred from the data source.
- Storage: existing canonical journals and model registry; no duplicate ledgers.
- Backup: existing encrypted Dropbox offsite process and quota guard.
- Failure mode: missing, stale, mismatched, or unverified evidence => NO_TRADE.

## 2026-11-18 first readiness run
- Existing regime model V2: 12,858 feature rows from one contiguous Gate.io BTC_USDT 1m sample; descriptive clustering only.
- Existing supervised movement model V1: 12,860 samples; its target is a coarse 60-minute UP/DOWN/NEUTRAL movement class, not a trade outcome. Walk-forward accuracy lift over the mean-majority baseline is about 1.18 percentage points, which is weak and does not establish a tradable edge.
- Canonical learning report snapshot: 2,356 decisions, 29 candidates, 0 gate-approved candidates, and 0 gate-approved resolved outcomes.
- Readiness result: RESEARCH_FOUNDATION_READY_BRAIN_TRAINING_BLOCKED; reasons are insufficient matured trade outcomes and no gate-approved strategy candidates.
- The readiness runner also verifies SHA-256 identity of both existing model files against their training-run manifests. It does not infer any sequence semantics from numeric IDs; the separate versioned Sequence Semantics Registry remains authoritative for exact venue/channel contracts.
- Regression tests: Blackbox, Adaptive Hybrid, indicator family and strategy learning loop passed together (45 tests).

## Four-state regime brain correction — 2026-11-18
Blackbox's top-level market state is explicitly four-way: **BULLISH, BEARISH, RANGE, NO_TRADE**. RANGE is a first-class state, not a synonym for inactivity. Existing HES range mean-reversion research family is reused; no parallel range strategy is created.
- BULLISH maps from confirmed UPTREND; BEARISH from confirmed DOWNTREND.
- RANGE is retained explicitly and routes research context to the existing range mean-reversion family; candidate generation and confirmation remain separate gates.
- TRANSITION, TRANSITION_UNCERTAIN, UNKNOWN, stale/incomplete data, low confidence, or 15m/1h/4h disagreement resolve to NO_TRADE.
- Initial conservative regime consensus requires 15m, 1h and 4h agreement and confidence >= 0.70. This is a research guard, not a claim of calibrated probability; it must be validated before promotion.
- A range breakout/exit requires fresh regime reclassification before any directional candidate.
- The K-means V2 clusters are volatility descriptors, not Bull/Bear/Range labels. Blackbox must not relabel those clusters as direction or market regime.
- Added `forward/blackbox_regime_brain_v1.py`, its four-state policy contract and regression tests.
- Combined Blackbox + strategy-family + learning + structure regression suite: **154 passed**.


## 2026-11-18 experiential memory and hypothesis tournament V1

A separate isolated implementation now provides:
- Reference-only experience indexing over the canonical decision journal, NO_TRADE outcome ledger, strategy-policy outcome ledger, indicator-family research outcomes and forward-paper journal. Source payloads remain in their original ledgers; no second full trade journal is created.
- Four explicit regimes: BULLISH, BEARISH, RANGE, NO_TRADE.
- Strict training-label eligibility: only matured, gate-approved, provenance-complete trade outcomes with verified costs and a valid directional result may be eligible. The first source preview yielded 9,126 references; the latest refresh yielded 9,133, with zero eligible training labels.
- Append-only, lock-protected, idempotent experience persistence. Exact replays are ignored; changed content under the same event identity fails closed.
- Append-only hypothesis discovery and lifecycle events: DISCOVERED -> PREREGISTERED -> TESTING -> ACCEPTED / REJECTED / INCONCLUSIVE -> RETIRED. Illegal transitions and final states without evidence hashes/rationale are rejected.
- Statistical tournament with paired exact sign testing on OOS net-R differences against a matched baseline, Holm-Bonferroni family-wise correction, >=100 train and >=100 independent purged OOS outcomes, verified costs, clean linkage, complete provenance, at least two OOS regimes, positive net expectancy and baseline superiority. SHORT additionally requires validated short-side economics.
- Statistically significant underperformance can reject a hypothesis; weak/insufficient evidence remains INCONCLUSIVE. Rejected hypotheses are retained, not deleted.

The readiness evaluator now reports a read-only preview of experiential-memory coverage. The append runner defaults to preview; persistent experience append requires `--append`; hypothesis discovery-event append separately requires `--append-hypotheses`. This implementation remains in an isolated candidate branch; it is not wired into a daemon, not deployed, and does not authorize model training, signal generation, strategy routing, policy mutation or execution. The current production source checkout and live services were not modified.


## Pattern discovery and statistical falsification update — 2026-11-18

The read-only discovery pass mined the existing historical indicator shadow journal into 35 frozen regime-conditioned feature motifs (BEARISH 20, BULLISH 15; six feature dimensions; support 27–101). This source did not contain RANGE or NO_TRADE motifs; the experience index itself does cover all four states. Motifs are descriptive hypotheses only; no outcome labels were used to discover them and no candidate is training-eligible.

The tournament's primary statistical comparison now uses paired per-event OOS net-R values against the matched preregistered baseline, with an exact two-sided sign test and Holm-Bonferroni correction within each declared hypothesis family. Acceptance additionally requires positive train/OOS net expectancy, positive mean paired lift, verified costs, independent purged chronology, complete provenance, clean linkage, and regime diversity. Statistically significant paired underperformance rejects a hypothesis; otherwise missing or weak evidence remains inconclusive.


## Strategy-family tournament boundary — 2026-11-18

The readiness brain now consumes the existing versioned family-results projection and independently verifies each journal SHA. Current Trend Breakout and Range Mean Reversion journals contain 15 and 14 outcomes respectively, but both have zero gate-approved resolved outcomes and zero verified paired net-R evidence. Trend Breakout has four preapproval outcomes; these remain separate from authorized/performance-eligible trades. Raw wins/losses are not used to rank families. Blackbox's 35 discovered motifs remain `DISCOVERY_ONLY_NOT_YET_COMPARABLE` until every compared family has the required matched, cost-verified, independent OOS evidence.
