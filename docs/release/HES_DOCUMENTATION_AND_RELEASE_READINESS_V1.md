# HES Trade Agent — Documentation and Release Readiness Control v1

**Version:** 1.0  
**Recorded:** 2026-11-06 (UTC)  
**Applies to:** HES Trade Agent application, the existing Mother Command Center, the canonical Gate.io market-data path, paper evaluation and the single production VPS.  
**Disposition:** Control standard; it does not itself approve a release or enable trading.

## 1. Purpose and authority

This document defines the minimum durable documentation and evidence required to prepare, publish, operate, recover and maintain an HES release. It is deliberately a control standard rather than a second implementation or a duplicate operator runbook.

Use the following authority order:

1. **GitHub source and exact commit SHA:** technical implementation and review history.
2. **Exact-SHA CI, test reports, manifests and runtime evidence:** proof that a specific candidate or release passed a specific check.
3. **Versioned repository contracts and runbooks:** durable operating and engineering procedures.
4. **Notion Master Checkpoint:** concise project resume map, current status, decisions, blockers and next actions.
5. **Chat:** discussion history, not technical proof.

A green workflow, a draft PR, a deployment record or a successful smoke test is not by itself a complete release approval. Every claim must identify its scope, exact artifact/SHA, timestamp and evidence source. Historical evidence must not be silently reused for a different release.

## 2. Fixed product and safety boundaries

- **Canonical market data:** Gate.io Public Spot `BTC_USDT` is the single source for live market data, closed candles, charting and indicator inputs. Reuse the existing adapter, persisted feed and `global_market_data_reader_v1`. Do not create a parallel reader or silently mix venue data.
- **Execution separation:** the exchange/broker execution adapter is distinct from market-data ingestion. Gate.io market-data selection does not prove that Gate.io is the execution venue. Instrument mapping and account permissions require separate evidence and approval.
- **Topology:** one production VPS, one existing dashboard and one existing Mother orchestrator. No duplicate frontend, collector, journal, evaluator, monitor or agent brain.
- **Mother Command Center:** Free-First, bounded and read-only. It may explain status and request clarification; it must not gain order, account, shell, Git, deployment, journal-write or policy-mutation authority.
- **Trading posture:** paper-only / `NO_TRADE_ONLY` until every relevant gate is accepted. `execution_enabled=false`, `orders_placed=false` and `policy_mutation_enabled=false` remain enforced.
- **Signal cap:** no more than three signals per day. This is a ceiling, never a quota.
- **Performance claim:** do not claim a >90% win rate until at least 100 eligible, resolved, closed paper trades show >90% net of verified fees, slippage and other applicable costs, with complete immutable provenance and independent out-of-sample evidence. If the eligible sample is zero or insufficient, report the rate as not calculable.
- **Fail-closed behavior:** stale or incomplete market data, unknown protocol semantics, missing confirmation, unapproved risk, unresolved instrument mapping, invalid provenance or failed health checks must prevent promotion and keep the affected path in `NO_TRADE`.

## 3. Documentation set and maintenance ownership

Keep one authoritative document per purpose. Extend the existing artifact instead of creating a parallel document.

| Artifact | Owns | Update trigger |
| --- | --- | --- |
| `README.md` | Product overview, boundaries, topology and documentation map | Product scope or architecture changes |
| Mother Command Center contract | Chat scope, permissions, trust boundary and non-goals | Any Mother capability or permission change |
| Dashboard security/release/rollback runbook | Deployment, listener/security checks, rollback and deployment records | Every deployment or rollback |
| Versioned API/data/strategy/risk contracts | Machine-readable interfaces, invariants and compatibility | Contract/schema/policy change |
| Protocol registry and evidence guide | Venue/product/channel-specific semantics and pinned source evidence | Venue docs, protocol version or observed schema changes |
| Backup/restore runbook | Backup contents, encryption, retention, restore and off-host recovery | Backup/recovery implementation or drill |
| Notion Master Checkpoint | Current verified status, blockers, dated decisions and next resume point | Each material milestone or blocker change |

Do not copy volatile status tables into every document. Put durable rules in repository documentation and current measurements in the Master Checkpoint. Keep historical entries append-only or clearly superseded; do not silently rewrite prior evidence.

### Required metadata for durable technical documents

- Title and stable purpose.
- Version or dated revision.
- Status: `DRAFT`, `CANDIDATE`, `ACTIVE`, `SUPERSEDED` or `RETIRED`.
- Exact scope (venue/product/channel, component, environment and release where relevant).
- Primary evidence references and retrieval/review date.
- Dependencies and compatibility notes.
- Acceptance criteria and failure behavior.
- Change history for material decisions.
- Named approval only when an actual approval exists; never invent a reviewer or sign-off.

## 4. Release lifecycle and mandatory gates

A release is eligible only when all gates relevant to its scope are evidenced on the same immutable candidate SHA. A failure in a safety-critical gate blocks release; it is not averaged away by green checks elsewhere.

### Gate A — source identity and review

