"""Deterministic specialist-agent registry."""
from dataclasses import dataclass
from typing import Callable

from core.agents.contract import AgentContext, AgentResult, AgentRole


AgentCallable = Callable[[AgentContext], AgentResult]


@dataclass(frozen=True)
class AgentDefinition:
    role: AgentRole
    handler: AgentCallable
    enabled: bool = True


class AgentRegistry:
    def __init__(self, definitions: tuple[AgentDefinition, ...] = ()) -> None:
        self._definitions: dict[AgentRole, AgentDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: AgentDefinition) -> None:
        if definition.role in self._definitions:
            raise ValueError(f"agent already registered: {definition.role.value}")
        self._definitions[definition.role] = definition

    def get(self, role: AgentRole) -> AgentDefinition:
        return self._definitions[role]

    def enabled_roles(self) -> tuple[AgentRole, ...]:
        return tuple(role for role, definition in self._definitions.items() if definition.enabled)

    def run(self, role: AgentRole, context: AgentContext) -> AgentResult:
        definition = self.get(role)
        if not definition.enabled:
            return AgentResult(role, False, {}, ("agent_disabled",))
        result = definition.handler(context)
        if result.role != role:
            raise ValueError("agent result role mismatch")
        return result
