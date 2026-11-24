# HES Intelligent Multi-Layer Backup & Compression v1

**Policy date:** 2026-11-22
**Scope:** existing HES VPS + existing Dropbox account only.
**Owners:** existing Smart Backup, Smart Storage Manager, Smart Cleanup Manager and recovery runbooks. No parallel manager or new storage provider.

## 1. Permanent objectives

1. Identify duplicate content by cryptographic hash and Git object identity; reduce duplicate payload storage without deleting path, provenance, timestamp, or source evidence.
2. Use layered, content-aware compression: Git pack compression for repository objects, long-window Zstandard for the combined recovery stream, then AES-256 encryption. Zstandard chooses encoding per block; the long window is sized to capture repeated HES rehearsal datasets and clone content.
3. Maintain an independent recovery set: primary checkout/object store, exact refs, worktree/candidate tracked diffs, untracked overlays, non-Git candidate inventory, deployment manifests, configuration inventory, evidence and restore instructions.
4. Keep generations bounded. Build a new uniquely named candidate, preserve the previous known-good copy, and replace the canonical Dropbox core only after local and remote restore acceptance.
5. Perform exact capacity preflight before archive creation and again before transfer. Canonical encrypted core target is ≤380,000,000 bytes; the complete HES Dropbox backup folder must remain ≤400,000,000 bytes. Stop before writing or uploading if the projected result breaches either limit.
6. Run an isolated real restore before pruning, overwriting, or retiring an older recovery generation.

## 2. Reuse and data flow

`Smart Backup → Smart Storage Manager preflight → differential recovery inventory → content dedup → layered archive/compression → AES-256 encryption → bounded Dropbox transfer → remote checksum/download → isolated restore drill → restore marker → Smart Cleanup/retention`.

- Local Restic remains the incremental, content-addressed backup on the VPS.
- Dropbox stores the compact rolling off-site recovery core, not a second copy of the multi-gigabyte Restic repository.
- GitHub refs are used only when an exact commit-to-ref equality is verified. Otherwise local-only nested repositories are bundled.
- Root Git partial-clone/promisor objects must be explicitly hydrated and verified; no backup may silently rely on a lazy network fetch during restore.
- Nested repositories represented by a compact depth-1 bundle retain the exact HEAD commit, full tree and blobs, tracked diff, untracked tar, original shallow-state metadata and explicit archive shallow boundary. Their full historical ancestry is retained in the local full-history recovery tier, not silently claimed to exist in the compact bundle.
- Optional disabled local-LLM weights are fingerprinted separately; they are not part of the compact core. They must not be reported as backed up unless an independent local Restic coverage check proves it.

## 3. Deduplication and evidence preservation

- Use one shared Git bundle for local-only nested repositories where their current trees can be independently verified. Shared pack storage deduplicates identical Git objects across repositories.
- Keep the exact repository path, HEAD, branch, source shallow boundary, archive shallow boundary, ref, bundle hash, tracked-diff hash, untracked-tar hash and excluded-file reason in machine-readable metadata.
- Scan untracked files and staged non-Git snapshots by SHA-256. Duplicate path occurrences remain in the inventory. The source files are not removed or rewritten; the long-window compression layer stores repeated payloads efficiently.
- Reproducible caches may be omitted only when explicitly allowlisted and fingerprinted. Unknown, dirty, untracked, or evidence-bearing paths remain KEEP unless an independently verified recovery representation exists.

## 4. Compression, encryption and chunked transfer

- Current compact-core profile: tar stream → adaptive Zstandard level 9/12/15 with a 128/256/512 MiB long window (`--long=27/28/29`, selected from available RAM) → GPG symmetric AES-256. The preflight and production streams must use identical settings.
- Restore compatibility is mandatory: every Zstandard integrity test and streaming decompression path must explicitly allow the same 512 MiB window (`zstd -t --long=29` and `zstd --long=29 -dc`). A default 128 MiB decoder is not compatible with this archive profile.
- Git packs provide the repository-object compression layer. Zstandard's block encoding and long window capture repeated JSONL/CSV and clone content across staged trees.
- Dropbox transfer uses rclone's chunked upload session with an explicit 64 MiB chunk size. The encrypted archive remains one logical recovery object; transport chunks are not separate recovery generations.
- Keep the encryption passphrase/key outside the archive. Capture key-file permissions and recovery-custody instructions without copying secret contents into logs or manifests.