- Confirm repository, base branch, exact 40-character candidate SHA and intended deployment target.
- Inspect the complete diff, dependency chain, PR ancestry and overlapping files. Resolve sibling-PR conflicts before merging.
- Preserve the sole VPS's dirty working checkout. Do not use `reset`, `clean`, force checkout, blanket staging or overwrite as a shortcut.
- Require an independent review for safety-sensitive changes. The author's own CI result is not a substitute for review.

**Evidence:** PR URL, base/head SHAs, changed-file list, review decision and merge commit SHA.

### Gate B — exact-SHA build and regression

- Run every required GitHub Actions check on the exact PR head/candidate SHA.
- Require all mandatory workflows to finish successfully; report skipped workflows as skipped, never as passed.
- Run the full repository regression and relevant focused suites.
- Include browser/render checks for UI changes, protocol fixtures for adapter changes, and fault-injection tests for recovery/security changes.
- Record test counts, subtest counts, workflow run URLs and artifact hashes.

**Evidence:** exact-SHA workflow list, successful/failed/skipped counts, test report and artifact provenance.

### Gate C — immutable release provenance

- Build from the exact reviewed Git commit, not from a dirty working tree.
- Enumerate tracked Git blobs and verify every expected release file byte-for-byte.
- Reject missing, altered, unsafe, symlinked, duplicate or unsupported paths.
- Generate the versioned release manifest and SHA-256 sidecar before making the release immutable.
- Make the release directory read-only, hold the deployment lock, atomically switch the `current` pointer and verify pointer stability before recovery is eligible.
- Preserve the previous immutable release and its deployment record.

**Evidence:** commit SHA, manifest status, files checked, manifest and sidecar hashes, archive hash, pointer target and rollback target.

### Gate D — market-data integrity and soak

- Verify that live analysis, charts and indicators use only Gate.io Public Spot `BTC_USDT` through the existing reader and persisted feed.
- Verify closed-candle identity, timeframe, freshness, source identity and matching batch hash between chart and analysis.
- Verify the existing 1m integrity witness and the 1m/15m/1h/4h feed health; no parallel feed is allowed.
- Complete one uninterrupted soak of at least **86,400 seconds** and at least **1,400 valid samples**, with zero invalid samples, zero sample-number gaps, no interval beyond the accepted 90-second bound, and the runner's terminal `passed=true` summary.
- Record the final evidence file SHA-256 and independently review the run. Do not combine separate runs or infer completion from elapsed time alone.
- Run reconnect/restart fault injection as a separate test after the soak; do not interrupt the acceptance soak to perform it.

**Evidence:** exact service/unit and release identity, start/end timestamps, terminal summary, sample counts, gap/interval metrics, final SHA-256, 1m witness and independent review.

### Gate E — UI and user-facing behavior

- Test the deployed UI against the same release SHA used for the API and data path.
- Verify 1m and 15m chart rendering and that chart candles and signal analysis reference the same canonical Gate.io batch/hash.
- Exercise desktop, tablet and mobile layouts; English and Persian; LTR and RTL; authentication, clarification, logout and safe error states.
- Verify stale-feed, gap, unavailable-confirmation, risk-veto and `NO_TRADE` states are visible and cannot be mistaken for a valid signal.
- Confirm the dashboard binds only to loopback and is reachable through the intended authenticated access path, not a public application listener.

**Evidence:** browser run URL, viewport/locale matrix, screenshots or render artifacts, API response checks and source/batch parity report.

### Gate F — strategy, risk and paper-performance acceptance

- Confirm each active strategy family has an explicit market-regime scope, entry/exit definition, invalidation, stop-loss, position-sizing rule and evidence-backed confirmation path.
- Require independent risk approval, drawdown/tail-risk controls and verified execution-instrument mapping before any promotion.
- Keep rejected candidates and learning-loop hypotheses research-only. No automatic threshold, strategy, risk or policy mutation.
- Evaluate only eligible, resolved, closed paper trades with immutable code/config/data lineage and verified costs.
- Require at least 100 eligible closed trades and >90% net-of-cost win rate plus independent out-of-sample evidence before making the requested performance claim or considering a separate live-authorization review.
- Treat the daily three-signal maximum as a cap, not a target. `NO_TRADE` is a valid final decision.

**Evidence:** frozen strategy/risk contract hashes, gate attribution, eligible cohort definition, cost model, resolved outcome ledger, confidence/sample report and independent OOS report.

### Gate G — security and operational recovery

- Verify SSH key-only access, firewall default-deny policy, intended listeners, dashboard loopback binding, service sandboxing and secret-file ownership/modes.
- Keep tokens, private keys and backup passphrases outside Git and chat. Verify permissions without displaying secret values.
- Run dependency, vulnerability, secret, license and static-analysis checks against the exact candidate/release; record tool versions and reports. A clean `pip check` alone is not a vulnerability audit.
- Verify operational health, disk headroom, NTP/time integrity, feed freshness, journal integrity and the bounded self-repair preconditions.
- Recovery may act only on the explicitly allowlisted paper workers after all preflight checks pass. It must not restart market-data feeds, the dashboard, SSH/tunnel, firewall, release pointer, risk policy or order paths unless a separate approved procedure explicitly permits it.
- Keep package/kernel maintenance outside an active acceptance soak. Re-enable any temporarily paused maintenance timer after the soak and complete maintenance only in an owner-approved window with access/recovery verification.

