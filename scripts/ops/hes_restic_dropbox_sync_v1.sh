#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
REPO=/var/backups/hes-trade-agent/restic-compact-v1/repo
FILELIST=/var/backups/hes-trade-agent/offsite-staging/compact-core-files.nul
KEY=/root/.config/hes-backup/passphrase
HOST=hes-vps-recovery-v1
TAG=hes-full-recovery-core-v1
REMOTE='hesdropbox:HES Trade Agent Backups/hes-restic-core-v1'
LOCK=/run/lock/hes-restic-dropbox-sync.lock
MAX_BYTES=$((400 * 1024 * 1024))
RESERVE_BYTES=$((64 * 1024 * 1024))
exec 9>"$LOCK"
flock -n 9 || { echo 'RESTIC_DROPBOX_SYNC_ALREADY_RUNNING'; exit 0; }
[[ -s "$KEY" && -d "$REPO" ]] || { echo 'RESTIC_DROPBOX_SYNC_PREREQUISITE_MISSING'; exit 10; }
export RESTIC_REPOSITORY="$REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR=/run/hes-restic

/usr/local/sbin/hes-restic-compact-filelist
[[ -s "$FILELIST" ]] || { echo 'COMPACT_FILELIST_MISSING'; exit 11; }

/usr/bin/restic backup --compression max --host "$HOST" --tag "$TAG" --files-from-raw "$FILELIST"
/usr/bin/restic forget --host "$HOST" --keep-last 2 --group-by host --prune --quiet

/usr/bin/restic snapshots --json > /run/hes-restic/dropbox-snapshots.json
/usr/bin/python3 - /run/hes-restic/dropbox-snapshots.json "$HOST" "$TAG" <<'PY'
import json,sys,datetime
items=json.load(open(sys.argv[1])); host,tag=sys.argv[2:]
valid=[]
now=datetime.datetime.now(datetime.timezone.utc)
for s in items:
    if s.get('hostname')!=host or tag not in (s.get('tags') or []) or len(s.get('paths') or []) < 7000:
        continue
    dt=datetime.datetime.fromisoformat(s['time'].replace('Z','+00:00'))
    if dt <= now+datetime.timedelta(minutes=5):
        valid.append((dt,s))
if not valid:
    raise SystemExit('NO_VALID_COMPACT_RECOVERY_SNAPSHOT')
dt,s=max(valid,key=lambda x:x[0])
print('RESTIC_OFFSITE_SOURCE snapshot='+s['id']+' time='+s['time']+' paths='+str(len(s['paths'])))
PY

/usr/bin/restic check --read-data-subset=1/20
local_bytes=$(find "$REPO" -type f -printf '%s\n' | awk '{s+=$1} END {printf "%.0f\n",s}')
local_files=$(find "$REPO" -type f | wc -l)
(( local_bytes <= MAX_BYTES )) || { echo "COMPACT_RESTIC_SIZE_POLICY_BLOCK bytes=$local_bytes max=$MAX_BYTES"; exit 19; }

remote_bytes=0
if rclone lsf "$REMOTE" >/dev/null 2>&1; then
  remote_bytes=$(rclone size "$REMOTE" --json | /usr/bin/python3 -c 'import json,sys;print(int(json.load(sys.stdin).get("bytes",0)))')
fi
quota=$(rclone about hesdropbox: --json)
free=$(printf '%s' "$quota" | /usr/bin/python3 -c 'import json,sys;print(int(json.load(sys.stdin).get("free",0)))')
(( free + remote_bytes >= local_bytes + RESERVE_BYTES )) || { echo "DROPBOX_RESTIC_QUOTA_GUARD_BLOCK free=$free remote_existing=$remote_bytes incoming=$local_bytes reserve=$RESERVE_BYTES"; exit 20; }
printf 'RESTIC_DROPBOX_SYNC_START local_bytes=%s local_files=%s remote_existing_bytes=%s free_bytes=%s reserve=%s\n' "$local_bytes" "$local_files" "$remote_bytes" "$free" "$RESERVE_BYTES"

rclone sync "$REPO" "$REMOTE" --transfers 2 --checkers 4 --check-first --delete-after --retries 5 --low-level-retries 10 --stats 30s --stats-one-line
rclone check "$REPO" "$REMOTE" --checkers 2

# Verify the repository through Dropbox's rclone backend, not only by file hashes.
export RESTIC_REPOSITORY='rclone:hesdropbox:HES Trade Agent Backups/hes-restic-core-v1'
/usr/bin/restic check --read-data-subset=1/20
/usr/bin/restic snapshots --json > /run/hes-restic/dropbox-remote-snapshots.json
/usr/bin/python3 - /run/hes-restic/dropbox-remote-snapshots.json "$HOST" "$TAG" <<'PY'
import json,sys
items=json.load(open(sys.argv[1])); host,tag=sys.argv[2:]
full=[s for s in items if s.get('hostname')==host and tag in (s.get('tags') or []) and len(s.get('paths') or []) >= 7000]
if not full: raise SystemExit('REMOTE_COMPACT_SNAPSHOT_MISSING')
s=max(full,key=lambda x:x['time'])
print('RESTIC_REMOTE_SNAPSHOT_OK id='+s['id']+' paths='+str(len(s['paths'])))
PY

remote_after=$(rclone size 'hesdropbox:HES Trade Agent Backups/hes-restic-core-v1' --json | /usr/bin/python3 -c 'import json,sys;d=json.load(sys.stdin);print(int(d.get("bytes",0)))')
remote_files=$(rclone size 'hesdropbox:HES Trade Agent Backups/hes-restic-core-v1' --json | /usr/bin/python3 -c 'import json,sys;d=json.load(sys.stdin);print(int(d.get("count",0)))')
[[ "$remote_after" == "$local_bytes" ]] || { echo "RESTIC_REMOTE_SIZE_MISMATCH local=$local_bytes remote=$remote_after"; exit 21; }
rclone about hesdropbox: --json | /usr/bin/python3 -c 'import json,sys;d=json.load(sys.stdin);print("DROPBOX_AFTER_RESTIC_SYNC total={total} used={used} free={free}".format(**d))'
printf 'RESTIC_DROPBOX_SYNC_OK bytes=%s files=%s\n' "$remote_after" "$remote_files"
