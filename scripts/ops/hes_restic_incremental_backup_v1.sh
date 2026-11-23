#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ROOT=/opt/hes-trade-agent
SCRIPT_DIR="/usr/local/lib/hes-storage-v1"
REPO=/var/backups/hes-trade-agent/restic-production-v1/repo
KEY=/root/.config/hes-backup/passphrase
HOST=hes-vps-recovery-v1
TAG=hes-full-recovery-v1
LOCK=/run/lock/hes-restic-incremental-backup.lock
MIN_FREE_BYTES=$((1024 * 1024 * 1024))
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
DASHBOARD_POINTER=/opt/hes-trade-agent/dashboard-current
[[ -L "$DASHBOARD_POINTER" ]] || { echo "RESTIC_DASHBOARD_POINTER_MISSING"; exit 11; }
DASHBOARD=$(readlink -f "$DASHBOARD_POINTER")
for p in "$ACTIVE" "$ROLLBACK" "$DASHBOARD"; do
  [[ "$p" == /opt/hes-trade-agent/releases/* && -d "$p" ]] || { echo "RESTIC_RELEASE_POINTER_INVALID path=$p"; exit 11; }
done
[[ "$ACTIVE" != "$ROLLBACK" && "$ACTIVE" != "$DASHBOARD" && "$ROLLBACK" != "$DASHBOARD" ]] || { echo 'RESTIC_RELEASE_POINTERS_COLLIDE'; exit 12; }
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
  [[ "$d" == "$ACTIVE" || "$d" == "$ROLLBACK" || "$d" == "$DASHBOARD" ]] || printf '%s\n' "$d" >> "$EXCLUDE"
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
 "$ACTIVE" "$ROLLBACK" "$DASHBOARD"
)
for p in "${ROOTS[@]}"; do
  [[ -e "$p" || -L "$p" ]] || { echo "RESTIC_REQUIRED_ROOT_MISSING path=$p"; exit 13; }
done
printf '%s\n' "${ROOTS[@]}" | sort -u > "$EXPECTED"
printf 'RESTIC_BACKUP_START utc=%s roots=%s active=%s rollback=%s dashboard=%s free_bytes=%s\n' "$(date -u +%FT%TZ)" "${#ROOTS[@]}" "$ACTIVE" "$ROLLBACK" "$DASHBOARD" "$free"
/usr/bin/restic backup --host "$HOST" --tag "$TAG" --one-file-system --exclude-file "$EXCLUDE" "${ROOTS[@]}"
/usr/bin/restic snapshots --json > "$RUNTIME_DIR/snapshots.json"
SNAPSHOT_ID=$(/usr/bin/python3 - "$RUNTIME_DIR/snapshots.json" "$EXPECTED" "$HOST" "$TAG" <<'PY'
import json,sys
from datetime import datetime,timezone,timedelta
snapshots=json.load(open(sys.argv[1])); expected=set(open(sys.argv[2]).read().splitlines()); host,tag=sys.argv[3:]
valid=[s for s in snapshots if s.get('hostname')==host and tag in (s.get('tags') or [])]
full=[s for s in valid if set(s.get('paths') or [])==expected]
now=datetime.now(timezone.utc)
full=[s for s in full if datetime.fromisoformat(s['time'].replace('Z','+00:00')) <= now+timedelta(minutes=5)]
if not full: raise SystemExit('RESTIC_NO_VALID_NON_FUTURE_44_ROOT_FULL_SCOPE_SNAPSHOT')
latest=max(full,key=lambda s:s['time'])
print(latest['id'])
PY
)
printf 'RESTIC_SCOPE_VERIFIED snapshot=%s roots=%s\n' "$SNAPSHOT_ID" "${#ROOTS[@]}"
STRATEGY_REF=refs/heads/feat/strategy-opportunity-diagnostic-v1
STRATEGY_COMMIT=$(/usr/bin/git -C "$ROOT" rev-parse "$STRATEGY_REF")
EVIDENCE_SAMPLE=$(find /srv/hes-evidence/operations/storage-lifecycle -type f -name 'audit-manifest.json' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
[[ -n "$EVIDENCE_SAMPLE" && -f "$EVIDENCE_SAMPLE" ]] || { echo 'RESTIC_RESTORE_DRILL_EVIDENCE_SAMPLE_MISSING'; exit 30; }
RESTORE_DRILL_STATUS=PASS
if /usr/bin/python3 "$SCRIPT_DIR/hes_restic_restore_drill_v1.py" \
  --snapshot-id "$SNAPSHOT_ID" --active-release "$ACTIVE" --rollback-release "$ROLLBACK" \
  --dashboard-release "$DASHBOARD" --strategy-ref "$STRATEGY_REF" --strategy-commit "$STRATEGY_COMMIT" \
  --evidence-sample "$EVIDENCE_SAMPLE" --marker /var/lib/hes-operational-health/restic-restore-verification.json --temp-parent /var/tmp; then
  :
else
  drill_rc=$?
  if (( drill_rc == 75 )); then
    RESTORE_DRILL_STATUS=DEFERRED_INSUFFICIENT_SPACE
    # Backup integrity remains checked; never create a partial restore or run retention.
    /usr/bin/restic check --read-data-subset=1/20
    printf 'RESTIC_RESTORE_DRILL_DEFERRED_INSUFFICIENT_SPACE snapshot=%s free_bytes=%s; retention=SKIPPED\n' \
      "$SNAPSHOT_ID" "$(df -PB1 /var/tmp | awk 'NR==2 {print $4}')"
  else
    echo "RESTIC_RESTORE_DRILL_FAILED exit_code=$drill_rc"
    exit "$drill_rc"
  fi
fi
# Snapshot pruning requires both the same-host restore marker and a fresh,
# independently signed replacement-host restore attestation. Missing proof blocks
# pruning without blocking creation/verification of the new backup.
if [[ "$RESTORE_DRILL_STATUS" == PASS ]]; then
  /usr/bin/python3 "$SCRIPT_DIR/hes_restic_retention_apply_v1.py" \
    --marker /var/lib/hes-operational-health/restic-restore-verification.json \
    --confirm HES_RESTIC_RETENTION_APPLY_V1 \
    --replacement-host-attestation /var/lib/hes-operational-health/replacement-host-restore-attestation.json \
    --replacement-host-signature /var/lib/hes-operational-health/replacement-host-restore-attestation.sig \
    --replacement-host-public-key /etc/hes-trade-agent/recovery-attestation.pub
else
  echo "RESTIC_RETENTION_SKIPPED reason=restore_drill_deferred_without_replacement_host_proof"
fi
printf 'RESTIC_BACKUP_OK repo_bytes=%s free_bytes=%s\n' "$(du -sB1 "$REPO" | awk '{print $1}')" "$(df -PB1 "$REPO" | awk 'NR==2 {print $4}')"