# HES Smart Storage Manager v1

## Purpose
A read-only capacity, archive, Dropbox quota and compression planner. It consumes the existing IDLM v1 source audit and dependency-aware Smart Cleanup Manager v1 output. It deliberately does not create a second recursive project scanner or a second dependency resolver.

## Safety
- Report-only: no delete, move, truncate, rotation, prune, archive rewrite, or service mutation.
- IDLM and Smart Cleanup reports must match exact schema/source snapshot, be no older than 15 minutes, and pass source/dependency scan gates. Stale, mismatched, incomplete or error-bearing input fails closed.
- Full restore gate must pass before any retention or cleanup authorization. Current recovery status remains BLOCKED_NOT_PROVEN.
- Active/rollback releases, canonical Gate.io data, journals, evidence and all backup archives remain protected.
- Unknown paths, scan errors and uncertain dependencies mean KEEP.
- Compression recommendations never alter existing archives. A future versioned zstd archive must be verified before publication, retain legacy gzip readers, and keep the encryption key outside Dropbox.
- No automatic cleanup timer is authorized by this version.

## Capacity controls
Uses the existing lifecycle inventory's per-item allocated bytes and Smart Cleanup dependency classifications, plus filesystem capacity/inodes, archive counts and same-day archive multiplicity, and Dropbox quota. This avoids duplicating the existing IDLM/Smart Cleanup scanner. The storage manager does not independently authorize cache cleanup.

## Compression evidence (2026-11-15)

A full-scope streaming benchmark used the same include-list semantics as the production offsite builder: 30,546 entries and 4,077,824,000 uncompressed tar bytes, including active and rollback releases. The benchmark streamed to byte counters; it did not write an archive or modify production data.

| Format | Output bytes | Elapsed | Peak RSS |
|---|---:|---:|---:|
| gzip -1 | 1,601,064,546 | 73.89 s | 8,016 KiB |
| zstd -3, single thread | 1,407,220,695 | 28.07 s | 7,936 KiB |
| zstd -9, single thread | 1,228,742,799 | 160.95 s | 8,000 KiB |

zstd -9 was 23.25% smaller than gzip -1 and 12.68% smaller than zstd -3. Both zstd levels are below the existing 1.5 GiB archive cap; zstd -9 has 381,869,937 bytes of headroom. The benchmark used nice 15, idle I/O priority and one zstd thread. These are full-scope measurements, but GPG encryption overhead and the full encrypted zstd round-trip remain separate acceptance checks. The evidence JSON is evidence/operations/hes_zstd_full_scope_benchmark_20261115.json.

Do not switch production until the complete zstd + AES-256 GPG stream is tested end-to-end, versioned restore detection is implemented, exact-head CI passes, and the existing Dropbox single-object replacement/quota behavior is reviewed. Never recompress ciphertext or remove a valid gzip archive before a new backup is independently verified.

## Current recovery boundary
The current Smart Cleanup report confirms encrypted local/offsite backup integrity and remote Dropbox hash match, but its full restore gate is BLOCKED_NOT_PROVEN. A prior selective restore and same-host application restore evidence do not prove full-system/replacement-host recovery. With one VPS and no suitable secondary local capacity, do not force full extraction onto production root or RAM.

## Next gates
1. Exact-head CI and independent review.
2. Representative full-scope compression benchmark including CPU, RAM, elapsed time, output size and archive integrity; no output archive written during benchmark.
3. Versioned zstd archive/restore implementation with legacy gzip compatibility before any format migration.
4. Full restore proof in a safe isolated target before changing backup retention.
5. Explicitly reviewed and reversible cache cleanup canary only after the dependency-aware scanner and restore gates permit it.