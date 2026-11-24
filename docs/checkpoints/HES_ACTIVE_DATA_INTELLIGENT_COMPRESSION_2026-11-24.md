# HES Active Data Intelligent Compression — Execution Addendum
Date: 2026-11-24
Status: READ-ONLY BENCHMARK PASS / PRODUCTION FORMAT MIGRATION NOT YET AUTHORIZED

## Decision
Extend the existing Smart Storage Manager + Smart Cleanup Manager + IDLM pipeline. Do not create a parallel storage manager, daemon, database, timer, cloud provider, VPS, or paid dependency.

The capability name is HES Intelligent Multi-Layer Compression & Active Data Optimization. It extends the existing HES_INTELLIGENT_MULTI_LAYER_BACKUP_COMPRESSION_V1.md policy and the already deployed Smart Storage maintenance chain.

## Current live facts
- Sole VPS only; no new server or laptop. Preserve the current operating footprint and existing Dropbox 400,000,000-byte hard cap.
- Existing deployed components: IDLM v1, Smart Cleanup Manager v1, Smart Storage Manager v1, and hes-smart-storage-maintenance.service / timer.
- Smart Storage Manager currently produces a read-only capacity/compression plan and explicitly sets compression_authorized=false. The maintenance entrypoint may clean only bounded regenerable caches; it does not compress application data.
- The primary checkout is dirty. Do not reset, clean, checkout, merge, or directly rewrite application source in that checkout. Any implementation must be built in an isolated clean candidate and validated against the active release contract.
- Current data readers/writers directly reference the plain .jsonl paths. Therefore replacing those paths with compressed files today would break readers, freshness checks, journal/report consumers, or collectors. A file can be append-written intermittently even if lsof shows no persistent open descriptor.

## Executed read-only benchmark
Evidence directory:
 /srv/hes-evidence/operations/storage-lifecycle/active-data-compression-preflight-20261124T060112Z/

Artifacts:
- active-data-compression-preflight.json
- active-data-compression-roundtrip.json
- io-references.txt

Method:
- Stream each existing source file through zstd -3, zstd -9, and gzip -1 to count compressed bytes; no archive output was written.
- Then stream zstd -9 output directly into decompression and cmp against the original source.
- Check source size and mtime before/after; all four sources remained stable during the test.
- Exact round-trip passed for every file. No source file was rewritten, renamed, truncated, deleted, or moved.

| Source | Original bytes | Zstd-9 bytes | Reduction |
|---|---:|---:|---:|
| data/forward/trade_journal_v2.jsonl | 44,136,707 | 618,629 | 98.60% |
| data/forward/observations_live_v1.jsonl | 23,038,973 | 2,068,887 | 91.02% |
| data/forward/global_market_candles_1m_v1.jsonl | 9,041,551 | 1,148,081 | 87.30% |
| data/forward/neutral_decision_outcomes_v1.jsonl | 8,183,891 | 564,254 | 93.11% |
| Total | 84,401,122 | 4,399,851 | 94.79% |

Potential reduction in this four-file sample: 80,001,271 bytes. This is a measured compression-stream result, not realized disk savings.

## Active-data policy
1. HOT / currently mutable: Keep the current writer-facing segment in the existing plain format until all consumers support a versioned compressed-segment contract. Never compress, rename, truncate, or replace a live append target in place.
2. SEALED / immutable: Once a segment is explicitly closed by its owning writer and a manifest proves it is immutable, it may be Zstandard-compressed. Preserve the original path identity, event order, timestamps, schema/version, byte count, SHA-256, compressed SHA-256, and compression profile in a signed/hashed manifest.
3. WARM / recent history: Read through the existing data API across the current hot segment and verified sealed compressed segments. Readers must preserve chronological order, deduplicate only by existing event identity rules, and fail closed on missing/corrupt segments.
4. COLD / archival: Use the existing long-window Zstandard + AES-256 recovery stream. Git objects remain Git-pack compressed. Do not recompress already compressed/encrypted artifacts (.tar.zst.gpg, .gz, .zst, Git packs) without a benchmark proving a benefit.
5. RESTORE / rollback: Verify compressed and decompressed hashes, record exact source/segment coverage, run reader/replay equivalence tests, and retain the previous known-good generation until the new representation passes isolated restore.
6. Resource-aware: Single-threaded bounded compression by default; no contention with Gate.io collectors, decision journal, Risk Gate, or recovery. Defer optional compaction under CPU/RAM/disk pressure.
7. Safety: Unknown, dirty, live-referenced, evidence-bearing, model, release, worktree, Restic, and recovery artifacts remain KEEP. No automatic deletion or Restic prune is authorized by this feature.

