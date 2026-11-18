import json
import pytest
from forward.blackbox_experience_memory_v1 import (
    append_experience_events, append_hypothesis_events, build_experience_event,
    build_hypothesis_event, build_hypothesis_transition_event, collect_canonical_experiences,
    evaluate_hypothesis_tournament, holm_adjust, validate_hypothesis_transition,
    discover_hypotheses_from_feature_snapshots,
)

SHA = "a" * 64

def experience(**overrides):
    args = dict(source_ref="data/forward/trade_journal_v2.jsonl", source_sha256=SHA,
        source_event_id="decision-123", experience_type="TRADE_OUTCOME",
        observed_at="2026-11-18T10:00:00Z", venue="gateio", market="spot",
        symbol="BTC_USDT", timeframe="15m", regime="BULLISH", family_id="trend_breakout",
        direction="LONG", gate_decision="LONG", outcome_class="WIN", matured=True,
        provenance_complete=True, costs_verified=True, net_r=2.1)
    args.update(overrides)
    return build_experience_event(**args)

def evidence(**overrides):
    train_values=[.18]*120
    baseline_values=[.01]*120
    oos_values=[.21]*90+[-.08]*30
    row = dict(hypothesis_id="HYP-1", train_n=120, train_wins=78, oos_n=120, oos_wins=90,
        baseline_oos_win_rate=.5, train_mean_net_r=.18, oos_mean_net_r=sum(oos_values)/120,
        baseline_oos_mean_net_r=sum(baseline_values)/120, train_net_r_values=train_values,
        oos_net_r_values=oos_values, baseline_oos_net_r_values=baseline_values,
        oos_regime_count=3, costs_verified=True,
        independent_oos=True, chronological_purged=True, unmatched=0, unscorable=0,
        provenance_complete=True, direction="LONG", preregistered=True,
        hypothesis_status="TESTING", preregistration_sha256=SHA,
        source_manifest_sha256=SHA, multiple_testing_family="test-family-v1")
    row.update(overrides)
    return row

def test_four_regime_memory_is_explicit_and_training_requires_verified_trade_label():
    for regime in ("BULLISH", "BEARISH", "RANGE", "NO_TRADE"):
        assert experience(regime=regime)["regime"] == regime
    assert experience()["training_eligible"] is True
    assert experience(costs_verified=False)["training_eligible"] is False
    assert experience(provenance_complete=False)["training_eligible"] is False
    assert experience(gate_decision="NO_TRADE")["training_eligible"] is False

def test_no_trade_counterfactual_is_never_trade_training_label():
    row = experience(experience_type="NO_TRADE_COUNTERFACTUAL", gate_decision="NO_TRADE",
                     counterfactual=True, outcome_class="MISSED_PROFIT")
    assert row["training_eligible"] is False
    assert row["counterfactual"] is True

def test_experience_append_is_idempotent_and_detects_conflicting_identity(tmp_path):
    path = tmp_path / "experience.jsonl"
    row = experience()
    assert append_experience_events(path, [row]) == {"appended": 1, "exact_replays": 0}
    assert append_experience_events(path, [row]) == {"appended": 0, "exact_replays": 1}
    altered = dict(row, net_r=99.0)
    with pytest.raises(ValueError, match="CONTENT_CONFLICT"):
        append_experience_events(path, [altered])
    assert len(path.read_text().splitlines()) == 1

