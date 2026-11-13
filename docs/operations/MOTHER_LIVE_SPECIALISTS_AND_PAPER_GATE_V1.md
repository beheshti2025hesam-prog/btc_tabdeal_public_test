# Mother live specialists and paper-execution gate v1

## Runtime authority

The production Mother API and Command Center use web.mother_runtime_dashboard_view and core.orchestration.mother_runtime_specialists_v1. Every request loads the current shared Gate.io Public Spot BTC_USDT candle ledger and invokes the deterministic HES evaluators. The report-backed mother_v2_dashboard_view is legacy-only and must not be wired back into the live API.

The seven registered specialists are:

1. **Data Quality** — validates the shared 15m/1h/4h candle input, provenance, and the dedicated 1m precision-entry feed.
2. **Market Structure** — derives the current 15m regime and causal structure from closed candles.
3. **Signal** — evaluates the active Strategy V2 policy against the current multi-timeframe snapshot.
4. **Confirmation** — independently detects the opportunity and evaluates direction/structure confirmation.
5. **Risk** — independently evaluates confirmation, stop/target geometry, minimum 3R, simulation sizing assumptions, exposure and cost-model gates.
6. **Decision** — applies the final policy/risk gates and records a no-trade decision whenever a required gate is not approved.
7. **Evaluation** — reads the existing decision journal; it does not infer outcomes or write new journal records.

On a valid shared market snapshot, all seven specialists are invoked in canonical order even when an upstream gate fails. An unconfirmed signal therefore does not suppress Risk, Decision, or Evaluation; the final result remains NO_TRADE and a risk rejection retains veto precedence. A runtime exception or invalid input still fails closed. The dashboard exposes registered and actually executed specialists separately.

## Market-data and sequence semantics

- Gate.io Public Spot BTC_USDT remains the sole live analysis/chart/candle source.
- 15m validates the setup; 1m is a precision-entry input only and has direction_authority=false.
- Sequence validation means **closed-candle open-time alignment, ordering, duplicate and gap checks only**.
- No venue trade ID, trade.sequence, WebSocket update ID, or sequence-like field is treated as a universal ordering guarantee, identity key, deduplication key, or gap detector. Unknown sequence semantics remain unused.

## Paper-simulation readiness gate

PaperExecutionGateV1 is a readiness gate, not an order executor. It requires all of the following:

- explicit active Strategy V2 policy and ruleset metadata;
- current Gate.io data, observed structure, candle integrity, clock and 1m health;
- verified release-bound 24h 1m recovery evidence;
- a directional strategy candidate and matching confirmation;
- an evaluated and approved risk result;
- precision-entry readiness;
- execution, historical-input leakage and future-outcome leakage all disabled.

The gate reports READY_FOR_PAPER_SIMULATION only when every condition passes. It never calls a venue adapter, creates a position, mutates capital, submits an order, or writes the decision journal. Missing or invalid evidence blocks the gate.

## PR #498 recovery evidence

The 24h recovery soak runs the immutable PR #498 candidate commit `7bc87617440cee0861cce608c297ef26613ce020` without replacing the production 1m collector. Its 1m collector runs as the separate systemd unit `hes-global-market-data-gateio-1m-pr498-candidate.service`, with `WorkingDirectory` and collector entrypoint bound to the exact candidate release and its output isolated at:

`/opt/hes-trade-agent/data/forward/pr498_candidate_root_7bc87617440cee0861cce608c297ef26613ce020/data/forward/global_market_candles_1m_v1.jsonl`

The isolated market root reuses the validated production 15m/1h/4h ledgers read-only; only its 1m ledger is written by the candidate collector. The soak wrapper checks the production 15m/1h/4h services, the official production 1m service and its integrity timer, plus the isolated candidate 1m service. The official 1m service and integrity timer remain required health gates; the separate candidate collector is additionally checked to prove the PR code itself is running without replacing production. The wrapper and captured `systemctl show` manifest are both hashed into the evidence package. The release manifest must also bind the collector entrypoint and `forward/global_market_data_gateio_v1.py`, not only the soak script and reader.

After a passing 24h soak, build the durable evidence package with:

    python scripts/ops/build_gateio_1m_recovery_evidence_v1.py \
      --data-root /opt/hes-trade-agent \
      --release-root /opt/hes-trade-agent/releases/7bc87617440cee0861cce608c297ef26613ce020 \
      --market-data-root /opt/hes-trade-agent/data/forward/pr498_candidate_root_7bc87617440cee0861cce608c297ef26613ce020 \
      --soak-log /opt/hes-trade-agent/data/forward/pr498_candidate_root_7bc87617440cee0861cce608c297ef26613ce020/data/forward/gateio_feed_soak_24h_pr498_candidate.jsonl \
      --soak-wrapper /opt/hes-trade-agent/data/forward/pr498_candidate_root_7bc87617440cee0861cce608c297ef26613ce020/run_candidate_soak.py \
      --candidate-collector-manifest /opt/hes-trade-agent/data/forward/pr498_candidate_root_7bc87617440cee0861cce608c297ef26613ce020/candidate_collector_unit_manifest.json \
      --output /opt/hes-trade-agent/data/forward/gateio_1m_recovery_24h_evidence.json

The builder preserves the official soak JSONL, canonical 1m snapshot, candidate collector journal, wrapper and collector-unit manifest. It verifies the exact release hashes and candidate service contract, makes evidence artifacts read-only, then runs the same verifier used by Mother. A failed or incomplete soak cannot produce verified recovery evidence.

## Safety and promotion

- Mother, paper readiness and dashboard are observation-only.
- No merge, active-release pointer change, collector restart, live order, or paper position is implied by a green unit test or a passing soak.
- Policy/ruleset activation and the separate PR #496 full-restore gate remain independent promotion requirements.
