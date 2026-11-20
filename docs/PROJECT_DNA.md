# HES Trade Agent — Project DNA

## Team and operating model

The project team consists of exactly two collaborators in its operating plan:

- **Project owner:** the user, who sets priorities and makes project decisions.
- **AI engineering partner:** ChatGPT, which advances technical analysis, implementation planning, code review, test design, evidence checks, and concise reporting.

Do not plan routine project execution around an assumed third team member. The owner has stated that no other person is available to take project actions. Prefer autonomous progress with minimal requests for owner intervention.

## Review and evidence policy

- ChatGPT performs a careful technical review, but must never misrepresent its own review as an independent third-party human review.
- Automated CI and tests provide repeatable evidence only for the exact commit and test scope actually run. A prior green run does not prove a later change.
- Tie reported CI results, artifacts, hashes, and claims to verifiable commit identifiers and source evidence.
- Distinguish clearly between completed work, proposed work, unverified assumptions, and blockers.
- Do not claim local tests ran if the required test command or dependencies were unavailable.
- If a repository branch-protection rule or external requirement mandates a human approval, report it honestly as a repository/policy constraint. Do not fabricate an approval or imply an unavailable person will act. Continue all work that can safely proceed without that approval.

## Security and release discipline

- No security gate passes on confidence, a green CI badge, or a hash alone; it passes only when its stated security properties are demonstrated by evidence.
- Keep HOLD for the affected security-sensitive release path until its required evidence is established.
- Do not enable live collection, exchange account access, VPS changes, or trading as an implicit consequence of documentation or test work.
- Prefer automation, adversarial tests, reproducible checks, and least-privilege operations while keeping the project owner informed of material decisions.

## Communication

Report in plain language, briefly and accurately. State what changed, the exact evidence, remaining uncertainty, and the next concrete action. Never overstate tool access or claim a GitHub change succeeded until its result is confirmed.


## Smart memory and storage lifecycle — 2026-11-20

The owner-set hard objective is to keep the complete local HES footprint below 5,000,000,000 allocated bytes (5 decimal GB). Scope: project checkout including releases/candidates/worktrees, independent evidence store, and local backup/offsite-staging roots. Ubuntu and SentinelX platform files are reported separately. This target supersedes the earlier 10 GiB planning objective; it is not yet achieved.

Latest exact-snapshot baseline after safe maintenance and release compaction: complete local HES footprint remains above target; full current value is recorded in `/srv/hes-evidence/operations/storage-lifecycle`. The daily IDLM → dependency-aware Smart Cleanup → Smart Storage Manager pipeline runs at 03:45 UTC and produces a machine-readable 5 GB budget report.

Automatic maintenance is deliberately narrow: only old direct-child `/tmp/pip-*` build/install/unpack directories older than 24 hours, with no active pip/build process and no open file handles; APT download cache; and journald retention capped at 256 MiB / 30 days. Unknown files remain KEEP. Active/rollback releases, registered or dirty worktrees, Gate.io market data, trade journals, evaluation evidence, Hoshyar models referenced by services, local Restic repositories, encrypted backup archives and Dropbox objects are protected.

Release compaction is allowed only when an exact release snapshot is proven reproducible from a GitHub-hosted commit, its manifest or full Git tree matches byte-for-byte, and there are no active symlink, deployment-record, systemd, process or open-file references. Current and rollback pointers, newest-five releases, and deployment-record references are retained. Backup pruning is prohibited until full archive restore, remote restore and replacement-host recovery pass. Dropbox's separate 400,000,000-byte folder cap remains unchanged.

Current limitation: the 5 GB objective is not yet met. Remaining large HES assets include candidate snapshots, active and registered worktrees, Hoshyar runtime/model assets, local Restic repository and protected offsite staging. These are not generic cache and must not be deleted by age-based cleanup. The operator dashboard contract is documented in `docs/dashboard/STORAGE_AND_MEMORY_MANAGEMENT_V1.md`.
