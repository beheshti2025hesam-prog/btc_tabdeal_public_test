# Mother Specialist Timeout & Recovery Supervisor V1

Status: integrated in the isolated Mother 13b candidate; production deployment remains gated by exact-head CI, controlled stress, and 24-hour read-only soak.

## Contract
- Runs each real runtime specialist evaluation in a separate Linux child process using the spawn start method; the callable, arguments and result must be pickle-serializable.
- The market bootstrap is also process-isolated. A timeout terminates the child; it does not leave an abandoned worker thread running.
- Each child receives a private copy of the request's memoized market context and returns its updated state to the parent. The parent restores that state before the next stage, preserving the one-snapshot/one-computation contract across the seven sequential specialists.
- The runtime supervisor is process-wide and permits at most 12 concurrent child processes per specialist name. Different requests have independent market contexts; excess work returns BUSY and maps to UNKNOWN/NO_TRADE.
- Duplicate request IDs bound to the same evidence digest return cached output or IN_PROGRESS and never invoke the specialist again. The cache is bounded and process-local. Market bootstrap requests deliberately use unique IDs so a new dashboard read never reuses an earlier disk snapshot.
- Default is one attempt. A second attempt is permitted only when the caller explicitly declares retry_safe=True; Mother runtime sets retry_safe=False.
- Consecutive failed requests open a circuit. Reset is explicit/operator-controlled; no blind restart loop.
- Failure, timeout, busy, duplicate, and circuit-open states are not approvals. Every non-success state maps to UNKNOWN, causing the existing Mother gate to block to NO_TRADE.
- No exchange, order, journal-write, policy-mutation, or execution capability is present.

## Integration point
The production route invokes the supervisor around the seven actual `live_specialists_v1` runtime specialists and the initial market bootstrap. The existing precomputed-report path remains unchanged. The seven-stage order, provenance checks, same-snapshot consensus, independent risk veto, witness, and `execution_authorized=False` contract remain unchanged.

## Recovery policy
A timed-out process is terminated and discarded. No automatic retry is assumed safe. Retry only for an explicitly pure/idempotent specialist. Repeated failures open a circuit until a controlled health check and explicit reset. Never convert a failed specialist to PASS.

## Validation
`tests/test_mother_supervisor_runtime_integration_v1.py` verifies market-state round-trip between sequential specialists, duplicate idempotency, timeout-to-UNKNOWN mapping, and Mother NO_TRADE behavior. Existing Mother runtime, orchestrator, witness and full repository suites remain required release gates.

## 24-hour read-only acceptance soak

Use `scripts/ops/mother_supervisor_soak_v1.py` under a transient systemd service with the same sandbox properties as `hes-readonly-dashboard.service`. The runner executes one live Mother observation every 300 seconds for 24 hours, checks the seven-stage order, witness, supervisor circuits/worker cleanup and all read-only invariants, and writes JSONL plus a final summary under `STATE_DIRECTORY`. It uses a private read-only copy of the current trade journal for the Evaluation specialist so the independent Strategy V2 journal writer cannot create false positives during the soak. The production journal itself is never passed as the soak journal and is never modified.

Release approval requires the soak summary to report `status=PASS`, `complete=true`, zero failures, an unchanged private journal snapshot, and no active/in-flight supervisor workers at every observation. This soak validates process/runtime reliability, not strategy profitability or trade performance.

## Separation from platform operations
- Mother and its specialist supervisor manage only the trading-decision specialist lifecycle. They must not execute Smart Cleanup, Smart Storage, Smart Backup, backup retention, remote pruning, or VPS service repair.
- Those capabilities remain in their existing dedicated operational managers, with separate allowlists, immutable evidence, quota ceilings, restore verification and explicit destructive-action gates. Do not create duplicate cleanup/backup agents inside Mother.
- Mother may consume sanitized, read-only operational status summaries when an approved dashboard integration exists. It receives no filesystem mutation, encryption-key, backup-content, Box/Dropbox write, or service-control capability.
- A missing restore-verification marker, failed quota check, or unverified remote copy is a blocker, never a success signal. Mother must not bypass those gates or authorize remote deletion.
