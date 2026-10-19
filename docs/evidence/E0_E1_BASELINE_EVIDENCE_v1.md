# HES Trade Agent — E0/E1 Baseline Evidence v1

Status: FROZEN BASELINE — EVIDENCE ONLY

Registered: 2026-09-30
Owner: Seyed Hesameddin Beheshti Shirazi

## Immutable provenance

- Repository: beheshti2025hesam-prog/btc_tabdeal_public_test
- Source branch: e0-e1-final-evidence-chain-clean-v1
- Source commit: 434055352bb66dc2211f171885a2b0fc934b10b9
- Validation workflow run: 36745760796
- Workflow: HES Trade Agent — Final E0/E1 Evidence Chain
- Job: 109991431115
- Artifact: e0-e1-final-evidence-chain
- Artifact ID: 11112332942
- Artifact SHA-256: 69e81aa74d8660ee8c2b5d25254a7dcce073133e12b32e94d22227d576e4ad41
- Artifact created: 2026-09-30T16:39:35Z
- Artifact expiry: 2026-12-29T16:39:09Z

## Frozen snapshot lineage

- Snapshot blob: 1a44d52a0588deb765bbbea04bfb5783dcb1050b
- Snapshot source commit: b8c4fe4fa054dbfa4fca17d2f307d269c16335e1
- Snapshot source run: 36489452534

## Evidence chain

E0 -> E1 -> Fold/Regime Survival -> LOO-Fold -> LOO-Winner -> Feature Stability -> Independence-adjusted conclusion

## Frozen results

- E0: 1049 evaluated OOS observations = 14 winners above 14 bps / 1035 controls
- E1: 14 / 1035 after the one-observation embargo adjustment; reconciles with E0
- Winner support: 4 of 8 temporal folds
- Winner regime support: 7 Range / 7 Uptrend
- Winner Kish effective sample size: approximately 2.97
- LOO-Winner: all 14 winners evaluated
- Feature stability: not uniformly stable under both LOO layers; EMA and VWAP do not preserve sign under fold-level LOO
- Evidence status: descriptive, independence-adjusted, not 14 independent confirmations

## Claim boundary

This baseline does NOT establish:
- a trading signal
- predictive validity
- parameter/threshold optimization
- model superiority
- live-trading readiness
- promotion to production

The baseline is evidence-only and must not be silently reinterpreted as a Signal Research result.

## Signal Research gate

Gate status: CONDITIONAL / HUMAN REVIEW REQUIRED

Allowed next activity, if approved: define a separate Signal Research protocol using the frozen evidence as an input hypothesis source.

Not allowed as part of this baseline:
- constructing a signal
- tuning thresholds against this evidence
- selecting a winner from this evidence
- live or paper execution
- modifying the frozen evidence artifact

## Integrity rule

Any future analysis that changes the frozen snapshot, population definition, embargo boundary, winner definition, or independence unit must create a new evidence version. It must not overwrite this baseline.
