"""Append-only, evidence-linked experiential memory and hypothesis gate for HES Blackbox.

This module indexes existing canonical evidence; it never copies/relabels NO_TRADE
counterfactuals as trade outcomes and never mutates strategy policy or executes.
"""
from __future__ import annotations
import fcntl, hashlib, json, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "hes_blackbox_experience_event_v1"
HYPOTHESIS_SCHEMA = "hes_blackbox_hypothesis_event_v1"
ALLOWED_REGIMES = {"BULLISH", "BEARISH", "RANGE", "NO_TRADE"}
EXPERIENCE_TYPES = {"TRADE_OUTCOME", "NO_TRADE_COUNTERFACTUAL", "REJECTED_PROPOSAL", "MARKET_CONTEXT", "FAMILY_RESEARCH"}
STATUSES = {"DISCOVERED", "PREREGISTERED", "TESTING", "ACCEPTED", "REJECTED", "INCONCLUSIVE", "RETIRED"}
TRANSITIONS = {
    "DISCOVERED": {"PREREGISTERED", "RETIRED"},
    "PREREGISTERED": {"TESTING", "RETIRED"},
    "TESTING": {"ACCEPTED", "REJECTED", "INCONCLUSIVE", "RETIRED"},
    "INCONCLUSIVE": {"TESTING", "RETIRED"},
    "ACCEPTED": {"RETIRED"}, "REJECTED": {"RETIRED"}, "RETIRED": set(),
}


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value.lower())


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc).isoformat()


def build_experience_event(*, source_ref: str, source_sha256: str, source_event_id: str,
                           experience_type: str, observed_at: str, venue: str,
                           market: str, symbol: str, timeframe: str, regime: str,
                           family_id: str | None = None, direction: str | None = None,
                           gate_decision: str | None = None, outcome_class: str | None = None,
                           matured: bool = False, provenance_complete: bool = False,
                           costs_verified: bool = False, net_r: float | None = None,
                           counterfactual: bool = False) -> dict[str, Any]:
    """Create a compact reference to a canonical record, not a duplicate source journal row."""
    if experience_type not in EXPERIENCE_TYPES:
        raise ValueError("UNKNOWN_EXPERIENCE_TYPE")
    if not source_ref or source_ref.startswith("/") or ".." in Path(source_ref).parts:
        raise ValueError("SOURCE_REF_MUST_BE_SAFE_RELATIVE_PATH")
    if len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256.lower()):
        raise ValueError("SOURCE_SHA256_INVALID")
    if not source_event_id or not venue or not market or not symbol or not timeframe:
        raise ValueError("EXPERIENCE_IDENTITY_INCOMPLETE")
    if regime not in ALLOWED_REGIMES:
        raise ValueError("REGIME_NOT_IN_FOUR_STATE_CONTRACT")
    if direction not in (None, "LONG", "SHORT"):
        raise ValueError("DIRECTION_INVALID")
    if net_r is not None and not math.isfinite(float(net_r)):
        raise ValueError("NET_R_MUST_BE_FINITE")
    if counterfactual and experience_type != "NO_TRADE_COUNTERFACTUAL":
        raise ValueError("COUNTERFACTUAL_TYPE_MISMATCH")
    eligible = bool(experience_type == "TRADE_OUTCOME" and matured and provenance_complete
                    and costs_verified and gate_decision in ("LONG", "SHORT")
                    and direction in ("LONG", "SHORT") and outcome_class in ("WIN", "LOSS", "FLAT")
                    and net_r is not None and not counterfactual)
    identity = {"source_ref": source_ref, "source_event_id": source_event_id,
                "source_sha256": source_sha256, "experience_type": experience_type}
    return {
        "schema": SCHEMA, "event_id": "HES-EXP-" + canonical_sha256(identity)[:24],
        "created_at": _utc(observed_at), "observed_at": _utc(observed_at),
        **identity, "venue": venue, "market": market, "symbol": symbol,
        "timeframe": timeframe, "regime": regime, "family_id": family_id,
        "direction": direction, "gate_decision": gate_decision,
        "outcome_class": outcome_class, "matured": bool(matured),
        "provenance_complete": bool(provenance_complete), "costs_verified": bool(costs_verified),
        "net_r": float(net_r) if net_r is not None else None,
        "counterfactual": bool(counterfactual), "training_eligible": eligible,
        "eligibility_reason": "ALL_TRADE_LABEL_GATES_PASSED" if eligible else "RESEARCH_OR_INCOMPLETE_EVIDENCE",
    }


