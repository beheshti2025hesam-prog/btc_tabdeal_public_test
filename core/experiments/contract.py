"""Mother Agent - reproducible experiment contract v1.0.

Research metadata only. No secrets, credentials, exchange connectivity, or
execution state belong in an experiment identity.
"""
from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class ExperimentSpec:
    name: str
    version: str
    dataset_id: str
    strategy_id: str
    timeframe_seconds: int
    parameters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.version:
            raise ValueError("version must not be empty")
        if not self.dataset_id:
            raise ValueError("dataset_id must not be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if self.timeframe_seconds <= 0:
            raise ValueError("timeframe_seconds must be positive")
        keys = [key for key, _ in self.parameters]
        if any(not key for key in keys):
            raise ValueError("parameter names must not be empty")
        if len(keys) != len(set(keys)):
            raise ValueError("parameter names must be unique")

    @property
    def experiment_id(self) -> str:
        payload = {
            "name": self.name,
            "version": self.version,
            "dataset_id": self.dataset_id,
            "strategy_id": self.strategy_id,
            "timeframe_seconds": self.timeframe_seconds,
            "parameters": sorted(self.parameters),
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return sha256(canonical).hexdigest()
