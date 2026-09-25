"""Tests for the operational safety evidence contract."""

import unittest

from core.evaluation.operational_safety import OperationalSafetyEvidence


class OperationalSafetyEvidenceTests(unittest.TestCase):
    def valid(self):
        return OperationalSafetyEvidence(
            execution_disabled=True,
            venue_connection_disabled=True,
            capital_mutation_disabled=True,
            leverage_controlled=True,
            risk_veto_enforced=True,
            raw_data_immutable=True,
            audit_trail_available=True,
        )

    def test_all_required_controls_must_be_present(self):
        self.assertTrue(self.valid().verify())

    def test_any_missing_control_invalidates_evidence(self):
        evidence = self.valid()
        invalid = OperationalSafetyEvidence(
            evidence.execution_disabled,
            evidence.venue_connection_disabled,
            evidence.capital_mutation_disabled,
            evidence.leverage_controlled,
            False,
            evidence.raw_data_immutable,
            evidence.audit_trail_available,
        )
        self.assertFalse(invalid.verify())


if __name__ == "__main__":
    unittest.main()
