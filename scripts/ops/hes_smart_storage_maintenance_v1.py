#!/usr/bin/env python3
"""HES IDLM -> dependency-aware cleanup audit -> 5 GB storage plan + safe cache maintenance.
Only stale /tmp pip build artifacts are eligible for automatic removal. Unknown/project data stays KEEP.
"""
from __future__ import annotations
import datetime as dt, json, os, pathlib, shutil, subprocess, sys, time
LIB=pathlib.Path('/usr/local/lib/hes-storage-v1')
EVID=pathlib.Path('/srv/hes-evidence/operations/storage-lifecycle')
TMP=pathlib.Path('/tmp')

def run(cmd, *, check=True, timeout=900):
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f"command failed rc={p.returncode}: {cmd[0]}: {p.stderr[-1200:]}")
    return p

def pip_temp_cleanup(out: pathlib.Path):
    now=time.time(); cutoff=now-86400; removed=[]; kept=[]
    # Refuse the cache cleanup if a package build/install process is active.
    proc=run(['pgrep','-af',r'(^|/)(pip|pip3)( |$)|pip\._internal|build_wheel|setup\.py'],check=False)
    active=[x for x in proc.stdout.splitlines() if 'hes-smart-storage-maintenance' not in x]
    if active:
        return {'status':'SKIPPED_ACTIVE_BUILD','active_processes':active[:20],'removed':[],'freed_bytes':0}
    for p in sorted(TMP.iterdir()):
        try:
            if not p.name.startswith('pip-') or not p.is_dir() or p.is_symlink(): continue
            st=p.lstat()
            if st.st_mtime>=cutoff: continue
            if st.st_dev != TMP.stat().st_dev: continue
            opened=run(['lsof','+D',str(p)],check=False,timeout=30)
            if opened.stdout.strip():
                kept.append({'path':str(p),'reason':'open_file_handle'}); continue
            du=run(['du','-sxB1',str(p)],timeout=60)
            size=int(du.stdout.split()[0])
            # Revalidate exact direct-child path, type, age, and open handles immediately before removal.
            st2=p.lstat()
            if p.parent!=TMP or p.is_symlink() or not p.is_dir() or st2.st_mtime>=cutoff:
                kept.append({'path':str(p),'reason':'changed_during_audit'}); continue
            opened=run(['lsof','+D',str(p)],check=False,timeout=30)
            if opened.stdout.strip():
                kept.append({'path':str(p),'reason':'open_file_handle_on_recheck'}); continue
            shutil.rmtree(p)
            removed.append({'path':str(p),'bytes':size})
        except Exception as e:
            kept.append({'path':str(p),'reason':type(e).__name__})
    return {'status':'PASS','removed':removed,'kept':kept,'freed_bytes':sum(x['bytes'] for x in removed),'policy':'Only /tmp direct-child pip-* directories older than 24h; no active pip/build process and no open handles.'}

def main():
    now=dt.datetime.now(dt.timezone.utc)
    stamp=now.strftime('%Y-%m-%dT%H%M%SZ')
    out=EVID/(now.strftime('%Y-%m-%d')+'T'+now.strftime('%H%MZ'))
    out.mkdir(parents=True,exist_ok=True,mode=0o750)
    idlm=out/f'hes-idlm-audit-{stamp}.json'; cleanup=out/f'hes-smart-cleanup-{stamp}.json'; storage=out/f'hes-smart-storage-{stamp}.json'
    run([sys.executable,str(LIB/'hes_data_lifecycle_audit_v1.py'),'--stale-after-days','3','--output',str(idlm)])
    run([sys.executable,str(LIB/'hes_smart_cleanup_manager_v1.py'),'--audit-manifest',str(idlm),'--output',str(cleanup)])
    run([sys.executable,str(LIB/'hes_smart_storage_manager_v1.py'),'--idlm-report',str(idlm),'--cleanup-report',str(cleanup),'--output',str(storage),'--target-gb','5'])
    # Cache cleanup is deliberately separate from project/release/backup cleanup.
    cache=pip_temp_cleanup(out)
    # Package download cache is always reproducible; no package database or installed package is removed.
    apt=run(['apt-get','clean'],check=False,timeout=300)
    # Journal retention is capped by the separately configured journald policy.
    journal=run(['journalctl','--vacuum-time=30d','--vacuum-size=256M'],check=False,timeout=120)
    result={'schema':'hes_storage_maintenance_result_v1','generated_at':now.isoformat(),'reports':{'idlm':str(idlm),'smart_cleanup':str(cleanup),'storage':str(storage)},'pip_temp_cleanup':cache,'apt_cache_clean_returncode':apt.returncode,'journal_vacuum_returncode':journal.returncode,'policy':{'target_gb':5,'unknown_paths':'KEEP','release_worktree_data_evidence_backup_model_cleanup':'NOT_AUTOMATED','restic_prune':'NOT_AUTOMATED','full_restore_gate_required_for_backup_retention':True}}
    rp=out/f'hes-storage-maintenance-{stamp}.json'; rp.write_text(json.dumps(result,indent=2)+'\n'); os.chmod(rp,0o640)
    d=json.loads(storage.read_text()); b=d['storage_budget']; rec=d['recovery_assessment']
    print(f"HES_STORAGE_MAINTENANCE_OK report={rp} target_gb=5 complete_footprint_gb={b.get('total_local_hes_gb')} over_target_bytes={b.get('over_target_bytes')} disk_free_percent={d['disk'].get('free_percent')} pip_freed_bytes={cache.get('freed_bytes',0)} restore={rec.get('status')} cleanup_authorized=0")
    return 0
if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as e:
        print(f'HES_STORAGE_MAINTENANCE_FAIL_CLOSED {type(e).__name__}: {e}',file=sys.stderr); raise SystemExit(2)