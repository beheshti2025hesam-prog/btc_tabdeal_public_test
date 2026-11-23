# Mother Decision Journal Writer v1

## Purpose

Persist one immutable, witnessed Mother decision observation into the existing
data/forward/trade_journal_v2.jsonl. This reuses ForwardJournalV1; it does
not create a parallel decision journal and does not make the dashboard GET
route write to disk.

## Runtime contract

- Runs once per 15-minute interval as a dedicated Type=oneshot systemd unit.
- Calls the deployed read_mother_runtime_dashboard() implementation and
  requires the live Mother schema, Gate.io Spot BTC_USDT 15m scope, valid
  SHA-256 provenance, a verified Mother witness, and all safety flags off.
- The read API must continue to report journal_write=false. The separate
  writer owns the append and reports RECORDED or ALREADY_RECORDED.
- Writes only hes_mother_decision_journal_event_v1 records to the existing
  append-only journal. Uses the existing file lock, duplicate scan, append,
  flush and fsync behavior.
- Event identity is deterministic over market batch provenance, raw news
  snapshot/brief digests, stable specialist states/evidence, consensus,
  proposal, selected candidate, and final decision. It excludes wall-clock
  observation time, trace ID, audit digest, news age, and per-request
  context hashes so repeated reads of identical evidence are idempotent.
- A new market candle, changed news snapshot, changed gate state, proposal,
  candidate or final decision creates a new event ID.
- If a selected paper candidate contains a complete valid direction/entry/SL/TP
  geometry, it is preserved. Otherwise the record remains directionless or
  geometry-incomplete and downstream verification must classify it as
  NOT_CLASSIFIABLE/context-only; no direction or geometry is invented.
- outcome and closed_at remain null. Future price movement is evaluated
  only by the existing forward-only NO_TRADE maturity pipeline.
- Execution, orders, external LLM access, outcome inference and policy mutation
  remain disabled.

## Learning and reporting boundaries

Mother records are distinguishable by service_name=mother_runtime_decision_journal_writer
and schema. They become visible in the existing decision journal. They may
increase total NO_TRADE observation counts and directionless market-context
observations, but they do not create paper candidates or count as Strategy V2
wins/losses. Strategy performance remains candidate-linked and gate-qualified.

## Acceptance and activation gate

The 2026-11-22 Mother 24-hour read-only soak intentionally hashes a frozen
journal snapshot and requires that snapshot copy to remain unchanged. Its
summary is written to
/var/lib/hes-mother-supervisor-soak-20261122-v1/mother-supervisor-soak-summary.json.
The completed run passed with 288 observations and the independent acceptance
gate returned PASS. The unchanged snapshot assertion applies to the frozen
soak copy; it must not be interpreted as proof that the live production
trade_journal_v2.jsonl received no writes from any other service.

The activation script is designed to run only after the exact soak completes.
It fails closed unless the summary is PASS, complete, has at least 288
observations, matches the frozen source commit/tree, confirms the snapshot
copy is unchanged, and reports a verified witness with no authorized execution
or active supervisor agents. It then installs and enables the 15-minute timer.
Installation itself does not append a production journal record.

## VPS deployment reconciliation — observed 2026-11-23

A read-only inspection after the soak found that the VPS already had an enabled
and active `hes-mother-decision-journal-writer.timer`, configured for a
15-minute cadence. Its oneshot service points to immutable release
`0ce4dba08fb31464a89c8b217e9a6d45c4e559c6`, not to the current PR head.
The deployed writer source SHA-256 is
`f3e2cf3e43ec1b3a1de334f979d8754668bbdc74710b30f65c988ed9def1735e`,
and it matches the file hash recorded in that release's manifest.

At the latest inspected journal snapshot, 129 Mother writer records were
present. All 129 were `NO_TRADE` with `BLOCKED_RISK_VETO`; event IDs were
unique; none had execution_enabled, orders_placed, or
policy_mutation_enabled set to true. The runtime writer validates that the
input Mother envelope contains a verified witness before mapping the record.
The deployed record schema does not persist a separate top-level
`witness_verified` boolean, so that field must not be used to audit historical
rows. The recent service logs also report successful `RECORDED` results and
no orders or policy mutation.

This discovery corrects the earlier operational assumption that the timer was
not installed and that no production journal appends had occurred. The timer
was not changed, restarted, or replaced during this inspection. The current
PR implementation is not the deployed implementation. Do not rerun the
activation script, replace the deployed release, or claim this PR is deployed
until source/provenance and journal-schema compatibility are reconciled and
revalidated. Keep the production writer's execution and order flags disabled.
