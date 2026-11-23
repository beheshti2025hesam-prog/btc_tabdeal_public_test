# HES Trade Agent — Operating Principles

## Governing rule
Use exchange-provided capabilities and data first. Keep the implementation as simple as possible. Validate only what is genuinely necessary for correct HES decisions and safe operation.

## Required behavior
- Prefer the exchange's existing market data and ready-made interfaces (especially official OHLCV candles/timeframes) over rebuilding equivalent data pipelines.
- Treat exchange candles/chart data as the primary market-data path where the HES architecture calls for them.
- Add depth, latest-trade feeds, WebSocket handling, sequence reconstruction, or other machinery only when an existing requirement or a demonstrated decision-critical gap makes it necessary.
- Do not turn sequence continuity, exhaustive trade reconstruction, or any other optional check into a universal blocker without evidence that HES depends on it.
- Validate only decision-relevant integrity, timestamp/freshness, schema, and failure behavior; tie every gate to a concrete HES risk or requirement.
- Before proposing new components or checks, inspect the current repository and exchange-provided features to avoid duplicating what already exists.
- Keep safe behavior on missing, stale, malformed, or contradictory data. Never claim a gate passed without evidence.
- Preserve the conservative HOLD / NO-TRADE posture until the actual required gates pass.

## Decision test before adding work
1. Does this capability already exist in the exchange or codebase?
2. Is the proposed work required for a correct HES decision or a demonstrated safety risk?
3. Is there a simpler way to reuse existing functionality?
4. What concrete evidence will prove the check is necessary and passed?

If no decision-critical need is demonstrated, do not build it.
