import hashlib
import json
from pathlib import Path
import pytest
from forward import source_evidence_registry_v1 as m
from forward.source_evidence_registry_v1 import SourceEvidenceRegistryError, SourceEvidenceRegistryV1

def fixture(tmp_path: Path, status="REVIEWED_PINNED"):
    artifact=tmp_path/"reviewed-evidence.txt"
    artifact.write_text("synthetic evidence\n", encoding="utf-8")
    item={"evidence_ref":"test:ordering","evidence_type":"source_ordering",
          "source_scope":"tabdeal-futures:BTC_USDT","evidence_path":artifact.name,
          "evidence_sha256":hashlib.sha256(artifact.read_bytes()).hexdigest(),
          "review_status":"INDEPENDENTLY_REVIEWED","review_record_ref":"test-review:001"}
    raw=(json.dumps({"schema":"hes_source_evidence_registry_v1","status":status,
                     "registry_version":1,"entries":[item]},sort_keys=True,separators=(",",":"))+"\n").encode()
    path=tmp_path/"registry.json"; path.write_bytes(raw)
    m.PINNED_SOURCE_EVIDENCE_REGISTRY_SHA256=hashlib.sha256(raw).hexdigest()
    return path,artifact,item

def test_pin_unset_blocks_even_if_caller_has_a_reference():
    m.PINNED_SOURCE_EVIDENCE_REGISTRY_SHA256=""
    with pytest.raises(SourceEvidenceRegistryError,match="PIN_UNSET"):
        SourceEvidenceRegistryV1.load("unused.json")

def test_exact_pinned_registry_and_scope_required(tmp_path):
    path,_,item=fixture(tmp_path); registry=SourceEvidenceRegistryV1.load(path)
    assert registry.resolve(item["evidence_ref"],evidence_type="source_ordering",
                            source_scope="tabdeal-futures:BTC_USDT")["review_status"]=="INDEPENDENTLY_REVIEWED"
    with pytest.raises(SourceEvidenceRegistryError,match="SCOPE_MISMATCH"):
        registry.resolve(item["evidence_ref"],evidence_type="source_ordering",source_scope="other")
    with pytest.raises(SourceEvidenceRegistryError,match="TYPE_MISMATCH"):
        registry.resolve(item["evidence_ref"],evidence_type="source_completeness",
                         source_scope="tabdeal-futures:BTC_USDT")

def test_registry_byte_change_invalidates_pin(tmp_path):
    path,_,_=fixture(tmp_path); path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(SourceEvidenceRegistryError,match="PIN_MISMATCH"):
        SourceEvidenceRegistryV1.load(path)

def test_artifact_byte_change_invalidates_reviewed_evidence(tmp_path):
    path,artifact,item=fixture(tmp_path); registry=SourceEvidenceRegistryV1.load(path)
    artifact.write_text("changed\n",encoding="utf-8")
    with pytest.raises(SourceEvidenceRegistryError,match="ARTIFACT_DIGEST_MISMATCH"):
        registry.resolve(item["evidence_ref"],evidence_type="source_ordering",
                         source_scope="tabdeal-futures:BTC_USDT")

def test_unreviewed_empty_registry_cannot_authorize(tmp_path):
    path,_,_=fixture(tmp_path,status="UNPINNED_EMPTY")
    with pytest.raises(SourceEvidenceRegistryError,match="NOT_REVIEWED"):
        SourceEvidenceRegistryV1.load(path)

def test_duplicate_json_keys_rejected(tmp_path):
    raw=b'{"schema":"hes_source_evidence_registry_v1","schema":"bad","status":"REVIEWED_PINNED","entries":[]}'
    path=tmp_path/"registry.json"; path.write_bytes(raw)
    m.PINNED_SOURCE_EVIDENCE_REGISTRY_SHA256=hashlib.sha256(raw).hexdigest()
    with pytest.raises(SourceEvidenceRegistryError,match="DUPLICATE_JSON_KEY"):
        SourceEvidenceRegistryV1.load(path)