def append_experience_events(path: str | Path, events: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Append idempotently; exact replays skip, same event ID with changed content fails closed."""
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    counts = {"appended": 0, "exact_replays": 0}
    with target.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0); existing: dict[str, str] = {}
        for line_no, line in enumerate(stream, 1):
            if not line.strip(): continue
            row = json.loads(line)
            if row.get("schema") != SCHEMA or not row.get("event_id"):
                raise ValueError(f"EXPERIENCE_LEDGER_CORRUPT:{line_no}")
            digest = canonical_sha256(row)
            prior = existing.setdefault(row["event_id"], digest)
            if prior != digest: raise ValueError("EXPERIENCE_EVENT_ID_COLLISION_IN_LEDGER")
        for event in events:
            if event.get("schema") != SCHEMA or not event.get("event_id"):
                raise ValueError("EXPERIENCE_EVENT_SCHEMA_INVALID")
            digest = canonical_sha256(event); prior = existing.get(event["event_id"])
            if prior is not None:
                if prior != digest: raise ValueError("EXPERIENCE_EVENT_ID_CONTENT_CONFLICT")
                counts["exact_replays"] += 1; continue
            stream.seek(0, 2); stream.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            existing[event["event_id"]] = digest; counts["appended"] += 1
        stream.flush()
    return counts



def collect_canonical_experiences(data_root: str | Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build reference-only memory events from existing HES ledgers; never mutates source data."""
    root = Path(data_root).resolve(); base = root / "data" / "forward"
    sources = {
        "trade_journal_v2.jsonl": "decision",
        "neutral_decision_outcomes_v1.jsonl": "neutral",
        "strategy_policy_v2_eval_outcomes.jsonl": "strategy_outcome",
        "indicator_strategy_shadow_outcomes_v1.jsonl": "family",
        "indicator_strategy_forward_paper_journal_v1.jsonl": "forward_paper",
        "strategy_family_trend_breakout_results_v1.jsonl": "family",
        "strategy_family_range_mean_reversion_results_v1.jsonl": "family",
    }
    events: list[dict[str, Any]] = []; counts: dict[str, int] = {}
    regime_map = {"UPTREND": "BULLISH", "BULLISH": "BULLISH", "DOWNTREND": "BEARISH",
                  "BEARISH": "BEARISH", "RANGE": "RANGE"}
    for filename, kind in sources.items():
        path = base / filename; count = 0
        if not path.exists(): counts[filename] = 0; continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip(): continue
            row = json.loads(line)
            if not isinstance(row, dict): raise ValueError(f"SOURCE_ROW_NOT_OBJECT:{filename}:{line_no}")
            if kind == "decision":
                decision = row.get("decision"); proposal = row.get("proposal_direction")
                if decision in ("LONG", "SHORT") and row.get("outcome") is not None:
                    etype = "TRADE_OUTCOME"
                elif proposal in ("LONG", "SHORT") and decision not in ("LONG", "SHORT"):
                    etype = "REJECTED_PROPOSAL"
                else:
                    etype = "MARKET_CONTEXT"
                event_id = row.get("event_id"); observed = row.get("observed_at")
                gate = decision; outcome = row.get("outcome"); direction = row.get("direction")
                matured = False; verified = False; family = row.get("policy_version")
            elif kind == "neutral":
                etype = "NO_TRADE_COUNTERFACTUAL"; event_id = row.get("outcome_id") or row.get("decision_event_id")
                observed = row.get("observed_at"); gate = "NO_TRADE"; outcome = row.get("outcome_class")
                direction = None; matured = row.get("horizon_complete") is True; verified = False; family = row.get("policy_version")
            elif kind == "strategy_outcome":
                etype = "TRADE_OUTCOME" if row.get("outcome") in ("wins", "losses", "flats") else "FAMILY_RESEARCH"
                event_id = row.get("event_id") or row.get("candidate_event_id"); observed = row.get("resolved_at")
                gate = row.get("final_gate_decision"); outcome = {"wins":"WIN", "losses":"LOSS", "flats":"FLAT"}.get(row.get("outcome"), row.get("outcome"))
                direction = row.get("direction"); matured = row.get("outcome") in ("wins", "losses", "flats")
                verified = row.get("costs_verified") is True; family = row.get("policy_version")
            elif kind == "family":
                etype = "FAMILY_RESEARCH"; event_id = row.get("event_id"); observed = row.get("exit_time") or row.get("observed_at")
                if isinstance(observed, (int, float)): observed = datetime.fromtimestamp(observed, timezone.utc).isoformat()
                gate = None; outcome = row.get("outcome"); direction = row.get("direction")
                matured = row.get("outcome") not in (None, "SHORT_NOT_TESTABLE_FROM_SPOT")
                verified = row.get("costs_verified") is True; family = row.get("strategy_family_id")
            else:
                etype = "FAMILY_RESEARCH" if row.get("direction") in ("LONG", "SHORT") else "MARKET_CONTEXT"
                event_id = row.get("event_id"); observed = row.get("observed_at"); gate = row.get("decision")
                outcome = row.get("outcome"); direction = row.get("direction"); matured = False
                verified = False; family = row.get("strategy_family_id")
            if not event_id or not observed: continue
            if isinstance(observed, (int, float)): observed = datetime.fromtimestamp(observed, timezone.utc).isoformat()
            raw_regime = row.get("market_regime") or row.get("regime")
            regime = regime_map.get(raw_regime, "NO_TRADE")
            source_hashes = row.get("source_hashes") if isinstance(row.get("source_hashes"), dict) else {}
            provenance_ok = bool(kind == "strategy_outcome" and len(source_hashes) >= 5
                and all(isinstance(v, str) and len(v) == 64 for v in source_hashes.values())
                and isinstance(row.get("run_manifest_sha256"), str) and len(row["run_manifest_sha256"]) == 64)
            events.append(build_experience_event(source_ref=f"data/forward/{filename}",
                source_sha256=canonical_sha256(row), source_event_id=str(event_id),
                experience_type=etype, observed_at=str(observed), venue="gateio", market="spot",
                symbol=str(row.get("symbol") or "UNKNOWN"), timeframe=str(row.get("timeframe") or "UNKNOWN"),
                regime=regime, family_id=str(family) if family else None,
                direction=direction if direction in ("LONG", "SHORT") else None,
                gate_decision=gate if gate in ("LONG", "SHORT", "NO_TRADE") else None,
                outcome_class=outcome if isinstance(outcome, str) else None, matured=matured,
                provenance_complete=provenance_ok, costs_verified=verified,
                net_r=row.get("net_R", row.get("net_r")),
                counterfactual=(kind == "neutral")))
            count += 1
        counts[filename] = count
    return events, counts



def discover_hypotheses_from_feature_snapshots(rows: list[dict[str, Any]], *,
                                               source_hashes: dict[str, str],
                                               minimum_support: int = 20) -> list[dict[str, Any]]:
    """Discover descriptive regime-conditioned feature motifs; never infer an edge or train.

    Quartile boundaries are frozen from the supplied discovery window. Generated motifs
    are hypotheses only and require a separate preregistered independent OOS tournament.
    """
    if minimum_support < 2: raise ValueError("MINIMUM_DISCOVERY_SUPPORT_TOO_SMALL")
    if not source_hashes or any(not _is_sha256(v) for v in source_hashes.values()):
        raise ValueError("DISCOVERY_SOURCE_HASHES_INVALID")
    usable = []
    for row in rows:
        snap = row.get("feature_snapshot")
        observed = row.get("observed_at")
        if not isinstance(snap, dict) or not isinstance(observed, str): continue
        try: observed_utc = _utc(observed)
        except (TypeError, ValueError): continue
        raw_regime = row.get("market_regime") or row.get("regime")
        regime = {"UPTREND":"BULLISH", "DOWNTREND":"BEARISH"}.get(raw_regime, raw_regime)
        if regime not in ALLOWED_REGIMES: regime = "NO_TRADE"
        numeric = {}
        for key, value in snap.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                continue
            numeric[str(key)] = float(value)
        if numeric: usable.append({"observed_at": observed_utc, "regime": regime, "features": numeric})
    if len(usable) < minimum_support: return []
    feature_names = sorted({name for row in usable for name in row["features"]})
    schema_sha = canonical_sha256(feature_names)
    hashes = {**source_hashes, "feature_schema": schema_sha}
    start = min(row["observed_at"] for row in usable); end = max(row["observed_at"] for row in usable)
    discovered = []
    for name in feature_names:
        values = sorted(row["features"][name] for row in usable if name in row["features"])
        if len(values) < minimum_support: continue
        cutoffs = [values[int((len(values)-1)*q)] for q in (.25, .50, .75)]
        for regime in sorted(ALLOWED_REGIMES):
            for bucket in ("Q1", "Q2", "Q3", "Q4"):
                members = []
                for row in usable:
                    if row["regime"] != regime or name not in row["features"]: continue
                    value = row["features"][name]
                    assigned = "Q1" if value <= cutoffs[0] else "Q2" if value <= cutoffs[1] else "Q3" if value <= cutoffs[2] else "Q4"
                    if assigned == bucket: members.append(row)
                if len(members) < minimum_support: continue
                feature_definition = {"regime": regime, "feature": name, "bucket": bucket,
                    "quantile_cutoffs_frozen_on_discovery_window": cutoffs,
                    "bucket_assignment": "Q1 <= q25; Q2 <= q50; Q3 <= q75; Q4 > q75",
                    "discovery_only": True, "minimum_support": minimum_support}
                hid = "HES-BBX-MOTIF-" + canonical_sha256({"feature_definition":feature_definition,
                    "source_hashes":hashes})[:16]
                event = build_hypothesis_event(hypothesis_id=hid, family_id="blackbox_feature_motif",
                    statement=f"Within {regime}, test whether {name} in {bucket} adds net expectancy beyond the preregistered family baseline.",
                    discovery_window={"start":start,"end":end}, source_hashes=hashes,
                    feature_definition=feature_definition,
                    null_hypothesis="The motif does not improve net expectancy over the preregistered baseline.",
                    alternative_hypothesis="The motif improves net expectancy on independent chronological OOS data.",
                    primary_metric="oos_mean_net_r_minus_baseline",
                    falsification_rule="Reject only on statistically significant OOS underperformance after Holm correction; otherwise inconclusive.",
                    multiple_testing_family="blackbox-feature-motif-v1")
                event["discovery_metadata"] = {"support_count":len(members),"research_only":True,
                    "outcomes_used_for_discovery":False,"training_eligible":False,
                    "regime":regime,"feature":name,"bucket":bucket}
                discovered.append(event)
    return sorted(discovered, key=lambda item: item["hypothesis_id"])



def build_strategy_family_competition_readiness(data_root: str | Path, *,
                                                blackbox_hypothesis_count: int = 0) -> dict[str, Any]:
    """Audit existing family journals for a fair paired OOS tournament; never rank weak cohorts."""
    root = Path(data_root).resolve(); base = root / "data" / "forward"
    report_path = base / "strategy_family_results_report_v1.json"
    if not report_path.exists():
        return {"schema":"hes_blackbox_family_competition_readiness_v1","status":"BLOCKED_MISSING_FAMILY_REPORT",
                "families":{},"blockers":["CANONICAL_FAMILY_REPORT_MISSING"],"comparison_ready":False,
                "blackbox_discovered_hypotheses":blackbox_hypothesis_count,
                "execution_enabled":False,"orders_placed":False}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") != "hes_strategy_family_results_report_v1":
        raise ValueError("CANONICAL_FAMILY_REPORT_SCHEMA_MISMATCH")
    blockers = []
    if report.get("execution_enabled") is True or report.get("orders_placed") is True:
        blockers.append("FAMILY_REPORT_CONTAINS_UNSAFE_EXECUTION_FLAGS")
    family_results = {}
    for family_id, family in sorted(report.get("families", {}).items()):
        filename = family.get("journal_file")
        if not filename or Path(filename).name != filename:
            raise ValueError("FAMILY_JOURNAL_PATH_INVALID")
        journal = base / filename
        actual_sha = hashlib.sha256(journal.read_bytes()).hexdigest() if journal.exists() else None
        sha_valid = bool(actual_sha and actual_sha == family.get("journal_sha256"))
        if not sha_valid: blockers.append(f"FAMILY_JOURNAL_HASH_MISMATCH:{family_id}")
        outcomes = []; paired = 0; candidate_events = 0; journal_events = 0; actual_eligible = 0
        if journal.exists():
            for line_no, line in enumerate(journal.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip(): continue
                event = json.loads(line); journal_events += 1
                if event.get("family_id") != family_id: raise ValueError(f"FAMILY_JOURNAL_IDENTITY_MISMATCH:{family_id}:{line_no}")
                if event.get("execution_enabled") is True or event.get("orders_placed") is True:
                    blockers.append(f"UNSAFE_FAMILY_EVENT_FLAGS:{family_id}")
                if event.get("event_type") == "PAPER_CANDIDATE": candidate_events += 1
                if event.get("event_type") == "PAPER_OUTCOME":
                    outcomes.append(event)
                    if event.get("performance_eligible") is True: actual_eligible += 1
                    if (event.get("performance_eligible") is True and event.get("costs_verified") is True
                        and isinstance(event.get("net_R"), (int,float))
                        and isinstance(event.get("baseline_net_R"), (int,float))):
                        paired += 1
        eligible = int(family.get("performance_eligible_resolved", 0) or 0)
        if family.get("execution_enabled") is True or family.get("orders_placed") is True:
            blockers.append(f"UNSAFE_FAMILY_REPORT_FLAGS:{family_id}")
        if journal_events != int(family.get("journal_event_count", journal_events) or 0):
            blockers.append(f"FAMILY_JOURNAL_EVENT_COUNT_MISMATCH:{family_id}")
        if candidate_events != int(family.get("candidate_count", candidate_events) or 0):
            blockers.append(f"FAMILY_CANDIDATE_COUNT_MISMATCH:{family_id}")
        if len(outcomes) != int(family.get("outcome_count", len(outcomes)) or 0):
            blockers.append(f"FAMILY_OUTCOME_COUNT_MISMATCH:{family_id}")
        if actual_eligible != eligible:
            blockers.append(f"FAMILY_ELIGIBLE_OUTCOME_COUNT_MISMATCH:{family_id}")
        if eligible < 100: blockers.append(f"INSUFFICIENT_GATE_APPROVED_FAMILY_OUTCOMES:{family_id}")
        if paired < 100: blockers.append(f"INSUFFICIENT_VERIFIED_PAIRED_NET_R_EVIDENCE:{family_id}")
        family_results[family_id] = {
            "family_version":family.get("family_version"), "activation_state":family.get("activation_state"),
            "candidate_count":candidate_events,
            "outcome_count":len(outcomes),
            "performance_eligible_resolved":eligible,
            "journal_performance_eligible_outcomes":actual_eligible,
            "preapproval_paper_eligible_outcomes":int(family.get("preapproval_paper_eligible_outcomes",0) or 0),
            "raw_outcome_counts":family.get("raw_outcome_counts",{}),
            "journal_sha256_verified":sha_valid,
            "verified_paired_net_r_evidence_count":paired,
            "tournament_eligible":bool(sha_valid and eligible >= 100 and paired >= 100),
        }
    ready = bool(len(family_results) >= 2 and not blockers and all(x["tournament_eligible"] for x in family_results.values()))
    if not ready and not blockers: blockers.append("AT_LEAST_TWO_VERSIONED_FAMILIES_REQUIRED")
    return {"schema":"hes_blackbox_family_competition_readiness_v1",
        "status":"READY_FOR_PAIRED_OOS_TOURNAMENT" if ready else "WAITING_FOR_VERIFIED_FAMILY_EVIDENCE",
        "families":family_results,"family_count":len(family_results),
        "blackbox_discovered_hypotheses":blackbox_hypothesis_count,
        "blackbox_hypotheses_competition_state":"DISCOVERY_ONLY_NOT_YET_COMPARABLE",
        "comparison_ready":ready,"blockers":blockers,
        "source_report_sha256":hashlib.sha256(report_path.read_bytes()).hexdigest(),
        "execution_enabled":False,"orders_placed":False,"policy_mutation_enabled":False}


def discover_canonical_shadow_hypotheses(data_root: str | Path, *, minimum_support: int = 20) -> list[dict[str, Any]]:
    """Read the existing historical indicator shadow journal as discovery-only input."""
    path = Path(data_root).resolve() / "data" / "forward" / "indicator_strategy_shadow_journal_v1.jsonl"
    if not path.exists(): return []
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip(): continue
        row = json.loads(line)
        if not isinstance(row, dict): raise ValueError(f"SHADOW_DISCOVERY_ROW_INVALID:{line_no}")
        rows.append(row)
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return discover_hypotheses_from_feature_snapshots(rows,
        source_hashes={"indicator_shadow_journal":source_sha}, minimum_support=minimum_support)


def build_hypothesis_event(*, hypothesis_id: str, family_id: str, statement: str,
                           discovery_window: dict[str, str], source_hashes: dict[str, str],
                           feature_definition: dict[str, Any], null_hypothesis: str,
                           alternative_hypothesis: str, primary_metric: str,
                           falsification_rule: str, multiple_testing_family: str,
                           status: str = "DISCOVERED") -> dict[str, Any]:
    if status not in STATUSES or status != "DISCOVERED":
        raise ValueError("NEW_HYPOTHESIS_MUST_START_DISCOVERED")
    if not all((hypothesis_id, family_id, statement, null_hypothesis, alternative_hypothesis,
                primary_metric, falsification_rule, multiple_testing_family)):
        raise ValueError("HYPOTHESIS_PREREGISTRATION_FIELDS_REQUIRED")
    if not discovery_window.get("start") or not discovery_window.get("end"):
        raise ValueError("DISCOVERY_WINDOW_REQUIRED")
    if not source_hashes or any(not _is_sha256(v) for v in source_hashes.values()):
        raise ValueError("SOURCE_HASHES_REQUIRED")
    return {"schema": HYPOTHESIS_SCHEMA, "event_type": "DISCOVERY", "event_id": "HES-HYP-" + canonical_sha256({
        "hypothesis_id": hypothesis_id, "statement": statement,
        "source_hashes": source_hashes, "feature_definition": feature_definition})[:24],
        "created_at": datetime.now(timezone.utc).isoformat(), "hypothesis_id": hypothesis_id,
        "family_id": family_id, "statement": statement, "discovery_window": discovery_window,
        "source_hashes": source_hashes, "feature_definition": feature_definition,
        "null_hypothesis": null_hypothesis, "alternative_hypothesis": alternative_hypothesis,
        "primary_metric": primary_metric, "falsification_rule": falsification_rule,
        "multiple_testing_family": multiple_testing_family, "status": "DISCOVERED"}


def validate_hypothesis_transition(previous: str, next_status: str, *, evidence_sha256: str | None = None) -> None:
    if previous not in STATUSES or next_status not in TRANSITIONS[previous]:
        raise ValueError("HYPOTHESIS_STATUS_TRANSITION_INVALID")
    if next_status in ("ACCEPTED", "REJECTED", "INCONCLUSIVE"):
        if not _is_sha256(evidence_sha256):
            raise ValueError("FINAL_HYPOTHESIS_TRANSITION_REQUIRES_EVIDENCE_HASH")



def build_hypothesis_transition_event(*, hypothesis_id: str, previous_status: str,
                                     next_status: str, evidence_sha256: str | None = None,
                                     rationale: str = "") -> dict[str, Any]:
    validate_hypothesis_transition(previous_status, next_status, evidence_sha256=evidence_sha256)
    if not hypothesis_id: raise ValueError("HYPOTHESIS_ID_REQUIRED")
    if next_status in ("ACCEPTED", "REJECTED", "INCONCLUSIVE") and not rationale:
        raise ValueError("FINAL_HYPOTHESIS_TRANSITION_REQUIRES_RATIONALE")
    payload = {"schema": HYPOTHESIS_SCHEMA, "hypothesis_id": hypothesis_id,
               "previous_status": previous_status, "status": next_status,
               "evidence_sha256": evidence_sha256, "rationale": rationale}
    return {**payload, "event_id": "HES-HYSTATE-" + canonical_sha256(payload)[:24],
            "created_at": datetime.now(timezone.utc).isoformat(), "event_type": "STATUS_TRANSITION"}


def append_hypothesis_events(path: str | Path, events: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Append immutable hypothesis discovery/status events and enforce the lifecycle."""
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    counts = {"appended": 0, "exact_replays": 0}
    with target.open("a+", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.seek(0); existing = {}; latest: dict[str, str] = {}
        for line_no, line in enumerate(stream, 1):
            if not line.strip(): continue
            row = json.loads(line)
            if row.get("schema") != HYPOTHESIS_SCHEMA or not row.get("event_id"):
                raise ValueError(f"HYPOTHESIS_LEDGER_CORRUPT:{line_no}")
            digest = canonical_sha256(row); prior = existing.setdefault(row["event_id"], digest)
            if prior != digest: raise ValueError("HYPOTHESIS_LEDGER_EVENT_COLLISION")
            hid = row.get("hypothesis_id")
            if row.get("event_type") == "DISCOVERY":
                latest[hid] = "DISCOVERED"
            elif row.get("event_type") == "STATUS_TRANSITION":
                if latest.get(hid) != row.get("previous_status"):
                    raise ValueError("HYPOTHESIS_LEDGER_LIFECYCLE_CORRUPT")
                validate_hypothesis_transition(row["previous_status"], row["status"], evidence_sha256=row.get("evidence_sha256"))
                latest[hid] = row["status"]
            else:
                raise ValueError("HYPOTHESIS_LEDGER_EVENT_TYPE_INVALID")
        for event in events:
            if event.get("schema") != HYPOTHESIS_SCHEMA or not event.get("event_id"):
                raise ValueError("HYPOTHESIS_EVENT_SCHEMA_INVALID")
            digest = canonical_sha256(event); prior = existing.get(event["event_id"])
            if prior is not None:
                if prior != digest: raise ValueError("HYPOTHESIS_EVENT_CONTENT_CONFLICT")
                counts["exact_replays"] += 1; continue
            hid = event.get("hypothesis_id")
            if event.get("event_type") == "DISCOVERY":
                if hid in latest: raise ValueError("HYPOTHESIS_ALREADY_DISCOVERED")
                latest[hid] = "DISCOVERED"
            elif event.get("event_type") == "STATUS_TRANSITION":
                previous = latest.get(hid)
                if previous != event.get("previous_status"):
                    raise ValueError("HYPOTHESIS_TRANSITION_PREVIOUS_STATE_MISMATCH")
                validate_hypothesis_transition(previous, event.get("status"), evidence_sha256=event.get("evidence_sha256"))
                latest[hid] = event["status"]
            else:
                raise ValueError("HYPOTHESIS_LEDGER_EVENT_TYPE_INVALID")
            stream.seek(0, 2); stream.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            existing[event["event_id"]] = digest; counts["appended"] += 1
        stream.flush()
    return counts


def binomial_upper_tail(successes: int, trials: int, null_rate: float) -> float:
    """Exact one-sided binomial tail P[X >= successes] under the preregistered null."""
    if trials < 1 or not 0 <= successes <= trials or not 0 < null_rate < 1:
        raise ValueError("BINOMIAL_INPUT_INVALID")
    # Stable recurrence starts at P(X=0), then accumulates through successes..n.
    p = (1.0 - null_rate) ** trials
    total = 0.0
    for k in range(trials + 1):
        if k >= successes: total += p
        if k < trials:
            p *= ((trials - k) / (k + 1)) * (null_rate / (1.0 - null_rate))
    return min(1.0, total)


def binomial_lower_tail(successes: int, trials: int, null_rate: float) -> float:
    """Exact one-sided binomial tail P[X <= successes] under the null."""
    if trials < 1 or not 0 <= successes <= trials or not 0 < null_rate < 1:
        raise ValueError("BINOMIAL_INPUT_INVALID")
    p = (1.0 - null_rate) ** trials
    total = p if successes >= 0 else 0.0
    for k in range(trials):
        p *= ((trials - k) / (k + 1)) * (null_rate / (1.0 - null_rate))
        if k + 1 <= successes: total += p
    return min(1.0, total)


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni family-wise error adjustment, monotone in sorted p-values."""
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    m = len(ordered); adjusted: dict[str, float] = {}; running = 0.0
    for rank, (key, value) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * float(value)))
        adjusted[key] = running
    return adjusted


def evaluate_hypothesis_tournament(rows: list[dict[str, Any]], *, alpha: float = 0.05,
                                   minimum_train_n: int = 100, minimum_oos_n: int = 100) -> dict[str, Any]:
    """Evaluate preregistered hypotheses with paired net-R sign tests + Holm per family."""
    if not 0 < alpha < 1: raise ValueError("ALPHA_INVALID")
    raw_p: dict[str, float] = {}; prelim: dict[str, dict[str, Any]] = {}; families: dict[str, dict[str, float]] = {}
    for row in rows:
        hid = str(row.get("hypothesis_id", ""))
        if not hid or hid in prelim: raise ValueError("HYPOTHESIS_ID_MISSING_OR_DUPLICATE")
        required = ("train_n", "train_wins", "oos_n", "oos_wins", "train_mean_net_r",
                    "oos_mean_net_r", "baseline_oos_mean_net_r", "train_net_r_values",
                    "oos_net_r_values", "baseline_oos_net_r_values", "oos_regime_count",
                    "costs_verified", "independent_oos", "chronological_purged", "unmatched",
                    "unscorable", "provenance_complete", "preregistered", "hypothesis_status",
                    "preregistration_sha256", "source_manifest_sha256", "multiple_testing_family")
        if any(k not in row for k in required): raise ValueError("HYPOTHESIS_EVIDENCE_FIELD_MISSING")
        train_values = row["train_net_r_values"]; oos_values = row["oos_net_r_values"]
        baseline_values = row["baseline_oos_net_r_values"]
        if not all(isinstance(v, list) for v in (train_values, oos_values, baseline_values)):
            raise ValueError("NET_R_EVIDENCE_MUST_BE_ARRAYS")
        if len(train_values) != int(row["train_n"]) or len(oos_values) != int(row["oos_n"]) or len(baseline_values) != int(row["oos_n"]):
            raise ValueError("NET_R_SAMPLE_COUNT_MISMATCH")
        if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(float(v))
               for values in (train_values, oos_values, baseline_values) for v in values):
            raise ValueError("NET_R_EVIDENCE_NON_FINITE")
        if int(row["train_n"]) < 0 or int(row["oos_n"]) < 0 or not 0 <= int(row["train_wins"]) <= int(row["train_n"]) or not 0 <= int(row["oos_wins"]) <= int(row["oos_n"]):
            raise ValueError("HYPOTHESIS_SAMPLE_COUNTS_INVALID")
        train_mean = sum(map(float, train_values)) / len(train_values) if train_values else 0.0
        oos_mean = sum(map(float, oos_values)) / len(oos_values) if oos_values else 0.0
        baseline_mean = sum(map(float, baseline_values)) / len(baseline_values) if baseline_values else 0.0
        if not math.isclose(train_mean, float(row["train_mean_net_r"]), rel_tol=1e-6, abs_tol=1e-9):
            raise ValueError("TRAIN_NET_R_MEAN_MISMATCH")
        if not math.isclose(oos_mean, float(row["oos_mean_net_r"]), rel_tol=1e-6, abs_tol=1e-9):
            raise ValueError("OOS_NET_R_MEAN_MISMATCH")
        if not math.isclose(baseline_mean, float(row["baseline_oos_mean_net_r"]), rel_tol=1e-6, abs_tol=1e-9):
            raise ValueError("BASELINE_NET_R_MEAN_MISMATCH")
        differences = [float(a)-float(b) for a,b in zip(oos_values, baseline_values)]
        positive = sum(x > 0 for x in differences); negative = sum(x < 0 for x in differences)
        ties = sum(x == 0 for x in differences); non_ties = positive + negative
        mean_lift = (sum(differences) / len(differences)) if differences else 0.0
        eligible_for_test = (row["preregistered"] is True and row["hypothesis_status"] == "TESTING"
                             and _is_sha256(row["preregistration_sha256"])
                             and _is_sha256(row["source_manifest_sha256"])
                             and bool(str(row["multiple_testing_family"]).strip())
                             and non_ties >= minimum_oos_n)
        if eligible_for_test:
            upper = binomial_upper_tail(positive, non_ties, .5)
            lower = binomial_lower_tail(positive, non_ties, .5)
            p = min(1.0, 2.0 * min(upper, lower))
        else:
            p = 1.0
        raw_p[hid] = p
        family = str(row["multiple_testing_family"])
        families.setdefault(family, {})[hid] = p
        blockers = []
        if row["preregistered"] is not True or row["hypothesis_status"] != "TESTING": blockers.append("HYPOTHESIS_NOT_PREREGISTERED_FOR_TESTING")
        if not _is_sha256(row["preregistration_sha256"]) or not _is_sha256(row["source_manifest_sha256"]): blockers.append("PREREGISTRATION_OR_SOURCE_HASH_INVALID")
        if not str(row["multiple_testing_family"]).strip(): blockers.append("MULTIPLE_TESTING_FAMILY_MISSING")
        if int(row["train_n"]) < minimum_train_n: blockers.append("INSUFFICIENT_TRAIN_SAMPLE")
        if int(row["oos_n"]) < minimum_oos_n or non_ties < minimum_oos_n: blockers.append("INSUFFICIENT_INDEPENDENT_OOS_SAMPLE")
        if row["independent_oos"] is not True: blockers.append("OOS_NOT_INDEPENDENT")
        if row["chronological_purged"] is not True: blockers.append("PURGED_CHRONOLOGY_NOT_PROVEN")
        if row["provenance_complete"] is not True: blockers.append("PROVENANCE_INCOMPLETE")
        if int(row["unmatched"]) or int(row["unscorable"]): blockers.append("OUTCOME_LINKAGE_OR_SCORING_NOT_CLEAN")
        if row["costs_verified"] is not True: blockers.append("EXECUTION_COSTS_UNVERIFIED")
        if int(row["oos_regime_count"]) < 2: blockers.append("INSUFFICIENT_REGIME_DIVERSITY")
        if row.get("direction") == "SHORT" and row.get("short_economics_validated") is not True: blockers.append("SHORT_ECONOMICS_NOT_VALIDATED")
        prelim[hid] = {"blockers": blockers, "eligible_for_statistical_test": eligible_for_test,
                       "family": family, "positive_pairs":positive, "negative_pairs":negative,
                       "ties":ties, "mean_net_r_lift":mean_lift}
    adjusted = {}
    for family, values in families.items(): adjusted.update(holm_adjust(values))
    results = []
    for row in rows:
        hid = row["hypothesis_id"]; item = prelim[hid]; blockers = list(item["blockers"])
        significant = adjusted[hid] <= alpha
        above_baseline = (float(row["oos_mean_net_r"]) > 0 and item["mean_net_r_lift"] > 0
                          and float(row["train_mean_net_r"]) > 0 and item["positive_pairs"] > item["negative_pairs"])
        below_baseline = (item["mean_net_r_lift"] < 0 and item["negative_pairs"] > item["positive_pairs"])
        if blockers:
            status = "INCONCLUSIVE"
        elif significant and below_baseline:
            status = "REJECTED"
        elif significant and above_baseline:
            status = "ACCEPTED"
        else:
            status = "INCONCLUSIVE"
            if float(row["oos_mean_net_r"]) <= 0: blockers.append("NON_POSITIVE_OOS_NET_EXPECTANCY")
            if item["mean_net_r_lift"] <= 0: blockers.append("NO_OOS_EXPECTANCY_LIFT_OVER_BASELINE")
            if float(row["train_mean_net_r"]) <= 0: blockers.append("NON_POSITIVE_TRAIN_NET_EXPECTANCY")
            if not significant: blockers.append("MULTIPLE_TEST_ADJUSTED_SIGNIFICANCE_NOT_MET")
        results.append({"hypothesis_id": hid, "status": status, "multiple_testing_family": item["family"],
                        "raw_two_sided_p_value": raw_p[hid], "holm_adjusted_p_value": adjusted[hid], "alpha": alpha,
                        "positive_oos_net_r_pairs": item["positive_pairs"],
                        "negative_oos_net_r_pairs": item["negative_pairs"], "tied_oos_net_r_pairs": item["ties"],
                        "mean_oos_net_r_lift_vs_baseline": item["mean_net_r_lift"],
                        "blockers": blockers, "evidence_sha256": canonical_sha256(row),
                        "policy_mutation_enabled": False, "production_approved": False})
    return {"schema": "hes_blackbox_hypothesis_tournament_v1", "method": "PAIRED_EXACT_SIGN_TEST_ON_OOS_NET_R_VS_BASELINE_PLUS_HOLM_PER_FAMILY",
            "multiple_testing_family_sizes": {k: len(v) for k, v in families.items()}, "results": results,
            "safety": {"execution_enabled": False, "orders_placed": False,
                       "policy_mutation_enabled": False, "production_approved": False,
                       "risk_gate_bypass": False}}
