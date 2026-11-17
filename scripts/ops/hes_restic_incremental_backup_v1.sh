#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
REPO=/var/backups/hes-trade-agent/restic-production-v1/repo
KEY=/root/.config/hes-backup/passphrase
HOST=hes-vps-recovery-v1
TAG=hes-full-recovery-v1
LOCK=/run/lock/hes-restic-incremental-backup.lock
MIN_FREE_BYTES=$((512 * 1024 * 1024))
RUNTIME_DIR=${RUNTIME_DIRECTORY:-/run/hes-restic}
mkdir -p "$RUNTIME_DIR"
export RESTIC_REPOSITORY="$REPO" RESTIC_PASSWORD_FILE="$KEY" RESTIC_CACHE_DIR="$RUNTIME_DIR"
exec 9>"$LOCK"
flock -n 9 || { echo 'RESTIC_BACKUP_ALREADY_RUNNING'; exit 0; }
[[ -s "$KEY" && -d "$REPO" && -x /usr/bin/restic ]] || { echo 'RESTIC_PREREQUISITE_MISSING'; exit 10; }
/usr/local/sbin/hes-operational-healthcheck >/dev/null
free=$(df -PB1 "$REPO" | awk 'NR==2 {print $4}')
[[ "$free" =~ ^[0-9]+$ ]] && (( free >= MIN_FREE_BYTES )) || { echo "RESTIC_DISK_GUARD_BLOCK free=$free minimum=$MIN_FREE_BYTES"; exit 20; }
ACTIVE=$(readlink -f /opt/hes-trade-agent/current)
ROLLBACK=$(readlink -f /opt/hes-trade-agent/current-before-4329a3df)
for p in "$ACTIVE" "$ROLLBACK"; do
  [[ "$p" == /opt/hes-trade-agent/releases/* && -d "$p" ]] || { echo "RESTIC_RELEASE_POINTER_INVALID path=$p"; exit 11; }
done
[[ "$ACTIVE" != "$ROLLBACK" ]] || { echo 'RESTIC_RELEASE_POINTERS_COLLIDE'; exit 12; }
EXCLUDE="$RUNTIME_DIR/excludes.txt"
EXPECTED="$RUNTIME_DIR/expected-paths.txt"
: > "$EXCLUDE"
printf '%s\n' \
  '/opt/hes-trade-agent/.venv' \
  '/opt/hes-trade-agent/.pytest_cache' \
  '/opt/hes-trade-agent/.mypy_cache' \
  '/opt/hes-trade-agent/.ruff_cache' \
  '/opt/hes-trade-agent/__pycache__' \
  '/opt/hes-trade-agent/**/__pycache__' \
  '/opt/hes-trade-agent/**/.pytest_cache' \
  '/opt/hes-trade-agent/**/.mypy_cache' \
  '/opt/hes-trade-agent/**/.ruff_cache' > "$EXCLUDE"
while IFS= read -r d; do
  [[ "$d" == "$ACTIVE" || "$d" == "$ROLLBACK" ]] || printf '%s\n' "$d" >> "$EXCLUDE"
done < <(find /opt/hes-trade-agent/releases -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort)
ROOTS=(
 /opt/hes-trade-agent /srv/hes-evidence
 /etc/apt /etc/cloud /etc/cron.d /etc/cron.daily /etc/cron.hourly /etc/cron.weekly
 /etc/environment /etc/fstab /etc/hes-trade-agent /etc/hostname /etc/hosts /etc/logrotate.d
 /etc/modules-load.d /etc/netplan /etc/network /etc/nftables.conf /etc/security /etc/sentinelx
 /etc/ssh /etc/sudoers /etc/sudoers.d /etc/sysctl.d /etc/systemd/system /etc/ufw
 /var/lib/apt/extended_states /var/lib/cloud /var/lib/dpkg/status /var/lib/hes-operational-health
 /var/lib/sentinelx/audit.jsonl /var/lib/sentinelx/hes-release-live-replay-8e31
 /var/lib/sentinelx/hes-release-manifests /var/lib/sentinelx/hes-runtime-snapshots
 /var/lib/systemd /var/spool/cron/crontabs /root/.config/rclone /root/.ssh
 /usr/local/sbin/hes-operational-healthcheck /usr/local/sbin/hes-restic-incremental-backup
 /usr/local/sbin/hes-restic-production-dropbox-sync
 "$ACTIVE" "$ROLLBACK"
)
for p in "${ROOTS[@]}"; do
  [[ -e "$p" || -L "$p" ]] || { echo "RESTIC_REQUIRED_ROOT_MISSING path=$p"; exit 13; }
done
printf '%s\n' "${ROOTS[@]}" | sort -u > "$EXPECTED"
printf 'RESTIC_BACKUP_START utc=%s roots=%s active=%s rollback=%s free_bytes=%s\n' "$(date -u +%FT%TZ)" "${#ROOTS[@]}" "$ACTIVE" "$ROLLBACK" "$free"
/usr/bin/restic backup --host "$HOST" --tag "$TAG" --one-file-system --exclude-file "$EXCLUDE" "${ROOTS[@]}"
/usr/bin/restic snapshots --json > "$RUNTIME_DIR/snapshots.json"
/usr/bin/python3 - "$RUNTIME_DIR/snapshots.json" "$EXPECTED" "$HOST" "$TAG" <<'PY'
import json,sys
from datetime import datetime,timezone,timedelta
snapshots=json.load(open(sys.argv[1])); expected=set(open(sys.argv[2]).read().splitlines()); host,tag=sys.argv[3:]
valid=[s for s in snapshots if s.get('hostname')==host and tag in (s.get('tags') or [])]
full=[s for s in valid if set(s.get('paths') or [])==expected]
now=datetime.now(timezone.utc)
full=[s for s in full if datetime.fromisoformat(s['time'].replace('Z','+00:00')) <= now+timedelta(minutes=5)]
if not full: raise SystemExit('RESTIC_NO_VALID_NON_FUTURE_43_ROOT_FULL_SCOPE_SNAPSHOT')
latest=max(full,key=lambda s:s['time'])
actual=set(latest.get('paths') or [])
print('RESTIC_SCOPE_VERIFIED snapshot='+latest['id']+' roots='+str(len(actual))+' time='+latest['time'])
PY
# Scope-aware retention: Restic groups snapshots by the exact host + path set.
# Full 43-root snapshots and evidence-only partial snapshots therefore remain
# separate retention groups; a partial snapshot can never replace a full restore point.
/usr/bin/restic forget --host "$HOST" --tag "$TAG" --group-by host,paths \
  --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --keep-yearly 2 --prune
/usr/bin/restic check --read-data-subset=1/20
printf 'RESTIC_BACKUP_OK repo_bytes=%s free_bytes=%s\n' "$(du -sB1 "$REPO" | awk '{print $1}')" "$(df -PB1 "$REPO" | awk 'NR==2 {print $4}')"
