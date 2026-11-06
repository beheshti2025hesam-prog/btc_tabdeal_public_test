#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
ARCHIVE_ROOT=/
BACKUP_DIR=/var/backups/hes-trade-agent/encrypted-local
KEY_FILE=/root/.config/hes-backup/passphrase
LOCK_FILE=/run/lock/hes-encrypted-local-backup.lock
HEALTHCHECK_CMD=/usr/local/sbin/hes-operational-healthcheck
MIN_FREE_KB=5242880
S2K_COUNT=65011712
ROOT="$ARCHIVE_ROOT/opt/hes-trade-agent"
[[ -d "$ROOT" && ! -L "$ROOT" ]]
[[ -d "$BACKUP_DIR" && ! -L "$BACKUP_DIR" ]]
[[ -f "$KEY_FILE" && ! -L "$KEY_FILE" && -s "$KEY_FILE" ]]
[[ "$(stat -c '%a' "$KEY_FILE")" == "600" ]]
[[ "$(stat -c '%a' "$BACKUP_DIR")" == "700" ]]
[[ -x "$HEALTHCHECK_CMD" ]]
(( S2K_COUNT >= 1024 && S2K_COUNT <= 65011712 ))
exec 9>"$LOCK_FILE"
flock -n 9 || { echo 'backup already running'; exit 0; }
tmp=""
manifest_tmp=""
final=""
manifest=""
final_created=0
cleanup() {
    local rc=$?
    trap - EXIT
    if (( rc != 0 )); then
        [[ -z "$tmp" ]] || rm -f -- "$tmp" 2>/dev/null || true
        [[ -z "$manifest_tmp" ]] || rm -f -- "$manifest_tmp" 2>/dev/null || true
        if (( final_created )); then
            [[ -z "$final" ]] || rm -f -- "$final" 2>/dev/null || true
            [[ -z "$manifest" ]] || rm -f -- "$manifest" 2>/dev/null || true
        fi
        printf 'BACKUP_FAILED rc=%s\n' "$rc" >&2
    fi
    exit "$rc"
}
trap cleanup EXIT
"$HEALTHCHECK_CMD" >/dev/null
avail_kb=$(df -Pk "$BACKUP_DIR" | awk 'NR==2{print $4}')
[[ "$avail_kb" =~ ^[0-9]+$ ]]
(( avail_kb >= MIN_FREE_KB )) || { echo 'insufficient free disk for safe backup'; exit 20; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
base="hes-full-$stamp.tar.gz.gpg"
final="$BACKUP_DIR/$base"
tmp="$BACKUP_DIR/.$base.partial"
manifest="$BACKUP_DIR/$base.sha256"
manifest_tmp="$BACKUP_DIR/.$base.sha256.partial"
paths=(opt/hes-trade-agent etc/ssh etc/nftables.conf etc/systemd/system)
for p in etc/xray etc/nginx usr/local/sbin/hes-operational-healthcheck usr/local/sbin/hes-runtime-healthcheck usr/local/sbin/hes-encrypted-local-backup root/.ssh/authorized_keys var/lib/hes-gateio-1m-integrity var/lib/hes-operational-health var/lib/hes-news-monitor var/lib/hes-tabdeal-readonly var/lib/sentinelx/hes-release-manifests var/lib/sentinelx/hes-runtime-snapshots; do
    if [[ -e "$ARCHIVE_ROOT/$p" || -L "$ARCHIVE_ROOT/$p" ]]; then paths+=("$p"); fi
done
tar --one-file-system --numeric-owner --xattrs --acls --exclude='*/__pycache__' --exclude='*/.pytest_cache' --exclude='*/.mypy_cache' --exclude='*/.ruff_cache' -C "$ARCHIVE_ROOT" -cf - "${paths[@]}" | gzip -1 | gpg --batch --yes --pinentry-mode loopback --symmetric --cipher-algo AES256 --s2k-mode 3 --s2k-count "$S2K_COUNT" --passphrase-file "$KEY_FILE" --output "$tmp"
chmod 0600 "$tmp"
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY_FILE" --decrypt "$tmp" 2>/dev/null | gzip -t
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY_FILE" --decrypt "$tmp" 2>/dev/null | tar -tzf - >/dev/null
hash=$(sha256sum "$tmp" | awk '{print $1}')
printf '%s  %s\n' "$hash" "$base" > "$manifest_tmp"
chmod 0600 "$manifest_tmp"
mv "$tmp" "$final"
tmp=""
final_created=1
mv "$manifest_tmp" "$manifest"
manifest_tmp=""
(cd "$BACKUP_DIR" && sha256sum -c "$base.sha256")
final_created=0
today=$(date -u +%F)
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'hes-full-*.tar.gz.gpg' -print0 | while IFS= read -r -d '' path; do
    name=$(basename "$path")
    ds=$(printf '%s' "$name" | sed 's/^hes-full-//;s/\.tar\.gz\.gpg$//')
    day=$(printf '%s' "$ds" | cut -c1-8)
    year=$(printf '%s' "$day" | cut -c1-4)
    month=$(printf '%s' "$day" | cut -c5-6)
    dom=$(printf '%s' "$day" | cut -c7-8)
    iso="$year-$month-$dom"
    [[ "$iso" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || continue
    age=$(( ( $(date -u -d "$today" +%s) - $(date -u -d "$iso" +%s) ) / 86400 ))
    dow=$(date -u -d "$iso" +%u)
    keep=0
    if (( age >= 0 && age < 7 )); then keep=1; fi
    if (( age >= 0 && age < 28 )) && [[ "$dow" == 7 ]]; then keep=1; fi
    if (( age >= 0 && age < 180 )) && [[ "$dom" == 01 ]]; then keep=1; fi
    if (( keep == 0 )); then rm -f -- "$path" "$path.sha256"; fi
done
printf 'BACKUP_OK file=%s size_bytes=%s sha256=%s\n' "$final" "$(stat -c %s "$final")" "$(sha256sum "$final" | awk '{print $1}')"
printf 'retained_archives=%s free_disk_kb=%s\n' "$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'hes-full-*.tar.gz.gpg' | wc -l)" "$(df -Pk "$BACKUP_DIR" | awk 'NR==2{print $4}')"
