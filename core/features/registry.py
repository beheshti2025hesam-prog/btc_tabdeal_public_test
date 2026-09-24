"""Mother Agent - feature registry v1.0.

Metadata only: registry does not calculate or trade.
"""
from dataclasses import dataclass
from typing import Callable, Mapping


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    version: str
    timeframe_seconds: int | None = None
    required: bool = False


class FeatureRegistry:
    def __init__(self, definitions: tuple[FeatureDefinition, ...] = ()):
        self._definitions: dict[str, FeatureDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: FeatureDefinition) -> None:
        if not definition.name:
            raise ValueError("feature name must not be empty")
        if not definition.version:
            raise ValueError("feature version must not be empty")
        if definition.timeframe_seconds is not None and definition.timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        if definition.name in self._definitions:
            raise ValueError(f"feature already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> FeatureDefinition:
        return self._definitions[name]

    def definitions(self) -> tuple[FeatureDefinition, ...]:
        return tuple(self._definitions.values())