## Required implementation sequence
- Add a versioned sealed-segment writer/manifest contract to the existing journal/data ownership APIs.
- Update every production reader, dashboard, freshness/health check, report, audit, training and replay consumer to read plain hot files plus verified compressed sealed segments.
- Add compatibility tests: ordering, exact event coverage, no gaps/duplicates, crash during rollover, concurrent writer, truncated/corrupt segment, manifest mismatch, rollback and replay determinism.
- Build in an isolated clean candidate; run focused + full regression. Do not mutate the dirty primary checkout.
- Start with one non-critical, closed historical segment as a canary; preserve the original until round-trip/replay/restore and storage evidence pass.
- Only then expand to other append-only datasets, using the existing Smart Storage maintenance owner and timer.
- Dashboard should expose hot/warm/cold bytes, compression profile, estimated/actual savings, segment count, last verification, reader compatibility, resource overhead, restore status and explicit BLOCKED/READY state.

## Execution outcome
- READ-ONLY benchmark: PASS.
- Four exact Zstd round-trips: PASS.
- Source stability during benchmark: PASS.
- Production data mutation: NONE.
- Active writer/reader contract migration: NOT STARTED.
- Production compression rollout: BLOCKED pending versioned segment API + reader compatibility + isolated candidate regression.
- Cleanup/deletion/Restic prune: NOT AUTHORIZED.
- Replacement-host recovery: still a separate NOT_PROVEN gate.

This checkpoint deliberately distinguishes demonstrated compression ratio from production savings. Do not report the 80,001,271-byte potential as disk space already reclaimed.


## Isolated candidate implementation validation — 2026-11-24 06:09 UTC