## 5. Capacity and version controls

- Preflight the exact encrypted byte stream before creating an archive; require the archive ≤380 MB and enough local free space for the candidate plus the configured emergency reserve.
- Apply a second byte cap while writing the archive. Do not rely on a post-build size check alone.
- Before transfer, measure the exact current Dropbox HES folder bytes and projected total. A transfer is blocked if it would breach 400 MB or the Dropbox account free-space reserve.
- Use immutable, unique candidate names in staging. Never use broad `sync --delete` against the HES backup folder.
- Keep the previous verified core recoverable until the candidate has passed download, SHA-256, AES-256 decryption, Zstandard integrity, safe extraction, Git/ref validation, overlay reconstruction and critical-file checks.
- Only after the new remote restore marker is durable may Smart Cleanup prune exact superseded objects listed by the retention plan. Preserve unknown objects and the canonical manifest, hash, provenance and runbook sidecars.

## 6. Restore acceptance gates

A candidate is not READY merely because upload or checksum succeeded. Required gates:

1. Local archive SHA-256 equals the candidate manifest and sidecar.
2. AES-256 decryption succeeds using the separately held recovery key.
3. Zstandard integrity test passes.
4. Tar path-safety scan rejects absolute paths, `..` traversal, unsafe links and unexpected device entries.
5. Full isolated extraction succeeds without touching production paths.
6. Primary Git HEAD, required refs, all reachable objects and critical release manifests verify.
7. Every differential row has its exact HEAD/ref; every shared-bundle ref is present; shallow boundaries are restored; tracked diffs apply; untracked overlays extract and match recorded hashes.
8. Critical configuration/evidence hashes reconcile. No secret contents are included in the archive.
9. Remote object is downloaded again and passes the same restore drill before canonical replacement or pruning.
10. Replacement-host boot/recovery remains a separate gate and must not be inferred from same-host restore success.

## 7. Dashboard contract

Read-only dashboard fields: last attempt, last successful preflight, exact estimated and actual bytes, Dropbox folder bytes/free quota, compression profile, dedup bytes/groups, source HEAD/manifest, archive SHA-256, encryption/decryption status, local restore status, remote restore status, age, last known-good generation, and deterministic failure reason. States remain distinct: `CREATED`, `PREFLIGHT_PASSED`, `UPLOADED`, `REMOTE_VERIFIED`, `RESTORE_TESTED`, `RECOVERY_READY`, `BLOCKED`, `UNKNOWN`. No dashboard delete/prune/move action is exposed.

## 8. Current execution notes — 2026-11-22

- The main repository is a partial clone with a promisor remote. Missing reachable blobs were explicitly fetched by object ID; the 52 pinned root commit closures were then verified with no missing reachable objects.
- The compact differential generator now inventories worktrees, candidates, forward integrations, staging/archive/script release clones and root-level PR/isolated clones before the builder prunes those trees from the main filesystem tar.
- A 9-repository shared depth-1 bundle probe completed successfully at 15,391,624 bytes with 9 explicit shallow boundaries. This preserves each exact current commit/tree/blob state; full ancestry is not claimed by the compact bundle.
- Staging duplicate-content scan found 565,312,461 bytes across 3,198 files, 1,275 unique hashes and 312,388,149 duplicate extra bytes. Duplicate paths remain in source and inventory; the long-window compression layer is intended to compress the repeated payloads without deleting evidence.
- A full-history Git bundle probe for four local-only repositories reduced 579,280,191 bytes of individual bundles to 198,857,181 bytes in one shared bundle (65.7% less) before the additional compact depth-1 profile. This is a measured probe, not a claim that the Dropbox core already contains the full historical packs.
- Previous Dropbox core is locally copied and revalidated as a rollback source. No Dropbox object has been overwritten or pruned during this build work.
- Final archive size, remote transfer, full isolated restore, and post-restore retention are acceptance gates and must be recorded with exact evidence before this section is marked complete.