**Evidence:** exact release health report, security scan artifacts, effective systemd unit properties, service state, listener inventory and repair audit.

### Gate H — backup, restore and rollback

- Verify encrypted archive integrity and SHA-256 sidecar; verify the archive can be decrypted using the separately escrowed recovery key.
- Perform a restore test that byte-matches critical application, configuration and evidence files.
- Replicate encrypted backups to an independent off-host destination with owner-approved retention and access controls. A same-VPS archive is not disaster recovery.
- Escrow the passphrase outside the VPS through an owner-controlled trusted mechanism; never place it in Git or chat.
- Exercise the release rollback procedure against the previous immutable release. Verify health after rollback and preserve journal/ledger files and their hashes.
- For a replacement-VPS recovery claim, rehearse recovery on an isolated replacement environment; do not claim full disaster recovery from a targeted same-host restore.

**Evidence:** archive/hash verification, restore log and byte comparisons, off-host object identity, key-escrow confirmation without secret disclosure, rollback record and post-rollback health.

### Gate I — final approval and publication

- Complete the release checklist with explicit `PASS`, `FAIL`, `BLOCKED` or `NOT_APPLICABLE` for every gate.
- Link each `PASS` to evidence for the exact candidate/release SHA.
- List all unresolved defects, deferred capabilities, operational dependencies and user-visible limitations.
- Obtain the owner's explicit release approval after the technical review. Live execution requires a separate authorization and must never be inferred from application delivery approval.
- Publish the exact release version, commit SHA, supported features, known limitations, rollback reference and operator instructions.
- Update the Master Checkpoint only after the source artifacts and runtime evidence have been verified.

## 5. Rollback and incident rule

When a release health, data-integrity, security or provenance gate fails:

1. Fail closed for the affected decision path; retain `NO_TRADE` and execution-disabled state.
2. Preserve logs, journal records, manifests, hashes and the failed release for diagnosis.
3. Follow the existing dashboard/release rollback runbook. Restore the previous immutable release pointer atomically and restart only the specifically authorized affected service.
4. Do not delete, rewrite or regenerate canonical journals to make the report look clean.
5. Re-run the relevant health, source-parity, security and journal-integrity checks.
6. Record the incident, root cause, affected SHA, rollback SHA, evidence and preventive regression test.

A self-repair action must be bounded, preflighted, auditable, rate-limited and reversible. If its preconditions or audit trail are invalid, it must take no action and report the failure.

## 6. Long-horizon maintenance and protocol drift

- Review primary venue documentation and changelogs at least monthly and after every relevant API, endpoint, channel, schema or SDK change.
- Pin source URLs, retrieval dates, source snapshots/hashes, schema fingerprints and raw fixtures. A URL or a live capture alone is not a protocol guarantee.
- Keep sequence/identity/order/gap capabilities scoped to venue, product, endpoint, channel, message type, field path and protocol version. Unknown remains unknown until primary evidence and regression tests support a change.
- Run the relevant fixture and full regression suites for each adapter or contract change.
- Review dependency vulnerabilities and supported runtime versions on a scheduled cadence and before every release.
- Test backup integrity and restore capability on a recurring schedule; test off-host recovery and release rollback after material infrastructure changes.
- Record deprecations and migrations; do not silently change schemas, thresholds, permissions, source identity or execution behavior.

The objective is durable maintainability, not a claim that a changing exchange API, operating system or dependency can be made immutable for twenty years.

## 7. Delivery control dates

The current project control dates are:

- **2026-11-12:** scope freeze and mandatory-gate go/no-go.
- **2026-11-16:** release-candidate gate; only evidence-complete candidates qualify.
- **2026-11-19:** fixed application delivery target.

These dates are planning controls, not waivers. If a safety-critical gate is still open, record the exact limitation and do not label the affected capability production-ready.

## 8. Release record template

Copy this section for each candidate; never reuse a previous release's evidence.

| Field | Value |
| --- | --- |
| Release/version | |
| Repository / branch | |
| Exact candidate SHA | |
| PR / independent review | |
| Required CI workflows | |
| Full regression result | |
| Manifest status / SHA-256 | |
| Immutable release path | |
| Active pointer target | |
| Gate.io source / batch evidence | |
| Soak start/end / duration / samples / final hash | |
| Browser / locale / viewport evidence | |
| Strategy / risk / paper cohort evidence | |
| Security / dependency scan evidence | |
| Backup / restore / off-host evidence | |
| Rollback target / rehearsal evidence | |
| Open limitations | |
| Owner approval and timestamp | |
| Final disposition | |

Allowed final dispositions: `APPROVED`, `APPROVED_WITH_DOCUMENTED_LIMITATIONS`, `HOLD`, `ROLLBACK`. A blank field is not a pass.
