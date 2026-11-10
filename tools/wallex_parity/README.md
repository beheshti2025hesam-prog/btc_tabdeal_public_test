# Wallex OHLCV parity core

A deliberately small, read-only comparator. It does not fetch data, connect to accounts,
place orders, normalize volume, shift timestamps, fill gaps, or infer source semantics.
The two JSON inputs must be captured independently by separate acquisition paths.

## Input formats

Either a Wallex/TradingView UDF-style object with parallel `t/o/h/l/c/v` arrays, or
a list of candle objects using `timestamp` (Unix seconds) and `open/high/low/close/volume`
(or their `o/h/l/c/v` aliases). An optional envelope can include `metadata` and `candles`.

## Example

```sh
python3 tools/wallex_parity/compare_ohlcv.py \
  --source-a evidence/wallex-udf.json \
  --source-b evidence/wallex-chart-export.json \
  --label-a wallex-udf-api \
  --label-b wallex-rendered-chart-export \
  --symbol BTCUSDT --resolution 1 \
  --output evidence/wallex-parity-report.json
```

Exit code: `0` means supplied candles match exactly; `1` means mismatch/coverage/duplicate
or requested metadata failure; `2` means invalid input. Numeric tolerance defaults to zero
and must be explicitly selected if appropriate.

## Guardrails

- Exact Unix-second timestamps are joined; no automatic time shifting.
- Decimal arithmetic avoids binary-float rounding.
- OHLC and volume are compared independently.
- Exact 2x volume ratios are reported as observations, never fixed.
- Missing timestamps, duplicate timestamps, malformed UDF arrays and invalid numbers fail closed.
- A numerical match proves equality of the supplied captures only. It does not prove that either
  source is complete or semantically correct. Confirm symbol/venue, resolution, timezone,
  candle-boundary convention, and volume units before interpreting results.
- Public market-data comparison only; no API key required or accepted by this component.

Run tests:

```sh
python3 -m unittest discover -s tests -p 'test_wallex_parity_core.py' -v
```

## Browser-backed Wallex chart/API probe

The separate `tools/wallex_parity/capture_wallex_chart.py` script opens the official Wallex BTCUSDT chart in headless Chromium, retains a screenshot and the raw UDF history response observed by the browser, then issues a separate direct HTTP request to the exact same public request URL. It compares only common closed 1-minute candles using exact Decimal values and timestamps. It records raw SHA-256 hashes and an explicit status in `artifacts/wallex-chart-parity/manifest.json`.

Run in an environment with Playwright Chromium installed:

```sh
python -m pip install playwright
python -m playwright install chromium
python tools/wallex_parity/capture_wallex_chart.py
```

A passing result proves that the chart page's observed UDF datafeed and a separate direct request returned equal values for the compared closed candles. It does **not** prove independent chart-vs-exchange volume semantics: the chart and API may share the same backend. It does not compare pixel values or make `/v1/trades` complete. Any 2x volume relationship is reported only as an observation and must not be corrected without authoritative evidence. The workflow uploads raw captures, screenshot, and manifest as a 90-day artifact.
