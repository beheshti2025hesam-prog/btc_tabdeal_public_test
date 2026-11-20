#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ROOT=/opt/hes-trade-agent KEY=/root/.config/hes-backup/passphrase
OUT=/var/backups/hes-trade-agent/offsite-staging STATE=/var/lib/hes-operational-health
MAX_BYTES=$((64 * 1024 * 1024))
exec 9>/run/lock/hes-dropbox-recovery-capsule.lock
flock -n 9 || exit 10
[[ -s "$KEY" && -d "$ROOT/releases" && -d "$STATE" ]] || exit 11
mkdir -p "$OUT"; chmod 0700 "$OUT"
WORK=$(mktemp -d "$OUT/.capsule.XXXXXX"); trap 'rm -rf -- "$WORK"' EXIT
LIST="$WORK/include.list0" INV="$WORK/release-inventory.json"
python3 - "$ROOT" "$STATE" "$INV" <<'PY'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]).resolve(strict=True); state=Path(sys.argv[2]).resolve(strict=True); out=Path(sys.argv[3])
for n in ("current","current-before-4329a3df"):
 if not (root/n).is_symlink(): raise SystemExit("CAPSULE_REQUIRED_POINTER_MISSING "+n)
pointers={root/"current"}; pointers.update(root.glob("*-current")); pointers.update(root.glob("current-before-*")); pointers.update(root.glob("current-rollback-*"))
targets={}
def add(label,value):
 p=Path(value)
 if not p.is_absolute(): p=root/p
 p=p.resolve(strict=True)
 if p.parent!=(root/"releases").resolve(strict=True) or not p.is_dir(): raise SystemExit("CAPSULE_UNSAFE_RELEASE_TARGET "+str(p))
 targets.setdefault(p,set()).add(label)
for p in sorted(pointers):
 if p.is_symlink(): add(p.name,p)
if (root/"dashboard-current").is_symlink():
 rollback=None
 for rp in reversed(sorted(state.glob("dashboard-deploy-*/postdeploy.json"))):
  d=json.loads(rp.read_text())
  if d.get("result")!="DEPLOYED_HEALTHY": continue
  c=d.get("checks") or {}; rollback=c.get("rollback_target") or d.get("previous_release")
  if rollback: break
 if not rollback: raise SystemExit("CAPSULE_DASHBOARD_ROLLBACK_UNVERIFIED")
 add("dashboard-rollback",rollback)
rows=[{"path":str(p),"archive_path":p.relative_to("/").as_posix(),"pointers":sorted(v)} for p,v in sorted(targets.items(),key=lambda x:str(x[0]))]
if len(rows)<2: raise SystemExit("CAPSULE_RELEASE_COVERAGE_TOO_SMALL")
out.write_text(json.dumps({"schema":"hes_recovery_capsule_inventory_v1","release_targets":rows},indent=2)+"\n")
print("CAPSULE_RELEASE_INVENTORY_OK count="+str(len(rows)))
PY
python3 - "$INV" > "$WORK/releases.txt" <<'PY'
import json,sys
for x in json.load(open(sys.argv[1]))["release_targets"]: print(x["archive_path"])
PY
: > "$LIST"
while IFS= read -r p; do
 [[ -d "/$p" ]] || { echo "CAPSULE_RELEASE_MISSING $p"; exit 13; }
 find "$p" -mindepth 0 \( -name .venv -o -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache \) -prune -o -print0 >> "$LIST"
done < "$WORK/releases.txt"
for p in opt/hes-trade-agent/current opt/hes-trade-agent/current-before-4329a3df opt/hes-trade-agent/dashboard-current opt/hes-trade-agent/precision-current opt/hes-trade-agent/current-rollback-20261119-09f660d6 etc/ssh etc/nftables.conf etc/systemd/system etc/ufw etc/netplan etc/apt etc/sentinelx etc/hes-trade-agent etc/sysctl.d etc/modules-load.d etc/fstab etc/hosts etc/hostname etc/sudoers etc/sudoers.d etc/cron.d etc/cron.daily etc/cron.hourly etc/cron.weekly etc/logrotate.d etc/security etc/environment var/lib/apt/extended_states var/lib/dpkg/status var/lib/hes-operational-health var/lib/systemd var/lib/sentinelx/hes-release-manifests var/lib/sentinelx/hes-runtime-snapshots root/.ssh root/.config/rclone usr/local/sbin/hes-operational-healthcheck usr/local/sbin/hes-restic-incremental-backup usr/local/sbin/hes-restic-production-dropbox-sync opt/hes-trade-agent/evidence opt/hes-trade-agent/reports opt/hes-trade-agent/docs; do
 [[ ! -e "/$p" && ! -L "/$p" ]] || find "$p" -mindepth 0 -print0 >> "$LIST"
