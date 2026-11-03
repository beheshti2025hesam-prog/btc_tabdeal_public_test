# Federal Reserve Event Calendar v1

## Scope

The existing News Monitor now includes a separate, informational-only calendar made from two official Federal Reserve endpoints:

- Statistical release calendar JSON: `https://www.federalreserve.gov/data/statcalendar.json`
- FOMC meeting schedule: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`

Both were probed from the production VPS with HTTPS, zero redirects, bounded response sizes, and successful parsing. The calendar is refreshed on the existing five-minute News Monitor cycle; no additional service or scheduler is created.

## Included events

The statistical calendar is filtered to selected official releases: industrial production, consumer credit, financial accounts, SLOOS/SCOOS, money stock, commercial-bank assets/liabilities, and reserve-balance releases. The FOMC page contributes meeting date ranges.

The dashboard shows the next **45 days**. Exact Eastern local times are converted to UTC using the IANA `America/New_York` timezone. FOMC meeting dates have no published time in the schedule and therefore remain date ranges; no statement time is guessed.

## Explicit exclusions and limits

- The official BLS calendar endpoint returned HTTP 403 from the VPS. It is not bypassed, proxied, or replaced with an unqualified source. Therefore CPI and employment-release coverage is not complete.
- This is a Federal Reserve-only schedule, not a complete global macro calendar.
- Events are marked `unrated`; no impact score, direction, or veto is inferred from a calendar entry.
- Calendar fetch failure is reported independently and does not silently mark the news-source monitor healthy or unhealthy.
- Neither a scheduled event nor news alone can create a signal, authorize a trade, override Risk Gate, or enable execution.
