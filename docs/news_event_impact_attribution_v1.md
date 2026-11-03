# News Event Journal and Gate.io Impact Attribution v1

## Purpose

This is a read-only evidence path for measuring what happened in the Gate.io BTC_USDT market after HES first observed a news item. It is not a causal model, directional signal, trade simulator, or execution permission.

## Reused inputs

- News evidence comes from the existing `NewsIntelligenceBrain` and `NewsMonitorV1`.
- The monitor appends one hash-verified record per source item to `/var/lib/hes-news-monitor/news_events_YYYY.jsonl`.
- Files are partitioned by UTC year. Records preserve source ID, publisher, source URL, published time, first-seen time, source-feed hash, raw-item hash, brief hash, score context, and deterministic event-cluster ID.
- Duplicate source item IDs are not appended again. Each record has a SHA-256 digest. Invalid JSON, non-object records, or digest mismatches fail closed.
- Event cluster IDs are time-bucketed for recurring event families. Unknown items remain separate; the clusterer does not guess that unrelated events are the same event.

## Market-data boundary

- The evaluator reads only persisted closed candles through `forward.global_market_data_reader_v1`.
- Source is `gateio_public_spot`, symbol `BTC_USDT`, timeframe `15m`.
- No direct exchange HTTP client, alternate market-data source, or duplicate candle adapter is created.

## Evaluation method

The event anchor is the earliest `first_seen_at` in the cluster: when HES could first know about the item. The evaluator uses the last closed candle before that anchor as the baseline and then measures:

| Window | 15m bars |
|---|---:|
| 15 minutes | 1 |
| 1 hour | 4 |
| 4 hours | 16 |
| 24 hours | 96 |

Each matured window reports close-to-close price change, maximum favorable/adverse excursion, realized volatility, and average volume relative to the preceding 20-bar median. A window remains `PENDING` until all required closed candles exist. Events older than the retained Gate.io candle window are marked `HISTORY_UNAVAILABLE`; timestamps that cannot be verified are not guessed.

## Run on demand

```bash
python3 scripts/news_impact_attribution_v1.py
```

The report is written atomically to `data/forward/news_impact_attribution_v1.json`. It includes the event-ledger digest and its own SHA-256.

## Interpretation limits

- Post-publication market response is observational; it does not prove the news caused the move.
- OHLCV does not provide bid/ask spread, order-book depth, or slippage; those are not inferred.
- This report evaluates market response, not trade PnL or the accuracy of LONG/SHORT predictions.
- News alone cannot create a signal, authorize a trade, override the existing Risk Gate, or turn execution on.
- Event attribution becomes meaningful only as the append-only ledger accumulates observations and the relevant 1h/4h/24h windows mature.
