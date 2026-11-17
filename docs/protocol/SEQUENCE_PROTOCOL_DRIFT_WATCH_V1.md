# HES Sequence Protocol Drift Watch v1

## Purpose

Run a monthly and manually triggerable read-only audit of the official source documents referenced by the runtime sequence-semantics registry (`forward/sequence_semantics_registry_v1.json`). This closes the maintenance gap between a pinned protocol decision and later changes to an exchange's published documentation.

## Behavior

- Deduplicate exact HTTPS source URLs and fetch each URL once per audit.
- Enforce bounded request time and response size; never follow a redirect to non-HTTPS.
- Compare the retrieved full-document SHA-256 only with an explicitly pinned `source_content_sha256` in the runtime registry.
- Report unpinned baselines, conflicting registry baselines, changed documents, and fetch failures as review-required.
- Preserve the registry unchanged. The audit never updates hashes, never changes `status`, and never grants capabilities.
- Attach a JSON evidence report and a concise GitHub Actions summary.
- Runtime capability resolution requires `last_verified` to be no older than the registry's configured 90-day UTC freshness window; stale or future-dated verification fails closed for that exact record.
- Upstream integrations can trigger an immediate audit through `repository_dispatch` events `exchange-api-announcement`, `schema-observed`, or `protocol-version-change`.

## Interpretation limits

A full-document hash detects that a source document changed; it does not prove that the relevant protocol clause changed. A mismatch requires a human to inspect the exact section, preserve a source snapshot and excerpt hash, update fixtures/tests, and issue an append-only registry revision. A matching hash is not proof that a protocol guarantee exists; it only says the fetched document body matches the pinned baseline. The 90-day runtime freshness window is a separate guard: it prevents an old positive verification from granting capabilities indefinitely, but it does not replace source-drift review.

The current runtime registry intentionally keeps Tabdeal `trade.sequence` UNKNOWN and the Gate.io candle `open_time` as a time-bucket key, not a trade-event sequence. Binance/OKX/Bybit/Coinbase/Kraken records remain unverified until their exact source snapshots and review gates are completed. This monitor does not change those states.

## Operations

Workflow: `.github/workflows/sequence-protocol-drift-watch-v1.yml`

- Scheduled: monthly on day 1 at 06:17 UTC.
- Manual: `workflow_dispatch`.
- Change-triggered: pushes/PRs touching the runtime registry, audit code, tests, or workflow.
- Output: `sequence-protocol-drift-report` artifact containing `sequence_protocol_drift_audit_v1.json`; the summary includes HTTP status, Last-Modified, ETag, content type, and SHA-256 when available.
- Scheduled, manual, and repository-dispatch runs surface review-required results as failed workflow alerts after preserving the evidence artifact.

A `REVIEW_REQUIRED` result is deliberately non-destructive and does not authorize trading or a service restart. Reviewers should update the registry only after validating the relevant primary-source excerpt and replay fixtures.
