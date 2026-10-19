from pathlib import Path

SPEC = Path("docs/research/controlled_signal_research_v1.md").read_text()


def test_controlled_signal_research_contract_is_frozen():
    required = [
        "Evaluation population inherited from the fixed evidence protocol: 1,049 OOS observations.",
        "No threshold search.",
        "No period search.",
        "No model fitting.",
        "No ranking/scoring optimization.",
        "Candidate inputs must use information available at or before the candidate timestamp.",
    ]
    for phrase in required:
        assert phrase in SPEC


def test_candidate_definition_is_deterministic():
    assert "Buy Ratio" in SPEC
    assert "Delta (Buy-Sell Delta)" in SPEC
    assert "Trade Count" in SPEC
    assert "The candidate is a research input set, not a tuned numeric rule." in SPEC
    assert "No new numeric threshold is introduced here." in SPEC
    assert "EMA and VWAP: fold-sensitive and therefore excluded" in SPEC


def test_research_is_not_execution_or_promotion():
    assert "does not create a production Signal" in SPEC
    assert "promotion: OFF" in SPEC
    assert "live execution: OFF" in SPEC
    assert "data-engine-v1 integration: OFF" in SPEC
