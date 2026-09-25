"""Tests for the execution-free order state machine."""

import unittest

from core.execution.order_state import (
    OrderEvent,
    OrderState,
    OrderStateMachine,
)


class OrderStateMachineTests(unittest.TestCase):
    def test_new_order_requires_submission(self):
        machine = OrderStateMachine()

        self.assertEqual(
            machine.transition(OrderEvent.SUBMIT).state,
            OrderState.SUBMITTED,
        )

    def test_normal_fill_lifecycle(self):
        machine = OrderStateMachine()
        machine = machine.transition(OrderEvent.SUBMIT)
        machine = machine.transition(OrderEvent.ACCEPT)
        machine = machine.transition(OrderEvent.PARTIAL_FILL)
        machine = machine.transition(OrderEvent.FILL)

        self.assertEqual(machine.state, OrderState.FILLED)

    def test_cancel_lifecycle(self):
        machine = OrderStateMachine()
        machine = machine.transition(OrderEvent.SUBMIT)
        machine = machine.transition(OrderEvent.ACCEPT)
        machine = machine.transition(OrderEvent.REQUEST_CANCEL)
        machine = machine.transition(OrderEvent.CANCEL)

        self.assertEqual(machine.state, OrderState.CANCELED)

    def test_invalid_transition_is_rejected(self):
        machine = OrderStateMachine()

        with self.assertRaises(ValueError):
            machine.transition(OrderEvent.FILL)

    def test_terminal_states_cannot_transition(self):
        machine = OrderStateMachine(state=OrderState.FILLED)

        with self.assertRaises(ValueError):
            machine.transition(OrderEvent.CANCEL)

    def test_state_machine_is_immutable(self):
        machine = OrderStateMachine()
        next_machine = machine.transition(OrderEvent.SUBMIT)

        self.assertEqual(machine.state, OrderState.NEW)
        self.assertEqual(next_machine.state, OrderState.SUBMITTED)


if __name__ == "__main__":
    unittest.main()
