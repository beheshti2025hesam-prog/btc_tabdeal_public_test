# Sequence Capability Freshness Gate — 2026-11-16

- Runtime registry revision: **v2**. Policy: `max_age_days=90`, UTC clock, stale behavior `FAIL_CLOSED_NO_CAPABILITY`.
- A positive capability now requires an exact registry-issued capability, a primary-source content hash, a review revision, a valid `last_verified` date, and verification age within the configured window.
- Future-dated, missing, malformed, or expired verification is rejected for the affected record. A stale record does not invalidate unrelated registry entries.
- `SequenceCapabilitiesV1.verified` rechecks freshness at use time, so a capability object retained in memory does not remain valid indefinitely.
- All current venue records remain `UNKNOWN`, `SOURCE_REVIEWED_UNPINNED`, or `SOURCE_REVIEW_REQUIRED`; no exchange capability was promoted by this change.
- Gate.io candle `open_time` remains a time-bucket key, not an individual-trade sequence.
- Monthly/manual drift monitoring remains read-only; `repository_dispatch` can trigger immediate checks for API announcements, observed schemas, and protocol-version changes. Source drift and freshness expiry require human review before any registry revision.

## Verification evidence

- Focused sequence + drift-watch tests: 77 passed.
- Full repository regression: 1280 passed, 82 subtests passed.
- Workflow action pin audit: PASS; workflow YAML parse: PASS; `git diff --check`: PASS.
- Read-only source audit against runtime registry v2: 17 records, 11 source URLs, 11 review-required. Six source documents were reachable but have no pinned baseline; five were unreachable from the VPS network. HTTP Last-Modified/ETag/content-type metadata and body hashes were captured where available in `evidence/operations/sequence_protocol_drift_audit_v1_20261116_freshness.json`. No hash was silently accepted and no capability was promoted.
- The 90-day expiry gate is inert for current records because none is `VERIFIED`; it protects future positive records from remaining valid indefinitely.

## Deliberate boundary

The uploaded research artifact does not contain complete machine-readable wire-schema fixtures for every venue/channel. Therefore this change does not fabricate schema fingerprints. Schema fingerprint baselines must be added only from exact primary-source examples or provenance-bearing raw captures, and remain non-authorizing until reviewed. Existing deterministic replay/regression tests continue to protect the current known contracts.
