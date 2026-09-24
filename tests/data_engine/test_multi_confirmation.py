from core.data_engine.feature_engine import FeatureSnapshot
from core.strategy.baseline import Decision
from core.strategy.multi_confirmation import MultiConfirmationEngine


def snapshot():
    return FeatureSnapshot("BTC_USDT", 900, 100, 99, 98, 1, 0.6, 0.01, 1, 1.2, False, "uptrend")


def test_required_confirmation_count_is_deterministic():
    engine = MultiConfirmationEngine(
        checks=(
            ("trend", lambda s, d: s.close > s.ema),
            ("pressure", lambda s, d: s.buy_ratio > 0.5),
            ("volume", lambda s, d: s.volume_ratio > 1),
        ),
        required_count=2,
    )
    result = engine.evaluate(snapshot(), Decision.LONG)
    assert result.confirmed
    assert result.passed_count == 3


def test_insufficient_confirmations_reject():
    engine = MultiConfirmationEngine(
        checks=(
            ("trend", lambda s, d: s.close < s.ema),
            ("pressure", lambda s, d: s.buy_ratio < 0.5),
            ("volume", lambda s, d: False),
        ),
        required_count=2,
    )
    result = engine.evaluate(snapshot(), Decision.LONG)
    assert not result.confirmed
    assert result.passed_count == 0
