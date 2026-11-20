#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
LOCAL_REPO=/var/backups/hes-trade-agent/restic-production-v1/repo
KEY=/root/.config/hes-backup/passphrase
HOST=hes-vps-recovery-v1
TAG=hes-full-recovery-v1
REMOTE_NAME=hesgdrive
REMOTE_PATH='hesgdrive:HES Trade Agent Backups/restic-production-v1'
REMOTE_REPO="rclone:$REMOTE_PATH"
RESERVE=$((512*1024*1024))
LOCK=/run/lock/hes-restic-google-drive-sync.lock
RUNTIME_DIR=/run/hes-restic
mkdir -p "$RUNTIME_DIR"
exec 9>"$LOCK"; flock -n 9 || { echo RESTIC_DRIVE_SYNC_ALREADY_RUNNING; exit 0; }
[[ -s "$KEY" && -d "$LOCAL_REPO" ]] || exit 10
rclone listremotes | grep -Fxq "$REMOTE_NAME:" || { echo RESTIC_DRIVE_REMOTE_NOT_CONFIGURED; exit 11; }

export RESTIC_REPOSITORY="$LOCAL_REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR="$RUNTIME_DIR"
restic snapshots >/dev/null
restic check --read-data-subset=1/20
local_bytes=$(find "$LOCAL_REPO" -type f -printf '%s\n' | awk '{s+=$1} END{printf "%.0f\n",s}')
remote_bytes=$(rclone size "$REMOTE_PATH" --json 2>/dev/null | python3 -c 'import json,sys;print(int(json.load(sys.stdin).get("bytes",0)))' || echo 0)
quota=$(rclone about "$REMOTE_NAME:" --json)
free=$(printf '%s' "$quota" | python3 -c 'import json,sys;print(int(json.load(sys.stdin).get("free",0)))')
((free+remote_bytes>=local_bytes+RESERVE)) || { echo "RESTIC_DRIVE_QUOTA_BLOCK free=$free existing=$remote_bytes local=$local_bytes reserve=$RESERVE"; exit 20; }

# A dedicated destination repo is initialized with the source chunker parameters
# so identical files deduplicate across snapshots copied from the local repo.
if ! RESTIC_REPOSITORY="$REMOTE_REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR="$RUNTIME_DIR" restic snapshots >/dev/null 2>&1; then
  existing=$(rclone lsf "$REMOTE_PATH" 2>/dev/null | head -1 || true)
  [[ -z "$existing" ]] || { echo RESTIC_DRIVE_REMOTE_NONEMPTY_UNREADABLE; exit 21; }
  RESTIC_REPOSITORY="$REMOTE_REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR="$RUNTIME_DIR" \
    restic init --from-repo "$LOCAL_REPO" --from-password-file "$KEY" --copy-chunker-params
fi

echo "RESTIC_DRIVE_COPY_START local_bytes=$local_bytes remote_existing=$remote_bytes free=$free"
RESTIC_REPOSITORY="$REMOTE_REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_FROM_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR="$RUNTIME_DIR" \
  restic copy --from-repo "$LOCAL_REPO" --host "$HOST" --tag "$TAG"

# Compare snapshot metadata rather than repository byte sizes: native Restic copy
# re-encrypts data into a distinct repository and uses its own pack layout.
RESTIC_REPOSITORY="$LOCAL_REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR="$RUNTIME_DIR" \
  restic snapshots --json > "$RUNTIME_DIR/local-snapshots.json"
RESTIC_REPOSITORY="$REMOTE_REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR="$RUNTIME_DIR" \
  restic snapshots --json > "$RUNTIME_DIR/remote-snapshots.json"
python3 - "$RUNTIME_DIR/local-snapshots.json" "$RUNTIME_DIR/remote-snapshots.json" "$HOST" "$TAG" <<'PY'
import json,sys
local=json.load(open(sys.argv[1])); remote=json.load(open(sys.argv[2])); host,tag=sys.argv[3:]
def selected(items):
    return [s for s in items if s.get("hostname")==host and tag in (s.get("tags") or [])]
def key(s):
    return (s.get("time"),s.get("hostname"),tuple(sorted(s.get("paths") or [])),tuple(sorted(s.get("tags") or [])))
src={key(s) for s in selected(local)}
dst={key(s) for s in selected(remote)}
missing=src-dst
if missing:
    raise SystemExit("RESTIC_DRIVE_SNAPSHOT_COVERAGE_MISSING count="+str(len(missing)))
print("RESTIC_DRIVE_SNAPSHOT_COVERAGE_OK count="+str(len(src)))
PY

# Match local scope-aware retention on the remote; this prunes only HES-tagged
# snapshots in the dedicated remote repository, never unrelated Drive files.
RESTIC_REPOSITORY="$REMOTE_REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR="$RUNTIME_DIR" \
  restic forget --host "$HOST" --tag "$TAG" --group-by host,paths \
  --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --keep-yearly 2 --prune
RESTIC_REPOSITORY="$REMOTE_REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR="$RUNTIME_DIR" \
  restic check --read-data-subset=1/20
remote_after=$(rclone size "$REMOTE_PATH" --json | python3 -c 'import json,sys;print(int(json.load(sys.stdin)["bytes"]))')
echo "RESTIC_DRIVE_SYNC_OK remote_bytes=$remote_after"