done
mkdir -p "$WORK/recovery-metadata"
/opt/hes-trade-agent/.venv/bin/python -m pip freeze --all | sort > "$WORK/recovery-metadata/python-venv-freeze.txt"
dpkg-query -W -f='${db:Status-Status}\t${binary:Package}\t${Version}\n' | awk -F '\t' '$1=="installed"{print $2 "\t" $3}' | sort > "$WORK/recovery-metadata/apt-installed-packages.tsv"
. /etc/os-release
printf 'OS=%s\nKERNEL=%s\nPYTHON=%s\nCAPTURED_UTC=%s\n' "$PRETTY_NAME" "$(uname -r)" "$(python3 --version 2>&1)" "$(date -u +%FT%TZ)" > "$WORK/recovery-metadata/platform.txt"
cp "$INV" "$WORK/recovery-metadata/release-inventory.json"
find "${WORK#/}" -mindepth 0 -print0 >> "$LIST"
sort -zu "$LIST" -o "$LIST"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BASE="hes-recovery-capsule-$STAMP.tar.zst.gpg"; PART="$WORK/$BASE.partial"; FINAL="$OUT/$BASE"
[[ ! -e "$FINAL" ]] || exit 14
echo "CAPSULE_BUILD_START utc=$STAMP cap_bytes=$MAX_BYTES"
if tar -C / --no-recursion --one-file-system --numeric-owner --xattrs --acls --null --files-from="$LIST" -cf - | zstd -q -T1 -19 --long=27 -c | gpg --batch --yes --pinentry-mode loopback --symmetric --cipher-algo AES256 --s2k-mode 3 --s2k-count 65011712 --passphrase-file "$KEY" --output - | head -c "$MAX_BYTES" > "$PART"; then :
else rc=$?; bytes=$(stat -c %s "$PART" 2>/dev/null || echo 0); if ((bytes>=MAX_BYTES)); then echo "CAPSULE_REJECTED_SIZE_CAP bytes=$bytes cap=$MAX_BYTES"; exit 30; fi; echo "CAPSULE_BUILD_FAILED rc=$rc bytes=$bytes"; exit "$rc"; fi
chmod 0600 "$PART"; bytes=$(stat -c %s "$PART"); ((bytes<MAX_BYTES)) || exit 30
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY" --decrypt "$PART" 2>/dev/null | zstd -t -q
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY" --decrypt "$PART" 2>/dev/null | zstd -dc -q | tar -tf - > "$WORK/archive.list"
python3 - "$INV" "$WORK/archive.list" <<'PY'
import json,sys
inv=json.load(open(sys.argv[1])); entries=set(x.rstrip("/") for x in open(sys.argv[2]))
missing=[x["archive_path"] for x in inv["release_targets"] if x["archive_path"] not in entries]
if missing: raise SystemExit("CAPSULE_RELEASE_COVERAGE_FAIL "+",".join(missing))
for p in ("etc/systemd/system","etc/hes-trade-agent","var/lib/hes-operational-health","recovery-metadata"):
 if not any(x==p or x.startswith(p+"/") for x in entries): raise SystemExit("CAPSULE_REQUIRED_PATH_MISSING "+p)
print("CAPSULE_CONTENT_VALIDATION_OK release_trees="+str(len(inv["release_targets"])))
PY
mv "$PART" "$FINAL"; chmod 0600 "$FINAL"
sha256sum "$FINAL" > "$FINAL.sha256"; chmod 0600 "$FINAL.sha256"
cat > "$FINAL.manifest.txt" <<EOF
HES Recovery Capsule v1
Created UTC: $STAMP
Encrypted archive bytes: $bytes
SHA-256: $(sha256sum "$FINAL" | awk '{print $1}')
Included: active/rollback releases, dashboard and precision, system config, services, operational health, release manifests, package inventories, docs/reports/project evidence.
Excluded: full Restic repository, bulk evidence, historical candidates/worktrees, caches, virtualenv binaries, recovery passphrase.
Full data recovery tier: separate encrypted Restic repository on a larger authorized free-tier provider.
EOF
chmod 0600 "$FINAL.manifest.txt"; sha256sum -c "$FINAL.sha256"
echo "CAPSULE_BUILD_OK file=$FINAL bytes=$bytes sha256=$(sha256sum "$FINAL" | awk '{print $1}')"