## Operational hardening — 2026-11-22

- **Live data is frozen, not read live during tar:** data/forward is copied to a timestamped recovery-metadata snapshot with per-file SHA-256, size and source-growth checks. The archive restores that snapshot to the original opt/hes-trade-agent/data/forward path and preserves the root directory metadata. The collector is never stopped.
- **The raw forward workspace is excluded from the compact core.** Its nested Git repositories are represented by a shared depth-1 Git bundle plus per-repository tracked diffs and untracked overlays. The five-ref bundle is tested by writing its recorded shallow boundaries into the restore repository's .git/shallow before fetching, then running git fsck --full. Non-Git candidate trees are path/hash inventoried and their full content remains in local Restic.
- **Optional local-LLM assets:** model weights are fingerprinted in model-assets.json but excluded from both the compact core and local Restic while the local-LLM service is disabled. They are optional and are not recoverable from the current backup tiers; reacquire them only if that feature is enabled later.
- **Legacy recursive backup staging** under forward/.backup-staging is excluded. A non-secret inventory records hashes for the old encrypted archive and sidecar; passphrase/token contents and hashes are deliberately withheld. The original files remain on the VPS and are covered by the local /opt/hes-trade-agent Restic root.
- **Archive safety gate:** before publication, decrypt/decompress and scan every tar member for absolute/traversal paths, duplicate names, symlink ancestors, unsafe hardlink targets and special files. Any violation fails closed. Zstandard uses an adaptive level/window profile selected from available RAM; every decoder accepts the maximum --long=29 window.
- **Key escrow is a hard recovery gate:** the GPG passphrase is excluded from the archive. Do not mark RECOVERY_READY, overwrite the last known-good remote core, or prune legacy Dropbox objects until the operator confirms independent possession of the passphrase or completes a separate encrypted escrow. Plaintext key material must never be uploaded.
- **Local capacity retention:** preserve the current and previous verified core, current differential snapshot and non-secret failure manifests. After remote download and isolated restore pass, use the existing Smart Cleanup Manager to remove redundant local mirrors, stale snapshots and corrupt partial archives; never delete their evidence manifests first. The current capacity forecast is elevated by recent staging/mirror creation and must be recalculated after controlled cleanup.
- **Scheduling:** local Restic remains daily at 03:00 UTC; Dropbox audit and gated retention timers remain enabled. The legacy full-Restic-to-Dropbox sync is not the offsite design and must be retired after the compact-core cycle is verified. A new compact-core schedule is not enabled until the first end-to-end cycle and key escrow pass.

## Verification update — 2026-11-23

- Built the compact encrypted core `hes-offsite-core-20261123T053817Z.tar.zst.gpg` at 242,990,234 bytes (SHA-256 recorded in the dated verification checkpoint). The build preflight estimated 242,991,537 bytes, below the 380,000,000-byte cap.
- Archive safety scan passed for 17,497 members. Full isolated extraction passed; 3,891 evidence files and the 374-file live-data snapshot were reconciled, including the live snapshot manifest hash. Active, rollback and dashboard release directories were present.
- Shared nested Git bundle passed `git bundle verify`, fetch and `git fsck --full` with five refs and five explicit shallow boundaries. Focused backup tests passed: 50/50.
- Local Restic `check --read-data` passed across all 9 snapshots and 213 packs. Existing isolated Restic restore marker remains PASS with 2,155 release files verified.
- The current Dropbox contents were fully checked against the local safety mirror: 100 matching files, zero differences. No Dropbox mutation has been performed.
- The current read-only retention inventory projects 398,250,231 bytes after pruning 86 known obsolete objects, while preserving 7 KEEP and 7 KEEP_UNKNOWN objects. This inventory must be regenerated after the new remote candidate is independently restored.
- **Not complete / not RECOVERY_READY:** independent GPG key escrow has not been confirmed; the new archive has not been uploaded or restored from Dropbox; replacement-host recovery has not been tested. Do not replace the previous remote core or prune old Dropbox history until key escrow is confirmed and the candidate passes remote restore. Exact evidence: `docs/checkpoints/HES_BACKUP_VERIFICATION_2026-11-23.md` and `/srv/hes-evidence/operations/storage-lifecycle/dropbox/hes-backup-verification-2026-11-23.json`.


