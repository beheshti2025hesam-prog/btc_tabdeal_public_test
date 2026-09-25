import unittest

from core.identity import APP_NAME, OWNER_NAME, validate_identity


class TestCanonicalApplicationIdentity(unittest.TestCase):
    def test_canonical_application_identity(self):
        self.assertEqual(APP_NAME, "HES Trade Agent")
        self.assertEqual(OWNER_NAME, "Seyed Hesameddin Beheshti Shirazi")

    def test_identity_integrity(self):
        validate_identity()


if __name__ == "__main__":
    unittest.main()
