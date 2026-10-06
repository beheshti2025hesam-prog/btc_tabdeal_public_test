import unittest

from core.learning.self_improvement import (
    OutcomeRecord,
    PromotionCheck,
    SelfImprovementEngine,
)


class SelfImprovementTests(unittest.TestCase):
    def test_repeated_loss_pattern_becomes_proposal_not_mutation(self):
        records = [
            OutcomeRecord(
                outcome="loss",
                direction="long",
                regime="trend",
                failure_codes=("LIQUIDITY_FALSE_BREAK",),
                fold=i,
            )
            for i in range(5)
        ]
        engine = SelfImprovementEngine(min_support=5)
        proposals = engine.propose(records)

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].pattern, "failure:LIQUIDITY_FALSE_BREAK")
        self.assertFalse(proposals[0].auto_promote)

    def test_no_loss_pattern_is_not_flagged(self):
        records = [
            OutcomeRecord(
                outcome="win",
                direction="long",
                regime="trend",
                failure_codes=("LIQUIDITY_FALSE_BREAK",),
            )
            for _ in range(5)
        ]
        self.assertEqual(SelfImprovementEngine(min_support=5).propose(records), ())

    def test_promotion_requires_independent_oos_and_approval(self):
        base = dict(
            candidate_id="candidate-1",
            oos_evaluated=True,
            oos_independent=True,
            oos_improves_quality=True,
            no_material_risk_regression=True,
        )
        self.assertFalse(SelfImprovementEngine.can_promote(PromotionCheck(**base)))
        self.assertTrue(
            SelfImprovementEngine.can_promote(
                PromotionCheck(**base, approved=True)
            )
        )

    def test_summary(self):
        records = [
            OutcomeRecord("win", "long", "trend"),
            OutcomeRecord("loss", "short", "range"),
            OutcomeRecord("no_trade", None, "range"),
        ]
        self.assertEqual(
            SelfImprovementEngine.summarize(records),
            {"wins": 1, "losses": 1, "no_trade": 1, "total": 3},
        )


if __name__ == "__main__":
    unittest.main()
