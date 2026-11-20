# HES Trade Agent — DNA / Roadmap: Canonical Repository Identity

**Recorded:** 2026-10-25 (UTC)
**Status:** Identity finding is final for the currently accessible surfaces; production frontend repository remains unresolved.

## Verified repository identity

- **Repository:** `beheshti2025hesam-prog/btc_tabdeal_public_test`
- **URL:** https://github.com/beheshti2025hesam-prog/btc_tabdeal_public_test
- **Local VPS checkout:** `/opt/hes-trade-agent`
- **Branch / observed HEAD:** `feat/gateio-global-market-data-v1` / `b2466bc118217dcc6446498effe38181589ed2db` (volatile; re-check before code changes)
- **Purpose proven by its README:** first Tabdeal BTC/USDT futures public market-data collector for the HES Trade Agent Data Foundation phase; README explicitly says it does not access private balances, place orders, or trade.
- **Conclusion:** this is a real HES-related repository, but the evidence does **not** establish it as the production frontend/UI repository.

## Frontend repository resolution — canonical outcome

- **Production frontend repository:** `NOT FOUND / NOT VERIFIED`.
- **Frontend entrypoint/path:** `NOT FOUND / NOT VERIFIED`.
- **Evidence searched on 2026-10-25:** all repositories visible to the connected GitHub account (one repo returned); installed-repository searches for HES; searches for HES Trade Agent/frontend; and local directories `/opt`, `/srv`, `/var/www`, `/home` for Git repositories and common web entry markers (`package.json`, `index.html`, Vite/Next config). Local Git repos found were `/opt/hes-trade-agent`, `/opt/sentinelx-cloud-core`, and `/srv/hes-evidence/isolated-pr320-final-acceptance`; no production web-app entrypoint was found.
- The GitHub repo README was fetched and confirms the collector/data-foundation scope.
- Public global search results for similarly named trading apps are unrelated and are not evidence of project ownership; do not adopt them.

## Anti-rediscovery rule

1. Treat this document as the canonical record of the completed search. Do not restart generic searches for the same known repo.
2. Re-open this search only when new authoritative evidence arrives: a new GitHub installation/repository permission, a user-provided URL, an app deployment manifest/domain mapping, or a frontend checkout path.
3. Do not create a parallel frontend or claim the collector is the frontend as a workaround.
4. When authoritative evidence arrives, verify repository owner/name, default branch, exact frontend entrypoint, build command, runtime/deployment target, and commit SHA; then update this record and the master checkpoint in the same change.
5. Until then, keep frontend integration/release gate explicitly BLOCKED; do not delay unrelated backend/data/security work, and do not enable live trading.

## Roadmap consequence

- **Closed:** repository discovery attempt across currently connected GitHub and the sole VPS; canonical known repo identity documented.
- **Blocked on external evidence:** production frontend repository and entrypoint identification.
- **Next actionable step:** continue existing global market-data → analysis/runtime integration and deployment/security gates. Ask for access/URL only if no new connected evidence becomes available; do not fabricate a repo.
- **Delivery target:** 2026-11-19.

## Product ambition and non-negotiable evidence standard — 2026-10-27

The user's enduring product vision is that **HES Trade Agent should aim to become materially smarter, more efficient, more profitable, and more user-friendly than the strongest comparable systems used by major global financial institutions**. This is an aspirational north star, not a claim of current superiority or guaranteed returns. It must guide prioritization and remain explicit in future project checkpoints.

Translate the ambition into evidence-backed acceptance gates:

