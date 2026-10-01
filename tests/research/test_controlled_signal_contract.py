from pathlib import Path

SPEC = Path("docs/research/controlled_signal_research_v1.md").read_text()

def test_controlled_signal_research_contract_is_frozen():
    required = [
        "1,049 observations",
        "No threshold search.",
        "No period search.",
        "No model fitting.",
        "No ranking, scoring, or optimization.",
        "Feature values must be timestamped at or before the eligible observation boundary.",
    ]
    for phrase in required:
        assert phrase in SPEC

def test_candidate_definition_is_deterministic():
    assert "close > EMA20 AND momentum10 > 0 AND close > VWAP" in SPEC
    assert "close < EMA20 AND momentum10 < 0 AND close < VWAP" in SPEC
    assert "Equality or missing inputs are candidate-negative/invalid" in SPEC

def test_research_is_not_execution_or_promotion():
    assert "does not create a production signal" in SPEC
    assert "promotion decision" in SPEC
