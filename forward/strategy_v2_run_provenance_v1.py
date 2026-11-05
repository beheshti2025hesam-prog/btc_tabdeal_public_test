"""Immutable per-process Strategy V2 run identity and source attestation."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Mapping
from forward.forward_journal_v1 import ForwardJournalV1

SOURCE_PATHS = {
 "strategy_source_sha256":"forward/strategy_policy_v2.py",
 "evaluator_source_sha256":"scripts/run_strategy_policy_v2_forward_eval.py",
 "gate_pipeline_source_sha256":"forward/strategy_gate_pipeline_v1.py",
 "entry_context_source_sha256":"forward/strategy_entry_context_v1.py",
 "precision_engine_source_sha256":"forward/precision_entry_engine_v1.py",
 "precision_journal_source_sha256":"scripts/run_precision_entry_journal_v1.py",
 "learning_loop_source_sha256":"scripts/run_strategy_learning_loop_v1.py",
 "market_data_reader_source_sha256":"forward/global_market_data_reader_v1.py",
 "acceptance_evaluator_source_sha256":"forward/signal_quality_acceptance_v1.py",
 "provenance_module_sha256":"forward/strategy_v2_run_provenance_v1.py",
}

def sha256_file(path: Path) -> str:
 digest=hashlib.sha256()
 with Path(path).open("rb") as handle:
  for chunk in iter(lambda:handle.read(1024*1024),b""): digest.update(chunk)
 return digest.hexdigest()

def canonical_sha256(value: Mapping[str, object]) -> str:
 payload={key:item for key,item in dict(value).items() if key!="run_manifest_sha256"}
 raw=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()
 return hashlib.sha256(raw).hexdigest()

def create_run_manifest(*,root:Path,service_name:str,policy_version:str,run_id:str)->dict:
 root=Path(root)
 if not isinstance(run_id,str) or not run_id.startswith("HESV2-") or len(run_id)<12: raise ValueError("invalid Strategy V2 run_id")
 if not isinstance(service_name,str) or not service_name.strip(): raise ValueError("invalid service_name")
 hashes={key:sha256_file(root/relative) for key,relative in SOURCE_PATHS.items()}
 payload={"schema":"hes_strategy_v2_run_manifest_v1","event_id":run_id,"run_id":run_id,
  "service_name":service_name,"policy_version":policy_version,"code_release_id":root.name,
  "source_hashes":hashes,**hashes,"execution_enabled":False,"orders_placed":False}
 payload["run_manifest_sha256"]=canonical_sha256(payload)
 return payload

def validate_run_manifest(manifest:Mapping[str,object])->bool:
 if not isinstance(manifest,Mapping) or manifest.get("schema")!="hes_strategy_v2_run_manifest_v1" or manifest.get("event_id")!=manifest.get("run_id"): return False
 hashes=manifest.get("source_hashes")
 if not isinstance(hashes,dict) or set(hashes)!=set(SOURCE_PATHS): return False
 if any(not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value) for value in hashes.values()): return False
 if any(manifest.get(key)!=value for key,value in hashes.items()): return False
 if manifest.get("execution_enabled") is not False or manifest.get("orders_placed") is not False: return False
 digest=manifest.get("run_manifest_sha256")
 if not isinstance(digest,str) or len(digest)!=64: return False
 try: return canonical_sha256(manifest)==digest
 except (TypeError,ValueError): return False

def append_run_manifest(path:Path,manifest:Mapping[str,object])->None:
 if not validate_run_manifest(manifest): raise ValueError("invalid Strategy V2 run manifest digest")
 if not ForwardJournalV1(path).append_event(dict(manifest)): raise ValueError("duplicate Strategy V2 run_id")
