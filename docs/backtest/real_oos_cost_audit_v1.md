# Real BTC/USDT OOS Cost Audit v1

## Scope

Execution-free audit of the frozen real-data OOS protocol on the project BTC/USDT trade snapshot.

- Raw source: `trades.csv`
- Snapshot size: 129,920 trade rows
- Symbol: BTC_USDT
- Timeframe: 60 seconds
- EMA period: 20
- Frozen OOS protocol: train=800, test=400, step=400, embargo=0
- Expected folds: 8
- No parameter tuning, capital compounding, leverage, order execution, or live trading.

## Data integrity

The snapshot validates to 129,920 valid rows under the current RawDataValidator contract.

The deterministic pipeline produces:

- 4,108 one-minute candles
- 4,062 chronological observations
- 26 continuity exclusions
- 2,737 NO_TRADE observations
- 1,049 evaluated OOS observations
- 528 wins and 479 losses in the execution-free OOS result

The 4,062 observations produce exactly eight frozen OOS folds.

## Fold-by-fold cost/slippage matrix

Costs are explicit measurement scenarios, not claims about Tabdeal fees.

| Fold | 0/0 bps net | 5/2 bps net | 10/5 bps net | evaluated |
|---:|---:|---:|---:|---:|
| 0 | +0.003715 | -0.164285 | -0.356285 | 120 |
| 1 | +0.003387 | -0.181413 | -0.392613 | 132 |
| 2 | +0.007373 | -0.181627 | -0.397627 | 135 |
| 3 | +0.014016 | -0.177784 | -0.396984 | 137 |
| 4 | -0.003366 | -0.196566 | -0.417366 | 138 |
| 5 | +0.005769 | -0.172031 | -0.375231 | 127 |
| 6 | -0.000777 | -0.177177 | -0.378777 | 126 |
| 7 | -0.002277 | -0.189877 | -0.404277 | 134 |

## Aggregate

The frozen runner produced 24 measurements: 8 folds × 3 scenarios.

| Scenario | Net return | Evaluated | Wins | Losses |
|---|---:|---:|---:|---:|
| 0 bps fee + 0 bps slippage | +0.027840 | 1,049 | 528 | 479 |
| 5 bps fee + 2 bps slippage per side | -1.440760 | 1,049 | 14 | 1,035 |
| 10 bps fee + 5 bps slippage per side | -3.119160 | 1,049 | 1 | 1,048 |

The execution-free OOS win rate is 52.43297%.

These returns are summed per-trade returns, not compounded account equity. They must not be interpreted as percentage changes in account capital.

## Interpretation boundary

This audit is evidence for the validation pipeline, not a live-trading recommendation.

The current baseline's gross edge on this snapshot is small relative to the explicit adverse-cost scenarios. The measured result is therefore not sufficient for promotion to live execution. Further work must establish durable signal/trade economics under independently justified execution assumptions and additional out-of-sample evidence.

The frozen matrix itself must not be used to tune the baseline retrospectively.

## Evidence and reproducibility

The successful GitHub Actions run generated the machine-readable evidence artifact `real-btcusdt-oos-cost-matrix-evidence`. The artifact records the frozen protocol, all eight folds, all 24 scenario measurements, aggregate results, and safety flags.

## Safety

- Main branch is not modified by this audit.
- `data-engine-v1` remains separate.
- Live execution remains disabled.
- No exchange fee/slippage values are asserted by this document.
- No parameter tuning, model fitting, capital mutation, or order execution is performed.