1. **Intelligence:** multi-agent reasoning with independent specialist evidence, calibrated uncertainty, regime awareness, and gate-by-gate attribution; never treat unconfirmed market movement as proof that a trade should have been taken.
2. **Efficiency:** one canonical market-data path, deterministic/reproducible runs, bounded compute/API cost, deduplicated events, reliable recovery, and no parallel duplicate product implementations.
3. **Profitability discipline:** net-of-fees/slippage/funding evaluation on untouched out-of-sample data, baseline comparisons, drawdown/tail-risk controls, sample-size and confidence reporting, and no profit/win-rate promises without verified evidence.
4. **Risk and governance:** fail-closed risk veto, NO_TRADE as a valid outcome, immutable run lineage (data/config/code hashes), paper-first promotion gates, and no live execution or automatic policy mutation before explicit approvals and all evidence gates pass.
5. **User experience:** discoverable status, clear explanations of why a decision was made/rejected, actionable blockers, responsive accessible UI, and honest freshness/uncertainty indicators. Do not fabricate or build a parallel frontend while the production frontend repo remains unverified.
6. **Transferability:** universal core independent of exchange, venue, asset class, country, symbol, timeframe, or strategy; venue-specific behavior stays behind adapters/profiles.
7. **Continuous learning:** learn from both accepted and rejected decisions with forward outcomes, counterfactuals labelled as such, source hashes, complete horizon checks, and no leakage from future data into past decisions.

**Permanent project rule:** compare HES against relevant institutional-grade baselines with reproducible evidence. If superiority is not measured, say “not yet demonstrated”; never imply that aspiration itself proves performance. Keep this north star in the DNA and master checkpoints, not only in chat.


## 2026-11-03 Precision Entry Engine checkpoint

See `docs/checkpoints/MASTER_CHECKPOINT_PRECISION_ENTRY_2026-11-03.md`. The isolated candidate is `candidates/precision-entry-engine-20261103/`; production `current` remains unchanged and live execution remains OFF.


## Intelligent Data Lifecycle Manager (IDLM) — accepted DNA / roadmap decision — 2026-11-08

**Status:** Architecture accepted. Phase A read-only inventory and policy design are in progress. No automatic deletion, archive mutation, production cleanup, or new service activation is authorized until the corresponding acceptance gate passes.

### Purpose

HES must manage storage as a permanent, market-agnostic core capability. It must prevent uncontrolled disk growth, detect stale or regenerable data, forecast capacity pressure, and preserve all information required for market-data integrity, trade/NO_TRADE evaluation, learning, audit, reproducibility, security, rollback, and recovery.

### Core capabilities

1. **Data Inventory & Classification:** identify path/service owner, purpose, sensitivity, source, dependencies, reproducibility, size, age, retention class, and recovery value.
2. **Retention Policy Engine:** versioned policy with explicit KEEP / ARCHIVE / REVIEW / DELETE eligibility; unknown means KEEP.
3. **Storage Optimizer:** compression and proven deduplication only; preserve original hashes, schema, timestamps, and lineage.
4. **Cleanup Executor:** dry-run first, candidate manifest, reason codes, bounded batches, locks, quarantine/atomic operations, fail-closed behavior, and kill switch.
5. **Disk & Inode Guard:** monitor free bytes, inode availability, growth rate, per-service budgets, and forecast time-to-capacity; alert and apply backpressure before exhaustion.
6. **Audit & Recovery:** append-only action records, checksums, archive manifests, tested restore procedures, and rollback references.

### Permanent protected data classes

- Trade journals, outcomes, rejected-signal records, NO_TRADE decisions, and counterfactual evaluation evidence.
- Canonical market candles, raw market/trade payloads, source identity, connection/session epochs, receive and venue timestamps, schema fingerprints, registry revisions, and source hashes.
- Model/policy/config versions, code/run hashes, provenance, decision attribution, and reproducibility fixtures.
- Security/audit logs, recovery manifests, backup evidence, current and rollback release pointers, and any data with unknown ownership or dependencies.

**Sequence-semantics protection:** a field named `sequence` or `id` has no generic meaning. For Tabdeal FAPI/Margin `trade.sequence`, current reviewed public evidence does not establish unique identity, ordering, contiguity, or gap detection. Never deduplicate or delete events based on this opaque field. Preserve full raw payload and its source/session/timestamp/hash/registry lineage. Exact-payload replay handling is distinct from event-ID deduplication. Adapter-specific capabilities and evidence govern any such operation.

### Retention classes

