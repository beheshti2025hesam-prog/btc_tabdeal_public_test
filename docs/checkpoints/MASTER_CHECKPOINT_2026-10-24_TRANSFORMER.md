# HES Trade Agent — Master Checkpoint: Transformer Agent
Date: 2026-10-24

## Status
**Inference contract, reproducible training code, and verified checkpoint adapter implemented. Real-market model promotion remains HOLD.** The branch now contains an actual small causal Transformer training/evaluation pipeline and adapter, but no genuine market model has been trained or promoted because the available repository CSV archives are trade tape rather than the required canonical global OHLCV candles.

## Reuse-first canonical path
Approved global OHLCV source → existing canonical data/feature boundary → Transformer evidence adapter → existing Signal Agent → existing Confirmation/Risk Gate/Decision chain → separately gated execution boundary. The Transformer Agent cannot create orders or bypass existing gates. No new collector, dashboard, or order route is introduced.

## Implemented
- `forward/transformer_agent_v1.py`: fail-closed evidence-only inference contract.
- `forward/transformer_training_v1.py`: OHLCV-only dataset reader, causal feature representation, explicit future-return labels, purged chronological train/validation/test split, train-only normalization, causal Transformer training, validation-loss checkpoint selection, test accuracy/class recall/ECE, and hashed manifest.
- `forward/transformer_torch_adapter_v1.py`: validates model SHA-256 and saved feature/class schema, loads checkpoint, and returns LONG/NEUTRAL/SHORT probabilities to the existing inference contract.
- `tests/test_transformer_agent_v1.py` and `tests/test_transformer_training_v1.py`: malformed-input tests, trade-tape rejection, chronological leakage controls, synthetic training smoke test, checkpoint integrity, and inference-contract integration.
- `.github/workflows/transformer-agent-contract.yml` and `.github/workflows/transformer-training-pipeline.yml`: contract and CPU PyTorch training CI.
- `forward/TRANSFORMER_AGENT_V1.md` and `forward/TRANSFORMER_TRAINING_V1.md`: architecture, execution boundary, training method, and evidence limitations.

## Verification status
- Earlier inference-contract CI passed on tested code SHA `9312db0a4596d3bdad82d97736114498e8d0c240`: [run 40072369820](https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test/actions/runs/40072369820). That run predates the new training/adapter files and does not validate them.
- New training workflow was added to the branch; its result must be checked after the latest commit before claiming the new code is CI-green.
- Training tests use synthetic fixture data only. Synthetic results are code tests, not market evidence.

## Verified remaining blocker
The repo contains `data/trades.csv` and `data/archive/*.csv`, but their schema is raw trade tape (`symbol/price/amount/side/updated/sequence)); the new trainer deliberately rejects that data. No approved global OHLCV candle export, pre-registered fee/slippage neutral band, or genuine out-of-sample model evaluation is currently attached to this branch. Do not train on the Tabdeal trade tape to bypass the user's canonical global-data rule.

## Remaining gates before production use
1. Obtain and hash a closed-candle OHLCV export from the approved global provider and record the exact source, symbol, interval, and retrieval window.
2. Pre-register horizon and neutral-return band using evidenced fees/slippage.
3. Run training on that immutable source; retain model artifact and manifest hashes.
4. Compare on identical immutable OOS snapshots against the existing strategy and naive baselines, net of fees/slippage; evaluate calibration, abstention coverage, drawdown, turnover, and regime stability.
5. Obtain independent promotion approval, then integrate evidence behind existing Signal Agent and Risk Gate; run paper/shadow validation.
6. Live execution remains separately gated and OFF.

## Delivery and operational guardrails
- Product delivery target remains **19 November 2026**.
- Risk checkpoint remains **26 October 2026**.
- One VPS only. No VPS changes, deployment, collector activation, credentials, or live orders were performed.
- PR #364 remains Draft/HOLD until current CI and review evidence are checked. No model is promoted automatically.
