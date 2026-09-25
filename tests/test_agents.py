import pytest

from core.agents.contract import AgentContext, AgentResult, AgentRole
from core.agents.registry import AgentDefinition, AgentRegistry


def test_registry_runs_enabled_agent():
    registry = AgentRegistry((
        AgentDefinition(
            AgentRole.DATA_QUALITY,
            lambda ctx: AgentResult(AgentRole.DATA_QUALITY, True, {"rows": 3}),
        ),
    ))
    result = registry.run(
        AgentRole.DATA_QUALITY,
        AgentContext("BTC_USDT", 900, "SIGNAL_ONLY", {"rows": 3}),
    )
    assert result.accepted is True
    assert result.outputs["rows"] == 3


def test_registry_blocks_disabled_agent():
    registry = AgentRegistry((
        AgentDefinition(
            AgentRole.EXECUTION,
            lambda ctx: AgentResult(AgentRole.EXECUTION, True, {}),
            enabled=False,
        ),
    ))
    result = registry.run(
        AgentRole.EXECUTION,
        AgentContext("BTC_USDT", 900, "SIGNAL_ONLY", {}),
    )
    assert result.accepted is False
    assert result.reasons == ("agent_disabled",)


def test_registry_rejects_duplicates_and_invalid_context():
    definition = AgentDefinition(
        AgentRole.RISK,
        lambda ctx: AgentResult(AgentRole.RISK, True, {}),
    )
    registry = AgentRegistry((definition,))
    with pytest.raises(ValueError):
        registry.register(definition)
    with pytest.raises(ValueError):
        AgentContext("", 900, "SIGNAL_ONLY", {})

