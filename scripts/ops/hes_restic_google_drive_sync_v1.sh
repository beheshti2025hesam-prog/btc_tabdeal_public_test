#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
REPO=/var/backups/hes-trade-agent/restic-production-v1/repo
KEY=/root/.config/hes-backup/passphrase
REMOTE_NAME=hesgdrive
REMOTE='hesgdrive:HES Trade Agent Backups/restic-production-v1'
RESERVE=$((512*1024*1024))
LOCK=/run/lock/hes-restic-google-drive-sync.lock
exec 9>"$LOCK"; flock -n 9 || { echo RESTIC_DRIVE_SYNC_ALREADY_RUNNING; exit 0; }
[[ -s "$KEY" && -d "$REPO" ]] || exit 10
rclone listremotes | grep -Fxq "$REMOTE_NAME:" || { echo RESTIC_DRIVE_REMOTE_NOT_CONFIGURED; exit 11; }
export RESTIC_REPOSITORY="$REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR=/run/hes-restic
restic snapshots >/dev/null; restic check --read-data-subset=1/20
local_bytes=$(find "$REPO" -type f -printf '%s\n' | awk '{s+=$1} END{printf "%.0f\n",s}')
remote_bytes=$(rclone size "$REMOTE" --json 2>/dev/null | python3 -c 'import json,sys;print(int(json.load(sys.stdin).get("bytes",0)))' || echo 0)
quota=$(rclone about "$REMOTE_NAME:" --json)
free=$(printf '%s' "$quota" | python3 -c 'import json,sys;print(int(json.load(sys.stdin).get("free",0)))')
((free+remote_bytes>=local_bytes+RESERVE)) || { echo "RESTIC_DRIVE_QUOTA_BLOCK free=$free existing=$remote_bytes local=$local_bytes reserve=$RESERVE"; exit 20; }
echo "RESTIC_DRIVE_COPY_START local_bytes=$local_bytes remote_existing=$remote_bytes free=$free"
rclone copy "$REPO" "$REMOTE" --transfers 2 --checkers 4 --check-first --retries 5 --low-level-retries 10 --stats 30s --stats-one-line
rclone check "$REPO" "$REMOTE" --checkers 2
remote_after=$(rclone size "$REMOTE" --json | python3 -c 'import json,sys;print(int(json.load(sys.stdin)["bytes"]))')
[[ "$remote_after" == "$local_bytes" ]] || { echo "RESTIC_DRIVE_SIZE_MISMATCH local=$local_bytes remote=$remote_after"; exit 21; }
RESTIC_REPOSITORY="rclone:$REMOTE" restic check --read-data-subset=1/20
echo "RESTIC_DRIVE_SYNC_OK bytes=$remote_after"