## Execution acceptance update — 2026-11-23 07:29 UTC

- Canonical Dropbox core: `hes-recovery-core-latest.tar.zst.gpg`, 254,167,681 bytes; SHA-256 `71816f9f535982eefc2dd781bfde013d3180db6b8f2bf24b9872cdb77c59c8c4`. The live Dropbox object hash was streamed and matched the local archive exactly.
- Full isolated core restore: PASS — 17,495 archive members, GPG AES-256 decrypt, Zstandard integrity, safe extraction, zero unsafe paths, and 2,155 active/rollback/dashboard release files verified. Latest strategy ref and commit were present in the restored Git store.
- Independent non-Git candidate sidecar: 14,086,995 bytes; SHA-256 `15218078e995544b6e08e47942f43362ca52a2baf70eee40f6af1b1ab6fb20d6`. Isolated reconstruction passed for 8,527 files / 996 unique content objects; 3,776 excluded items remain represented in the manifest with reasons and hashes.
- The cycle's exact projected Dropbox folder size was checked before transfer; worst-case prebuild projection was 394,129,172 bytes and the post-build exact projection was 268,292,447 bytes. Remote readback SHA-256 checks passed for core and candidate sidecar.
- Fresh final Dropbox inventory: 268,292,489 bytes across 17 files, 131,707,511 bytes below the 400,000,000-byte hard cap. Dropbox account quota used: 12.49%. Retention classification: 7 KEEP / 10 KEEP_UNKNOWN; zero remaining prune candidates. All unknown records were preserved.
- The existing marker-gated retention manager now treats concurrent/already-absent deletions idempotently and serializes runs with a lock. Unknown remote objects remain KEEP.
- New compact-core cycle orchestrator passed end-to-end in `VERIFY_EXISTING` mode, including candidate reconstruction, full core restore, exact remote capacity projection, canonical upload/readback, restore marker, retention, and final cap assertion.
- The scheduled systemd sandbox execution and first fresh archive build remain separate acceptance checks; replacement-host boot/recovery is still NOT_PROVEN. Do not claim RECOVERY_READY from same-host restore alone.


## Active operational data compression and transparent access — 2026-11-24

This section extends the existing Smart Backup → Smart Storage → Smart Cleanup ownership chain. It does not introduce a second manager, daemon, database, timer, provider, or storage tier.

### Hot / warm / cold data contract

- HOT: the current mutable writer-facing JSONL file remains in its existing plain format. Never compress, rename, truncate, or replace a live append target in place.
- SEALED: only a writer-closed immutable segment may be Zstandard-compressed. A versioned manifest must preserve original path identity, event order, timestamps, schema/version, provenance, byte count, source SHA-256, compressed SHA-256, and compression profile.
- WARM: the existing application data API must transparently read the current hot segment plus verified sealed segments in chronological order. Missing, corrupt, incomplete, or hash-mismatched segments fail closed.
- COLD: use the existing long-window Zstandard + AES-256 recovery stream. Git packs remain Git-pack compressed. Do not recompress already compressed/encrypted archives or packfiles without a measured benefit.

### Resource and safety contract