- **KEEP:** canonical data, evidence, journals, provenance, security records, backups, rollback assets, unknown items.
- **ARCHIVE:** immutable cold data only after policy review, hash/manifest verification, and restore proof.
- **REVIEW:** stale temporary workspaces, duplicate same-day backups, caches, and old build artifacts; review is not deletion permission.
- **DELETE:** only explicitly allowlisted regenerable/disposable items after dependency scans, retention expiry, verified recovery where required, and an audited dry-run manifest.

### Non-negotiable safety invariants

- No deletion based only on age, filename, size, last access, or a repeated sequence-like value.
- No in-place mutation of canonical market data, journals, evidence, model state, or active runtime files.
- Dry-run is the rollout default; uncertainty means KEEP.
- Verify checksums and restore paths before source deletion.
- Never remove active release, rollback release, worktree, dirty/untracked project file, running-service data, or backup without proven dependencies and recovery coverage.
- Reuse existing operational health checks, journald/logrotate, backup, and recovery controls; do not create duplicate monitors or parallel implementations.
- No trading/execution authority is granted to IDLM.

### Roadmap gates

- **A — Read-only discovery:** inventory filesystem, active writers/readers, data classes, backup schedule, retention mechanisms, disk/inode use, and growth baseline.
- **B — Policy mapping:** assign owner, retention class, replay/audit value, dependency and restore requirements to each discovered data class.
- **C — Dry-run implementation:** candidate manifest, reason codes, disk/inode forecast, audit output, and deterministic tests. No production deletion.
- **D — Safety validation:** unknown files, symlinks/path traversal, concurrent writers, open descriptors, interrupted archives, checksum mismatch, disk-full/inode exhaustion, stale manifests, rollback, and restore tests.
- **E — Canary:** only allowlisted regenerable cache/temp data, low batch limits, monitoring, and immediate kill switch.
- **F — Production acceptance:** exact-SHA tests, independent review, verified backup/restore, measured disk reduction, zero protected-data loss, clean audit, and soak.

### Verified VPS baseline — 2026-11-08 (read-only)

- Sole VPS root filesystem: 50G; about 40G used; 7.4G available; 85% displayed use; inode use about 14%.
- `/var/backups/hes-trade-agent`: about 18G; encrypted-local backup tier about 15G; 11 encrypted full backups were found and all 11 sidecar SHA-256 checks passed.
- Existing daily backup timer runs around 02:30 UTC. Its script verifies the newly created encrypted archive before retention, then keeps every backup younger than 7 days, Sunday backups under 28 days, and first-of-month backups under 180 days. It does not cap multiple same-day backups; duplicate same-day snapshots are therefore review candidates, not deletion-authorized.
- No full restore drill has yet been completed for the encrypted-local tier. Keep every backup until recovery/offsite coverage is proven.
- `/tmp`: about 5.4G, containing many dated test/replay workspaces and a roughly 924M Playwright browser cache. These are review candidates only; age and cache naming do not independently authorize deletion.
- `/opt`: about 6.4G; `/home`: about 2.5G; `/var`: about 20G, largely explained by backups.
- Existing HES runtime health checks already monitor disk pressure (15% free warning / 10% critical in runtime check, and 85% used critical in host check). Current recorded issue is `disk-free:14.8%`. Extend this monitor with inode/growth/forecast signals rather than creating a duplicate service.
- Generic logrotate timer is enabled. No HES-specific logrotate rule was found in the inspected configuration. systemd tmpfiles currently gives `/tmp` a 30-day cleanup age; do not rely on that as HES retention policy.
- The current checkout remains dirty with many untracked files. Preserve all local changes, worktrees, candidate/release trees, evidence, and active service data.

**Current disposition:** read-only monitoring and discovery only. No files have been deleted, moved, compressed, rotated, or pruned; no service was restarted; no production retention setting was changed. The next implementation step is a tested read-only IDLM audit/candidate-manifest tool and an isolated review of backup retention improvements.


### IDLM implementation hardening update — 2026-11-08