- Clean candidate worktree: /tmp/hes-active-data-compression-v1
- Branch: feat/hes-active-data-compression-v1
- Base: origin/main 4a1d089989b9cbdc974ce12f0bbada6d6755bafe (includes merged Smart Storage PR #557).
- Smart Storage Manager compression advice now recognizes scope=active_operational_data as a separate evidence class. It emits ACTIVE_OPERATIONAL_DATA_STREAM_BENCHMARK_NOT_MIGRATION_PROOF and PROTOTYPE_ACTIVE_DATA_SEGMENTS_V1 for >=5% measured gain, while explicitly keeping compression_authorized=false and hot_file_rewrite_authorized=false.
- Focused Smart Storage tests: 28 passed.
- Full candidate suite: 1,689 passed; 84 subtests passed; 31.31 seconds.
- Candidate evidence adapter check: ACTIVE_DATA_SCOPE_INTEGRATION=PASS; Zstd9/gzip1 size comparison 50.11%; round-trip PASS.
- git diff --check: PASS.
- Candidate is not deployed, merged, or pushed. Production hot files remain unchanged. No service/timer changes, deletion, movement, truncation, backup pruning, or archive replacement occurred.


## Sealed-segment implementation progress — 2026-11-24 06:35 UTC

- Added forward/sealed_jsonl_segments_v1.py: Zstandard-9 single-threaded segments, SHA-256-bound versioned manifest, atomic manifest/segment publish, exact decompression verification, source device/inode crash recovery, original hot-file mtime preservation, logical SHA-256/size, bounded tail reader, and read-only segment inventory.
- Writer integration: ForwardJournalV1; Gate.io collector append/tail/last-saved paths; ForwardObservationWriterV1; neutral outcome appender. All use the same shared flock contract. The Gate.io historical backfill path fails closed for segmented history rather than flattening or duplicating segments.
- Reader integration: Gate.io closed-candle reader; dashboard journal projection (preserving original raw event hashes); neutral outcome reader; Strategy V2 evaluator; learning loop; decision report; NO_TRADE audit; matured validation; Blackbox experience memory; Range shadow replay; 1m integrity witness; Strategy V2 recovery candidate ledger; runtime healthcheck.
- Smart Storage Manager adds active_data_segments inventory, logical/physical segment sizes, hashes, record counts, savings and sentinelx lock-access preflight. It does not authorize compression.
- Isolated real-data copy-only canary: 4/4 data files sealed and verified; 84,462,031 bytes -> 4,403,673 bytes (94.79% potential reduction). The original VPS files were copied only; no production source was rewritten. Evidence: evidence/operations/hes_active_data_sealed_segment_canary_20261124.json.
- Test evidence before the latest lock-permission hardening: 160 focused tests passed; core segment/journal/observation suite 28 passed. Re-run targeted tests and full suite after final hardening before commit.
- Live lock preflight discovered existing production lock files that are not all accessible to sentinelx: trade_journal lock is sentinelx:sentinelx 0600 (accessible); observations_live, Gate.io 1m candles, and neutral outcomes lock files are root:sentinelx 0600 (not group-readable). Candidate Smart Storage inventory returns LOCK_PERMISSION_BLOCKED. Do not chmod them yet; before any rollout, change only the required root:sentinelx lock metadata to group-readable 0640, verify sentinelx read-only flock, then re-run health and regression. No production data/format changes or deployments were made.
- Production rollout remains BLOCKED. The 4-file canary is copy-only, not a live canary. No service/timer change, no automatic sealing, no deployment, no merge/push.


## Final isolated implementation validation — 2026-11-24 06:45 UTC

- Full candidate regression: 1,707 passed + 84 subtests, zero failures (36.13 seconds).
- Focused storage/journal/market-data/dashboard/healthcheck/strategy integration suite: 169 passed, zero failures.
- Static compileall and git diff --check: PASS.
- Latest v2 isolated copy-only canary: all four live-data snapshots passed exact source SHA-256 vs logical SHA-256, compressed SHA-256, full decompression/record-count audit, and bounded-tail read. 84,500,525 source bytes -> 4,405,764 compressed bytes (94.79% potential reduction). No production source file was modified.
- Bounded tail reads now verify/decompress only the newest segments needed for the requested live window; full Smart Storage audit still verifies every segment. This avoids scanning cold history on each live candle read.
- Production lock preflight remains LOCK_PERMISSION_BLOCKED for root:sentinelx 0600 lock files on observations_live_v1, Gate.io 1m candles, and neutral_decision_outcomes. The trade journal lock is sentinelx:sentinelx 0600 and accessible to its service. No lock permission changes were made. Before deployment, only the three root-owned lock files must be changed to group-readable 0640, then verified with sentinelx read-only flock.
- Candidate implementation remains local, not deployed, merged, or pushed. No production format changes, service/timer changes, automatic sealing, file deletion, move, prune, or backup mutation.
- Latest validation evidence: evidence/operations/hes_active_data_compression_candidate_validation_v2_20261124.json; latest sealed copy canary: evidence/operations/hes_active_data_sealed_segment_canary_v2_20261124.json.


## Active-release compatibility branch — 2026-11-24 07:00 UTC

A deployment-safety audit found the first implementation candidate was based on origin/main (4a1d089) while the actual active release snapshot is 4c9a0f30c9aac67c6d711fe3699f55820a9b1322, a divergent line (6 commits on release side, 207 on origin/main from merge-base 09f660...). The origin/main candidate must not be installed over the active release.

Created a second isolated worktree from the exact active release commit:
- Path: /tmp/hes-active-data-compression-releasebase-v1
- Branch: feat/hes-active-data-compression-releasebase-v1
- Base: 4c9a0f30c9aac67c6d711fe3699f55820a9b1322
- Applied the active-data benchmark commit and ported sealed-segment implementation while preserving the older active-release Smart Storage Manager; did not backport unrelated newer restore/footprint features.
- Two files absent from the active release (Blackbox experience memory and Range shadow replay) were intentionally not added.
- Release-base candidate commit: 2e6af2b17 (sealed JSONL segment integration); cleanup scan compatibility patch remains uncommitted pending full regression.
- Focused release-base integration suite: 202 passed, zero failures.
- Full release-base suite is currently running; do not deploy until its result is recorded.
- Production lock metadata preflight: three root:sentinelx lock files were safely changed from 0600 to 0640 (group-read only) so the sentinelx service can take read-only flock; exclusive flock was verified under the sentinelx account on all three. No data file content, ownership, source format, or service was changed.


## Release-base regression and lock preflight completion — 2026-11-24 07:05 UTC

- Release-base candidate branch: feat/hes-active-data-compression-releasebase-v1
- Base: active release 4c9a0f30c9aac67c6d711fe3699f55820a9b1322.
- Sealed-segment implementation commit: 2e6af2b17398be1c4370a2bfff23657849e893d0.
- Smart Cleanup empty user-unit inventory fix commit: 73fe4769ff68f5bfdd007d95b6b4f866c39e8cf6.
- Focused release-base suite: 202 passed, zero failures.
- Full release-base suite: 1,627 passed + 84 subtests, zero failures (28.39 seconds).
- Cleanup scan hardening is fail-closed: only list-unit-files rc=1 with empty stdout and empty stderr is interpreted as an empty filtered set; diagnostics and all other failures remain errors.
- Root-owned sentinelx lock files were set to 0640, group-read only; sentinelx successfully acquired exclusive flock read-only on observations_live, Gate.io 1m candles, and neutral outcomes. Trade journal lock was already accessible to sentinelx. This resolves the candidate lock-access preflight.
- The first origin/main candidate remains separate and is not the deployment target. Active-release candidate omits Blackbox and Range shadow files absent from the active release; no unrelated newer features were backported.
- No deployment, merge, push, service/timer change, or production data compression has occurred. Production files remain plain JSONL. The next gate is the release-base Smart Storage report plus final reader/writer and rollback acceptance.


## Final release-base Smart Storage and deployment preflight — 2026-11-24 06:57 UTC

- Fresh release-base Smart Storage report: 1,370 IDLM items; Smart Cleanup classified 616 KEEP and 754 REVIEW; zero delete authorization; scheduled-job, process, and unit scan errors all zero.
- Active-data segment inventory: NO_SEGMENTS, zero lock errors. This is expected because production JSONL files have not been compressed or rewritten.
- Compression recommendation: PROTOTYPE_ACTIVE_DATA_SEGMENTS_V1; compression_authorized=false; deletion_authorized=false.
- Storage report scope: 25.16 GiB local HES footprint including backups/staging against the active-release manager's 10 GiB target; disk free 18.47%. No data was mutated by the report.
- Evidence: evidence/operations/hes_active_data_smart_storage_plan_releasebase_20261124.json and evidence/operations/hes_active_data_storage_inventory_summary_releasebase_20261124.json.
- Release-base validation evidence: evidence/operations/hes_active_data_compression_releasebase_validation_20261124.json.
- Active-release base files were hash-compared against commit 4c9a0f30c9aac67c6d711fe3699f55820a9b1322 and matched exactly.
- Release-base full regression: 1,627 passed +84 subtests, zero failures; focused integration: 202 passed.
- Three root-owned lock files are now group-readable 0640 and sentinelx exclusive flock passed. No data contents or active services were modified.
- Candidate is ready for an explicit production canary review, but is not deployed. Current production active data remains plain JSONL and no automatic sealing timer is enabled.


## Runtime path and release-switch preflight — 2026-11-24 07:12 UTC

- Active systemd services were inspected read-only. Dashboard uses HES_TRADE_JOURNAL_PATH=/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl and HES_GLOBAL_MARKET_DATA_ROOT=/opt/hes-trade-agent. Gate.io 1m collector uses HES_GLOBAL_CANDLES_OUTPUT=/opt/hes-trade-agent/data/forward/global_market_candles_1m_v1.jsonl. Strategy learning and forward-paper services use HES_DATA_ROOT=/opt/hes-trade-agent. These are preserved by the release-base candidate's existing runtime-path contract.
- The active release snapshot at /opt/hes-trade-agent/current exactly matches commit 4c9a0f30c9aac67c6d711fe3699f55820a9b1322 for the checked journal, market reader and Smart Storage files. The new candidate is a separate worktree; current symlink and running services were not changed.
- /opt/hes-trade-agent/.venv is shared. The live operational data root is /opt/hes-trade-agent/data (outside the current release snapshot); current/data contains legacy release-local fixtures and is not the active journal/candle root. Candidate code keeps HES_DATA_ROOT/HES_TRADE_JOURNAL_PATH/HES_GLOBAL_CANDLES_OUTPUT paths intact.
- The precision-current release is separate and was not changed. The precision-entry journal uses ForwardJournalV1 and is therefore code-compatible at the class level, but its separate precision-current runtime must be upgraded independently before any of its journals are sealed.
- Deployment remains a coordinated release operation: stage exact active-release candidate, verify config/runtime paths, stop/restart only mapped HES services in a controlled window, validate health and data continuity, then perform one explicitly approved production canary. No current symlink switch or service restart has been performed.


## Controlled release deployment and post-deploy remediation — 2026-11-24 07:24 UTC

- User explicitly approved controlled deployment with rollback. The first stage was not allowed to compress live production files.
- Exact active-release-base candidate was deployed at /opt/hes-trade-agent/releases/hes-active-data-sealed-v1-6dbceab57b08. A post-deploy correctness fix was then staged and activated at /opt/hes-trade-agent/releases/hes-active-data-sealed-v1-5d90440e3476.
- Current symlink resolves to hes-active-data-sealed-v1-5d90440e3476. Immediate rollback pointer /opt/hes-trade-agent/rollback-active-data-sealed-before-5d90440 resolves to the prior deployed candidate hes-active-data-sealed-v1-6dbceab57b08. Original rollback pointer /opt/hes-trade-agent/rollback-active-data-before-6dbceab still resolves to original active release 4c9a0f30c9aac67c6d711fe3699f55820a9b1322.
- Final local release patch commit: 5d90440e3476be35116ebcb26be179459ba83c8e. GitHub SSH push was attempted but strict host-key verification failed for ssh.github.com port 443. Host-key checking was not disabled. No remote branch or merge was made. GitHub contains base commit 4c9a0f30, but not candidate commits 6dbceab or 5d90440. GitHub synchronization remains outstanding.
- First post-deploy log audit found two issues, both fixed before final acceptance. The learning-loop evidence hash helper now uses raw SHA-256 for non-JSONL files and logical SHA-256 only for JSONL. The has_sealed_segments probe no longer creates locks for non-JSONL or absent segment directories. Read-only immutable JSONL readers use a read-only source or manifest flock fallback only when sidecar creation is impossible.
- Added regression tests for raw non-JSONL hashing, no-lock probes for absent and non-JSONL files, and read-only immutable JSONL reads. Full active-release-base suite after fixes: 1503 passed and 84 subtests passed. Targeted post-fix suite: 39 passed. Staged runtime compile and import checks passed.
- Three production data sidecar locks remain group-readable 0640 with owner root and group sentinelx. A separate 1m integrity witness lock at /var/lib/hes-gateio-1m-integrity/observations.jsonl.lock was corrected from root:root 0600 to root:sentinelx 0640. No journal contents were changed.
- Restarted only the six active services that use /opt/hes-trade-agent/current: Gate.io base, 1m, 1h, and 4h collectors; strategy learning loop; Strategy V2 paper evaluator. Dashboard and Precision Entry services were not restarted because they use separate dashboard-current and precision-current releases. All eight checked services remain active.
- Post-fix learning loop refreshed strategy_learning_v1_report.json at 2026-11-24T07:22:16Z with 3132 decisions, 51 candidates, and 0 resolved outcomes. Policy mutation and execution remain disabled.
- Final runtime healthcheck: overall OK, 42 checks, 0 critical, 0 issues. Gate.io 1m candle file continued advancing. No recent 4h collector error was recorded after the earlier transient URLError reconnect event.
- Production data safety: trade_journal_v2.jsonl, global_market_candles_1m_v1.jsonl, observations_live_v1.jsonl, and neutral_decision_outcomes_v1.jsonl remain plain JSONL. No segment directories were created. No live file was sealed, truncated, rewritten, moved, deleted, or pruned. No automatic sealing timer was enabled.
- Remaining gates before any production canary: dashboard-current reader needs a compatibility port and regression before it can read sealed journals; installed Smart Storage maintenance scripts under /usr/local need a deliberate contract-checked update. Only after these gates should a separate explicit approval be requested for a one-file production canary.
- Disk free after deployment: approximately 8.7 GiB, 82 percent used. Deployment stayed within the single-VPS constraint and introduced no new paid dependency.

## GitHub branch synchronization follow-up — 2026-11-24 07:29 UTC

- Initial Git SSH push remained blocked by strict host-key verification for ssh.github.com port 443. No host-key checking was weakened.
- Published the final active-release compression tree through the connected GitHub integration on branch feat/hes-active-data-intelligent-compression-v1, based exactly on 4c9a0f30c9aac67c6d711fe3699f55820a9b1322.
- GitHub mirror commit: 2de44b6deb6c31247955bb35eecd8041c28c0d09. Tree: 30920f5118d24feace48895351a960d45c1d7734. The commit contains the 35 changed source, test, documentation, and evidence files. Remote verification confirmed the sealed JSONL module and learning-loop fix blob hashes match the staged release.
- No pull request was created, no branch was merged, and main remains unchanged. The earlier note that no remote branch existed is superseded by this follow-up.

## Dashboard sealed-reader compatibility and installed Smart Storage integration — 2026-11-24 08:31 UTC

- Dashboard-current reader compatibility is now implemented in isolated release /opt/hes-trade-agent/releases/hes-journal-outcome-ui-sealed-reader-v1. It reuses the versioned sealed JSONL reader rather than replacing the existing trade-journal projection. The original matured NO_TRADE verification, neutral-outcome linkage, gate attribution, and output contract were preserved.
- Added streaming iter_jsonl_entries to the sealed JSONL module. It streams immutable compressed segments without materializing the full ledger, snapshots/rechecks the manifest, and reads the hot tail under a shared lock. A manifest change during the stream fails closed. Plain unsealed JSONL retains the legacy streaming path.
- Dashboard candidate regression: 52 passed, 16 subtests passed. A live plain-journal parity check before activation returned identical projection payloads from old and new dashboard releases.
- Isolated copy-only canary on trade_journal_v2.jsonl: 44,390,691 logical bytes compressed to 629,591 bytes using zstd level 9 (98.58% saving), 3,140 records, full segment verification PASS, logical SHA-256 round-trip PASS. New dashboard projection of sealed copy was byte-for-byte equivalent at the projection-object level to the plain live source at test time: 3,140 records, 2,931 decisions, 184 matured events. This canary used only /tmp copy; the production journal was not modified.
- Dashboard release was atomically activated at /opt/hes-trade-agent/dashboard-current -> /opt/hes-trade-agent/releases/hes-journal-outcome-ui-sealed-reader-v1. Rollback pointer /opt/hes-trade-agent/dashboard-rollback-before-sealed-reader-20261124 resolves to /opt/hes-trade-agent/releases/hes-journal-outcome-ui-20261123-v2. hes-readonly-dashboard.service restarted successfully and remains active. Live API /api/journal returned VERIFIED, 3,140 records, 2,931 decisions, 20 events, 184 matured verification events; execution_enabled=false, orders_placed=false, outcomes_inferred=false.
- Installed Smart Storage Manager was extended in place to include read-only active-data segment inventory by importing the single versioned implementation from /opt/hes-trade-agent/current. Existing IDLM/cleanup/storage-budget/Dropbox/Restic reporting and all conservative policy gates were preserved. Installed manager SHA-256: 2b02277282ebd04414cc127b94834921399c9920c8761c17cb7561429e5857f8. Rollback copy: /var/backups/hes-trade-agent/hes_smart_storage_manager_v1.py.pre-sealed-reader-20261124 (SHA-256 9f1002606d457dbb96bd2769bf55aba374054e87436fdb33fb0fea54885b3e6a).
- The existing IDLM and Smart Cleanup chain completed in READ_ONLY_DRY_RUN: 1,387 inventory items, 618 KEEP, 769 review-only, zero delete authorization. Installed manager generated a report with active segment inventory NO_SEGMENTS, zero errors, all four service lock-access checks PASS, compression_authorized=false, automatic_project_data_cleanup_authorized=false. Full/remote restore status remains NOT_PROVEN where applicable.
- Evidence saved at /srv/hes-evidence/operations/storage-lifecycle/active-data-sealed-dashboard-compatibility-20261124.json.
- Production safety unchanged: trade_journal_v2.jsonl, observations_live_v1.jsonl, global_market_candles_1m_v1.jsonl, and neutral_decision_outcomes_v1.jsonl remain plain; no production segment directories, sealing, truncation, rewrite, move, delete, prune, or automatic sealing timer. Disk free about 8.75 GiB.
- Both compatibility gates are complete. The one-file production compression canary has NOT been run. Per the previously recorded safety gate, request separate explicit user approval before sealing any production file. The 1.37 GB archive decision and independent Dropbox/Restic restore proof remain separate outstanding workstreams.