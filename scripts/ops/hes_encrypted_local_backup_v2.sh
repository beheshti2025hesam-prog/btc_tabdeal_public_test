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
COVERAGE_MANIFEST_PARTIAL_FILE=''

exec 9>"$LOCK_FILE"
flock -n 9 || { echo 'backup already running'; exit 0; }
trap 'rc=$?; echo "BACKUP_FAILED rc=$rc line=${BASH_LINENO[0]:-unknown}" >&2; exit "$rc"' ERR
cleanup() {
  local rc=$?
  if (( rc != 0 )); then
    if [[ -n "$PARTIAL_FILE" ]]; then rm -f -- "$PARTIAL_FILE"; fi
    if [[ -n "$MANIFEST_PARTIAL_FILE" ]]; then rm -f -- "$MANIFEST_PARTIAL_FILE"; fi
    if [[ -n "$COVERAGE_MANIFEST_PARTIAL_FILE" ]]; then rm -f -- "$COVERAGE_MANIFEST_PARTIAL_FILE"; fi
  fi
  if [[ -n "$LIST_FILE" ]]; then rm -f -- "$LIST_FILE"; fi
}
trap cleanup EXIT

prune_archives() {
  local name
  local -a expired=()
  mapfile -t expired < <(python3 "$ROOT/scripts/ops/hes_backup_retention_v2.py" \
    --directory "$BACKUP_DIR" --today "${HES_BACKUP_TODAY:-$(date -u +%F)}" --delete-list)
  for name in "${expired[@]}"; do
    [[ "$name" =~ ^hes-full-[0-9]{8}T[0-9]{6}Z\.tar\.(gz|zst)\.gpg$ ]] || {
      echo "RETENTION_REFUSE_INVALID_OUTPUT" >&2; return 30;
    }
    printf 'RETENTION_DELETE file=%s\\n' "$name"
    rm -f -- "$BACKUP_DIR/$name" "$BACKUP_DIR/$name.sha256" "$BACKUP_DIR/$name.manifest.txt"
  done
}

