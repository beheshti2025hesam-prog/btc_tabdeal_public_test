#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
KEY=/root/.config/hes-backup/passphrase
REMOTE_REPO='rclone:hesgdrive:HES Trade Agent Backups/restic-production-v1'
HOST=hes-vps-recovery-v1
TAG=hes-full-recovery-v1
RUNTIME_DIR=/run/hes-restic
REPORT_DIR=/var/lib/hes-operational-health
RESTORE_PARENT=/var/backups/hes-trade-agent/restore-drills
LOCK=/run/lock/hes-restic-google-drive-restore-drill.lock
mkdir -p "$RUNTIME_DIR" "$REPORT_DIR" "$RESTORE_PARENT"
exec 9>"$LOCK"; flock -n 9 || { echo RESTIC_DRIVE_RESTORE_DRILL_ALREADY_RUNNING; exit 0; }
[[ -s "$KEY" ]] || exit 10
export RESTIC_REPOSITORY="$REMOTE_REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR="$RUNTIME_DIR"
restic check --read-data-subset=1/20
restic snapshots --json > "$RUNTIME_DIR/drive-snapshots.json"
python3 - "$RUNTIME_DIR/drive-snapshots.json" "$HOST" "$TAG" "$RUNTIME_DIR/restore-plan.json" <<'PY'
import json,sys
from datetime import datetime,timezone,timedelta
snapshots=json.load(open(sys.argv[1])); host,tag,out=sys.argv[2:]
valid=[]
for s in snapshots:
    if s.get("hostname")!=host or tag not in (s.get("tags") or []): continue
    paths=s.get("paths") or []
    releases=sorted(p for p in paths if p.startswith("/opt/hes-trade-agent/releases/"))
    if len(releases)<6: continue
    if not all(p in paths for p in ("/opt/hes-trade-agent","/srv/hes-evidence","/etc/systemd/system","/etc/hes-trade-agent")): continue
    t=datetime.fromisoformat(s["time"].replace("Z","+00:00"))
    if t>datetime.now(timezone.utc)+timedelta(minutes=5): continue
    valid.append((t,s,releases))
if not valid: raise SystemExit("RESTIC_DRIVE_RESTORE_NO_FULL_RELEASE_SNAPSHOT")
_,latest,releases=max(valid,key=lambda x:x[0])
pointers=[
 "/opt/hes-trade-agent/current",
 "/opt/hes-trade-agent/current-before-4329a3df",
 "/opt/hes-trade-agent/dashboard-current",
 "/opt/hes-trade-agent/precision-current",
 "/opt/hes-trade-agent/current-rollback-20261119-09f660d6",
]
includes=sorted(set(releases+pointers+[
 "/srv/hes-evidence",
 "/etc/hes-trade-agent",
 "/etc/systemd/system",
 "/etc/ssh",
 "/etc/sentinelx",
 "/var/lib/hes-operational-health",
 "/var/lib/sentinelx/hes-release-manifests",
 "/var/lib/sentinelx/hes-runtime-snapshots",
 "/usr/local/sbin/hes-operational-healthcheck",
 "/usr/local/sbin/hes-restic-incremental-backup",
]))
with open(out,"w") as f: json.dump({"snapshot_id":latest["short_id"],"time":latest["time"],"paths":latest["paths"],"release_paths":releases,"includes":includes},f,indent=2)
print("RESTIC_DRIVE_RESTORE_PLAN_OK snapshot="+latest["short_id"]+" releases="+str(len(releases))+" includes="+str(len(includes)))
PY
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RESTORE=$(mktemp -d "$RESTORE_PARENT/.restore-$STAMP.XXXXXX")
trap 'rm -rf -- "$RESTORE"' EXIT
mapfile -t INCLUDES < <(python3 - "$RUNTIME_DIR/restore-plan.json" <<'PY'
import json,sys
for p in json.load(open(sys.argv[1]))["includes"]: print(p)
PY
)
SNAPSHOT=$(python3 - "$RUNTIME_DIR/restore-plan.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["snapshot_id"])
PY
)
echo "RESTIC_DRIVE_RESTORE_START snapshot=$SNAPSHOT include_paths=${#INCLUDES[@]}"
ARGS=()
for p in "${INCLUDES[@]}"; do ARGS+=(--include "$p"); done
restic restore "$SNAPSHOT" --target "$RESTORE" "${ARGS[@]}"
python3 - "$RUNTIME_DIR/restore-plan.json" "$RESTORE" <<'PY'
import json,sys
from pathlib import Path
plan=json.load(open(sys.argv[1])); root=Path(sys.argv[2])
for p in plan["release_paths"]:
    if not (root/p.lstrip("/")).is_dir(): raise SystemExit("RESTIC_DRIVE_RESTORE_RELEASE_MISSING "+p)
for p in ("/opt/hes-trade-agent/current","/opt/hes-trade-agent/current-before-4329a3df","/opt/hes-trade-agent/dashboard-current","/opt/hes-trade-agent/precision-current"):
    q=root/p.lstrip("/")
    if not q.is_symlink() or not q.is_dir(): raise SystemExit("RESTIC_DRIVE_RESTORE_POINTER_FAIL "+p)
for p in ("/srv/hes-evidence","/etc/systemd/system","/etc/hes-trade-agent","/var/lib/hes-operational-health"):
    if not (root/p.lstrip("/")).exists(): raise SystemExit("RESTIC_DRIVE_RESTORE_REQUIRED_PATH_MISSING "+p)
count=sum(1 for p in root.rglob("*") if p.is_file() or p.is_symlink())
print("RESTIC_DRIVE_ISOLATED_RESTORE_PASS release_trees="+str(len(plan["release_paths"]))+" restored_entries="+str(count))
PY
python3 - "$RUNTIME_DIR/restore-plan.json" "$REPORT_DIR/hes-restic-drive-restore-drill-$STAMP.json" "$RESTORE" <<'PY'
import json,sys
from pathlib import Path
plan=json.load(open(sys.argv[1])); target=Path(sys.argv[3])
report={"schema":"hes_restic_drive_restore_drill_v1","result":"PASS","snapshot_id":plan["snapshot_id"],"snapshot_time":plan["time"],"release_paths":plan["release_paths"],"include_paths":plan["includes"],"restored_entries":sum(1 for p in target.rglob("*") if p.is_file() or p.is_symlink())}
Path(sys.argv[2]).write_text(json.dumps(report,indent=2)+"\n")
print("RESTIC_DRIVE_RESTORE_REPORT="+sys.argv[2])
PY
echo "RESTIC_DRIVE_RESTORE_DRILL_OK snapshot=$SNAPSHOT"
