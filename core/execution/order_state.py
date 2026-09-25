"""Execution-free order state machine for HES Trade Agent.

This module models lifecycle transitions only. It does not submit orders,
connect to venues, mutate capital, or enable live execution.
"""

from dataclasses import dataclass
from enum import Enum


class OrderState(str, Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class OrderEvent(str, Enum):
    SUBMIT = "SUBMIT"
    ACCEPT = "ACCEPT"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILL = "FILL"
    REQUEST_CANCEL = "REQUEST_CANCEL"
    CANCEL = "CANCEL"
    REJECT = "REJECT"


_ALLOWED_TRANSITIONS: dict[OrderState, dict[OrderEvent, OrderState]] = {
    OrderState.NEW: {
        OrderEvent.SUBMIT: OrderState.SUBMITTED,
        OrderEvent.REJECT: OrderState.REJECTED,
    },
    OrderState.SUBMITTED: {
        OrderEvent.ACCEPT: OrderState.ACCEPTED,
        OrderEvent.REJECT: OrderState.REJECTED,
    },
    OrderState.ACCEPTED: {
        OrderEvent.PARTIAL_FILL: OrderState.PARTIALLY_FILLED,
        OrderEvent.FILL: OrderState.FILLED,
        OrderEvent.REQUEST_CANCEL: OrderState.CANCEL_REQUESTED,
        OrderEvent.REJECT: OrderState.REJECTED,
    },
    OrderState.PARTIALLY_FILLED: {
        OrderEvent.PARTIAL_FILL: OrderState.PARTIALLY_FILLED,
        OrderEvent.FILL: OrderState.FILLED,
        OrderEvent.REQUEST_CANCEL: OrderState.CANCEL_REQUESTED,
    },
    OrderState.CANCEL_REQUESTED: {
        OrderEvent.CANCEL: OrderState.CANCELED,
        OrderEvent.PARTIAL_FILL: OrderState.PARTIALLY_FILLED,
        OrderEvent.FILL: OrderState.FILLED,
    },
    OrderState.FILLED: {},
    OrderState.CANCELED: {},
    OrderState.REJECTED: {},
}


@dataclass(frozen=True)
class OrderStateMachine:
    """Immutable lifecycle state with explicit, validated transitions."""

    state: OrderState = OrderState.NEW

    def transition(self, event: OrderEvent) -> "OrderStateMachine":
        """Return the next state or reject an invalid lifecycle transition."""
        next_state = _ALLOWED_TRANSITIONS.get(self.state, {}).get(event)
        if next_state is None:
            raise ValueError(
                f"invalid order transition: {self.state.value} + {event.value}"
            )
        return OrderStateMachine(state=next_state)