command -v zstd >/dev/null || { echo "zstd is required for local v2 backups"; exit 19; }
[[ -x "$ROOT/scripts/ops/hes_backup_archive_verify_v1.py" && -f "$ROOT/scripts/ops/hes_backup_retention_v2.py" ]] || {
  echo "versioned archive verifier/retention helper missing"; exit 18;
}
[[ -L "$ROOT/current" && -L "$ROOT/current-before-4329a3df" ]] || { echo "active/rollback release pointers missing"; exit 12; }
ACTIVE_REL="$(readlink -f "$ROOT/current" | sed 's#^/##')"
ROLLBACK_REL="$(readlink -f "$ROOT/current-before-4329a3df" | sed 's#^/##')"
case "$ACTIVE_REL" in opt/hes-trade-agent/releases/*) ;; *) echo "active release resolves outside release root"; exit 13 ;; esac
case "$ROLLBACK_REL" in opt/hes-trade-agent/releases/*) ;; *) echo "rollback release resolves outside release root"; exit 14 ;; esac
[[ -d "/$ACTIVE_REL" && -d "/$ROLLBACK_REL" ]] || { echo "active/rollback release target missing"; exit 15; }
[[ -d "$ROOT" && -s "$KEY_FILE" && -d /srv/hes-evidence ]] || { echo "project, evidence store, or encryption key unavailable"; exit 10; }
/usr/local/sbin/hes-operational-healthcheck >/dev/null
avail_kb=$(df -Pk "$BACKUP_DIR" | awk 'NR==2{print $4}')
[[ "$avail_kb" =~ ^[0-9]+$ ]] && (( avail_kb >= MIN_FREE_KB )) || { echo 'insufficient free disk for safe backup'; exit 20; }

stamp=$(date -u +%Y%m%dT%H%M%SZ)
base="hes-full-$stamp.tar.zst.gpg"
final="$BACKUP_DIR/$base"
tmp="$BACKUP_DIR/.$base.partial"
PARTIAL_FILE="$tmp"
manifest="$BACKUP_DIR/$base.sha256"
manifest_tmp="$manifest.partial"
MANIFEST_PARTIAL_FILE="$manifest_tmp"

[[ ! -e "$final" && ! -e "$tmp" ]] || { echo 'refusing to overwrite an existing backup'; exit 17; }

# Recovery-critical host configuration and state. These paths are protected by
# the existing AES-256 encrypted archive; the archive passphrase remains external.
# Keep credentials/configuration needed to reconnect and reproduce the host, but
# never include the backup encryption key itself.
paths=(
  opt/hes-trade-agent srv/hes-evidence
  etc/ssh etc/nftables.conf etc/systemd/system etc/ufw etc/netplan
  etc/apt etc/sentinelx etc/hes-trade-agent etc/sysctl.d etc/modules-load.d
  etc/fstab etc/hosts etc/hostname
  var/lib/dpkg/status var/lib/apt/extended_states
  var/lib/hes-operational-health var/lib/systemd
  root/.ssh root/.config/rclone
)
for p in etc/xray etc/nginx usr/local/sbin/hes-operational-healthcheck usr/local/sbin/hes-runtime-healthcheck usr/local/sbin/hes-encrypted-local-backup; do
  [[ ! -e "/$p" && ! -L "/$p" ]] || paths+=("$p")
done

# Freeze the directory-entry set before archiving. --no-recursion prevents tar
# from re-scanning live directories whose entries may change while collectors run.
# Append-only runtime files are archived from their observed size; a future backup
# captures later appends. Any file-content race still fails closed via tar's status.
LIST_FILE=$(mktemp "$BACKUP_DIR/.include.XXXXXX")
for p in "${paths[@]}"; do
  [[ ! -e "/$p" && ! -L "/$p" ]] || {
    if [[ "$p" == "srv/hes-evidence" ]]; then
      # Preserve the independent evidence store completely, including cache-named
      # artifacts that are part of its recorded evidence set.
      find "$p" -mindepth 0 -print0 >> "$LIST_FILE"
    else
      find "$p" -mindepth 0 \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) -prune -o -print0 >> "$LIST_FILE"
    fi
  }
done

echo "BACKUP_START utc=$stamp"
echo "ARCHIVE_MODE=FROZEN_EXPLICIT_PATH_LIST"
echo "FILE_LIST_ENTRIES=$(tr -cd '\0' < "$LIST_FILE" | wc -c)"

tar -C / --no-recursion --one-file-system --numeric-owner --xattrs --acls --null --files-from="$LIST_FILE" -cf - \
  | nice -n 15 ionice -c3 zstd -q -T1 -9 \
  | gpg --batch --yes --pinentry-mode loopback --symmetric --cipher-algo AES256 --s2k-mode 3 --s2k-count 65011712 --passphrase-file "$KEY_FILE" --output "$tmp"

chmod 0600 "$tmp"
python3 "$ROOT/scripts/ops/hes_backup_archive_verify_v1.py" \
  --archive "$tmp" --key-file "$KEY_FILE" \
  --active-release "$ACTIVE_REL" --rollback-release "$ROLLBACK_REL" >/dev/null
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY_FILE" --decrypt "$tmp" 2>/dev/null | zstd -q -dc | tar -tf - >/dev/null
expected_evidence_entries=$(find /srv/hes-evidence -xdev \( -type f -o -type l \) -printf '%y\n' | wc -l)
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY_FILE" --decrypt "$tmp" 2>/dev/null | zstd -q -dc | tar -tf - | awk -v expected="$expected_evidence_entries" '
  $0 == "srv/hes-evidence/" || $0 == "srv/hes-evidence" { root=1 }
  index($0, "srv/hes-evidence/") == 1 && $0 !~ /\/$/ { entries++ }
  END { if (!root || entries != expected) exit 1 }
' || { echo "BACKUP_EVIDENCE_STORE_MISSING_OR_INCOMPLETE"; exit 22; }

mv "$tmp" "$final"
PARTIAL_FILE=''
sha256sum "$final" > "$manifest_tmp"
chmod 0600 "$manifest_tmp"
mv "$manifest_tmp" "$manifest"
MANIFEST_PARTIAL_FILE=''
coverage_manifest="$BACKUP_DIR/$base.manifest.txt"
coverage_manifest_tmp="$coverage_manifest.partial"
COVERAGE_MANIFEST_PARTIAL_FILE="$coverage_manifest_tmp"
cat > "$coverage_manifest_tmp" <<EOF
HES encrypted local full backup
Created UTC: $stamp
Archive: $base
Archive bytes: $(stat -c %s "$final")
SHA-256: $(sha256sum "$final" | awk '{print $1}')
Required evidence store: /srv/hes-evidence (coverage verified by archive listing).
Evidence store entries: $expected_evidence_entries
Active release: $ACTIVE_REL
Rollback release: $ROLLBACK_REL
Included roots: project and evidence stores; SSH, nftables, systemd, UFW, netplan, APT, SentinelX and HES runtime configuration; sysctl/modules, host identity/network mount files; dpkg/apt package state; HES operational state; root SSH and rclone configuration. All included secrets are protected by AES-256 encryption. The backup encryption passphrase itself is intentionally excluded and must remain in separate secure escrow.
External recovery secret: /root/.config/hes-backup/passphrase is intentionally NOT included.
Encryption: GPG symmetric AES-256.
EOF
chmod 0600 "$coverage_manifest_tmp"
mv "$coverage_manifest_tmp" "$coverage_manifest"
COVERAGE_MANIFEST_PARTIAL_FILE=''

prune_archives
printf 'BACKUP_OK file=%s size_bytes=%s sha256=%s\\n' "$final" "$(stat -c %s "$final")" "$(sha256sum "$final" | awk '{print $1}')"
printf 'retained_archives=%s free_disk_kb=%s\\n' "$(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'hes-full-*.tar.gz.gpg' -o -name 'hes-full-*.tar.zst.gpg' \) | wc -l)" "$(df -Pk "$BACKUP_DIR" | awk 'NR==2{print $4}')"