- The read-only IDLM scanner now reads the Git worktree registry and protects exact registered worktree paths. If the registry cannot be verified, temporary paths fail closed as KEEP_UNKNOWN. This prevents a registered worktree from being misclassified as a stale temporary directory.
- Actual VPS scan v5 inventoried 702 entries with zero scan errors; 11 existing scanned paths were recognized as registered worktrees and protected. The report remains read-only with automatic_action=NONE.
- Draft PR #485 passed 32/32 GitHub Actions workflow runs; the HES Full Regression Gate reported 1,195 passed and 82 subtests passed, with live execution OFF. The PR remains unmerged and undeployed.
- A synthetic test exposed a backup-retention edge case: future-dated archive filenames were treated as expired because age was negative. The live backup script now fails closed for age<0, logs RETENTION_KEEP_FUTURE_DATED, and preserves the archive and sidecar. Original script is backed up at /root/hes-encrypted-local-backup.pre-idlm-20261108; original and patched SHA-256 values are recorded in the Notion Master Checkpoint. bash -n and the synthetic retention regression passed.
- No backup run was triggered, no service was restarted, no backup or evidence was deleted, and the existing retention policy was not otherwise changed.


### Backup recovery and offsite status — 2026-11-08

- Selective encrypted-backup restore drill passed: archive SHA-256 verified, decryption and 42,753-member tar listing succeeded, and three selected critical files (systemd unit, operational health wrapper, immutable release healthcheck) were extracted to an isolated scratch directory and matched live SHA-256 byte-for-byte (11,457 bytes total). This is not a full-system restore. Manifest: /root/hes-restore-drill-20261108/restore-drill-manifest.json.
- Dropbox folder /HES Trade Agent Backups exists but is empty; VPS dropbox-staging is also empty. Offsite backup coverage is not verified. Do not transfer ciphertext to Dropbox without explicit user authorization; never transfer the passphrase/key file.
- Full restore and offsite recovery remain acceptance gates; no backup pruning or production cleanup is authorized by this selective restore.


### Capacity monitoring extension — 2026-11-08

- The IDLM PR extends the existing HES runtime/operational health monitor; no duplicate service is added. Runtime checks now include inode availability (10% free WARN, 5% free CRITICAL).
- The existing five-minute operational monitor records one compact disk-capacity sample per hour in /var/lib/hes-operational-health/capacity-trend-v1.json using an atomic mode-0600 update. It uses EWMA growth, requires six samples before forecasting, resets after a filesystem-size change or a sample gap over 48 hours, warns below 72 hours to full, and becomes critical below 24 hours. Corrupt state/backward clock is WARN and preserved.
- The existing service already has StateDirectory=hes-operational-health and ReadWritePaths=/var/lib/hes-operational-health; no new service or permission expansion is needed. This change is in the isolated PR only and is not deployed.
- Isolated VPS validation of the latest PR head: 20 tests passed and four Python modules compiled. Tests ran in a temporary directory that was removed; no production state or service was touched.
- Current VPS snapshot: root filesystem 84% used, 7.5G available, inode use 13%; the existing last-issues state is empty.


### Offsite staging correction — 2026-11-08

- VPS /var/backups/hes-trade-agent/dropbox-staging contains a 69,266,627-byte GPG encrypted archive (hes-agent-offsite-20261107T165625Z.tar.gz.gpg) and a 112-byte SHA-256 sidecar. The sidecar passes.
- The remote Dropbox folder HES Trade Agent Backups is still empty. No offsite uploader service/timer/cron, rclone installation/configuration, or offsite key file was found in inspected paths. The local staging file is not an offsite copy.
- GPG packet metadata identifies symmetric AES-256/SHA-512 encryption; decryption with the current full-backup key file fails with Bad session key. Key provenance remains unknown; do not guess keys or delete this protected artifact.
- IDLM scanner v6 explicitly inventories this staging path and classifies its directory/archive/sidecar as KEEP_BACKUP_STAGING. The refreshed scan reports 706 entries, zero scan errors, and automatic_action=NONE.


### Dry-run backup retention planner — 2026-11-08

