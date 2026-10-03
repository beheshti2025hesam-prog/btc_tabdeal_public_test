"""Immutable promotion evidence snapshot contract."""
from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True)
class EvidenceSnapshot:
    project_name: str
    owner: str
    source_commit: str
    evidence: tuple[tuple[str, bool], ...]
    digest: str

    @classmethod
    def create(cls, project_name: str, owner: str, source_commit: str, evidence: dict[str, bool]):
        normalized = tuple(sorted((str(k), bool(v)) for k, v in evidence.items()))
        payload = json.dumps(
            {"project_name": project_name, "owner": owner, "source_commit": source_commit, "evidence": normalized},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        digest = hashlib.sha256(payload).hexdigest()
        return cls(project_name, owner, source_commit, normalized, digest)

    def verify(self) -> bool:
        if not self.project_name.strip() or not self.owner.strip() or not self.source_commit.strip():
            return False
        if not self.evidence or any(not key.strip() or not isinstance(value, bool) for key, value in self.evidence):
            return False
        if len(self.digest) != 64:
            return False
        try:
            int(self.digest, 16)
        except ValueError:
            return False

        payload = json.dumps(
            {
                "project_name": self.project_name,
                "owner": self.owner,
                "source_commit": self.source_commit,
                "evidence": self.evidence,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest() == self.digest
