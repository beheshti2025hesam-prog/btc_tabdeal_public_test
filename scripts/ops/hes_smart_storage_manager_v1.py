#!/usr/bin/env python3
"""Read-only HES storage planner. Never deletes, moves, compresses or prunes data."""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json, os
from pathlib import Path
import shutil, subprocess
from typing import Any

ROOT = Path("/opt/hes-trade-agent")
BACKUP_ROOT = Path("/var/backups/hes-trade-agent")
SCOPES = {
    "releases": ROOT / "releases", "candidates": ROOT / "candidates",
    "worktrees": ROOT / ".worktrees", "forward_data": ROOT / "data/forward",
    "evidence": ROOT / "evidence",
    "local_backups": BACKUP_ROOT / "encrypted-local",
    "offsite_staging": BACKUP_ROOT / "offsite-staging",
    "browser_cache": Path("/home/hes-remote/.cache/ms-playwright"),
    "npm_npx_cache": Path("/home/hes-remote/.npm/_npx"),
    "system_journal": Path("/var/log/journal"),
}
PROTECTED = {"releases", "forward_data", "evidence", "local_backups", "offsite_staging"}
REBUILDABLE_REVIEW = {"browser_cache", "npm_npx_cache"}

def allocated_size(path: Path) -> dict[str, int]:
    """Measure allocated bytes without following symlinks or crossing mounts."""
    try: root_stat = path.lstat()
    except OSError: return {"allocated_bytes":0,"logical_bytes":0,"files":0,"directories":0,"symlinks":0,"errors":1}
    if not path.is_dir() or path.is_symlink():
        return {"allocated_bytes":root_stat.st_blocks*512,"logical_bytes":root_stat.st_size,
                "files":int(path.is_file()),"directories":0,"symlinks":int(path.is_symlink()),"errors":0}
    device=root_stat.st_dev
    total=logical=files=directories=symlinks=errors=0
    for current,dirs,names in os.walk(path,topdown=True,followlinks=False):
        kept=[]
        for name in dirs:
            p=Path(current)/name
            try:
                st=p.lstat()
                if st.st_dev!=device or p.is_symlink():
                    symlinks+=int(p.is_symlink()); continue
                total+=st.st_blocks*512; logical+=st.st_size; directories+=1; kept.append(name)
            except OSError: errors+=1
        dirs[:]=kept
        for name in names:
            p=Path(current)/name
            try:
                st=p.lstat()
                if st.st_dev!=device: continue
                if p.is_symlink(): symlinks+=1; continue
                total+=st.st_blocks*512; logical+=st.st_size; files+=1
            except OSError: errors+=1
    return {"allocated_bytes":total,"logical_bytes":logical,"files":files,"directories":directories,"symlinks":symlinks,"errors":errors}

def disk_state(path: Path=Path("/")) -> dict[str,Any]:
    try:
        st=os.statvfs(path); total=st.f_blocks*st.f_frsize; free=st.f_bavail*st.f_frsize
        it=st.f_files; inf=st.f_favail
        return {"path":str(path),"total_bytes":total,"free_bytes":free,"used_bytes":total-free,
                "free_percent":round(100*free/total,2) if total else None,
                "inode_total":it,"inode_free":inf,"inode_free_percent":round(100*inf/it,2) if it else None,
                "pressure":"CRITICAL" if total and free/total<.10 else "WARN" if total and free/total<.15 else "OK"}
    except OSError as exc: return {"path":str(path),"pressure":"UNKNOWN","error":type(exc).__name__}

def archive_inventory(folder:Path,prefix:str)->dict[str,Any]:
    rows=[]; by_day:dict[str,list[dict[str,Any]]]=defaultdict(list)
    for p in sorted(folder.glob(prefix+"*")):
        if not p.is_file() or p.name.endswith((".sha256",".manifest.txt")): continue
        try: size=p.stat().st_size
        except OSError: continue
        row={"name":p.name,"size_bytes":size,"format":"zstd" if ".tar.zst." in p.name else "gzip"}
        rows.append(row); stamp=p.name[len(prefix):]; day=stamp[:8] if len(stamp)>=8 and stamp[:8].isdigit() else "unknown"
        by_day[day].append(row)
    return {"archive_count":len(rows),"total_bytes":sum(x["size_bytes"] for x in rows),"archives":rows,
            "same_day_multiple":{d:v for d,v in by_day.items() if d!="unknown" and len(v)>1}}