- IDLM scanner now mirrors the current local backup retention policy without executing it: daily under 7 UTC date-days; Sunday weekly anchor under 28 days; first-of-month monthly anchor under 180 days.
- Future-dated and unparseable backup filenames fail closed as KEEP. Expired items are REVIEW_RETENTION_EXPIRED with retention_action=NONE. The report records sidecar presence but does not claim checksum verification; full restore/offsite status remains NOT_CHECKED_BY_SCANNER and deletion_authorized=false.
- Scanner v7: 704 entries, zero scan errors, 11 encrypted full archives across 7 UTC dates, four same-day additional snapshots, all 11 inside the daily window, zero expired candidates, one unparsed local staging archive. All 11 full-archive sidecars are present.
- Same-day additional snapshots remain review-only, not proven byte-identical, and are not deleted.
- Latest isolated VPS validation: 22 tests passed; four Python modules compiled; no production service/state was touched.


### Evidence-store coverage — 2026-11-08

- Root inventory identified /srv/hes-evidence as an immutable project evidence store: approximately 411,423,488 allocated bytes across 3,744 files. It was not an explicit IDLM scanner root in v7.
- Scanner v8 explicitly inventories /srv/hes-evidence and classifies its descendants KEEP_EVIDENCE, regardless of age.
- Scanner v8: 806 entries, zero scan errors; 102 top-level evidence entries protected; 11 registered worktrees KEEP; 3 backup-staging entries KEEP; 4 same-day backup extras REVIEW; 22 caches REVIEW; 172 stale temp REVIEW; 297 other temp REVIEW; 156 unknown KEEP. Disk 15.23% free; inodes 87.05% free.
- Dry-run retention: 11 encrypted full backups in the daily window, one unparsed local staging archive, zero expired candidates, deletion_authorized=false.
- Latest isolated VPS validation: 23 tests passed and four Python modules compiled; no production state/service touched.


### IDLM PR validation milestone — 2026-11-08

- PR #485 (feat/hes-intelligent-data-lifecycle-audit-v1) is ready for review, open, mergeable, and unmerged/undeployed.
- Latest head fc46bb521cd5c896f9e5f7a24038906a672e26f4 passed 32/32 GitHub Actions workflows. HES Full Regression Gate: 1,209 passed and 82 subtests passed; LIVE_EXECUTION=OFF.
- Latest isolated VPS validation: 23 tests passed; four Python modules compiled.
- Production cleanup remains disabled. Full-system restore and independent offsite backup remain open gates; the Dropbox remote folder is empty and the local staging archive key provenance is unknown.


## Multi-regime strategy coverage — Range & Correction Intelligence (2026-11-19)

**Architecture decision:** add a dedicated Range Strategy family as a modular specialist under the existing Mother Orchestrator and strategy-family router. Do not create a parallel trading stack, market-data pipeline, precision-entry engine, journal, or risk engine.

### Strategy-family map
- **Trend:** preserve the existing trend/breakout contract and behavior unchanged.
- **Range:** research-first mean-reversion family for well-formed persistent ranges; evaluate LONG near validated lower boundaries and SHORT near validated upper boundaries only with reversal/structure confirmation and viable net-of-cost geometry.
- **Correction / Pullback:** separate research family for counter-trend corrections and trend resumption; do not conflate corrections with stable ranges.
- **Breakout / Transition:** detect range invalidation and confirmed volatility expansion; stop Range candidate generation when the range ceases to be valid.
- **Unknown / mixed / low-quality:** no family; fail closed to NO_TRADE.

### Shared evidence and controls
- Reuse canonical Gate.io readers, closed 15m setup authority, 1m precision-entry refinement, Market Regime Engine, strategy-family router/context, Confirmation/Consensus, Risk Gate, journal, Blackbox and Learning Loop.
- Regime/family routing is not a signal approval. Confirmation and Risk Gate remain independent and fail-closed.
- Candidate evidence may include dynamic support/resistance, range width/persistence, ADX/CHOP/efficiency ratio, RSI/MFI, Bollinger position/width, VWAP, volume, liquidity sweeps, BOS/CHOCH, Order Blocks and FVG. No individual indicator is a sufficient trigger.
- Require data freshness/quality, valid boundaries, reversal confirmation, sufficient remaining range, conservative stop/target geometry and positive expected value after verified fees, spread, slippage and applicable funding.
- Record family ID/version, regime evidence, candidate/rejection reason, gate attribution, code/config/data lineage and matured outcomes.

