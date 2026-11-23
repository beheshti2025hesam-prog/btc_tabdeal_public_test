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
journal snapshot and requires it to remain unchanged. Therefore this writer
must not be enabled while hes-mother-supervisor-soak-20261122-v1.service is
active. Its summary is written to
/var/lib/hes-mother-supervisor-soak-20261122-v1/mother-supervisor-soak-summary.json.
After it finishes, run
scripts/ops/activate_mother_decision_journal_writer_v1.sh from the exact
immutable release directory with that release ID. The activation script fails
closed unless the soak summary is PASS, complete, has at least 288 observations,
matches the frozen source commit/tree, confirms the journal snapshot is
unchanged, and reports a verified witness with no authorized execution or
active supervisor agents. It then installs and enables the 15-minute timer.
No production journal append is performed by installation.
