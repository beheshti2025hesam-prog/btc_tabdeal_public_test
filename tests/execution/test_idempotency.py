"""Tests for the execution idempotency safety contract."""

import unittest

from core.execution.idempotency import (
    IdempotencyKey,
    IdempotencyRegistry,
)


class IdempotencyContractTests(unittest.TestCase):
    def test_first_registration_is_stored(self):
        registry = IdempotencyRegistry()
        key = IdempotencyKey("req-1")

        record = registry.register(
            key,
            accepted=False,
            reason="execution_disabled",
        )

        self.assertTrue(registry.contains(key))
        self.assertEqual(registry.get(key), record)

    def test_duplicate_registration_returns_original_result(self):
        registry = IdempotencyRegistry()
        key = IdempotencyKey("req-2")

        first = registry.register(
            key,
            accepted=False,
            reason="execution_disabled",
        )
        second = registry.register(
            key,
            accepted=True,
            reason="should_not_replace",
        )

        self.assertEqual(second, first)
        self.assertFalse(second.accepted)
        self.assertEqual(second.reason, "execution_disabled")

    def test_distinct_request_ids_are_independent(self):
        registry = IdempotencyRegistry()
        first_key = IdempotencyKey("req-3")
        second_key = IdempotencyKey("req-4")

        first = registry.register(first_key, accepted=False, reason="disabled")
        second = registry.register(second_key, accepted=False, reason="disabled")

        self.assertNotEqual(first.key, second.key)
        self.assertEqual(registry.get(first_key), first)
        self.assertEqual(registry.get(second_key), second)


if __name__ == "__main__":
    unittest.main()
