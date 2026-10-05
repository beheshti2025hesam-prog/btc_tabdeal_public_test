# Historical Run / Checkpoint Lineage Audit — 2026-10-05

## Scope
Read-only forensic audit of the collector transition around 2026-10-04 → 2026-10-05.

Required chain:
Historical Run/Checkpoint Lineage → Writer Attribution → N → natural completion → N+1 startup → checkpoint boundary → gap/duplicate/single-writer proof.

Safety boundary:
- No Collector start/stop/restart/enable/disable was performed by this audit.
- No observation was deleted.
- No threshold/tuning/evidence-selection change was made.
- GitHub Actions scheduled execution was verified blocked before lineage analysis.

## 1. GitHub scheduled-run gate
Current main:.github/workflows/run.yml contains on: workflow_dispatch only; no schedule trigger. Collector remains manually dispatchable. Concurrency group is tabdeal-btc-usdt-collector with cancel-in-progress false.

Conclusion: PASS — GitHub scheduled Collector execution is blocked. Any future GitHub run requires explicit manual dispatch.

## 2. Current VPS state
At audit time hes-trade-agent-collector.service was inactive/dead, MainPID=0, unit file state enabled. No Collector process was started by this audit. The service was intentionally left untouched.

## 3. Historical writer attribution
The retained systemd journal shows two historical Collector PIDs that actually emitted SAVED records in the examined lineage window:

| PID | Role | SAVED records | Boundary |
|---|---|---:|---|
| 49603 | prior VPS run | 932 | ended 2026-10-04 21:35:55 UTC |
| 59572 | subsequent successful VPS run | 5,806 | ended 2026-10-05 01:36:13 UTC |

Repeated startup attempts between these runs failed during startup Git fetch because the SentinelX SSH identity was inaccessible. They exited before websocket connection/data writing. The successful run PID 59572 began only after the failed-startup storm ended.

Conclusion for the retained journal window: PASS — no overlapping data-writing PIDs were found.
Limitation: this is a journal-retention-window proof, not a proof for every historical writer since project inception.

## 4. N → stop/checkpoint boundary
Prior writer PID 49603 completed startup sync and sequence recovery, connected to BTC_USDT, and last saved sequence observed before stop was 40329260383. At 21:35:52 UTC a Git push failed; at 21:35:54 UTC a stop signal was received; final checkpoint ran; CSV closed safely; systemd stopped the service at 21:35:55 UTC.

This is NOT classified as natural completion. Natural-completion gate = OPEN / NOT PROVEN for this transition.

## 5. Startup storm before successful N+1
After the prior stop, systemd attempted repeated starts. First failed startup: 2026-10-04 21:59:40 UTC. Successful long-lived startup: 2026-10-04 22:07:35 UTC. Restart counter reached at least 34.

The failed starts consistently died in startup data-state synchronization while running git fetch origin main because the service could not access /home/sentinelx/.ssh/hes_trade_agent_github_ed25519. These attempts did not produce SAVED records.

This is a startup failure storm, not a multi-writer period.

## 6. Successful N+1 startup
PID 59572 detected local handoff data, preserved VPS data, recorded startup base SHA c6979a91bdbef998a1b09693b34f61c39b5bba95, completed sequence recovery, connected to wss://api1.tabdeal.org/special_margin/broadcast/, and subscribed to BTC_USDT.

First saved sequence observed: 40335229818. Last saved sequence: 40373844351. Previous run last saved sequence: 40329260383.

The numeric sequence difference is not automatically classified as missing data because sequence identifiers are not guaranteed contiguous integers. Missingness requires a declared reference population.

## 7. Checkpoint lineage
Successful run checkpoints recorded in Git included:

- 40350124041 at commit 061ef8cd...
- 40353857792 at commit 0aa1f94...
- 40357608437 at commit 277377d...
- 40361359097 at commit 618b062...
- 40365129270 at commit a35fc9d...
- 40368884190 at commit aeee8d7...
- 40372610597 at commit 791d9ba...
- final 40373844351 at commit f396de84...

The final VPS artifact and GitHub main artifact are byte-identical at the audited checkpoint: 110,566 rows; 8,342,334 bytes; SHA-256 c5dbd78fe8aade258c28f1254f0a399051ab32d3b026e246ff36285dd020de87.

## 8. Final stop / N+1 availability
At 01:35:55 UTC systemd stopped PID 59572. The collector received STOP SIGNAL, completed FINAL GIT CHECKPOINT, successfully pushed the final checkpoint, closed the CSV safely, and was stopped at 01:36:13 UTC.

No subsequent automatic N+1 was observed in the audited window. Because the GitHub schedule is disabled, this absence is expected and is not evidence of a missing scheduled run.

## 9. Gap / duplicate / single-writer conclusion
Duplicate proof previously closed: 860,566 rows across 14 archive segments + active file; 860,566 unique sequence values; 0 global duplicates; 0 cross-segment overlap; 0 internal segment duplicates.

Gap proof: no numeric sequence gap is automatically labeled missing. The transition 40329260383 → 40335229818 has a large numeric delta and a wall-clock collection gap, but neither alone proves missing observations. A missing/extra conclusion requires a declared reference population or external stream reconciliation.

Single-writer proof for the retained journal window: SAVED records came from PID 49603 and PID 59572 only; the two writers did not overlap; the 34 failed startup attempts produced no SAVED records; no concurrent writer is evidenced.

Conclusion: PASS for the retained journal window.

## 10. Gate status
| Gate | Status |
|---|---|
| GitHub scheduled Collector blocked | PASS |
| Historical run attribution | PASS for retained journal window |
| Failed startup storm isolated from writer population | PASS |
| N checkpoint boundary | PASS |
| Natural completion | OPEN / NOT PROVEN |
| N+1 successful startup lineage | PASS |
| Checkpoint lineage continuity | PASS |
| Duplicate/overlap | PASS |
| Numeric gap ≠ missing classification | PASS |
| Single-writer | PASS for retained journal window |
| Collector mutation during audit | NONE |

## Next action
Do not rerun the artifact/VPS identity audit from scratch.

Next forensic target:
Run #196 / GitHub legacy handoff evidence → natural-completion proof → final checkpoint lock → N/N+1 boundary reconciliation → historical writer attribution outside current journal retention → Reconciliation Closure.

Only after that should we advance to Independence / Fold Stability.