- Start with single-threaded bounded compression. Defer optional compaction under CPU, RAM, disk, or recovery pressure.
- No change to Gate.io canonical data source, journal semantics, decision gates, risk policy, or execution authority.
- No source file is rewritten until every writer, reader, dashboard, freshness/health check, report, audit, training, and replay consumer supports the versioned segment contract.
- Retain the previous known-good representation until exact source coverage, decompressed hash, reader/replay equivalence, and isolated restore pass.
- Unknown, dirty, live-referenced, evidence-bearing, model, release, worktree, Restic, and recovery artifacts remain KEEP. No automatic deletion or Restic prune is authorized.

### Measured active-data benchmark

Evidence files are stored under evidence/operations:
- hes_active_data_compression_preflight_20261124.json
- hes_active_data_compression_roundtrip_20261124.json
- hes_active_data_compression_benchmark_20261124.json

Four active operational JSONL streams were benchmarked read-only. Zstandard level 9 produced 4,399,851 bytes from 84,401,122 source bytes (94.79% potential reduction). Exact decompression comparison passed for all four files. This is benchmark potential, not reclaimed disk space; production files were not changed.

The Smart Storage Manager now distinguishes scope=active_operational_data from local-backup and offsite benchmarks. It reports ACTIVE_OPERATIONAL_DATA_STREAM_BENCHMARK_NOT_MIGRATION_PROOF and recommends PROTOTYPE_ACTIVE_DATA_SEGMENTS_V1 when the measured gain is at least 5%. This recommendation does not grant compression authority; compression_authorized remains false and hot_file_rewrite_authorized remains false.

### Required migration gates

1. Versioned sealed-segment manifest and writer-owned atomic rollover.
2. Transparent readers for all production consumers, preserving order, exact event coverage, deduplication semantics, and replay hashes.
3. Tests for concurrent writers, crash during rollover, incomplete tail records, corrupted compressed segments, manifest mismatch, rollback, and no gaps/duplicates.
4. Isolated clean candidate full regression and bounded resource soak.
5. One non-critical closed-segment canary, with original retained until read/replay/restore acceptance.
6. Dashboard evidence for hot/warm/cold bytes, measured savings, segment count, compression profile, verification age, CPU/RAM overhead, and recovery status.

Production compression remains BLOCKED until these gates pass.

## Sealed JSONL segment implementation — 2026-11-24

The isolated candidate adds forward/sealed_jsonl_segments_v1.py as a shared, versioned storage contract. It uses the already installed system zstd CLI (-9 -T1), not a new Python dependency or paid service.

### On-disk layout

For a canonical name.jsonl artifact:
- name.jsonl remains the plain active HOT append target.
- name.jsonl.segments/manifest.json records ordered sealed segments.
- Each segment-NNNNNNNN-<source-hash-prefix>.jsonl.zst is one independently verifiable Zstandard frame.
- Manifest records include sequence, compression profile, source/compressed byte counts, source/compressed SHA-256, source device/inode identity, record count, and first/last event/time metadata.

### Writer/reader safety

- Readers take a shared advisory lock; writers and seal operations take the same per-file exclusive lock.
- Lock files are opened read-only for flock (Linux permits exclusive flock on a read-only descriptor). Newly created locks inherit the setgid data-directory group with mode 0640, so root maintenance and the sentinelx services can coordinate without making lock contents writable.
- Smart Storage reports a LOCK_PERMISSION_BLOCKED preflight when an existing root-owned lock is not group-readable by sentinelx. Existing root:sentinelx 0600 locks must be group-readable before rollout; this metadata preflight is recorded but not changed in production.
- ForwardJournalV1 duplicate-ID detection now spans sealed segments plus the hot tail; it exposes an explicit seal() operation.
- Gate.io candle collector append, tail-read and last-saved-time paths use the shared lock and logical segmented history. Historical backfill against a segmented history fails closed instead of flattening/duplicating the manifest.
- Neutral decision outcome appends serialize through the same lock and recheck idempotency after lock acquisition.
- Forward observation writer exposes verified read() and explicit seal() and checks IDs across sealed+hot records.
- Transparent readers are integrated for the Gate.io closed-candle input, canonical decision journal/dashboard projection, neutral-outcome evaluator, Strategy V2 evaluator, learning loop, decision report, NO_TRADE audit, matured validation, 1m integrity witness, Strategy V2 recovery candidate ledger, and runtime healthcheck.
- Blackbox experience memory and Range shadow replay are not present in the 2026-11-19 active-release snapshot; they were intentionally not imported from the newer origin/main branch to avoid unrelated feature backports.

