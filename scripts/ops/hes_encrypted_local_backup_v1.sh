#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
cd /

BACKUP_DIR=/var/backups/hes-trade-agent/encrypted-local
KEY_FILE=/root/.config/hes-backup/passphrase
LOCK_FILE=/run/lock/hes-encrypted-local-backup.lock
ROOT=/opt/hes-trade-agent
MIN_FREE_KB=5242880
LIST_FILE=''
PARTIAL_FILE=''
MANIFEST_PARTIAL_FILE=''

exec 9>"$LOCK_FILE"
flock -n 9 || { echo 'backup already running'; exit 0; }
trap 'rc=$?; echo "BACKUP_FAILED rc=$rc line=${BASH_LINENO[0]:-unknown}" >&2; exit "$rc"' ERR
cleanup() {
  local rc=$?
  if (( rc != 0 )); then
    if [[ -n "$PARTIAL_FILE" ]]; then rm -f -- "$PARTIAL_FILE"; fi
    if [[ -n "$MANIFEST_PARTIAL_FILE" ]]; then rm -f -- "$MANIFEST_PARTIAL_FILE"; fi
  fi
  if [[ -n "$LIST_FILE" ]]; then rm -f -- "$LIST_FILE"; fi
}
trap cleanup EXIT

prune_archives() {
 local today name ds day iso day_epoch age dow dom keep
 local -A latest_by_day=()
 local -a archive_names=()
 today=${HES_BACKUP_TODAY:-$(date -u +%F)}
 mapfile -t archive_names < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'hes-full-*.tar.gz.gpg' -printf '%f\n' | sort)
 for name in "${archive_names[@]}"; do
  ds=${name#hes-full-}; ds=${ds%.tar.gz.gpg}
  if [[ "$ds" =~ ^([0-9]{8})T[0-9]{6}Z$ ]]; then
   day=${BASH_REMATCH[1]}; latest_by_day["$day"]="$name"
  fi
 done
 for name in "${archive_names[@]}"; do
  ds=${name#hes-full-}; ds=${ds%.tar.gz.gpg}
  if [[ ! "$ds" =~ ^([0-9]{8})T[0-9]{6}Z$ ]]; then
   printf 'RETENTION_KEEP_INVALID_NAME file=%s\\n' "$name" >&2; continue
  fi
  day=${BASH_REMATCH[1]}; iso="${day:0:4}-${day:4:2}-${day:6:2}"
  day_epoch=$(date -u -d "$iso" +%s 2>/dev/null) || { printf 'RETENTION_KEEP_INVALID_DATE file=%s\\n' "$name" >&2; continue; }
  age=$(( ( $(date -u -d "$today" +%s) - day_epoch ) / 86400 ))
  dow=$(date -u -d "$iso" +%u); dom=$(date -u -d "$iso" +%d); keep=0
  if (( age < 0 )); then printf 'RETENTION_KEEP_FUTURE_DATED file=%s age_days=%s\\n' "$name" "$age" >&2; continue; fi
  if (( age < 7 )); then keep=1; fi
  if (( age < 28 )) && [[ "$dow" == 7 ]]; then keep=1; fi
  if (( age < 180 )) && [[ "$dom" == 01 ]]; then keep=1; fi
  if (( keep == 1 )) && [[ "${latest_by_day[$day]:-}" != "$name" ]]; then
   printf 'RETENTION_DELETE_DUPLICATE file=%s latest=%s\\n' "$name" "${latest_by_day[$day]}"
   rm -f -- "$BACKUP_DIR/$name" "$BACKUP_DIR/$name.sha256"
  elif (( keep == 0 )); then
   printf 'RETENTION_DELETE_EXPIRED file=%s age_days=%s\\n' "$name" "$age"
   rm -f -- "$BACKUP_DIR/$name" "$BACKUP_DIR/$name.sha256"
  fi
 done
}

[[ -d "$ROOT" && -s "$KEY_FILE" ]]
prune_archives
/usr/local/sbin/hes-operational-healthcheck >/dev/null
avail_kb=$(df -Pk "$BACKUP_DIR" | awk 'NR==2{print $4}')
[[ "$avail_kb" =~ ^[0-9]+$ ]] && (( avail_kb >= MIN_FREE_KB )) || { echo 'insufficient free disk for safe backup'; exit 20; }

stamp=$(date -u +%Y%m%dT%H%M%SZ)
base="hes-full-$stamp.tar.gz.gpg"
final="$BACKUP_DIR/$base"
tmp="$BACKUP_DIR/.$base.partial"
PARTIAL_FILE="$tmp"
manifest="$BACKUP_DIR/$base.sha256"
manifest_tmp="$manifest.partial"
MANIFEST_PARTIAL_FILE="$manifest_tmp"

[[ ! -e "$final" && ! -e "$tmp" ]] || { echo 'refusing to overwrite an existing backup'; exit 17; }

paths=(opt/hes-trade-agent etc/ssh etc/nftables.conf etc/systemd/system)
for p in etc/xray etc/nginx usr/local/sbin/hes-operational-healthcheck usr/local/sbin/hes-runtime-healthcheck usr/local/sbin/hes-encrypted-local-backup; do
  [[ ! -e "/$p" && ! -L "/$p" ]] || paths+=("$p")
done

# Freeze the directory-entry set before archiving. --no-recursion prevents tar
# from re-scanning live directories whose entries may change while collectors run.
# Append-only runtime files are archived from their observed size; a future backup
# captures later appends. Any file-content race still fails closed via tar's status.
LIST_FILE=$(mktemp "$BACKUP_DIR/.include.XXXXXX")
for p in "${paths[@]}"; do
  [[ ! -e "/$p" && ! -L "/$p" ]] || find "$p" -mindepth 0 \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) -prune -o -print0 >> "$LIST_FILE"
done

echo "BACKUP_START utc=$stamp"
echo "ARCHIVE_MODE=FROZEN_EXPLICIT_PATH_LIST"
echo "FILE_LIST_ENTRIES=$(tr -cd '\0' < "$LIST_FILE" | wc -c)"

tar -C / --no-recursion --one-file-system --numeric-owner --xattrs --acls --null --files-from="$LIST_FILE" -cf - \
  | gzip -1 \
  | gpg --batch --yes --pinentry-mode loopback --symmetric --cipher-algo AES256 --s2k-mode 3 --s2k-count 65011712 --passphrase-file "$KEY_FILE" --output "$tmp"

chmod 0600 "$tmp"
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY_FILE" --decrypt "$tmp" 2>/dev/null | gzip -t
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY_FILE" --decrypt "$tmp" 2>/dev/null | tar -tzf - >/dev/null

mv "$tmp" "$final"
PARTIAL_FILE=''
sha256sum "$final" > "$manifest_tmp"
chmod 0600 "$manifest_tmp"
mv "$manifest_tmp" "$manifest"
MANIFEST_PARTIAL_FILE=''

prune_archives
printf 'BACKUP_OK file=%s size_bytes=%s sha256=%s\\n' "$final" "$(stat -c %s "$final")" "$(sha256sum "$final" | awk '{print $1}')"
printf 'retained_archives=%s free_disk_kb=%s\\n' "$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'hes-full-*.tar.gz.gpg' | wc -l)" "$(df -Pk "$BACKUP_DIR" | awk 'NR==2{print $4}')"
