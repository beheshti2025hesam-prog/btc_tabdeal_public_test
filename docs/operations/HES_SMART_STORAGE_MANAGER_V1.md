# HES Smart Storage Manager v1

## Purpose
A read-only capacity, archive inventory, compression-evidence and quota planner. It complements (does not replace) IDLM v1 and the existing Smart Cleanup Manager.

## Safety
- Report-only: no delete, move, truncate, rotation, prune, archive rewrite, or service mutation.
- Active/rollback releases, canonical Gate.io market data, journals, evidence and all backup archives remain protected.
- Rebuildable caches are REGENERABLE_REVIEW_ONLY, never auto-delete candidates.
- Unknown paths, scan errors and uncertain dependencies mean KEEP.
- Compression recommendations never alter existing archives. A future v2 archive must be versioned, verified before publication, retain legacy gzip readers, and keep the encryption key outside Dropbox.
- No automatic cleanup timer is authorized by this version.

## Capacity controls
Reports allocated and logical bytes, file/directory counts, inode availability, archive counts, same-day archive duplicates, Dropbox quota and explicit protected/review-only scope totals. Forecasting and retention changes require durable time-series evidence and independent restore acceptance.

## Compression evidence (2026-11-15)
A bounded 86,883,681-byte project candidate sample produced:
- gzip -1: 31,656,094 bytes
- zstd -3: 30,324,382 bytes
- zstd -9: 28,132,792 bytes

zstd -9 was 11.13% smaller than gzip -1 for this sample. This is not a whole-backup benchmark and does not prove end-to-end CPU/memory suitability. Prototype zstd for new archives only after full-scope benchmark and compatibility tests. Never recompress ciphertext or delete/replace a valid gzip backup based on a sample.

## Next gates
1. Test the planner on the live IDLM report and verify the report remains read-only.
2. Benchmark representative full local/offsite input streams with CPU, memory, time and output-size limits.
3. Add versioned zstd archive/restore compatibility tests; retain gzip restore support.
4. Prove full restore in an isolated target before altering retention.
5. Only then consider a narrowly scoped, reversible cache cleanup canary with exact paths, dependency checks, a recovery manifest and a rollback plan.