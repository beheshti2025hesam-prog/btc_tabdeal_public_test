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


## Documentation as a first-class HES capability

- The Documentation library is a versioned, searchable capability inside the existing HES Command Center, not a separate application or a source of trading/runtime truth.
- It supports Persian (RTL), English, German and French (LTR), and covers project DNA/roadmap, product identity, architecture, market data and protocol contracts, strategies/indicators, risk/execution boundaries, training/evaluation, news/journals, operations/security/backup/recovery, glossary, troubleshooting and change history.
- The library reuses the existing dashboard, locale selector and static-asset/API delivery. Its endpoint is GET-only, locale/schema validated and fail-closed. It cannot read secrets, access exchange accounts, mutate journals or policies, deploy code, invoke execution or place orders.
- Every new capability and architecture decision must update the project DNA/roadmap and all four dashboard locales together, with source provenance, catalog version/changelog and exact-commit tests.
- Editorial validation must check complete locale parity, stable technical terms, safety meaning, blank/untranslated/placeholder content, RTL/LTR direction and responsive browser behavior. Independent native-speaker review must be identified separately and never implied if it has not occurred.
- Documentation tests and green CI do not authorize production deployment or trading. Merge, production release and rollback remain separate approval gates.


## NO_TRADE decision-quality evaluation — 2026-11-19

- Every matured NO_TRADE decision is re-evaluated with forward-only closed Gate.io Public Spot BTC_USDT candles at 1h/4h/24h. A separate 1m structure-only shadow replay uses frozen decision-time evidence and fixed 3R geometry.
- The evaluation distinguishes valid directional counterfactuals, rejected proposals, structure-only candidates, directionless market context, incomplete coverage and invalid stop geometry. Gaps are never interpolated; ambiguous same-candle stop/target cases resolve conservatively as stop.
- Structure-only target hits are review candidates, not actual missed profits, realized PnL, win-rate evidence or causal proof. Spot-derived SHORT paths do not establish executable short economics.
- Production Learning Loop remains read-only. No automatic gate tuning, policy mutation, strategy activation, execution or orders.
- 2026-11-19 production snapshot: 94 matured decisions; 93 complete gap-free 24h horizons; zero tracker-boundary mismatches; 34 independent candidates; 30 evaluated shadow geometries; 4 invalid stop geometries; two LONG 24h target-hit review clusters. The actual-missed-profit claim remains false.
- Source checkpoint: `docs/checkpoints/NO_TRADE_COUNTERFACTUAL_MATURITY_V2_2026-11-19.md`. The operational report is evidence, not a trading authorization.


## Smart memory and storage lifecycle — 2026-11-20

The owner-set hard objective is to keep the complete local HES footprint below 5,000,000,000 allocated bytes (5 decimal GB). Scope: project checkout including releases/candidates/worktrees, independent evidence store, and local backup/offsite-staging roots. Ubuntu and SentinelX platform files are reported separately. This target supersedes the earlier 10 GiB planning objective; it is not yet achieved.

The daily IDLM → dependency-aware Smart Cleanup → Smart Storage Manager pipeline runs at 03:45 UTC and produces a machine-readable 5 GB budget report. Automatic maintenance is deliberately narrow: only old direct-child `/tmp/pip-*` build/install/unpack directories older than 24 hours, with no active pip/build process and no open file handles; APT download cache; and journald retention capped at 256 MiB / 30 days.

Unknown files remain KEEP. Active/rollback releases, registered or dirty worktrees, Gate.io market data, trade journals, evaluation evidence, Hoshyar models referenced by services, local Restic repositories, encrypted backup archives and Dropbox objects are protected. Release compaction is allowed only when an exact release snapshot is proven reproducible from a GitHub-hosted commit, its manifest or full Git tree matches byte-for-byte, and there are no active symlink, deployment-record, systemd, process or open-file references. Current and rollback pointers, newest-five releases, and deployment-record references are retained.

Backup pruning is prohibited until full archive restore, remote restore and replacement-host recovery pass. Dropbox's separate 400,000,000-byte folder cap remains unchanged. Current 5 GB objective is not yet met; remaining large HES assets include candidate snapshots, active/registered worktrees, Hoshyar runtime/model assets, local Restic repository and protected offsite staging. These are not generic cache and must not be deleted by age-based cleanup. Dashboard contract: `docs/dashboard/STORAGE_AND_MEMORY_MANAGEMENT_V1.md`.


## Smart memory/storage recovery validation — 2026-11-20

Local full Restic same-host restore and Dropbox compact-core remote restore are both verified PASS. The local full snapshot passed read-data integrity and full 43-root extraction; the remote 398,216,865-byte core matched its Dropbox manifest hash, passed GPG/Zstandard/tar safety and full extraction, with active/rollback release manifests and main Git connectivity verified. The Smart Storage Manager and daily runner record these as separate evidence gates. Replacement-host boot/recovery remains NOT_PROVEN; no backup pruning is authorized.

## Strategy-family activation boundary

Strategy families may be enabled for a dedicated PAPER_SHADOW candidate lane without being activated for live decisions. Trend-family candidates must pass the existing independent market-structure/confirmation and risk gates, the current news veto, and the closed-candle data contract. The legacy indicator-family Range variant is not admitted to Mother candidates; Range v2 remains RESEARCH_ONLY_NOT_PROMOTED until its own evidence gate passes. Shadow activation never grants decision authority, risk-gate bypass, execution, orders, or capital mutation. Live policy/ruleset activation remains a separate evidence-backed promotion decision.
