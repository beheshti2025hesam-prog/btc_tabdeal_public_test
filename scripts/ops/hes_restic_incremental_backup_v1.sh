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
ROOT=/opt/hes-trade-agent
RELEASE_INVENTORY="$RUNTIME_DIR/release-inventory.json"
RELEASE_PATHS="$RUNTIME_DIR/release-paths.txt"
python3 - "$ROOT" /var/lib/hes-operational-health "$RELEASE_INVENTORY" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve(strict=True)
state=Path(sys.argv[2]).resolve(strict=True)
out=Path(sys.argv[3])
for name in ("current","current-before-4329a3df"):
    if not (root/name).is_symlink():
        raise SystemExit("RESTIC_REQUIRED_RELEASE_POINTER_MISSING "+name)
pointers={root/"current"}
pointers.update(root.glob("*-current"))
pointers.update(root.glob("current-before-*"))
pointers.update(root.glob("current-rollback-*"))
targets={}
def add(label,value):
    p=Path(value)
    if not p.is_absolute(): p=root/p
    p=p.resolve(strict=True)
    if p.parent!=(root/"releases").resolve(strict=True) or not p.is_dir():
        raise SystemExit("RESTIC_UNSAFE_RELEASE_TARGET "+str(p))
    targets.setdefault(p,set()).add(label)
for pointer in sorted(pointers):
    if pointer.is_symlink(): add(pointer.name,pointer)
if (root/"dashboard-current").is_symlink():
    rollback=None
    for record_path in reversed(sorted(state.glob("dashboard-deploy-*/postdeploy.json"))):
        record=json.loads(record_path.read_text())
        if record.get("result")!="DEPLOYED_HEALTHY": continue
        checks=record.get("checks") or {}
        rollback=checks.get("rollback_target") or record.get("previous_release")
        if rollback: break
    if not rollback: raise SystemExit("RESTIC_DASHBOARD_ROLLBACK_UNVERIFIED")
    add("dashboard-rollback",rollback)
rows=[{"path":str(p),"archive_path":p.relative_to("/").as_posix(),"pointers":sorted(labels)}
      for p,labels in sorted(targets.items(),key=lambda item:str(item[0]))]
if len(rows)<2: raise SystemExit("RESTIC_RELEASE_COVERAGE_TOO_SMALL")
out.write_text(json.dumps({"schema":"hes_restic_release_inventory_v1","release_targets":rows},indent=2)+"\n")
print("RESTIC_RELEASE_INVENTORY_OK count="+str(len(rows)))
PY
python3 - "$RELEASE_INVENTORY" > "$RELEASE_PATHS" <<'PY'
import json,sys
for item in json.load(open(sys.argv[1]))["release_targets"]:
    print(item["path"])
PY
mapfile -t RELEASES < "$RELEASE_PATHS"
declare -A INCLUDED_RELEASES
for p in "\${RELEASES[@]}"; do INCLUDED_RELEASES["$p"]=1; done
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
  [[ -n "\${INCLUDED_RELEASES[$d]+x}" ]] || printf '%s\n' "$d" >> "$EXCLUDE"
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
 "\${RELEASES[@]}"
)
for p in "${ROOTS[@]}"; do
  [[ -e "$p" || -L "$p" ]] || { echo "RESTIC_REQUIRED_ROOT_MISSING path=$p"; exit 13; }
done
printf '%s\n' "${ROOTS[@]}" | sort -u > "$EXPECTED"
printf 'RESTIC_BACKUP_START utc=%s roots=%s release_trees=%s free_bytes=%s\n' "$(date -u +%FT%TZ)" "${#ROOTS[@]}" "${#RELEASES[@]}" "$free"
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
if not full: raise SystemExit('RESTIC_NO_VALID_NON_FUTURE_FULL_SCOPE_SNAPSHOT')
latest=max(full,key=lambda s:s['time'])
actual=set(latest.get('paths') or [])
print('RESTIC_SCOPE_VERIFIED snapshot='+latest['id']+' roots='+str(len(actual))+' time='+latest['time'])
PY
# Scope-aware retention: Restic groups snapshots by the exact host + path set.
# Full-scope snapshots and evidence-only partial snapshots therefore remain
# separate retention groups; a partial snapshot can never replace a full restore point.
/usr/bin/restic forget --host "$HOST" --tag "$TAG" --group-by host,paths \
  --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --keep-yearly 2 --prune
/usr/bin/restic check --read-data-subset=1/20
printf 'RESTIC_BACKUP_OK repo_bytes=%s free_bytes=%s\n' "$(du -sB1 "$REPO" | awk '{print $1}')" "$(df -PB1 "$REPO" | awk 'NR==2 {print $4}')"
