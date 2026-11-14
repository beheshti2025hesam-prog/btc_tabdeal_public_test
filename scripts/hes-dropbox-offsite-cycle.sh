#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin

ROOT=/opt/hes-trade-agent
BUILDER="$ROOT/scripts/hes-dropbox-offsite-build.sh"
OUTDIR=/var/backups/hes-trade-agent/offsite-staging
KEY_FILE=/root/.config/hes-backup/passphrase
REMOTE_DIR='hesdropbox:HES Trade Agent Backups'
REMOTE_FILE="$REMOTE_DIR/hes-offsite-latest.tar.gz.gpg"
LOCK_FILE=/run/lock/hes-dropbox-offsite-cycle.lock
MAX_BYTES=$((1792 * 1024 * 1024))
RESERVE_BYTES=$((128 * 1024 * 1024))

verify_remote_hash() {
  local tmp rc
  tmp=$(mktemp -d "$OUTDIR/.verify.XXXXXX")
  ln "$ARCHIVE" "$tmp/hes-offsite-latest.tar.gz.gpg"
  if rclone check "$tmp" "$REMOTE_DIR" --one-way --checkers 1; then
    rm -rf "$tmp"
    return 0
  else
    rc=$?
    rm -rf "$tmp"
    return "$rc"
  fi
}

exec 9>"$LOCK_FILE"
flock -n 9 || { echo 'OFFSITE_CYCLE_ALREADY_RUNNING'; exit 0; }
if [[ ! -r "$BUILDER" ]]; then echo "OFFSITE_PREREQUISITE_MISSING builder=$BUILDER"; exit 10; fi
if [[ ! -s "$KEY_FILE" ]]; then echo "OFFSITE_PREREQUISITE_MISSING key_file=$KEY_FILE"; exit 10; fi
if [[ ! -d "$OUTDIR" ]]; then echo "OFFSITE_PREREQUISITE_MISSING outdir=$OUTDIR"; exit 10; fi
command -v rclone >/dev/null
command -v gpg >/dev/null
command -v gzip >/dev/null

# Build at most one fresh bundle per UTC day; reuse today's verified local bundle on retries.
today=$(date -u +%Y%m%d)
latest=''
while IFS= read -r f; do latest="$f"; break; done < <(find "$OUTDIR" -maxdepth 1 -type f -name 'hes-offsite-core-*.tar.gz.gpg' -printf '%f\n' | sort -r)
latest_stamp=''
if [[ "$latest" =~ ^hes-offsite-core-([0-9]{8})T[0-9]{6}Z\.tar\.gz\.gpg$ ]]; then latest_stamp="${BASH_REMATCH[1]}"; fi
if [[ "${HES_OFFSITE_FORCE_BUILD:-0}" == "1" || "$latest_stamp" != "$today" ]]; then
  bash "$BUILDER"
  latest=''
  while IFS= read -r f; do latest="$f"; break; done < <(find "$OUTDIR" -maxdepth 1 -type f -name 'hes-offsite-core-*.tar.gz.gpg' -printf '%f\n' | sort -r)
fi
[[ -n "$latest" ]] || { echo 'NO_OFFSITE_ARCHIVE_FOUND'; exit 11; }
ARCHIVE="$OUTDIR/$latest"
[[ -s "$ARCHIVE" && -s "$ARCHIVE.sha256" && -s "$ARCHIVE.manifest.txt" ]] || { echo 'ARCHIVE_OR_SIDECAR_MISSING'; exit 12; }
grep -Fxq "Required evidence store: /srv/hes-evidence (coverage verified by archive listing)." "$ARCHIVE.manifest.txt" || { echo "EVIDENCE_STORE_COVERAGE_MISSING"; exit 14; }
size=$(stat -c %s "$ARCHIVE")
(( size <= MAX_BYTES )) || { echo "ARCHIVE_OVER_CAP bytes=$size cap=$MAX_BYTES"; exit 13; }
(cd "$OUTDIR" && sha256sum -c "$latest.sha256")
gpg --batch --pinentry-mode loopback --passphrase-file "$KEY_FILE" --decrypt "$ARCHIVE" 2>/dev/null | gzip -t
echo "OFFSITE_LOCAL_ARCHIVE_OK file=$latest bytes=$size"

# A matching Dropbox content hash means today's archive is already safely stored.
if verify_remote_hash; then
  echo 'REMOTE_ALREADY_MATCHES_SKIP_UPLOAD'
else
  remote_size=0
  if remote_json=$(rclone lsjson "$REMOTE_FILE" --stat 2>/dev/null); then
    remote_size=$(printf '%s' "$remote_json" | python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("Size",0)))')
  fi
  quota_json=$(rclone about hesdropbox: --json)
  free_bytes=$(printf '%s' "$quota_json" | python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("free",0)))')
  (( free_bytes + remote_size >= size + RESERVE_BYTES )) || {
    echo "QUOTA_GUARD_BLOCK free=$free_bytes existing_remote=$remote_size needed=$size reserve=$RESERVE_BYTES"
    exit 20
  }
  echo "UPLOAD_START target=stable-full-backup bytes=$size previous_remote_bytes=$remote_size"
  rclone copyto "$ARCHIVE" "$REMOTE_FILE" --ignore-times --transfers 1 --checkers 1 --retries 5 --low-level-retries 10 --stats 30s --stats-one-line
  verify_remote_hash
  echo 'REMOTE_HASH_VERIFIED'
fi

remote_json=$(rclone lsjson "$REMOTE_FILE" --stat)
remote_size=$(printf '%s' "$remote_json" | python3 -c 'import json,sys; print(int(json.load(sys.stdin)["Size"]))')
[[ "$remote_size" == "$size" ]] || { echo "REMOTE_SIZE_MISMATCH local=$size remote=$remote_size"; exit 21; }
quota_json=$(rclone about hesdropbox: --json)
printf '%s' "$quota_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("DROPBOX_QUOTA total={total} used={used} free={free}".format(**d))'

# Publish the non-secret checksum and recovery manifest alongside the encrypted archive.
(
  meta_tmp=$(mktemp -d "$OUTDIR/.metadata.XXXXXX")
  trap 'rm -rf -- "$meta_tmp"' EXIT
  cp "$ARCHIVE.sha256" "$meta_tmp/hes-offsite-latest.tar.gz.gpg.sha256"
  cp "$ARCHIVE.manifest.txt" "$meta_tmp/hes-offsite-latest.tar.gz.gpg.manifest.txt"
  rclone copy "$meta_tmp" "$REMOTE_DIR" --ignore-times --transfers 1 --checkers 1 --retries 5 --low-level-retries 10
  rclone check "$meta_tmp" "$REMOTE_DIR" --one-way --checkers 1
  echo 'REMOTE_METADATA_VERIFIED'
)

# Keep the two newest local offsite bundles. Never prune until the remote hash and size pass.
mapfile -t old_archives < <(find "$OUTDIR" -maxdepth 1 -type f -name 'hes-offsite-core-*.tar.gz.gpg' -printf '%f\n' | sort -r | tail -n +3)
for f in "${old_archives[@]}"; do
  rm -f -- "$OUTDIR/$f" "$OUTDIR/$f.sha256" "$OUTDIR/$f.manifest.txt"
  echo "LOCAL_OFFSITE_RETENTION_REMOVED=$f"
done

echo "DROPBOX_OFFSITE_CYCLE_OK file=$latest bytes=$size"