### Atomic seal and crash recovery

1. Under the exclusive writer lock, validate every source JSONL record and compute source SHA-256.
2. Compress to a temporary Zstandard frame with one thread.
3. Verify compressed SHA-256 and exact decompression comparison before publishing.
4. Atomically publish the segment, fsync its directory, then atomically publish the versioned manifest and fsync again.
5. Atomically replace the hot file with an empty file and preserve the original last-append mtime (rotation must not make a stale feed look fresh).
6. If the process stops after manifest publication but before hot-file replacement, the unchanged source device/inode plus exact source-prefix hash identify the unrotated file; readers skip that prefix and the next seal operation recovers the tail before creating another segment. A same-inode mismatching prefix fails closed. A new hot-file inode is treated as the next generation, not as a duplicate prefix.

The logical reader preserves append order, validates hashes/record counts, supports bounded tail reads, and provides logical uncompressed SHA-256 and logical byte counts. Bounded readers verify only the newest compressed segments needed to satisfy the requested tail, avoiding scans of cold history; full Smart Storage verification decompresses and verifies the complete logical stream and detects cold-segment corruption. It does not sort or silently deduplicate records.

### Isolated real-data canary (copy only)

Evidence:
- evidence/operations/hes_active_data_sealed_segment_canary_20261124.json (initial copy-only run)
- evidence/operations/hes_active_data_sealed_segment_canary_v2_20261124.json (latest schema + inode recovery + bounded-tail verification)

Four current production data files were copied to an isolated evidence directory, then sealed there only. Original source size and mtime stayed stable during snapshot; no production path was rewritten. The latest v2 run also verified source device/inode metadata, exact compressed/decompressed hashes, logical byte count, record count, full segment audit and bounded tail reads:

| Artifact | Source bytes | Sealed bytes | Saving |
|---|---:|---:|---:|
| trade journal | 44,203,616 | 621,583 | 98.59% |
| live observations | 23,038,973 | 2,068,887 | 91.02% |
| Gate.io 1m candles | 9,054,533 | 1,149,788 | 87.30% |
| neutral outcomes | 8,203,403 | 565,506 | 93.11% |
| Total | 84,500,525 | 4,405,764 | 94.79% |

All 4/4 sealed copies passed; bounded tail reads returned the expected newest records. This proves the sealed representation on copies, not deployment. The production source files remain plain and untouched.

### Operational visibility and controls

Smart Storage Manager now includes a read-only active_data_segments inventory with segment count, compressed/sealed/hot/logical bytes, record count, compression savings, manifest hash, logical hash, and verification state. It explicitly reports NO_SEGMENTS until a production canary is separately authorized and keeps production_compression_authorized=false.

Production rollout remains blocked until the complete regression suite, bounded resource soak, operational owner approval and an explicit production canary decision. No timer or service automatically seals files yet.


## Active-release compatibility and dependency scan hardening — 2026-11-24

The implementation was ported to the exact 2026-11-19 active release commit rather than deploying a branch based on the newer, divergent origin/main history. The active-release candidate preserves the release's Smart Storage Manager and does not import unrelated newer restore/footprint changes.

The existing Smart Cleanup Manager's user-systemd scan now treats only a filtered list-unit-files command that returns status 1 with both stdout and stderr empty as an empty result set. Any stderr, output, command execution failure, or other scan error still blocks the inventory. This prevents an empty enabled-service list in an active user manager from falsely blocking the storage report without weakening fail-closed behavior.

Existing root:sentinelx lock files for the active observations, Gate.io 1m candle and neutral-outcome paths were changed from mode 0600 to 0640 (group-read only). The sentinelx service account successfully acquired exclusive flock on all three using a read-only descriptor. No source data or service state changed.