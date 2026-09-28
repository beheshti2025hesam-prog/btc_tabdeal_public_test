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
- 1,041 evaluated signals
- 617 LONG signals
- 708 SHORT signals

The 4,062 observations produce exactly eight frozen OOS folds.

## Fold-by-fold cost/slippage matrix

Costs are explicit measurement scenarios, not claims about Tabdeal fees.

| Fold | 0/0 bps net | 5/2 bps net | 10/5 bps net | evaluated |
|---:|---:|---:|---:|---:|
| 0 | +0.000331 | -0.185869 | -0.398669 | 133 |
| 1 | +0.000964 | -0.174036 | -0.374036 | 125 |
| 2 | +0.000777 | -0.184023 | -0.395223 | 132 |
| 3 | +0.006359 | -0.185441 | -0.404641 | 137 |
| 4 | -0.009833 | -0.183433 | -0.381833 | 124 |
| 5 | -0.000199 | -0.191999 | -0.411199 | 137 |
| 6 | +0.011731 | -0.174469 | -0.387269 | 133 |
| 7 | +0.001083 | -0.166917 | -0.358917 | 120 |

## Aggregate

| Scenario | Net return | Evaluated | Wins | Losses |
|---|---:|---:|---:|---:|
| 0 bps fee + 0 bps slippage | +0.011213 | 1,041 | 519 | 516 |
| 5 bps fee + 2 bps slippage per side | -1.446187 | 1,041 | 18 | 1,023 |
| 10 bps fee + 5 bps slippage per side | -3.111787 | 1,041 | 1 | 1,040 |

## Interpretation boundary

This audit is evidence for the validation pipeline, not a live-trading recommendation.

The current baseline's gross edge on this snapshot is small relative to the explicit adverse-cost scenarios. Therefore this result must remain outside any live-execution promotion path until the strategy/feature layer demonstrates a durable edge under independently justified execution assumptions and additional out-of-sample evidence.

The frozen matrix itself must not be used to tune the baseline retrospectively.

## Safety

- Main branch is not modified by this audit.
- `data-engine-v1` remains separate.
- Live execution remains disabled.
- No exchange fee/slippage values are asserted by this document.