def compression_advice(evidence:dict[str,Any]|None)->dict[str,Any]:
    if not isinstance(evidence,dict): return {"status":"NO_BENCHMARK","recommendation":"KEEP_CURRENT_FORMAT_UNTIL_BENCHMARKED"}
    try:
        raw=int(evidence["source_bytes"]); gz=int(evidence["gzip1_bytes"])
        z3=int(evidence["zstd3_bytes"]); z9=int(evidence["zstd9_bytes"])
        if min(raw,gz,z3,z9)<=0 or max(gz,z3,z9)>=raw: raise ValueError
    except (KeyError,TypeError,ValueError): return {"status":"INVALID_EVIDENCE","recommendation":"KEEP_CURRENT_FORMAT"}
    saving=round(100*(gz-z9)/gz,2)
    return {"status":"SAMPLE_BENCHMARK_ONLY","sample_bytes":raw,"gzip1_bytes":gz,
            "zstd3_bytes":z3,"zstd9_bytes":z9,"zstd9_vs_gzip1_saving_percent":saving,
            "recommendation":"PROTOTYPE_ZSTD9_NEW_ARCHIVES_ONLY" if saving>=5 else "KEEP_GZIP1",
            "legacy_gzip_restore_required":True,"production_format_changed":False}

def build_report(*,now:datetime|None=None,scopes:dict[str,Path]|None=None,
                 evidence:dict[str,Any]|None=None,disk:dict[str,Any]|None=None)->dict[str,Any]:
    now=now or datetime.now(timezone.utc); scopes=scopes or SCOPES; inventory={}
    for name,path in scopes.items():
        stats=allocated_size(path)
        policy="UNKNOWN_KEEP" if stats["errors"] else "PROTECTED_KEEP" if name in PROTECTED else "REGENERABLE_REVIEW_ONLY" if name in REBUILDABLE_REVIEW else "OBSERVE_ONLY"
        inventory[name]={"path":str(path),**stats,"policy":policy,"action":"NONE"}
    local=archive_inventory(BACKUP_ROOT/"encrypted-local","hes-full-")
    offsite=archive_inventory(BACKUP_ROOT/"offsite-staging","hes-offsite-core-")
    capacity=disk or disk_state(); quota={"status":"NOT_CHECKED"}
    if shutil.which("rclone"):
        try:
            p=subprocess.run(["rclone","about","hesdropbox:","--json"],capture_output=True,text=True,timeout=30,check=False)
            if p.returncode==0:
                q=json.loads(p.stdout); total,used,free=(int(q.get(k,0)) for k in ("total","used","free"))
                quota={"status":"READ_OK","total_bytes":total,"used_bytes":used,"free_bytes":free,
                       "used_percent":round(100*used/total,2) if total else None}
            else: quota={"status":"UNAVAILABLE"}
        except (OSError,subprocess.TimeoutExpired,ValueError,TypeError): quota={"status":"UNAVAILABLE"}
    protected_bytes=sum(v["allocated_bytes"] for k,v in inventory.items() if k in PROTECTED)
    review_bytes=sum(v["allocated_bytes"] for k,v in inventory.items() if k in REBUILDABLE_REVIEW)
    return {"schema":"hes_smart_storage_manager_v1","generated_at":now.isoformat(),
        "mode":"READ_ONLY_CAPACITY_AND_COMPRESSION_PLAN","disk":capacity,"inventory":inventory,
        "summary":{"protected_bytes":protected_bytes,"rebuildable_review_only_bytes":review_bytes,
                   "local_backup":local,"offsite_staging":offsite,"dropbox_quota":quota},
        "compression":compression_advice(evidence),
        "policy":{"max_daily_signals":3,"canonical_market_data":"Gate.io Public Spot BTC_USDT",
          "backup_destination":"encrypted Dropbox","backup_retention":"existing policy unchanged pending restore proof",
          "unknown_or_unverified":"KEEP","deletion_authorized":False,"move_authorized":False,
          "compression_authorized":False,"automatic_cleanup_timer_authorized":False},
        "invariants":["No file is deleted, moved, truncated, rotated, pruned or compressed by this report.",
          "Active/rollback releases, market data, journals, evidence and all backup archives are protected.",
          "Caches are review-only until service, process, user and rebuild dependencies are independently verified.",
          "New compression format must be versioned; legacy gzip archives remain readable and retained.",
          "Dropbox free quota is a hard budget; never upload an unbounded second copy or exceed the free tier."]}

def main()->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True); parser.add_argument("--compression-evidence",type=Path)
    args=parser.parse_args()
    evidence=json.loads(args.compression_evidence.read_text()) if args.compression_evidence else None
    report=build_report(evidence=evidence); args.output.parent.mkdir(parents=True,exist_ok=True)
    tmp=args.output.with_suffix(args.output.suffix+".partial")
    tmp.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    os.replace(tmp,args.output)
    print(f"SMART_STORAGE_PLAN_OK scopes={len(report['inventory'])} deletion_authorized=false compression_authorized=false")
    return 0
if __name__=="__main__": raise SystemExit(main())