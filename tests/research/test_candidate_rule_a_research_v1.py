from scripts.candidate_rule_a_research_v1 import evaluate_rule_a


def test_rule_a_long():
    assert evaluate_rule_a(0.60, 10.0, 100.0) == "LONG"


def test_rule_a_short():
    assert evaluate_rule_a(0.40, -10.0, 100.0) == "SHORT"


def test_rule_a_neutral_is_no_trade():
    assert evaluate_rule_a(0.50, 10.0, 100.0) == "NO_TRADE"
    assert evaluate_rule_a(0.60, -10.0, 100.0) == "NO_TRADE"


def test_rule_a_invalid_is_no_trade():
    assert evaluate_rule_a(float("nan"), 1.0, 100.0) == "NO_TRADE"
    assert evaluate_rule_a(0.60, float("inf"), 100.0) == "NO_TRADE"


def test_trade_count_is_not_directional_threshold():
    assert evaluate_rule_a(0.60, 1.0, 1.0) == "LONG"
    assert evaluate_rule_a(0.60, 1.0, 1_000_000.0) == "LONG"