### Roadmap and acceptance
1. Inventory and reuse existing regime, family-router, context, journal and dashboard contracts; verify exact active release and source.
2. Freeze a versioned Range contract for eligibility, boundary/persistence, LONG/SHORT symmetry, reversal confirmation, invalidation, geometry, costs and NO_TRADE.
3. Add deterministic unit/contract and replay tests; prove Trend behavior unchanged.
4. Evaluate preregistered research/paper-shadow hypotheses on timestamp-aligned closed Gate.io candles; no look-ahead or same-sample retuning.
5. Require at least 100 resolved eligible observations, strict project paper-quality target (>90% win rate), positive net expectancy after verified costs, acceptable drawdown/tail risk, chronological walk-forward and independent OOS evidence. These are acceptance gates, not guarantees or trade-frequency quotas.
6. Wire only after contract/evidence gates pass. Production activation/execution still requires explicit human approval and all existing release/risk/execution gates.

### Evidence status at decision time
Existing Range research is **RESEARCH_ONLY_NOT_ACTIVE / EDGE_NOT_PROVEN**. Earlier prototypes did not establish positive net edge and costs materially affected outcomes. The existing router classifies RANGE to range_mean_reversion for research only; candidate generation remains unauthorized. This DNA entry formalizes architecture and does not claim a newly implemented, accepted, deployed or active engine. Keep RANGE/uncertain → NO_TRADE until fresh exact-release evidence passes. No threshold loosening to manufacture frequency; daily signal limit is a cap, not a quota. Do not destabilize the fixed delivery work; implementation must use a separately verified isolated worktree and preserve all dirty/untracked state.

## Dashboard documentation cross-link

See `docs/dashboard/STRATEGY_REGIME_AND_RANGE_FAMILY_V1.md` for the operator-facing strategy-regime and Range-family display contract.


## Range Strategy Engine v2 — implementation and evidence update (2026-11-19)

- Implemented a standalone research-only Range mean-reversion engine in isolated branch `feat/range-strategy-research-v1-20261119`, based exactly on active release `09f660d625df3f8964ba8ddd20c9a9cf8a400f19`.
- Engine v2 uses prior-only dynamic 64-bar boundaries, two-sided touch/persistence, CHOP/ER/ADX regime filters, 1h/4h EMA50 pressure, closed-candle sweep/reclaim, RSI/MFI reversal, and cost-adjusted midpoint geometry. It binds research candidates to the shared strategy-family context envelope.
- Range family/router/context versions are now `hes-range-mean-reversion-v2.0.0-research`, router v1.1.0 and context v1.1.0. Trend profile and its 3R/gate contract remain unchanged.
- 90-day historical replay: 8,639 closed 15m candles, zero source gaps, 646 boundary sweep/reclaim prefilter bars, **zero eligible Range candidates** across assumed 5/10/15/30 bp round-trip cost scenarios.
- Recent VPS shadow replay: 1,733 15m, 1,119 1h, 654 4h and 19,985 1m closed Gate.io candles; all four feeds passed uniqueness/contiguity checks. Actual 1h/4h files were used. **Zero eligible Range candidates**.
- Therefore no win rate, expectancy or edge has been measured. This is insufficient candidate frequency under the frozen hypothesis, not a 0% win rate and not proof that all Range strategies fail. Do not loosen thresholds on these same samples.
- Full repository regression after integration: 1,610 passed, 84 subtests passed. All candidate authority, confirmation, risk, execution and order flags remain false.
- The engine is not deployed, not connected to live Strategy V2 approval, not activated in the dashboard, and cannot place orders. Continue RANGE/unknown → NO_TRADE unless a separately preregistered future hypothesis earns acceptance.
