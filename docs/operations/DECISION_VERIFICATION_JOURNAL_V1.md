# Decision Verification in the Trade Journal — v1

The journal's new **Decision verification** column is a forward-only, evidence-qualified review of each immutable decision. It never edits the original decision record.

- `PENDING`: the 24-hour horizon or validator record is not complete.
- `CORRECT` (green check): allowed only when the frozen setup, direction, geometry, confirmation, structure, Risk approval, candidate authorization, execution-instrument evidence and complete unambiguous 24-hour forward path all pass, and the hypothetical path hits its frozen stop.
- `INCORRECT` (red cross): the same qualification requirements pass and the hypothetical path reaches the frozen target. It is a missed-profit hypothesis, not realized or guaranteed profit.
- `POTENTIAL_ONLY`: later price reached a target, but the original decision-time gates rejected or failed to authorize the candidate. This is diagnostic only; it is not called a wrong decision or missed profit.
- `NOT_CLASSIFIABLE`: no qualified frozen candidate/geometry or no decisive outcome. Large price movement alone cannot make a NO_TRADE decision wrong.

The validator uses the existing append-only `matured_no_trade_validation_v1.jsonl` ledger (24-hour maturity) and never infers missing candles. Ambiguous same-candle stop/target events, incomplete horizons, spot-only short economics, unverified execution instrument, or any failed/unknown gate cannot produce a green check or red cross. Original journal and outcome ledgers remain append-only. No policy mutation, execution, orders, or capital changes are permitted.

Current production evidence on 2026-11-22 contains 96 matured NO_TRADE reviews: 95 complete and one incomplete; all 96 gate qualifications are rejected, so none currently qualifies for a definitive green/red mark. Some rejected proposals later reach a hypothetical target, but they remain `POTENTIAL_ONLY`, not missed-profit counts.