def test_hypothesis_requires_preregistration_and_transition_evidence(tmp_path):
    h = build_hypothesis_event(hypothesis_id="HYP-1", family_id="range_reversion",
        statement="Range sweeps revert under condition X", discovery_window={"start":"2026-01-01","end":"2026-02-01"},
        source_hashes={"candles":SHA}, feature_definition={"sweep": "frozen-v1"},
        null_hypothesis="no net expectancy lift", alternative_hypothesis="positive net expectancy lift",
        primary_metric="oos_mean_net_r", falsification_rule="oos net expectancy <= baseline",
        multiple_testing_family="range-family-v1")
    assert h["status"] == "DISCOVERED"
    with pytest.raises(ValueError, match="FINAL_HYPOTHESIS_TRANSITION"):
        build_hypothesis_transition_event(hypothesis_id="HYP-1", previous_status="TESTING", next_status="ACCEPTED")
    prereg = build_hypothesis_transition_event(hypothesis_id="HYP-1", previous_status="DISCOVERED", next_status="PREREGISTERED")
    testing = build_hypothesis_transition_event(hypothesis_id="HYP-1", previous_status="PREREGISTERED", next_status="TESTING")
    transition = build_hypothesis_transition_event(hypothesis_id="HYP-1", previous_status="TESTING",
        next_status="ACCEPTED", evidence_sha256=SHA, rationale="Independent OOS criteria passed")
    path=tmp_path/"hypotheses.jsonl"
    sequence=[h,prereg,testing,transition]
    assert append_hypothesis_events(path,sequence)["appended"] == 4
    assert append_hypothesis_events(path,sequence)["exact_replays"] == 4
    with pytest.raises(ValueError, match="TRANSITION_INVALID"):
        validate_hypothesis_transition("DISCOVERED", "ACCEPTED", evidence_sha256=SHA)

def test_tournament_accepts_only_strong_independent_oos_after_holm():
    result = evaluate_hypothesis_tournament([evidence()])
    assert result["results"][0]["status"] == "ACCEPTED"
    assert result["results"][0]["holm_adjusted_p_value"] < .05
    assert result["safety"]["production_approved"] is False

def test_tournament_is_inconclusive_when_any_integrity_or_economic_gate_fails():
    for row, blocker in [
        (evidence(costs_verified=False), "EXECUTION_COSTS_UNVERIFIED"),
        (evidence(oos_regime_count=1), "INSUFFICIENT_REGIME_DIVERSITY"),
        (evidence(independent_oos=False), "OOS_NOT_INDEPENDENT"),
        (evidence(unmatched=1), "OUTCOME_LINKAGE_OR_SCORING_NOT_CLEAN"),
        (evidence(oos_net_r_values=[-.01]*120, oos_mean_net_r=-.01), "NON_POSITIVE_OOS_NET_EXPECTANCY"),
        (evidence(direction="SHORT", short_economics_validated=False), "SHORT_ECONOMICS_NOT_VALIDATED"),
        (evidence(oos_net_r_values=[.02]*65+[-.01]*55,
                  oos_mean_net_r=(65*.02-55*.01)/120), "MULTIPLE_TEST_ADJUSTED_SIGNIFICANCE_NOT_MET"),
    ]:
        result=evaluate_hypothesis_tournament([row])
        if blocker == "NON_POSITIVE_OOS_NET_EXPECTANCY":
            assert result["results"][0]["status"] == "REJECTED"
            assert result["results"][0]["holm_adjusted_p_value"] < .05
        else:
            assert result["results"][0]["status"] == "INCONCLUSIVE"
            assert blocker in result["results"][0]["blockers"]

def test_holm_controls_family_wide_error_and_is_monotone():
    got=holm_adjust({"a":.001,"b":.01,"c":.04})
    assert got["a"] == pytest.approx(.003)
    assert got["b"] == pytest.approx(.02)
    assert got["c"] == pytest.approx(.04)

def test_small_sample_never_accepts_even_if_observed_rate_is_perfect():
    row=evidence(train_n=10,train_wins=10,oos_n=20,oos_wins=20,
        train_net_r_values=[.18]*10, oos_net_r_values=[.21]*20,
        baseline_oos_net_r_values=[.01]*20, oos_mean_net_r=.21)
    result=evaluate_hypothesis_tournament([row])
    assert result["results"][0]["status"] == "INCONCLUSIVE"
    assert "INSUFFICIENT_TRAIN_SAMPLE" in result["results"][0]["blockers"]
    assert "INSUFFICIENT_INDEPENDENT_OOS_SAMPLE" in result["results"][0]["blockers"]


