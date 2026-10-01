# HES Trade Agent — DNA & 20-Year Architecture Roadmap

**Project:** HES Trade Agent  
**Owner:** Seyed Hesameddin Beheshti Shirazi  
**Architecture horizon:** 2026–2046  
**Status:** Architecture baseline / non-execution  
**Live execution:** OFF

## 1. Core DNA

HES Trade Agent is designed as a **Multi-Brain, Evidence-First, Market-Aware, Self-Evaluating, Modular, Future-Proof** trading intelligence platform.

The core must remain stable while new intelligence capabilities can be added as replaceable, contract-driven modules. A future model, algorithm, data source, or reasoning technology must be able to plug into the platform without forcing a redesign of the data lineage, evidence, safety, or promotion boundaries.

### Non-negotiable principles

- Raw Data is the source of truth.
- Immutable Snapshot → Manifest → Integrity → Replay → Research → OOS/Walk-Forward → Evidence → Promotion Gate.
- No leakage, look-ahead bias, hidden replacement rows, or untracked data transformations.
- Analysis/Signal Intelligence is strictly separated from Live Execution.
- Mother Brain / Command Center is non-executing.
- News Radar provides context/evidence; it does not directly execute trades.
- Pump/Dump detection is an evidence and pattern-recognition capability, not a promise of certainty or a direct execution trigger.
- Unknown/ambiguous market states must remain representable; the system must not force every anomaly into PUMP or DUMP.
- New ML/NN/Transformer/agent technologies are introduced behind contracts, tests, evaluation, and promotion gates.
- Tabdeal BTC_USDT is the first implementation profile, not the architectural limit.
- Secrets remain isolated in the secret/configuration layer.
- Free-first / open-source-first remains the default where practical; paid adapters are optional interfaces, not architectural dependencies.
- Integration into `main` is deliberate and evidence-backed.
- `data-engine-v1` remains separate from `main`; no merge/rebase/sync unless explicitly authorized.
- Live execution remains OFF until all required safety, research, OOS, paper, and promotion gates are satisfied.

## 2. Multi-Brain Target Architecture

The platform is intentionally extensible beyond three brains.

### Command and reasoning layer

1. **Mother Brain / Command Brain**
   - Coordinates evidence from all brains.
   - Produces explanations, hypotheses, scenarios, and research decisions.
   - Never bypasses safety or promotion gates.

2. **Reasoning Brain**
   - Cross-evidence synthesis and structured reasoning.
   - Distinguishes observation, inference, hypothesis, and decision.

### Fast market intelligence layer

3. **Fast Market Brain**
   - Low-latency market-state computation.
   - Price acceleration, volume anomalies, volatility expansion, liquidity changes, and other measurable microstructure features.

4. **Market Brain**
   - Price/volume/market-state interpretation.

5. **Flow Brain**
   - Trade-flow and imbalance analysis.

6. **Pattern Brain**
   - Pattern discovery and historical analogues.

7. **Pump/Dump Evidence Brain**
   - Detects measurable signatures compatible with pump, dump, liquidity shock, reversal, cascade, or unknown anomaly states.
   - Outputs evidence vectors, confidence/calibration metadata, and data-quality status rather than certainty.

8. **Regime Brain**
   - Identifies market regimes and regime transitions.

9. **Anomaly Brain**
   - Detects behavior outside established distributions or expected market states.

### Context and external intelligence

10. **Context / News Radar Brain**
    - News, announcements, events, macro context, sentiment and external evidence.
    - Feeds normalized Context/Evidence to the Mother Brain.

11. **Macro Brain**
    - Broader market and macroeconomic context where supported by reliable data.

12. **Event Brain**
    - Exchange, market, scheduled-event, and structural event awareness.

### Research, learning and memory

13. **Research Brain**
    - Controlled hypothesis generation and candidate research.

14. **Memory Brain**
    - Preserves validated experience with lineage:
      Observation → Hypothesis → Experiment → Result → OOS Evidence → Decision → Outcome.

15. **Adversarial Brain**
    - Actively searches for reasons a hypothesis or signal may be wrong.
    - Targets overfitting, leakage, instability, regime dependence, and false confidence.

16. **Forecasting Brain**
    - Produces multiple conditional scenarios rather than deterministic predictions.

17. **Evolution Brain**
    - Proposes improvements and new candidate components.
    - Cannot promote itself or bypass evaluation.

18. **Optimization Brain**
    - Searches candidate parameters/features/models behind strict anti-overfitting and promotion controls.

19. **Transfer Brain**
    - Separates universal intelligence from venue/market adapters so the core can expand beyond Tabdeal BTC_USDT.

### Safety and lifecycle

20. **Risk Brain**
    - Risk boundaries, exposure constraints, drawdown controls, and failure-state handling.

21. **Safety Brain**
    - Independent safety boundary capable of blocking unsafe downstream actions.

22. **Promotion Gate**
    - Evidence-based lifecycle gate from research to OOS, paper, and eventually production.

## 3. Long-Horizon Roadmap

### Phase A — Foundation and Evidence
Raw Data → Snapshot → Manifest → Integrity → Raw Replay → Candidate Performance Study.

### Phase B — Market Intelligence
Fast Market Brain → Market/Flow/Regime/Anomaly features → Pump/Dump Evidence Contract → Pattern research.

### Phase C — Context Intelligence
News Radar → Event/Macro normalization → Context/Evidence contracts → Mother Brain integration.

### Phase D — Controlled Research Intelligence
Research Brain → Adversarial Brain → Memory Brain → OOS / Walk-Forward → robustness and independence evidence.

### Phase E — Advanced AI
ML → NN → Transformer-class models → multimodal/context-aware models → agentic reasoning, each introduced only through reproducible evaluation and promotion gates.

### Phase F — Operational Intelligence
Risk Brain → Safety Brain → Paper → operational validation → Promotion Gate → Production only after all boundaries pass.

### Phase G — 2046-ready evolution
The architecture must permit new model families, new market data types, new reasoning methods, new venues, and new hardware/latency strategies to replace or extend individual brains without changing the foundational evidence and safety contracts.

## 4. Pump/Dump Intelligence Contract

The system should combine measurable evidence rather than a single rule:

- price acceleration
- volume shock
- trade-flow imbalance
- volatility expansion
- liquidity changes
- abnormal trade size/activity
- market-regime compatibility
- external/news/event context
- historical pattern similarity
- data-quality and timestamp integrity

Possible states include:

**PUMP / DUMP / REVERSAL / LIQUIDITY SHOCK / NORMAL / UNKNOWN**

Every detection must retain its evidence lineage and evaluation population.

A high confidence score is not equivalent to a guaranteed future outcome and must never directly authorize live execution.

## 5. Development Rule

Do not build every brain simultaneously.

Build the contracts and stable interfaces first, then implement the highest-value brains in dependency order. New intelligence is accepted only when it can be tested, reproduced, evaluated out-of-sample, and promoted without weakening existing boundaries.

**This document defines the long-term architectural direction. It does not authorize merging, live execution, or changing the current evidence gates.**
