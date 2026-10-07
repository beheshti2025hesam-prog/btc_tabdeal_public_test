# Structure Observation Layer v1

This is the causal bridge between normalized closed Forward candles and the Market Structure measurement layer.

Current status: UNKNOWN_NO_STRUCTURE_POLICY is intentional.

The layer does not invent pivot lookback, swing confirmation, BOS/CHOCH thresholds, or regime tuning. Until a separately versioned structure policy exists, no swing is inferred from candle shape alone.

Safety: closed candles only; observed_at is mandatory; future candles are rejected; mixed symbols are rejected; no historical Winner/Survivor inputs; no outcomes; no LONG/SHORT decision; observation-only and fail-closed.