def test_canonical_indexer_references_sources_without_copying_payloads(tmp_path):
    from pathlib import Path
    base=tmp_path/"data"/"forward"; base.mkdir(parents=True)
    (base/"trade_journal_v2.jsonl").write_text(json.dumps({"event_id":"d1","observed_at":"2026-11-18T10:00:00Z",
        "decision":"NO_TRADE","proposal_direction":"LONG","symbol":"BTC_USDT","timeframe":"15m",
        "market_regime":"RANGE","policy_version":"p1"})+"\n")
    (base/"neutral_decision_outcomes_v1.jsonl").write_text(json.dumps({"outcome_id":"n1","observed_at":"2026-11-18T10:00:00Z",
        "decision":"NO_TRADE","horizon_complete":True,"outcome_class":"DIRECTIONLESS_MARKET_CONTEXT",
        "symbol":"BTC_USDT","timeframe":"15m"})+"\n")
    events, counts=collect_canonical_experiences(tmp_path)
    assert counts["trade_journal_v2.jsonl"] == 1
    assert counts["neutral_decision_outcomes_v1.jsonl"] == 1
    assert len(events) == 2
    assert {e["regime"] for e in events} == {"RANGE","NO_TRADE"}
    assert all("source_ref" in e and "source_sha256" in e for e in events)
    assert all(e["training_eligible"] is False for e in events)


def test_tournament_rejects_a_preregistered_hypothesis_with_significant_oos_underperformance():
    baseline=[.02]*120
    oos=[-.13]*90+[.03]*30
    train=[-.03]*120
    row=evidence(oos_wins=30, oos_mean_net_r=sum(oos)/120,
                 baseline_oos_mean_net_r=.02, train_mean_net_r=-.03,
                 oos_net_r_values=oos, baseline_oos_net_r_values=baseline,
                 train_net_r_values=train)
    result=evaluate_hypothesis_tournament([row])
    assert result["results"][0]["status"] == "REJECTED"
    assert result["results"][0]["holm_adjusted_p_value"] < .05
    assert result["safety"]["policy_mutation_enabled"] is False


def test_hypothesis_ledger_rejects_invalid_transition_order(tmp_path):
    path=tmp_path/"hypotheses.jsonl"
    bad=build_hypothesis_transition_event(hypothesis_id="missing", previous_status="TESTING",
        next_status="ACCEPTED", evidence_sha256=SHA, rationale="proof")
    with pytest.raises(ValueError, match="PREVIOUS_STATE_MISMATCH"):
        append_hypothesis_events(path,[bad])

def test_unregistered_hypothesis_cannot_enter_statistical_tournament():
    row=evidence(preregistered=False)
    result=evaluate_hypothesis_tournament([row])
    assert result["results"][0]["status"] == "INCONCLUSIVE"
    assert "HYPOTHESIS_NOT_PREREGISTERED_FOR_TESTING" in result["results"][0]["blockers"]

def test_holm_adjustment_is_applied_within_the_declared_hypothesis_family():
    neutral=[.02]*60+[-.01]*60
    mean=sum(neutral)/120
    rows=[evidence(hypothesis_id="A",oos_net_r_values=neutral,oos_mean_net_r=mean),
          evidence(hypothesis_id="B",oos_net_r_values=neutral,oos_mean_net_r=mean)]
    result=evaluate_hypothesis_tournament(rows)
    assert result["multiple_testing_family_sizes"] == {"test-family-v1": 2}
    assert all(r["holm_adjusted_p_value"] >= r["raw_two_sided_p_value"] for r in result["results"])


def test_pattern_discovery_generates_frozen_research_only_hypotheses():
    rows=[]
    for i in range(160):
        regime=("BULLISH","BEARISH","RANGE","NO_TRADE")[i%4]
        rows.append({"observed_at":f"2026-11-01T00:{i%60:02d}:00+00:00", "market_regime":regime,
                     "feature_snapshot":{"rsi_14":float(i%100),"atr_pct":float((i*7)%50)}})
    found=discover_hypotheses_from_feature_snapshots(rows,source_hashes={"source":SHA},minimum_support=5)
    assert found
    assert {x["discovery_metadata"]["regime"] for x in found} == {"BULLISH", "BEARISH", "RANGE", "NO_TRADE"}
    assert all(x["status"]=="DISCOVERED" for x in found)
    assert all(x["discovery_metadata"]["research_only"] is True for x in found)
    assert all(x["discovery_metadata"]["outcomes_used_for_discovery"] is False for x in found)
    assert all(x["discovery_metadata"]["training_eligible"] is False for x in found)
    assert all(x["feature_definition"]["quantile_cutoffs_frozen_on_discovery_window"] for x in found)
