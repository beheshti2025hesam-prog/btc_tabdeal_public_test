#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
REPO=/var/backups/hes-trade-agent/restic-production-v1/repo
KEY=/root/.config/hes-backup/passphrase
HOST=hes-vps-recovery-v1
TAG=hes-full-recovery-v1
REMOTE='hesdropbox:HES Trade Agent Backups/restic-production-v1'
LOCK=/run/lock/hes-restic-production-dropbox-sync.lock
RESERVE_BYTES=$((128 * 1024 * 1024))
exec 9>"$LOCK"
flock -n 9 || { echo 'RESTIC_PRODUCTION_DROPBOX_SYNC_ALREADY_RUNNING'; exit 0; }
[[ -s "$KEY" && -d "$REPO" ]] || { echo 'RESTIC_PRODUCTION_DROPBOX_PREREQUISITE_MISSING'; exit 10; }
export RESTIC_REPOSITORY="$REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR=/run/hes-restic
/usr/bin/restic snapshots --json > /run/hes-restic/production-snapshots.json
/usr/bin/python3 - /run/hes-restic/production-snapshots.json "$HOST" "$TAG" <<'PY'
import json,sys,datetime
items=json.load(open(sys.argv[1])); host,tag=sys.argv[2:]
now=datetime.datetime.now(datetime.timezone.utc)
full=[]
for s in items:
    if s.get('hostname')!=host or tag not in (s.get('tags') or []) or len(s.get('paths') or [])!=43:
        continue
    dt=datetime.datetime.fromisoformat(s['time'].replace('Z','+00:00'))
    if dt <= now+datetime.timedelta(minutes=5): full.append((dt,s))
if not full: raise SystemExit('NO_VALID_43_ROOT_FULL_SNAPSHOT')
dt,s=max(full,key=lambda x:x[0])
print('RESTIC_OFFSITE_SOURCE snapshot='+s['id']+' time='+s['time']+' roots='+str(len(s['paths'])))
PY
/usr/bin/restic check --read-data-subset=1/20
local_bytes=$(find "$REPO" -type f -printf '%s\n' | awk '{s+=$1} END {printf "%.0f\n",s}')
local_files=$(find "$REPO" -type f | wc -l)
remote_bytes=0
if rclone lsf "$REMOTE" >/dev/null 2>&1; then
  remote_bytes=$(rclone size "$REMOTE" --json | /usr/bin/python3 -c 'import json,sys;print(int(json.load(sys.stdin).get("bytes",0)))')
fi
quota=$(rclone about hesdropbox: --json)
free=$(printf '%s' "$quota" | /usr/bin/python3 -c 'import json,sys;print(int(json.load(sys.stdin).get("free",0)))')
(( free + remote_bytes >= local_bytes + RESERVE_BYTES )) || { echo "DROPBOX_PRODUCTION_RESTIC_QUOTA_GUARD_BLOCK free=$free remote_existing=$remote_bytes incoming=$local_bytes reserve=$RESERVE_BYTES"; exit 20; }
printf 'RESTIC_PRODUCTION_DROPBOX_SYNC_START local_bytes=%s local_files=%s remote_existing_bytes=%s free_bytes=%s reserve=%s\n' "$local_bytes" "$local_files" "$remote_bytes" "$free" "$RESERVE_BYTES"
rclone sync "$REPO" "$REMOTE" --transfers 2 --checkers 4 --check-first --delete-after --retries 5 --low-level-retries 10 --stats 30s --stats-one-line
rclone check "$REPO" "$REMOTE" --checkers 2
remote_after=$(rclone size "$REMOTE" --json | /usr/bin/python3 -c 'import json,sys;print(int(json.load(sys.stdin).get("bytes",0)))')
remote_files=$(rclone size "$REMOTE" --json | /usr/bin/python3 -c 'import json,sys;print(int(json.load(sys.stdin).get("count",0)))')
[[ "$remote_after" == "$local_bytes" ]] || { echo "RESTIC_PRODUCTION_REMOTE_SIZE_MISMATCH local=$local_bytes remote=$remote_after"; exit 21; }
rclone about hesdropbox: --json | /usr/bin/python3 -c 'import json,sys;d=json.load(sys.stdin);print("DROPBOX_AFTER_PRODUCTION_RESTIC_SYNC total={total} used={used} free={free}".format(**d))'
printf 'RESTIC_PRODUCTION_DROPBOX_SYNC_OK bytes=%s files=%s\n' "$remote_after" "$remote_files"
